"""
rag_retriever.py — 轻量检索式 RAG 检索器（纯 Python + numpy，无 langchain、无向量数据库）。

原理：
1. 启动时扫描 knowledge 目录下的 .md/.txt/.pdf.txt 文档，按段落（约 350 字符）切成 chunk。
2. 每个 chunk 用「中文二元词组 + 英文词」tokenize，构造成归一化的词频向量（TF），并收藏到
   全局倒排索引计算 IDF。
3. 检索时对用户问题先做「口语→领域术语」查询扩展，再与每个 chunk 计算 TF-IDF 余弦相似度，
   叠加关键词命中加成，返回 top-k 最相关的知识片段，供上层拼接进 system 提示词。
4. 三道防误召回：相关性阈值、领域锚点词门控、领域边界声明（法规/执照/航拍等刻意不覆盖的话题）。

设计取舍（满足“轻量、可落地、可写进简历”的目标）：
- 不引入 SP-LM/向量数据库：本项目知识规模小（几 KB），TF-IDF 余弦已足够且零外部依赖（仅 numpy）。
- 中文不用分词库，用二元词组，避免 jieba 等额外依赖，对检索召回也足够。
"""
from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"

# 相关性阈值：由 eval_rag.py 在 52 条标准正例 + 12 条负例上扫描得出。
# 0.00~0.20 区间无召回损失（覆盖率 100%），0.30 起开始掉点，故取 0.1 过滤弱相关噪声。
DEFAULT_MIN_SCORE = 0.1

# 领域锚点词门控（替代此前的「查询词覆盖率」门槛）。
# 判定对象是「扩展后」的查询：只要命中了任意一个领域锚点词，就视为领域内问题并继续检索；
# 一个都没命中才判定为领域外，直接返回空。
# 相比覆盖率门槛的两点改进：
# 1) 不再按「未登录词占比」惩罚口语表达，因此不会误杀「表格里没写城市那一列」这类
#    几乎不含文档术语、但确实属于本领域的问题；
# 2) 判定依据是「是否落在知识库话题上」而非词面统计，领域外闲聊即使词数很多也会被拦下。
# 锚点词按知识库的六大主题分组，新增文档时应同步补充对应锚点。
_DOMAIN_ANCHORS: Tuple[str, ...] = (
    # 流程与网络
    "机坪", "停机坪", "起降点", "选址", "Stage", "阶段", "筛选", "初筛",
    "候选", "截断", "衰减", "覆盖", "漏斗", "入选", "门槛",
    # 空域与城市
    "禁飞区", "净空", "净高", "内环", "空域", "限飞", "限制区", "五环", "绕城",
    "冲突", "北京", "杭州", "深圳", "城市", "物流带",
    # 运力
    "运力", "无人机", "飞机", "架次", "配送", "高峰", "峰值", "订单", "单量",
    "容量", "覆盖半径", "距离", "同址", "drones_per_vertiport", "drone_order_rate_hour",
    # 成本与财务
    "成本", "收益", "折现率", "渗透率", "建设", "采购", "人力", "能源", "电费",
    "租金", "维护", "研发", "行政", "规划期",
    # 数据契约
    "表格", "上传", "数据", "列", "city", "dataset_id", "csv", "excel", "xlsx", "xls",
    "距离矩阵", "距离表", "pad_id", "altitude_limit_m", "vertiport_id",
    "rf_sales_10k", "haversine", "球面距离", "格式", "字段",
    # 结果排查与术语
    "为空", "空结果", "报错", "不一致", "缺失", "没结果", "没有结果", "排查",
    "P 值", "P值", "P=", "存量", "新建", "推荐方案", "物理网络推荐", "加权", "数据集",
)

