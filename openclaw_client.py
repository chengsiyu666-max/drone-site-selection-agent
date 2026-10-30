"""
OpenClaw WebSocket 客户端模块
用于从 Flask 发送消息到 OpenClaw，并接收 AI 回复。
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
import uuid
from typing import Generator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import websocket

WS_URL = os.environ.get("OPENCLAW_WS_URL", "ws://127.0.0.1:18789")
TOKEN = os.environ.get("OPENCLAW_TOKEN", "")
AGENT_ID = os.environ.get("OPENCLAW_AGENT_ID", "main")

# DeepSeek 官方 OpenAI 兼容 REST 端点（WS 不可用时的回退通道）。
DEEPSEEK_BASE = os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com/v1")
DEEPSEEK_TOKEN = os.environ.get("DEEPSEEK_TOKEN", "")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")


def _build_deepseek_messages(user_message: str, system_prompt: str | None) -> list:
    messages = []
    if system_prompt and system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_message})
    return messages


def _deepseek_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_TOKEN}",
    }


def deepseek_chat(
    user_message: str,
    system_prompt: str | None = None,
    timeout: int = 90,
) -> str:
    """调用 DeepSeek 官方 OpenAI 兼容 REST 端点，成功返回回复文本；失败抛用户友好 RuntimeError。"""
    if not DEEPSEEK_TOKEN:
        raise RuntimeError("AI 服务暂未配置 API 令牌，请设置环境变量 DEEPSEEK_TOKEN 后重试")
    body = json.dumps(
        {
            "model": DEEPSEEK_MODEL,
            "messages": _build_deepseek_messages(user_message, system_prompt),
            "stream": False,
        }
    ).encode("utf-8")
    url = DEEPSEEK_BASE.rstrip("/") + "/chat/completions"
    req = Request(url, data=body, headers=_deepseek_headers())
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8", errors="ignore")
    except HTTPError as exc:
        raise RuntimeError(f"AI 服务请求失败(HTTP {exc.code})：{exc.reason}") from exc
    except (URLError, TimeoutError) as exc:
        cause = exc.reason if hasattr(exc, "reason") else exc
        raise RuntimeError(f"AI 服务连接失败：{cause}") from exc
    try:
        data = json.loads(payload)
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        snippet = str(data.get("error") or payload[:200]) if "data" in locals() else payload[:200]
        raise RuntimeError(f"AI 服务返回异常：{snippet}") from exc


def deepseek_chat_stream(
    user_message: str,
    system_prompt: str | None = None,
    timeout: int = 600,
) -> Generator[dict, None, None]:
    """DeepSeek 流式（SSE）回退通道，事件格式与 openclaw_chat_stream 保持一致。"""
    if not DEEPSEEK_TOKEN:
        yield {"type": "error", "message": "AI 服务暂未配置 API 令牌，请设置环境变量 DEEPSEEK_TOKEN 后重试"}
        return
    body = json.dumps(
        {
            "model": DEEPSEEK_MODEL,
            "messages": _build_deepseek_messages(user_message, system_prompt),
            "stream": True,
        }
    ).encode("utf-8")
    url = DEEPSEEK_BASE.rstrip("/") + "/chat/completions"
    req = Request(url, data=body, headers=_deepseek_headers())
    try:
        resp = urlopen(req, timeout=timeout)
    except HTTPError as exc:
        yield {"type": "error", "message": f"AI 服务请求失败(HTTP {exc.code})：{exc.reason}"}
        return
    except (URLError, TimeoutError) as exc:
        cause = exc.reason if hasattr(exc, "reason") else exc
        yield {"type": "error", "message": f"AI 服务连接失败：{cause}"}
        return

    text = ""
    try:
        for raw in resp:
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
            piece = delta.get("content") or ""
            if piece:
                text += piece
                yield {"type": "delta", "text": text}
    except Exception as exc:
        yield {"type": "error", "message": f"AI 服务流式响应中断：{exc}"}
        return
    yield {"type": "done", "text": text, "session_key": ""}

CONNECT_PARAMS = {
    "minProtocol": 3,
    "maxProtocol": 3,
    "client": {
        "id": "openclaw-control-ui",
        "version": "control-ui",
        "platform": "web",
        "mode": "webchat",
    },
    "role": "operator",
    "scopes": ["operator.read", "operator.write"],
    "caps": ["tool-events"],
    "auth": {"token": TOKEN},
    "userAgent": "CommunitySiteSelection-WebApp/1.0",
    "locale": "zh-CN",
}

# 运行结束的 lifecycle phase 值
DONE_PHASES = {"done", "end", "complete", "finish", "error", "aborted", "cancelled"}
# chat 事件的结束 state 值
DONE_CHAT_STATES = {"done", "complete", "finish", "error"}


def _send(ws: websocket.WebSocketApp, method: str, params: dict) -> str:
    rid = str(uuid.uuid4())
    ws.send(json.dumps({"type": "req", "id": rid, "method": method, "params": params}))
    return rid


def _openclaw_ws_chat(user_message: str, session_key: str | None = None, timeout: int = 60) -> tuple[str, str]:
    """
    向 OpenClaw 的 main agent 发送消息，返回 (reply_text, session_key)。
    session_key: 传入已有的会话 key，可跨请求保持记忆；None 则新建会话。
    """
    state: dict = {
        "step": "init",       # 当前流程阶段
        "session_key": session_key,
        "text": "",           # AI 累积文本
        "error": None,
    }
    done_event = threading.Event()

    def on_message(ws: websocket.WebSocketApp, raw: str) -> None:
        data = json.loads(raw)
        msg_type = data.get("type", "")
        event_name = data.get("event", "")

        # 忽略心跳/滴答
        if event_name in ("heartbeat", "tick", "presence"):
            return

        step = state["step"]

        # ── Step 0: 收到 challenge → 发 connect ──
        if step == "init" and msg_type == "event" and event_name == "connect.challenge":
            state["step"] = "connecting"
            ws.send(json.dumps({
                "type": "req",
                "id": str(uuid.uuid4()),
                "method": "connect",
                "params": CONNECT_PARAMS,
            }))
            return

        # ── Step 1: connect 响应 ──
        if step == "connecting" and msg_type == "res":
            if not data.get("ok"):
                state["error"] = f"connect failed: {data.get('error')}"
                done_event.set()
                ws.close()
                return
            if state["session_key"]:
                # 复用已有会话
                state["step"] = "subscribing"
                _send(ws, "sessions.messages.subscribe", {"key": state["session_key"]})
            else:
                state["step"] = "creating"
                _send(ws, "sessions.create", {"agentId": AGENT_ID})
            return

        # ── Step 2: session 创建 ──
        if step == "creating" and msg_type == "res":
            if not data.get("ok"):
                state["error"] = f"sessions.create failed: {data.get('error')}"
                done_event.set()
                ws.close()
                return
            payload = data.get("payload", {})
            state["session_key"] = payload.get("key")
            state["step"] = "subscribing"
            _send(ws, "sessions.messages.subscribe", {"key": state["session_key"]})
            return

        # ── Step 3: 订阅成功 → 发消息 ──
        if step == "subscribing" and msg_type == "res":
            state["step"] = "sending"
            _send(ws, "sessions.send", {
                "key": state["session_key"],
                "message": user_message,
            })
            return

        # ── Step 4: sessions.send 响应 ──
        if step == "sending" and msg_type == "res":
            if not data.get("ok"):
                state["error"] = f"sessions.send failed: {data.get('error')}"
                done_event.set()
                ws.close()
                return
            state["step"] = "waiting"
            return

        # ── Step 5: 等待 AI 完整回复 ──
        if step == "waiting" and msg_type == "event":
            payload = data.get("payload", {})

            # agent 流式 text（累积）
            if event_name == "agent":
                stream = payload.get("stream", "")
                if stream == "assistant":
                    text = payload.get("data", {}).get("text", "")
                    if text:
                        state["text"] = text

                # lifecycle 结束信号
                elif stream == "lifecycle":
                    phase = payload.get("data", {}).get("phase", "")
                    if phase in DONE_PHASES:
                        done_event.set()
                        ws.close()

            # chat 事件结束信号
            elif event_name == "chat":
                chat_state = payload.get("state", "")
                if chat_state in DONE_CHAT_STATES:
                    # 取 chat 事件里的完整文本（更可靠）
                    msg_content = payload.get("message", {}).get("content", "")
                    if isinstance(msg_content, list):
                        for block in msg_content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                state["text"] = block.get("text", state["text"])
                                break
                    elif isinstance(msg_content, str) and msg_content:
                        state["text"] = msg_content
                    done_event.set()
                    ws.close()

    def on_error(ws: websocket.WebSocketApp, error: Exception) -> None:
        state["error"] = str(error)
        done_event.set()

    def on_close(ws: websocket.WebSocketApp, code: int, msg: str) -> None:
        done_event.set()

    ws_app = websocket.WebSocketApp(
        WS_URL,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    thread = threading.Thread(target=ws_app.run_forever, daemon=True)
    thread.start()

    done_event.wait(timeout=timeout)
    ws_app.close()  # 超时时确保关闭

    if state["error"]:
        raise RuntimeError(state["error"])

    return state["text"] or "(暂无回复)", state["session_key"] or ""


def openclaw_chat(
    user_message: str,
    session_key: str | None = None,
    timeout: int = 60,
    system_prompt: str | None = None,
) -> tuple[str, str]:
    """
    对外入口：优先走 OpenClaw WebSocket；连接失败或超时无回复时，
    自动回退到 DeepSeek 官方 OpenAI 兼容 REST 端点（需配置 DEEPSEEK_TOKEN）。
    """
    try:
        reply, key = _openclaw_ws_chat(user_message, session_key=session_key, timeout=timeout)
        if reply and reply != "(暂无回复)":
            return reply, key
    except RuntimeError:
        pass  # WS 不可用 → 回退 DeepSeek
    reply = deepseek_chat(user_message, system_prompt=system_prompt, timeout=timeout)
    return reply, ""


# ---------------------------------------------------------------------------
# 流式版本:generator 形式,边收边 yield,给 SSE 端点用
# ---------------------------------------------------------------------------

_STREAM_SENTINEL = object()


def _openclaw_ws_stream(
    user_message: str,
    session_key: str | None = None,
    timeout: int = 600,
) -> Generator[dict, None, None]:
    """
    向 OpenClaw 发消息,以 generator 的形式把事件逐个吐出来。

    yield 的事件格式:
      {"type": "session", "session_key": "..."}            # 拿到 session 时推一次
      {"type": "delta",   "text": "<累积全文>"}             # 每次 OpenClaw 推 assistant 流都 yield
      {"type": "done",    "text": "<最终全文>", "session_key": "..."}
      {"type": "error",   "message": "..."}
    """
    q: "queue.Queue[object]" = queue.Queue()
    state: dict = {
        "step": "init",
        "session_key": session_key,
        "text": "",
        "session_emitted": False,
    }

    def emit(ev: object) -> None:
        q.put(ev)

    def on_message(ws: websocket.WebSocketApp, raw: str) -> None:
        try:
            data = json.loads(raw)
        except Exception:
            return
        msg_type = data.get("type", "")
        event_name = data.get("event", "")

        if event_name in ("heartbeat", "tick", "presence"):
            return

        step = state["step"]

        # Step 0: challenge → connect
        if step == "init" and msg_type == "event" and event_name == "connect.challenge":
            state["step"] = "connecting"
            ws.send(json.dumps({
                "type": "req",
                "id": str(uuid.uuid4()),
                "method": "connect",
                "params": CONNECT_PARAMS,
            }))
            return

        # Step 1: connect res
        if step == "connecting" and msg_type == "res":
            if not data.get("ok"):
                emit({"type": "error", "message": f"connect failed: {data.get('error')}"})
                emit(_STREAM_SENTINEL)
                ws.close()
                return
            if state["session_key"]:
                state["step"] = "subscribing"
                _send(ws, "sessions.messages.subscribe", {"key": state["session_key"]})
                if not state["session_emitted"]:
                    emit({"type": "session", "session_key": state["session_key"]})
                    state["session_emitted"] = True
            else:
                state["step"] = "creating"
                _send(ws, "sessions.create", {"agentId": AGENT_ID})
            return

        # Step 2: sessions.create res
        if step == "creating" and msg_type == "res":
            if not data.get("ok"):
                emit({"type": "error", "message": f"sessions.create failed: {data.get('error')}"})
                emit(_STREAM_SENTINEL)
                ws.close()
                return
            payload = data.get("payload", {})
            state["session_key"] = payload.get("key")
            state["step"] = "subscribing"
            _send(ws, "sessions.messages.subscribe", {"key": state["session_key"]})
            if state["session_key"] and not state["session_emitted"]:
                emit({"type": "session", "session_key": state["session_key"]})
                state["session_emitted"] = True
            return

        # Step 3: subscribe res → send message
        if step == "subscribing" and msg_type == "res":
            state["step"] = "sending"
            _send(ws, "sessions.send", {
                "key": state["session_key"],
                "message": user_message,
            })
            return

        # Step 4: sessions.send res
        if step == "sending" and msg_type == "res":
            if not data.get("ok"):
                emit({"type": "error", "message": f"sessions.send failed: {data.get('error')}"})
                emit(_STREAM_SENTINEL)
                ws.close()
                return
            state["step"] = "waiting"
            return

        # Step 5: 流式事件
        if step == "waiting" and msg_type == "event":
            payload = data.get("payload", {})

            if event_name == "agent":
                stream = payload.get("stream", "")
                if stream == "assistant":
                    text = payload.get("data", {}).get("text", "")
                    if text and text != state["text"]:
                        state["text"] = text
                        emit({"type": "delta", "text": text})
                elif stream == "lifecycle":
                    phase = payload.get("data", {}).get("phase", "")
                    if phase in DONE_PHASES:
                        emit({
                            "type": "done",
                            "text": state["text"],
                            "session_key": state["session_key"] or "",
                        })
                        emit(_STREAM_SENTINEL)
                        ws.close()

            elif event_name == "chat":
                chat_state = payload.get("state", "")
                if chat_state in DONE_CHAT_STATES:
                    msg_content = payload.get("message", {}).get("content", "")
                    if isinstance(msg_content, list):
                        for block in msg_content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                state["text"] = block.get("text", state["text"])
                                break
                    elif isinstance(msg_content, str) and msg_content:
                        state["text"] = msg_content
                    emit({
                        "type": "done",
                        "text": state["text"],
                        "session_key": state["session_key"] or "",
                    })
                    emit(_STREAM_SENTINEL)
                    ws.close()

    def on_error(ws: websocket.WebSocketApp, error: Exception) -> None:
        emit({"type": "error", "message": str(error)})
        emit(_STREAM_SENTINEL)

    def on_close(ws: websocket.WebSocketApp, code: int, msg: str) -> None:
        emit(_STREAM_SENTINEL)

    ws_app = websocket.WebSocketApp(
        WS_URL,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    thread = threading.Thread(target=ws_app.run_forever, daemon=True)
    thread.start()

    deadline = time.monotonic() + timeout
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                yield {"type": "error", "message": "openclaw chat timeout"}
                return
            try:
                item = q.get(timeout=min(remaining, 30))
            except queue.Empty:
                continue
            if item is _STREAM_SENTINEL:
                return
            yield item  # type: ignore[misc]
    finally:
        try:
            ws_app.close()
        except Exception:
            pass


def openclaw_chat_stream(
    user_message: str,
    session_key: str | None = None,
    timeout: int = 600,
    system_prompt: str | None = None,
) -> Generator[dict, None, None]:
    """
    对外入口：优先走 OpenClaw WebSocket 流式；若在产出任何内容前 WS 就失败
    （连接被拒/超时等），自动回退到 DeepSeek REST 流式通道。
    """
    saw_content = False
    for ev in _openclaw_ws_stream(user_message, session_key=session_key, timeout=timeout):
        if ev.get("type") in ("delta", "done"):
            saw_content = True
        if ev.get("type") == "error" and not saw_content:
            break  # WS 未能产出任何内容 → 回退 DeepSeek
        yield ev
    else:
        return
    yield from deepseek_chat_stream(user_message, system_prompt=system_prompt, timeout=timeout)
