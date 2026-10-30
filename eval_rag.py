"""
eval_rag.py — 知识库检索效果评测（可重复运行的基准）。

测什么：
1) 正例召回：15 条领域问题，检查 top-k 片段是否覆盖预期关键词（rule 是否被召回）。
2) 负例拒答：5 条与领域无关的问题，检查是否被相关性阈值过滤为 0 命中（避免注入噪声）。
3) 阈值扫描：对多组 min_score 对比上述指标，用数据选择阈值。

用法：
    python eval_rag.py
    python eval_rag.py --top-k 4 --verbose
"""
from __future__ import annotations

import argparse
from typing import Dict, List, Tuple

import rag_retriever


# (问题, 期望在召回片段中出现的关键词)
POSITIVE_CASES: List[Tuple[str, List[str]]] = [
    # —— 流程与判定口径 ——
    ("机坪选址时哪些地点必须剔除？", ["禁飞区", "剔除"]),
    ("净空高度的要求是多少？", ["净空", "3 米"]),
    ("内环限制区里的机坪怎么处理？", ["内环限制区", "剔除"]),
    ("运力是怎么算的？", ["单架无人机", "每小时"]),
    ("P 值代表什么？", ["P 值", "覆盖"]),
    ("平均配送距离说明什么？", ["平均配送距离"]),
    ("衰减后的承载力用来干什么？", ["衰减", "承载力"]),
    ("为什么某个区域会没有选址结果？", ["机坪候选", "不足"]),
    ("市场渗透率会影响选址结果吗？", ["渗透率", "财务"]),
    ("Stage1 阶段做什么？", ["Stage1", "筛选"]),
    ("Stage2 阶段做什么？", ["Stage2", "覆盖单量"]),
    ("Stage3 阶段做什么？", ["Stage3", "机坪"]),
    ("无人机选址的目标是什么？", ["最大化", "配送单量"]),
    ("机坪数量是不是越多越好？", ["成本", "折衷"]),
    ("机坪应该尽量靠近哪里？", ["高需求", "配送距离"]),
    # —— Stage1 ——
    ("Stage1 的门槛是怎么算的？", ["70%", "累计"]),
    ("Stage1 会淘汰存量起降点吗？", ["存量", "Stage1"]),
    ("起降点的场地面积要求是多少？", ["80 平方米", "场地面积"]),
    # —— Stage2 ——
    ("Stage2 候选会截断到多少个？", ["45", "截断"]),
    ("空域衰减怎么按距离计算？", ["280 米", "500 米"]),
    ("多远距离算完全冲突？", ["小于 280 米", "完全冲突"]),
    ("两个起降点相距 400 米会衰减吗？", ["320 至 500 米", "下降"]),
    ("衰减后覆盖单量的硬门槛是多少？", ["20", "淘汰"]),
    ("新建起降点最多能入选多少个？", ["max_new_stores", "10"]),
    # —— Stage3 与运力 ——
    ("每个机坪最多服务几个起降点？", ["11 个起降点", "机坪最多服务"]),
    ("机坪到起降点的覆盖半径是多少公里？", ["5 公里", "覆盖半径"]),
    ("单个起降点的高峰容量是多少？", ["32 单", "8 格"]),
    ("峰值小时订单怎么换算？", ["4.687", "峰值小时订单"]),
    ("每个机坪配备几架无人机？", ["20 架", "drones_per_vertiport"]),
    ("单架无人机每小时能送多少单？", ["10 单", "每小时"]),
    ("P 值最大可以取到多少？", ["1 到 15", "忽略"]),
    ("推荐方案是怎么选出来的？", ["覆盖起降点数降序", "平均配送距离升序"]),
    ("存量起降点会进入 Stage3 网络吗？", ["存量起降点", "Stage3"]),
    # —— 成本与财务口径 ——
    ("机坪建设成本是多少？", ["40 万", "建设成本"]),
    ("无人机采购成本和寿命是多少？", ["6 万", "3 年"]),
    ("机坪人力成本每年多少？", ["25 万", "每年"]),
    ("单均收益和能源成本分别是多少？", ["6.5 元", "0.8 元"]),
    ("三个城市的折现率分别是多少？", ["北京 12%", "深圳 10%"]),
    ("阶段渗透率系数是多少？", ["0.133", "0.583"]),
    ("成熟期渗透率默认值是多少？", ["0.6", "渗透率"]),
    # —— 城市与空域 ——
    ("项目支持哪些城市？", ["北京、杭州、深圳", "三座城市"]),
    ("深圳内环限制区的半径是多少？", ["6.0 公里", "深圳"]),
    ("北京内环限制区的名称是什么？", ["五环内近似圈", "15.5 公里"]),
    ("内环限制区内的机坪会被保留吗？", ["剔除", "禁止无人机起降"]),
    ("三座城市各有哪些物流带？", ["马驹桥物流带", "宝安空港物流带"]),
    # —— 数据契约与异常 ——
    ("上传的起降点表至少需要哪些列？", ["pad_id", "lat", "lon"]),
    ("机坪表缺 altitude_limit_m 会怎样？", ["按 0 处理", "剔除"]),
    ("不提供距离矩阵会怎样？", ["球面距离", "haversine"]),
    ("上传文件有额外的列会报错吗？", ["多余的列", "忽略"]),
    ("服务重启后 dataset_id 还能用吗？", ["重启", "重新上传"]),
    ("平均配送距离为 0 是什么原因？", ["同址", "0 距离"]),
    ("选址结果里的单量是真实订单吗？", ["合成", "权重"]),
]