# 查询扩展：口语说法 → 领域术语。
# 动机：中文按二元组切分，"广告牌挡着"与"净空高度"零词共享，纯词面匹配必然漏召回。
# 做法：命中左侧口语词时，把右侧正式术语拼进查询再做检索（不改文档、不改切分）。
# 约束：左侧必须是足够具体的短语（如「投多少钱」而非「多少钱」），避免把领域外问题也扩进来。
_QUERY_EXPANSIONS: List[Tuple[str, str]] = [
    # 空域与场地
    ("广告牌", "净空 高度 限高 3 米"),
    ("遮挡", "净空 高度 限高 3 米"),
    ("市中心", "内环限制区 剔除"),
    ("繁华", "内环限制区 剔除"),
    ("机场旁边", "禁飞区 剔除"),
    ("机场附近", "禁飞区 剔除"),
    ("不让搞", "内环限制区 6.0 公里"),
    ("场地", "场地面积 80 平方米"),
    ("多小", "场地面积 80 平方米"),
    # 阶段与判定
    ("初筛", "Stage1 筛选 70% 累计"),
    ("挨得", "完全冲突 280 米"),
    ("挨着", "完全冲突 280 米"),
    ("离得太近", "衰减 冲突 280 米"),
    ("离得近", "衰减 冲突 280 米"),
    ("太近", "衰减 冲突 280 米"),
    ("扣掉", "衰减 下降"),
    ("多远距离", "完全冲突 280 米"),
    ("在哪一步", "Stage3 阶段"),
    ("四百来米", "320 至 500 米 下降"),
    ("覆盖量太低", "衰减后 硬门槛 20 淘汰"),
    ("十几个点", "11 个起降点 机坪最多服务"),
    ("最远能", "5 公里 覆盖半径"),
    ("对比几种", "P 值 1 到 15 P=1..15 枚举"),
    ("数量开到", "P 值 超过 15 忽略"),
    ("放进来", "max_new_stores 10 上限 入选"),
    ("最多能放", "max_new_stores 10 上限 入选"),
    ("存量点位", "存量起降点 不参与 Stage1"),
    ("一个点都没覆盖", "机坪候选 不足 空结果"),
    ("没覆盖", "机坪候选 不足 空结果"),
    ("为什么没有结果", "机坪候选 不足 空结果"),
    ("符号", "★ 物理网络推荐"),
    ("标出来", "★ 物理网络推荐"),
    ("净高", "净空 高度 altitude_limit_m Stage3"),
    ("禁飞区", "Stage3 机坪资格校验 剔除"),
    ("按什么标准", "覆盖起降点数降序 平均配送距离升序"),
    ("渗透率", "渗透率 财务 不影响"),
    # 运力
    ("配几架", "20 架 drones_per_vertiport"),
    ("一小时能送", "10 单 每小时 单架无人机"),
    ("接多少单", "32 单 8 格 高峰容量 每小时"),
    # 成本
    ("投多少钱", "建设成本 40 万"),
    ("能用几年", "采购成本 6 万 3 年"),
    ("人工开销", "人力成本 25 万 每年"),
    ("赚多少", "单均收益 6.5 元"),
    ("电费", "能源成本 0.8 元"),
    # 数据契约与异常
    ("几列", "pad_id lat lon 必需列"),
    ("列没填", "altitude_limit_m 缺失 剔除"),
    ("没写城市", "city 列 自动补全"),
    ("没填城市", "city 列 自动补全"),
    ("城市那一列", "city 列 自动补全"),
    ("距离表", "球面距离 haversine 距离矩阵"),
    ("重启", "dataset_id 重启 重新上传"),
    ("真实订单", "合成 权重 rf_sales_10k"),
    ("是零", "同址 0 距离"),
    ("bug", "同址 0 距离"),
    ("别的城市", "北京 杭州 深圳 三座城市 支持"),
    ("上海能", "北京 杭州 深圳 三座城市 支持"),
    ("上海可以", "北京 杭州 深圳 三座城市 支持"),
    ("上海用", "北京 杭州 深圳 三座城市 支持"),
]


# 领域边界声明：这些话题知识库刻意不覆盖（法规、执照、航拍、购机咨询），
# 命中时直接返回空，让上层回答「知识库无此规则」，而不是硬凑一个不相关片段。
# 注意：若未来把这些内容补进 knowledge/，必须同步删除对应 cue，否则会误杀。
_OUT_OF_SCOPE_CUES: Tuple[str, ...] = (
    "报备", "执照", "驾驶证", "航拍", "大疆", "禁飞申请", "空域申请",
)


def is_out_of_scope(query: str) -> bool:
    """查询是否属于知识库刻意不覆盖的话题（供工具层给出明确提示，避免模型用常识代答）。"""
    return any(cue in query for cue in _OUT_OF_SCOPE_CUES)


