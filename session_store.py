"""
session_store.py — Agent 会话持久化（文件存储，无需数据库）。

为什么需要它：
- 多轮对话要让 Agent 记得前几轮说过什么，否则用户追问「那 P=8 呢」时 Agent 会失忆。
- 会话必须落盘：刷新页面、重启服务后还能恢复历史。

存储格式（agent_outputs/sessions/{session_id}.json）：
{
  "session_id": "a1b2c3d4e5f6",
  "created_at": "2026-10-28T22:30:00",
  "updated_at": "2026-10-28T22:35:10",
  "messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
  "dataset_ids": ["9f8e7d6c"]
}

只做纯文件读写，不依赖 Flask / agent 模块，避免循环 import。
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
SESSION_DIR = BASE_DIR / "agent_outputs" / "sessions"

# session_id 白名单：防止 ../ 路径穿越
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,40}$")


def is_valid_session_id(session_id: str) -> bool:
    return bool(_SESSION_ID_RE.match(session_id or ""))


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]


def _path(session_id: str) -> Path:
    if not is_valid_session_id(session_id):
        raise ValueError(f"非法 session_id: {session_id}")
    return SESSION_DIR / f"{session_id}.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def create_session(session_id: Optional[str] = None) -> Dict[str, Any]:
    """新建会话并落盘，返回会话字典。"""
    sid = session_id if (session_id and is_valid_session_id(session_id)) else new_session_id()
    data = {
        "session_id": sid,
        "created_at": _now(),
        "updated_at": _now(),
        "messages": [],
        "dataset_ids": [],
    }
    save_session(sid, data)
    return data


def load_session(session_id: str) -> Optional[Dict[str, Any]]:
    """读取会话；不存在或损坏返回 None。"""
    if not is_valid_session_id(session_id):
        return None
    p = _path(session_id)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    data.setdefault("session_id", session_id)
    data.setdefault("messages", [])
    data.setdefault("dataset_ids", [])
    return data


def save_session(session_id: str, data: Dict[str, Any]) -> None:
    """写会话（先写临时文件再替换，避免写入中断留下半个 JSON）。"""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    p = _path(session_id)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def append_message(session_id: str, role: str, content: str) -> Dict[str, Any]:
    """追加一条消息并落盘。role ∈ user/assistant。"""
    data = load_session(session_id) or create_session(session_id)
    data["messages"].append({"role": role, "content": content})
    data["updated_at"] = _now()
    save_session(session_id, data)
    return data


def add_dataset_id(session_id: str, dataset_id: str) -> Dict[str, Any]:
    """记录本会话使用过的数据集 id（去重，最多保留最近 5 个）。"""
    if not dataset_id:
        return load_session(session_id) or create_session(session_id)
    data = load_session(session_id) or create_session(session_id)
    ids = [i for i in (data.get("dataset_ids") or []) if i != dataset_id]
    ids.append(dataset_id)
    data["dataset_ids"] = ids[-5:]
    data["updated_at"] = _now()
    save_session(session_id, data)
    return data


def list_sessions(limit: int = 20) -> List[Dict[str, Any]]:
    """按更新时间倒序列出会话摘要（不含消息正文）。"""
    if not SESSION_DIR.exists():
        return []
    items: List[Dict[str, Any]] = []
    for p in SESSION_DIR.glob("*.json"):
        if p.name.endswith(".json.tmp"):
            continue
        data = load_session(p.stem)
        if not data:
            continue
        items.append(
            {
                "session_id": data.get("session_id"),
                "updated_at": data.get("updated_at"),
                "message_count": len(data.get("messages") or []),
            }
        )
    items.sort(key=lambda x: str(x.get("updated_at") or ""), reverse=True)
    return items[:limit]


def delete_session(session_id: str) -> bool:
    if not is_valid_session_id(session_id):
        return False
    p = _path(session_id)
    if p.exists():
        p.unlink()
        return True
    return False
