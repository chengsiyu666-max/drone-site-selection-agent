"""
rag_retriever.py — 轻量检索式 RAG 检索器（纯 Python + numpy，无 langchain、无向量数据库）。

原理：
1. 启动时扫描 knowledge 目录下的 .md/.txt/.pdf.txt 文档，按段落（约 350 字符）切成 chunk。
2. 每个 chunk 用「中文二元词组 + 英文词」tokenize，构造成归一化的词频向量（TF），并收藏到
   全局倒排索引计算 IDF。
3. 检索时对用户问题做同样的向量化，与每个 chunk 计算 TF-IDF 余弦相似度，再叠加关键词命中加成，
   返回 top-k 最相关的知识片段，供上层拼接进 system 提示词。

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

# 相关性阈值：由 eval_rag.py 在 15 条正例 + 5 条负例上扫描得出。
# 0.05~0.15 区间无召回损失（覆盖率 100%），0.20 起开始掉点，故取 0.1 过滤弱相关噪声。
DEFAULT_MIN_SCORE = 0.1

# 查询覆盖度门槛：查询里「知识库中完全没有」的词占比过高时，判定为领域外问题直接返回空。
# 依据 eval_rag.py：52 条正例的未登录词占比最高 0.67，12 条负例最低 0.75，取 0.75 可完全分开。
# 作用：避免「推荐/前端/一个」这类泛化词命中少量片段造成负例误召回。
OOV_REJECT_RATIO = 0.75
OOV_MIN_TERMS = 4  # 词数少于 4 的短查询不做该判定，防止误杀

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
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        # 领域外问题防护：查询词在知识库中几乎都不存在时，直接视为无命中。
        q_terms_set = set(q_tokens)
        if len(q_terms_set) >= OOV_MIN_TERMS:
            oov = sum(1 for t in q_terms_set if self.df.get(t, 0) == 0)
            if oov / len(q_terms_set) >= OOV_REJECT_RATIO:
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