def is_in_domain(query: str) -> bool:
    """领域锚点词门控：扩展后的查询是否命中至少一个领域锚点词。

    只看「有没有落到知识库话题上」，不按未登录词占比惩罚口语表达，
    因此不会误杀完全不含文档术语、但确实属于本领域的问题。
    """
    expanded = expand_query(query)
    return any(anchor in expanded for anchor in _DOMAIN_ANCHORS)


def expand_query(query: str) -> str:
    """把口语化查询扩展为「原句 + 领域术语」，供 TF-IDF 检索使用。"""
    extra = [terms for cue, terms in _QUERY_EXPANSIONS if cue in query]
    return query + " " + " ".join(extra) if extra else query


# 中英文 tokenizer：中文按字符二元组，拉丁语按连续字母串。
_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_EN_SUFFIX = ("_en",)  # 英文词独立前缀，避免与中文二元组在倒排中混淆。


def _tokenize_en(text: str) -> List[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def _tokenize_zh(text: str) -> List[str]:
    # 去掉空白与标点，仅保留中文字符，再切成二元组。
    pure = re.sub(r"[^\u4e00-\u9fff]", "", text)
    if len(pure) < 2:
        return list(pure) if pure else []
    return [pure[i : i + 2] for i in range(len(pure) - 1)]


def tokenize(text: str) -> List[str]:
    return _tokenize_zh(text) + [t + "_en" for t in _tokenize_en(text)]


def _chunk_paragraphs(text: str, max_len: int = 350) -> List[str]:
    """按段落切分，并把过长的段落进一步截成长度不超过 max_len 的小段（含重叠）。

    标题行（# 开头）不单独成块，而是与紧随其后的正文合并：
    否则「运力与覆盖」这种标题会独占一个 chunk，导致「运力怎么算」召回不到正文里的实际规则。
    """
    import re as _re
    paragraphs = [p.strip() for p in _re.split(r"\n+|。", text) if p.strip()]

    merged: List[str] = []
    i = 0
    while i < len(paragraphs):
        cur = paragraphs[i]
        if cur.startswith("#") and i + 1 < len(paragraphs):
            merged.append(cur + " " + paragraphs[i + 1])
            i += 2
        else:
            merged.append(cur)
            i += 1

    chunks: List[str] = []
    for para in merged:
        if len(para) <= max_len:
            chunks.append(para)
        else:
            step = max_len // 2
            for i in range(0, len(para), step):
                chunk = para[i : i + max_len]
                if chunk:
                    chunks.append(chunk)
                if i + step >= len(para):
                    break
    return [c for c in chunks if c]


class RAGRetriever:
    def __init__(self, docs_dir: Path | None = None):
        self.docs_dir = docs_dir or KNOWLEDGE_DIR
        self.chunks: List[Dict] = []       # [{text, src, tokens, tf}]
        self.df: Dict[str, int] = {}       # 每个 token 出现在多少个 chunk
        self.idf: Dict[str, float] = {}
        self.n_docs = 0
        self.loaded = False

    def _load_docs(self) -> None:
        """加载 knowledge 目录下所有 .md/.txt 文档（递归），拼接成归一文本。"""
        docs: List[Tuple[str, str]] = []  # (path, text)
        if self.docs_dir.exists():
            for p in sorted(self.docs_dir.rglob("*")):
                if p.is_file() and p.suffix.lower() in (".md", ".txt"):
                    try:
                        docs.append((str(p), p.read_text(encoding="utf-8", errors="ignore")))
                    except Exception:
                        continue
        for path, text in docs:
            para_no = 0
            for chunk_text in _chunk_paragraphs(text):
                tokens = tokenize(chunk_text)
                if not tokens:
                    continue
                para_no += 1
                self.chunks.append({
                    "text": chunk_text,
                    "src": path,
                    "para": para_no,
                    "tokens": tokens,
                    "tf": _term_counts(tokens),  # Dict[term, count]
                })
        self.n_docs = len(self.chunks)
        # 文档频率 / IDF
        df: Dict[str, int] = {}
        for c in self.chunks:
            for term in set(c["tokens"]):
                df[term] = df.get(term, 0) + 1
        self.df = df
        n = max(self.n_docs, 1)
        # 平滑 IDF，避免新词爆炸
        self.idf = {term: math.log((n + 1) / (freq + 1)) + 1.0 for term, freq in df.items()}
        # 预计算每个 chunk 的归一化 TF-IDF 权重向量（dict）
        for c in self.chunks:
            vec = {}
            for term, cnt in c["tf"].items():
                w = (1.0 + math.log(cnt)) * self.idf.get(term, 1.0)
                vec[term] = w
            norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
            c["wvec"] = {t: w / norm for t, w in vec.items()}
        self.loaded = True

    def ensure_loaded(self) -> None:
        if not self.loaded:
            self._load_docs()

    def retrieve(self, query: str, top_k: int = 4, min_score: float = DEFAULT_MIN_SCORE) -> List[Dict]:
        """返回 [(chunk, score), ...]，score 为 TF-IDF 余弦 + 关键词加成。

        min_score 用于过滤弱相关的噪声片段（低于阈值视为未命中）。
        """
        self.ensure_loaded()
        if not self.chunks:
            return []
        # 领域边界：知识库刻意不覆盖的话题，直接视为无命中。
        if any(cue in query for cue in _OUT_OF_SCOPE_CUES):
            return []
        # 领域锚点词门控：扩展后一个锚点词都没命中，判定为领域外问题。
        expanded = expand_query(query)
        if not any(anchor in expanded for anchor in _DOMAIN_ANCHORS):
            return []
        q_tokens = tokenize(expanded)
        if not q_tokens:
            return []
        q_tf = _term_counts(q_tokens)
        q_norm = math.sqrt(sum((1.0 + math.log(c)) ** 2 for c in q_tf.values())) or 1.0
        # 查询向量
        q_vec = {t: (1.0 + math.log(c)) / q_norm * self.idf.get(t, 1.0) for t, c in q_tf.items()}
        q_terms = set(q_vec)

        scored: List[Tuple[float, Dict]] = []
        for c in self.chunks:
            # 余弦相似度（只遍历查询命中 term）
            dot = sum(q_vec.get(t, 0.0) * w for t, w in c["wvec"].items() if t in q_terms)
            # 关键词完全命中加成：共有词数 / 查询词数
            overlap = len(q_terms & set(c["tokens"])) / len(q_terms) if q_terms else 0.0
            score = dot + overlap * 0.2
            if score > max(1e-9, min_score):
                scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        # 去重同一来源连续重复文本，保留前 top_k
        seen_src = set()
        out: List[Dict] = []
        for score, c in scored:
            if len(out) >= top_k:
                break
            key = c["src"]
            if key in seen_src and len(seen_src) >= min(2, len(self.chunks)):
                continue
            seen_src.add(key)
            out.append({
                "text": c["text"],
                "source": Path(c["src"]).name,
                "para": c.get("para"),
                "score": round(float(score), 4),
            })
        return out


def _term_counts(tokens: List[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    return counts


# 全局单例，避免每次请求重新建索引
_retriever = RAGRetriever()


def retrieve_knowledge(query: str, top_k: int = 4, min_score: float = DEFAULT_MIN_SCORE) -> List[Dict]:
    """对外接口：返回最相关的知识片段列表。"""
    try:
        return _retriever.retrieve(query, top_k=top_k, min_score=min_score)
    except Exception:
        return []


def build_context_for_query(query: str, top_k: int = 4, min_score: float = DEFAULT_MIN_SCORE) -> str:
    """把检索到的知识片段拼成一段可注入 system 提示词的文本；无结果返回空串。

    每条片段带「文件名#段号」引用，便于回答时标注出处、也便于人工核对是否召回了正确规则。
    """
    hits = retrieve_knowledge(query, top_k=top_k, min_score=min_score)
    if not hits:
        return ""
    parts = []
    for i, h in enumerate(hits, start=1):
        ref = f"{h['source']}#段{h.get('para')}" if h.get("para") else h["source"]
        parts.append(f"[知识{i}·来自 {ref}·相关度{h['score']}] {h['text']}")
    return "\n".join(parts)


if __name__ == "__main__":
    # 冒烟测试
    q = "机坪选址时哪些地点必须剔除？"
    ctx = build_context_for_query(q)
    print("QUERY:", q)
    print(ctx)