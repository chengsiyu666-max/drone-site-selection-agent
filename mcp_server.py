"""
mcp_server.py — 极简 MCP(Model Context Protocol) server，零外部框架。

在 stdin/stdout 上以 JSON-RPC 2.0 与 MCP host(如支持 MCP 的客户端)通信，
把 agent_tools 里的选址能力暴露为标准 MCP 工具：

    tools/list      —— 返回 run_site_selection / get_city_configs 的 MCP 工具 schema
    tools/call      —— 分发到 agent_tools 实现并返回 text content（isError 遵循 MCP 约定）

长任务保活：run_site_selection 单次可能跑 1~2 分钟，期间无任何输出会让客户端的空闲超时
直接断开。若客户端在请求里带了 progressToken，本服务会在执行期间每 N 秒发一条
notifications/progress 心跳（N 由 MCP_PROGRESS_INTERVAL_SEC 控制，默认 5 秒），
让客户端知道任务仍在进行。

用法（单请求验证）：
    echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python mcp_server.py
    echo '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_city_configs","arguments":{}}}' | python mcp_server.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
from typing import Any, Dict, List, Optional

import app  # noqa: F401 加载 .env

from agent_tools import TOOL_SCHEMAS, _TOOL_IMPLS

_SERVER_INFO = {
    "name": "drone-site-selection",
    "version": "0.2.0",
}

# 心跳间隔（秒）：长任务执行期间多久发一次进度通知
_PROGRESS_INTERVAL = float(os.environ.get("MCP_PROGRESS_INTERVAL_SEC", "5") or 5)

# stdout 只允许出现 JSON-RPC 报文；心跳线程与主线程都会写，必须加锁防串行化错乱
_WRITE_LOCK = threading.Lock()


def _write_msg(msg: Dict[str, Any]) -> None:
    with _WRITE_LOCK:
        sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
        sys.stdout.flush()


class _ProgressHeartbeat:
    """执行长任务期间的进度心跳：有 token 才发，无 token 时完全不产生额外报文。"""

    def __init__(self, token: Any, tool_name: str, interval: float = _PROGRESS_INTERVAL):
        self.token = token
        self.tool_name = tool_name
        self.interval = max(0.2, interval)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._count = 0

    def _notify(self, progress: int, message: str) -> None:
        _write_msg(
            {
                "jsonrpc": "2.0",
                "method": "notifications/progress",
                "params": {
                    "progressToken": self.token,
                    "progress": progress,
                    "message": message,
                },
            }
        )

    def _run(self) -> None:
        started = time.monotonic()
        while not self._stop.wait(self.interval):
            self._count += 1
            elapsed = int(time.monotonic() - started)
            self._notify(self._count, f"{self.tool_name} 执行中，已耗时 {elapsed} 秒")

    def __enter__(self) -> "_ProgressHeartbeat":
        if self.token is not None:
            self._notify(0, f"开始执行 {self.tool_name}")
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc_info) -> None:
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=2)
            self._notify(self._count + 1, f"{self.tool_name} 执行结束")


def _to_mcp_tool(schema: Dict[str, Any]) -> Dict[str, Any]:
    """把 OpenAI function schema 转成 MCP tools/list 里的元素。"""
    fn = schema.get("function", schema)
    return {
        "name": fn["name"],
        "description": fn.get("description", ""),
        "inputSchema": fn.get("parameters") or {"type": "object", "properties": {}},
    }


def _handle_request(req: Dict[str, Any]) -> Dict[str, Any]:
    method = req.get("method") or ""
    rid = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": _SERVER_INFO,
        }}

    if method in ("notifications/initialized", "notifications/cancelled", "notifications/progress"):
        return None  # 通知类请求无需响应

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": [
            _to_mcp_tool(s) for s in TOOL_SCHEMAS if s.get("function", s).get("name") in _TOOL_IMPLS
        ]}}

    if method == "tools/call":
        name = (params.get("name") or "").strip()
        args = params.get("arguments") or {}
        # progressToken 按 MCP 规范放在 params._meta 里，这里兼容直接放在 params 上的写法
        token = (params.get("_meta") or {}).get("progressToken")
        if token is None:
            token = params.get("progressToken")
        impl = _TOOL_IMPLS.get(name)
        try:
            if impl is None:
                raise ValueError(f"未知工具:{name}")
            with _ProgressHeartbeat(token, name):
                value = impl(**args)
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}],
                "isError": False,
            }}
        except Exception as exc:  # noqa: BLE001 —— 错误按 MCP isError 约定返回，不中断
            traceback.print_exc(file=sys.stderr)
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": f"工具执行失败({type(exc).__name__}):{exc}"}],
                "isError": True,
            }}

    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"未知方法:{method}"}}


def main() -> int:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except json.JSONDecodeError as exc:
            _write_msg({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}})
            continue
        try:
            resp = _handle_request(req)
        except Exception as exc:  # noqa: BLE001
            resp = {"jsonrpc": "2.0", "id": req.get("id"), "error": {"code": -32603, "message": f"{type(exc).__name__}:{exc}"}}
        if resp is not None:
            _write_msg(resp)
    return 0


if __name__ == "__main__":
    sys.exit(main())