"""
run_agent.py — 无人机选址 Agent 的 CLI 入口。

用法：
    python run_agent.py "对深圳做三阶段选址分析，比较 P=6/8/10 并给推荐" --city shenzhen
    python run_agent.py "对比北京、深圳的选址漏斗" --max-steps 10
    python run_agent.py "……" --resume            # 从 checkpoint 续跑
"""
from __future__ import annotations

import argparse
import json
import sys
import time

# 先加载 .env（经 app 模块触发），再导入 agent 相关模块。
import app  # noqa: F401

from agent_orchestrator import AGENT_OUTPUT_DIR, run_agent


def main() -> int:
    parser = argparse.ArgumentParser(description="无人机低空配送选址分析 Agent")
    parser.add_argument("task", nargs="?", help="给 Agent 的自然语言任务")
    parser.add_argument("--city", default=None, help="限定目标城市 beijing/hangzhou/shenzhen")
    parser.add_argument("--max-steps", type=int, default=8, help="最多工具调用轮次")
    parser.add_argument("--checkpoint", default=None, help="checkpoint 文件路径")
    parser.add_argument("--resume", action="store_true", help="从 checkpoint 续跑")
    parser.add_argument("--no-write", action="store_true", help="不写报告文件")
    args = parser.parse_args()

    task = args.task or "对深圳做三阶段选址分析，比较 P=6/8/10 并基于工具返回数据给出推荐方案与结论。"

    print(f"▶ 任务：{task}")
    print(f"▶ 城市限定：{args.city or '未限定'} | 最大轮次：{args.max_steps} | resume={args.resume}")
    t0 = time.perf_counter()

    try:
        out = run_agent(
            task,
            city=args.city,
            max_steps=args.max_steps,
            checkpoint_path=args.checkpoint,
            resume=args.resume,
            write_report=not args.no_write,
        )
    except Exception as exc:  # noqa: BLE001 —— CLI 顶层把内部错误转成友好中文
        print(f"\n✗ Agent 执行失败（{type(exc).__name__}）：{exc}", file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - t0
    print("\n" + "=" * 70)
    print("最终选址分析结论")
    print("=" * 70)
    print(out["final"])
    print("\n" + "-" * 70)
    print(f"工具调用轮次：{out['steps']} | 累计 token：{out['total_tokens']} | 总耗时：{elapsed:.1f}s")
    if out.get("report_path"):
        print(f"报告已写入：{out['report_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())