NEGATIVE_CASES: List[str] = [
    "今天上海天气怎么样？",
    "帮我写一首关于春天的诗",
    "如何学习 Python 装饰器",
    "推荐一部好看的科幻电影",
    "红烧肉怎么做才好吃",
    "推荐几只值得买入的股票",
    "怎么写一份前端简历",
    "今天 NBA 谁赢了",
    "帮我把这句话翻译成英文",
    "一个月怎么减肥十斤",
    "如何申请日本旅游签证",
    "手机开不了机怎么修",
]


def _hits(query: str, top_k: int, min_score: float) -> List[Dict]:
    return rag_retriever.retrieve_knowledge(query, top_k=top_k, min_score=min_score)


def _eval_once(top_k: int, min_score: float, verbose: bool) -> Dict[str, float]:
    coverages: List[float] = []
    top1_hit = 0
    details: List[str] = []

    for q, kws in POSITIVE_CASES:
        hits = _hits(q, top_k, min_score)
        joined = " ".join(h["text"] for h in hits)
        matched = [kw for kw in kws if kw in joined]
        cov = len(matched) / len(kws)
        coverages.append(cov)
        h1 = bool(hits) and any(kw in hits[0]["text"] for kw in kws)
        top1_hit += int(h1)
        if verbose:
            ref = f"{hits[0]['source']}#段{hits[0]['para']}" if hits else "-"
            details.append(
                f"  [{'✓' if cov == 1 else '△' if cov > 0 else '✗'}] {q} "
                f"命中{len(matched)}/{len(kws)} top1={'Y' if h1 else 'N'} 首条={ref}"
            )

    neg_fp = 0
    neg_detail: List[str] = []
    for q in NEGATIVE_CASES:
        hits = _hits(q, top_k, min_score)
        if hits:
            neg_fp += 1
            if verbose:
                neg_detail.append(f"  [✗ 误召回] {q} -> {hits[0]['score']}")
        elif verbose:
            neg_detail.append(f"  [✓ 已过滤] {q}")

    if verbose:
        print("\n".join(details))
        print("--- 负例 ---")
        print("\n".join(neg_detail))

    return {
        "coverage": sum(coverages) / len(coverages),
        "full_match_rate": sum(1 for c in coverages if c == 1.0) / len(coverages),
        "top1_acc": top1_hit / len(POSITIVE_CASES),
        "neg_fp_rate": neg_fp / len(NEGATIVE_CASES),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    thresholds = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]

    print(f"知识库片段数: {len(rag_retriever._retriever.chunks) if rag_retriever._retriever.loaded else '(首次加载)'}")
    rag_retriever._retriever.ensure_loaded()
    print(f"知识库片段数: {len(rag_retriever._retriever.chunks)}"
          f" | 正例 {len(POSITIVE_CASES)} 条 | 负例 {len(NEGATIVE_CASES)} 条 | top_k={args.top_k}\n")

    header = f"{'min_score':>10} | {'关键词覆盖率':>12} | {'完全命中率':>10} | {'Top1命中':>8} | {'负例误召回率':>12}"
    print(header)
    print("-" * len(header))
    rows = []
    for ms in thresholds:
        m = _eval_once(args.top_k, ms, verbose=False)
        rows.append((ms, m))
        print(f"{ms:>10.2f} | {m['coverage']:>12.1%} | {m['full_match_rate']:>10.1%} | "
              f"{m['top1_acc']:>8.1%} | {m['neg_fp_rate']:>12.1%}")

    # 无损失区间：在不丢召回、不误召回的前提下，阈值能取到多大
    max_cov = max(m["coverage"] for _, m in rows)
    max_top1 = max(m["top1_acc"] for _, m in rows)
    plateau = [
        ms for ms, m in rows
        if m["neg_fp_rate"] == 0.0
        and m["coverage"] >= max_cov - 1e-9
        and m["top1_acc"] >= max_top1 - 1e-9
    ]
    if plateau:
        print(f"\n无损失阈值区间: {min(plateau):.2f} ~ {max(plateau):.2f}")
    print(f"项目默认阈值: min_score={rag_retriever.DEFAULT_MIN_SCORE}"
          f"（见 rag_retriever.py 的 DEFAULT_MIN_SCORE）")

    if args.verbose:
        print(f"\n=== 明细（min_score={rag_retriever.DEFAULT_MIN_SCORE}） ===")
        _eval_once(args.top_k, rag_retriever.DEFAULT_MIN_SCORE, verbose=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
