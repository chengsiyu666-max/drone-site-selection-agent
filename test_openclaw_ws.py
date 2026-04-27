"""
OpenClaw WebSocket 聊天测试
运行: python test_openclaw_ws.py
"""
import json
import os
import sys
import uuid
import websocket

TOKEN = os.environ.get("OPENCLAW_TOKEN", "")
WS_URL = os.environ.get("OPENCLAW_WS_URL", "ws://127.0.0.1:18789")
AGENT_ID = os.environ.get("OPENCLAW_AGENT_ID", "main")
TEST_MSG = "你好！请用一句话介绍某硬折扣社区超市便利店的核心竞争优势。"

session_key = None
session_id = None
step = "init"


def req(ws, method, params):
    rid = str(uuid.uuid4())
    ws.send(json.dumps({"type": "req", "id": rid, "method": method, "params": params}))
    return rid


def on_open(ws):
    print("[OPEN] 已连接，等待 challenge...")


def on_message(ws, message):
    global session_key, session_id, step
    data = json.loads(message)
    msg_type = data.get("type", "")
    event_name = data.get("event", "")

    # 忽略心跳等噪音
    if event_name in ("heartbeat", "tick", "presence"):
        return

    print(f"\n[{step.upper()}] type={msg_type} event={event_name or '-'}")

    # ── 1. 收到 challenge → 发 connect ──
    if msg_type == "event" and event_name == "connect.challenge":
        step = "connecting"
        ws.send(json.dumps({
            "type": "req",
            "id": str(uuid.uuid4()),
            "method": "connect",
            "params": {
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
            },
        }))
        return

    # ── 2. connect 成功 → 创建新 session ──
    if step == "connecting" and msg_type == "res":
        if not data.get("ok"):
            print(f"❌ 连接失败: {data.get('error')}")
            ws.close()
            return
        print("✅ 认证成功！正在创建会话...")
        step = "creating"
        req(ws, "sessions.create", {
            "agentId": AGENT_ID,
        })
        return

    # ── 3. session 创建成功 → 订阅 + 发送消息 ──
    if step == "creating" and msg_type == "res":
        if not data.get("ok"):
            print(f"❌ sessions.create 失败: {data.get('error')}")
            ws.close()
            return
        payload = data.get("payload", {})
        session_key = payload.get("key")
        session_id = payload.get("sessionId")
        print(f"✅ 会话创建成功！key={session_key}")

        # 订阅会话消息
        step = "subscribing"
        req(ws, "sessions.messages.subscribe", {"key": session_key})
        return

    # ── 4. 订阅成功 → 发消息 ──
    if step == "subscribing" and msg_type == "res":
        print("✅ 已订阅，发送测试消息...")
        step = "waiting_reply"
        req(ws, "sessions.send", {
            "key": session_key,
            "message": TEST_MSG,
        })
        return

    # ── 5. 等待 AI 回复 ──
    if step == "waiting_reply":
        # sessions.send 的响应
        if msg_type == "res":
            print(f"sessions.send 响应: ok={data.get('ok')} payload={data.get('payload')}")
            if not data.get("ok"):
                print(f"❌ 发送失败: {data.get('error')}")
                ws.close()
            return

        # 打印所有事件的 payload（只打印前400字）
        if msg_type == "event":
            payload = data.get("payload", {})
            payload_str = json.dumps(payload, ensure_ascii=False)[:400]
            print(f"  payload: {payload_str}")

            # 检查 session.message 是否是 AI 回复
            if event_name == "session.message":
                role = payload.get("role", "")
                content = payload.get("content", "") or payload.get("text", "")
                if role == "assistant" and content:
                    print(f"\n🤖 AI 完整回复: {content}")
                    ws.close()
                    return

            # 检查 agent 事件里的文本 delta
            if event_name == "agent":
                delta = payload.get("delta", {})
                text = delta.get("text", "") if isinstance(delta, dict) else ""
                if text:
                    print(f"  [delta] {text}", end="", flush=True)

            # 检查 chat 事件
            if event_name == "chat":
                content = payload.get("content", "") or payload.get("text", "")
                if content:
                    print(f"\n🤖 chat事件内容: {content[:300]}")
                    ws.close()
                    return

    # chat.send 路径
    if step == "chat_send":
        if msg_type == "res":
            print(f"chat.send 响应: ok={data.get('ok')}")
            print(json.dumps(data, indent=2, ensure_ascii=False)[:800])
        if msg_type == "event" and event_name in ("chat", "session.message", "agent"):
            print(f"\n🤖 事件: {json.dumps(data, indent=2, ensure_ascii=False)[:800]}")


def on_error(ws, error):
    print(f"\n[ERROR] {error}")


def on_close(ws, code, msg):
    print(f"\n[CLOSE] code={code}")
    print("--- 测试结束 ---")


if __name__ == "__main__":
    if not TOKEN:
        print("请先设置 OPENCLAW_TOKEN 环境变量。")
        sys.exit(1)
    print(f"目标: {WS_URL}")
    print(f"测试消息: {TEST_MSG}")
    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    ws.run_forever()
