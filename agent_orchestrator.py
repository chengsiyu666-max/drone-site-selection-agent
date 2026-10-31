"""
agent_orchestrator.py — Agent 主循环（多轮工具调用编排 + 只读并行/写串行 + checkpoint + trace）。

职责：
1. 组装分层 system 提示词（领域常识 + 工具规范 + 任务工作流）＝ 上下文工程。
2. 循环驱动 LLM：返回 tool_calls → 并行执行(只读) → 追加 tool 结果 → 继续；
   返回纯文本 → 结束输出最终选址分析。
3. 每步记录 trace（工具名/参数/结果摘要/token/耗时）＝ 可观测性。
4. 每步落盘 checkpoint；支持 --resume 从断点续跑 ＝ 可中断、可恢复。
5. 循环结束后把最终报告串行写入 agent_outputs/ ＝ 写入串行（与只读并行区分）。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_llm import chat_with_tools
from agent_tools import TOOL_SCHEMAS, dispatch_tool_calls

BASE_DIR = Path(__file__).resolve().parent
AGENT_OUTPUT_DIR = BASE_DIR / "agent_outputs"

MAX_HISTORY_TURNS = 8  # 超过则把更早轮次折叠成摘要（上下文工程兜底）
_TOOL_RESULT_PREVIEW = 600  # 工具结果在 trace / 历史折叠时保留的最大字符数

# —— 跨会话历史注入（多轮记忆）——
MAX_HISTORY_MESSAGES = 12  # 最多注入最近 6 轮（user+assistant 各算一条）
MAX_HISTORY_CHARS = 1200  # 单条历史消息超长时截断，防止上下文膨胀

_DOMAIN_KNOWLEDGE = (
    "你是城市无人机低空物流配送网络选址规划 Agent。选址目标：从候选起降点中挑选网络节点，"
    "并决定在哪些机坪(vertiport)投放无人机、每个机坪覆盖哪些起降点，以最大化配送单量覆盖。"
    "三段流程：Stage1 按单量覆盖前70%门槛+场地/坐标落地校验初筛；Stage2 在空域/噪声冲突衰减系数下"
    "最大化衰减后覆盖单量并设「衰减后≥20」硬门槛；Stage3 在运力约束(每机坪≤11起降点、小时峰值运力、"
    "覆盖半径5km)下选 P 个机坪并做最近邻归属，P=1..10 中按「覆盖起降点数降序、平均距离升序」取最优并标记推荐。"
    "重要口径：引擎输出的「覆盖单量/需求量」是样例合成的权重rf_sales_10k(万)，不是真实日单量；"
    "平均配送距离含机坪与起降点同址的0距离边，属样例数据结构特性。回答务必基于工具返回的真实数据，不编造数字。"
)

_TOOL_GUIDE = (
    "可用工具：\n"
    "1) run_site_selection(city, p_values, dataset_id, ...) —— 跑选址引擎，返回漏斗数与各P覆盖（核心工具）。"
    "同一城市可按需用多组 p_values 多次调用对比；用户上传了数据时先 load_csv 拿 dataset_id 再传入本工具。\n"
    "2) get_city_configs() —— 列出城市与内环限制区。\n"
    "3) regeo_label(lat,lon) —— 坐标→商圈/街道标签（高德逆地理编码）。"
    "当 run_site_selection 返回 best.open_vertiport_details / best.covered_pad_details 时，"
    "应对推荐机坪（以及关键起降点）批量调用本工具，把裸经纬度转成可读商圈，写进结论便于落地核对。\n"
    "4) rag_retrieve(query) —— 检索领域知识库。返回 hits 为空且带 note 时，"
    "按 note 说明「知识库没有这条规则」，不要用通用常识或自身记忆补答。\n"
    "5) load_csv(stores_path, rdcs_path, distances_path, city) —— 装载用户上传的 CSV/Excel 真实数据，"
    "返回 dataset_id 与缺列警告；stores 必需且至少含 pad_id/lat/lon，需求量放 rf_sales_10k 列。\n"
    "调用规范：一次可并行调用多个工具；城市参数只接受 beijing/hangzhou/shenzhen；"
    "若一次要对比多个 P，把 p_values 设为如 '6,8,10'。"
)

_TASK_WORKFLOW = (
    "工作流程：(a) 若不确定城市范围，先 get_city_configs()；(b) 调用 run_site_selection 获取该城选址结果，"
    "需要对比多个 P 时用一组 p_values 一次跑清；"
    "(c) 视需要 regeo_label / rag_retrieve 补充位置标签与领域细节；(d) 汇总成一份清晰的选址分析结论："
    "给出漏斗数字、推荐 P、覆盖起降点数、覆盖单量权重、平均配送距离，并注明口径（合成权重、含同址0距离）。"
    "不得臆造未出现在工具返回里的数字，结论需与返回数据一致。"
)


@dataclass
class TraceStep:
    step: int
    called_tools: list = field(default_factory=list)  # {name, args, result_summary}
    usage: Dict[str, int] = field(default_factory=dict)
    elapsed_ms: int = 0


def build_agent_system_prompt() -> str:
    return "\n\n".join([_DOMAIN_KNOWLEDGE, _TOOL_GUIDE, _TASK_WORKFLOW])


def _preview(obj: Any, limit: int = _TOOL_RESULT_PREVIEW) -> str:
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + f"...(截断,共{len(s)}字)"


def _compact_history(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """上下文工程兜底：历史超长时，把最早的工具轮次折叠成一句摘要。"""
    assistant_turns = sum(1 for m in messages if m.get("role") == "assistant")
    if assistant_turns <= MAX_HISTORY_TURNS:
        return messages
    # 保留首条 system + 末 N 轮，中间折叠。
    keep_last = MAX_HISTORY_TURNS
    head = [m for m in messages if m.get("role") == "system"]
    tail_msgs: List[Dict[str, Any]] = []
    for m in reversed(messages):
        if m.get("role") == "system":
            break
        tail_msgs.insert(0, m)
    tail = tail_msgs[-(keep_last * 3) :]

    dropped = len(messages) - len(head) - len(tail)
    if dropped > 0:
        note = {
            "role": "system",
            "content": f"[上下文压缩] 已折叠最早的 {dropped} 条工具/助手消息以免超长。"
                       f"请基于仍然保留的选址结果继续，不要重复已完成的步骤。",
        }
        return head + [note] + tail
    return messages


class RunAgentError(RuntimeError):
    pass


def _build_history_messages(history: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """把持久化会话里最近的 user/assistant 文本转成 LLM 可用的历史消息。

    只保留纯文本对话（不含工具调用细节），并做条数/长度双重裁剪。
    """
    if not history:
        return []
    picked: List[Dict[str, Any]] = []
    for m in history:
        role = str(m.get("role") or "")
        if role not in ("user", "assistant"):
            continue
        content = str(m.get("content") or "").strip()
        if not content:
            continue
        if len(content) > MAX_HISTORY_CHARS:
            content = content[:MAX_HISTORY_CHARS] + f"...(截断,原{len(content)}字)"
        picked.append({"role": role, "content": content})
    return picked[-MAX_HISTORY_MESSAGES:]


def run_agent(
    task: str,
    *,
    city: Optional[str] = None,
    max_steps: int = 8,
    checkpoint_path: Optional[Path] = None,
    resume: bool = False,
    write_report: bool = True,
    history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """执行一次选址分析 Agent 任务。

    history 为本会话此前的 user/assistant 文本消息（用于多轮记忆），
    只注入最近若干轮，避免上下文膨胀。

    返回 {"final": str, "trace": [...], "steps": int, "total_tokens": int, "report_path": str|None}
    """
    AGENT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ckpt: Optional[Path] = checkpoint_path or (AGENT_OUTPUT_DIR / "agent_checkpoint.json")

    messages: List[Dict[str, Any]] = [{"role": "system", "content": build_agent_system_prompt()}]
    trace: List[TraceStep] = []
    start_step = 0

    if resume and ckpt.exists():
        try:
            saved = json.loads(ckpt.read_text(encoding="utf-8"))
            messages = saved.get("messages") or messages
            trace = [TraceStep(**s) for s in saved.get("trace") or []]
            start_step = saved.get("step", 0)
        except Exception:
            messages = [{"role": "system", "content": build_agent_system_prompt()}]
            trace = []
            start_step = 0

    # 注入本会话历史（若有），让 Agent 能接住「那 P=8 呢」这类追问。
    history_msgs = _build_history_messages(history)
    if history_msgs:
        messages.extend(history_msgs)

    user_line = task
    if city:
        user_line = f"[目标城市: {city}] {task}"
    messages.append({"role": "user", "content": user_line})

    final = ""
    total_tokens = 0
    step = start_step

    for step in range(start_step, max_steps):
        # —— 上下文压缩（防超长）——
        messages = _compact_history(messages)

        t_start = time.perf_counter()
        res = chat_with_tools(messages, TOOL_SCHEMAS, max_tokens=2048)
        elapsed_ms = int((time.perf_counter() - t_start) * 1000)
        usage = res.get("usage") or {}
        total_tokens += int(usage.get("total_tokens", 0))

        if not res.get("tool_calls"):
            final = res.get("reply") or ""
            trace.append(TraceStep(step=step, called_tools=[], usage=usage, elapsed_ms=elapsed_ms))
            _save_checkpoint(ckpt, messages, trace, step)
            break

        # —— 并行执行只读工具 ——
        tool_calls = res["tool_calls"]
        # 追加 assistant 的 tool_calls 消息（OpenAI 兼容格式）
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"], ensure_ascii=False)},
                    }
                    for tc in tool_calls
                ],
            }
        )
        executed = dispatch_tool_calls(tool_calls)
        for ex in executed:
            messages.append({"role": "tool", "tool_call_id": ex["id"], "content": ex["content"]})

        trace.append(
            TraceStep(
                step=step,
                called_tools=[
                    {"name": tc["name"], "args": tc.get("arguments") or {}, "result_summary": _preview(ex["content"])}
                    for tc, ex in zip(tool_calls, executed)
                ],
                usage=usage,
                elapsed_ms=elapsed_ms,
            )
        )
        _save_checkpoint(ckpt, messages, trace, step + 1)

        last_err_msgs = []
        if any('"ok": false' in ex["content"] for ex in executed):
            last_err_msgs.append("上次工具调用存在失败项，请修正参数后重试或跳过。")
        # 防死循环
        if step == max_steps - 1:
            messages.append({"role": "user", "content": "这是最后一轮，请直接综合已有工具结果输出最终选址分析结论。" + " ".join(last_err_msgs)})
    else:
        final = final or "(已达最大轮次，未能生成结论)"

    if resume or step - start_step >= 0:
        pass

    report_path: Optional[str] = None
    if write_report and final:
        report_path = _write_report(final, trace, total_tokens, task)

    return {
        "final": final,
        "trace": [t.__dict__ for t in trace],
        "steps": len(trace),
        "total_tokens": total_tokens,
        "report_path": report_path,
    }


def _save_checkpoint(path: Path, messages: List[Dict[str, Any]], trace: List[TraceStep], step: int) -> None:
    try:
        path.write_text(
            json.dumps(
                {
                    "messages": messages,
                    "trace": [t.__dict__ for t in trace],
                    "step": step,
                    "saved_at": datetime.now().isoformat(timespec="seconds"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass  # checkpoint 失败不阻断主流程


def _md_trace_table(trace: List[TraceStep]) -> str:
    lines = ["| 步 | 工具调用 | token | 耗时ms |", "|---|--------|------|-------|"]
    for t in trace:
        calls = "; ".join(f"`{c['name']}({json.dumps(c['args'], ensure_ascii=False)})`" for c in t.called_tools) or "(等待最终结论)"
        usage = t.usage or {}
        lines.append(f"| {t.step} | {calls} | {usage.get('total_tokens','')} | {t.elapsed_ms} |")
    return "\n".join(lines)


def _write_report(final: str, trace: List[TraceStep], total_tokens: int, task: str) -> str:
    """串行写入最终选址报告（写入动作在循环结束后执行 → 写串行）。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = AGENT_OUTPUT_DIR / f"agent_report_{ts}.md"
    body = [
        "# 选址分析 Agent 报告",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 任务：{task}",
        f"- 工具调用轮次：{len(trace)}，累计 token：{total_tokens}",
        "",
        "## Agent 运行轨迹",
        _md_trace_table(trace),
        "",
        "## 最终结论",
        "",
        final,
        "",
    ]
    path.write_text("\n".join(body), encoding="utf-8")
    return str(path)