"""
agent_llm.py — OpenAI 兼容的「函数调用(Function Calling)」客户端。

现有 openclaw_client.deepseek_chat 只支持 messages → 文本，不支持 tools 参数，
无法支撑 Agent 的工具调用循环。本模块新增一个能传 tools / tool_call 的客户端，
复用项目已有常量（DEEPSEEK_BASE / DEEPSEEK_TOKEN / DEEPSEEK_MODEL），密钥只读不打印。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener, getproxies, urlopen

DEEPSEEK_BASE = os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com/v1")
DEEPSEEK_TOKEN = os.environ.get("DEEPSEEK_TOKEN", "")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")


def _headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_TOKEN}",
    }


def _open_request(req: Request, timeout: int):
    """发起请求时遵循系统代理设置。

    openrouter.ai 等境外端点在国内需要代理；而 urllib 默认不读 Windows 系统代理
    （只在设置了 HTTP_PROXY/HTTPS_PROXY 环境变量时才生效）。
    getproxies() 会同时读环境变量和 Windows 注册表里的系统代理设置，这里显式套用，
    避免出现「浏览器能打开、Python 连不上」的情况。
    """
    proxies = getproxies()
    if proxies:
        return build_opener(ProxyHandler(proxies)).open(req, timeout=timeout)
    return urlopen(req, timeout=timeout)


def chat_with_tools(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    *,
    tool_choice: str = "auto",
    max_tokens: int = 2048,
    temperature: float = 0.2,
    timeout: int = 240,
) -> Dict[str, Any]:
    """调用 DeepSeek 聊天补全，返回可选 tool_calls 或文本回复。

    返回结构：
        {
          "reply": str | None,                  # 无工具调用时的最终文本
          "tool_calls": [                       # 有工具调用时非空
              {"id": str, "name": str, "arguments": dict}  # arguments 已解析为 dict
          ],
          "usage": {"prompt_tokens": n, "completion_tokens": n, "total_tokens": n},
        }
    失败抛 RuntimeError（友好中文，不含密钥）。
    """
    if not DEEPSEEK_TOKEN:
        raise RuntimeError("AI 服务暂未配置 API 令牌，请设置环境变量 DEEPSEEK_TOKEN 后重试")

    body: Dict[str, Any] = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = tool_choice

    url = DEEPSEEK_BASE.rstrip("/") + "/chat/completions"
    req = Request(url, data=json.dumps(body).encode("utf-8"), headers=_headers())
    try:
        with _open_request(req, timeout) as resp:
            payload = resp.read().decode("utf-8", errors="ignore")
    except HTTPError as exc:
        raise RuntimeError(f"AI 服务请求失败(HTTP {exc.code})：{exc.reason}") from exc
    except (URLError, TimeoutError) as exc:
        cause = exc.reason if hasattr(exc, "reason") else exc
        raise RuntimeError(f"AI 服务连接失败：{cause}") from exc

    try:
        data = json.loads(payload)
        choice = data["choices"][0]
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        snippet = str(data.get("error") or payload[:200]) if "data" in locals() else payload[:200]
        raise RuntimeError(f"AI 服务返回异常：{snippet}") from exc

    msg = choice.get("message") or {}
    usage = data.get("usage") or {}

    tool_calls: List[Dict[str, Any]] = []
    for tc in msg.get("tool_calls") or []:
        raw_args = (tc.get("function") or {}).get("arguments") or "{}"
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            args = {"_raw_arguments": raw_args}
        tool_calls.append(
            {
                "id": tc.get("id") or "",
                "name": (tc.get("function") or {}).get("name") or "",
                "arguments": args,
            }
        )

    return {
        "reply": msg.get("content"),
        "tool_calls": tool_calls,
        "usage": {
            "prompt_tokens": int(usage.get("prompt_tokens", 0)),
            "completion_tokens": int(usage.get("completion_tokens", 0)),
            "total_tokens": int(usage.get("total_tokens", 0)),
        },
    }