# api/rag.py
"""
本地知识库 RAG 检索模块（向量 + 字符串混合打分）。

设计：
- 语义检索：用 embedding 模型对知识库和用户输入做向量化，
  通过余弦相似度计算语义相关性。
- 字符串匹配：保留原有的术语/读音/同义词子串匹配 + 场景加权。
- 混合打分：final = VEC_WEIGHT * cosine_sim + STR_WEIGHT * normalized_str_score
- 增量更新：新增知识库条目时只嵌入新条目，已缓存的向量直接复用。
- 降级策略：embedding 模型不可用时自动回退为纯字符串匹配。

对外接口：
- load_knowledge_base(force_reload=False) -> list[dict]
- retrieve(query, scene=None, top_k=RAG_TOP_K) -> list[dict]
- build_context(entries) -> str
- rebuild_embeddings() -> int   # 手动重建全部 embedding
"""
import json

import numpy as np

from config import KB_FILE, RAG_TOP_K, VEC_WEIGHT, STR_WEIGHT
from logger import logger
from api import embedding

# Scene 枚举值（dictionary.Scene）→ 知识库 scenario_tags（中文标签）
_SCENE_TAGS = {
    "task": ["任务安排"],
    "hr": ["HR通知"],
    "refusal": ["委婉拒绝"],
    "meeting": ["会议", "会议汇报"],
    "email": ["邮件确认"],
    "other": [],
}

_cache = None
_embeddings = None       # {id: np.ndarray}
_embedding_ids = None    # [id, ...] 对应矩阵行顺序
_embedding_matrix = None # np.ndarray (n, dim)


def load_knowledge_base(force_reload: bool = False) -> list:
    """加载并缓存知识库。任何失败都降级为 []，不抛异常。"""
    global _cache
    if _cache is not None and not force_reload:
        return _cache

    try:
        with open(KB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("knowledge base root must be a list")
        _cache = data
        logger.info(f"knowledge base loaded: {len(_cache)} entries")
    except FileNotFoundError:
        logger.warning(f"knowledge base file not found: {KB_FILE}")
        _cache = []
    except Exception as e:
        logger.warning(f"load knowledge base failed: {e}")
        _cache = []
    return _cache


def _ensure_vectors() -> None:
    """
    懒加载知识库 embedding。
    成功后构建 _embedding_matrix 供批量余弦计算使用。
    失败时 _embeddings 保持 None，检索回退为纯字符串匹配。
    """
    global _embeddings, _embedding_ids, _embedding_matrix

    if _embeddings is not None:
        return

    entries = load_knowledge_base()
    if not entries:
        _embeddings = {}
        _embedding_ids = []
        _embedding_matrix = np.array([])
        return

    result = embedding.ensure_embeddings(entries)
    if result is None:
        logger.warning("embedding unavailable, using string-only matching")
        _embeddings = {}
        _embedding_ids = []
        _embedding_matrix = np.array([])
        return

    _embedding_ids = [str(e.get("id", "")) for e in entries
                      if str(e.get("id", "")) in result]
    _embedding_matrix = np.array(
        [result[eid] for eid in _embedding_ids], dtype=np.float32
    ) if _embedding_ids else np.array([])
    _embeddings = result
    logger.info(f"embeddings ready: {len(_embedding_ids)}/{len(entries)} entries")


# ========== 字符串匹配打分（原有逻辑） ==========

def _hit_score(keyword: str, text: str, base: float) -> float:
    """子串命中得分。短词易误命中，按长度衰减。"""
    if not keyword or keyword not in text:
        return 0.0
    n = len(keyword)
    if n <= 2:
        return base * 0.4
    if n <= 4:
        return base
    return base + min((n - 4) * 0.5, 3.0)


def _str_score(entry: dict, text: str, scene_tags: list) -> float:
    """字符串匹配得分（原有逻辑不变）。"""
    score = 0.0

    term = entry.get("term", "")
    score += _hit_score(term, text, 10.0)

    reading = entry.get("reading", "")
    if reading and reading != term:
        score += _hit_score(reading, text, 6.0)

    for syn in entry.get("synonyms", []):
        score += _hit_score(syn, text, 5.0)

    # 场景标签仅在文本实际命中术语时作排序加权
    if score <= 0:
        return 0.0

    if scene_tags:
        tags = entry.get("scenario_tags", [])
        if any(t in scene_tags for t in tags):
            score += 1.0

    return score


def _normalize_str_scores(scores: list) -> list:
    """把字符串得分归一化到 [0, 1]。"""
    if not scores:
        return []
    mx = max(scores)
    if mx <= 0:
        return [0.0] * len(scores)
    return [s / mx for s in scores]


# ========== 混合检索 ==========

def retrieve(query: str, scene: str | None = None,
             top_k: int = RAG_TOP_K) -> list:
    """
    混合检索：向量余弦相似度 + 字符串匹配。
    scene 为 Scene 枚举值（如 "task"），用于场景加权。
    """
    entries = load_knowledge_base()
    if not entries or not query:
        return []

    scene_tags = _SCENE_TAGS.get(scene or "", [])

    # --- 字符串匹配得分 ---
    str_scores = [_str_score(e, query, scene_tags) for e in entries]
    str_norm = _normalize_str_scores(str_scores)

    # --- 向量余弦相似度 ---
    vec_scores = np.zeros(len(entries), dtype=np.float32)
    _ensure_vectors()
    if _embedding_matrix is not None and _embedding_matrix.size > 0:
        q_vec = embedding.embed_query(query)
        if q_vec is not None:
            # 只对有 embedding 的条目计算
            sims = embedding.cosine_similarity(q_vec, _embedding_matrix)
            vec_map = {eid: float(s) for eid, s
                       in zip(_embedding_ids, sims)}
            for i, e in enumerate(entries):
                eid = str(e.get("id", ""))
                if eid in vec_map:
                    vec_scores[i] = max(0.0, vec_map[eid])
            logger.info(f"vector search done, "
                        f"max sim={vec_scores.max():.4f}")

    # --- 混合打分 ---
    final_scores = []
    for i, entry in enumerate(entries):
        combined = VEC_WEIGHT * float(vec_scores[i]) + \
                   STR_WEIGHT * float(str_norm[i])
        # 只要有一项命中就保留
        if vec_scores[i] > 0 or str_scores[i] > 0:
            final_scores.append((combined, i, entry))

    final_scores.sort(key=lambda x: x[0], reverse=True)

    # 调试日志
    if final_scores:
        top = final_scores[0]
        logger.info(
            f"RAG top: id={entries[top[1]].get('id', '')} "
            f"score={top[0]:.4f} "
            f"(vec={vec_scores[top[1]]:.4f}, str={str_norm[top[1]]:.4f})"
        )

    return [entry for _, _, entry in final_scores[:top_k]]


def build_context(entries: list, lang: str = "ja") -> str:
    """
    把检索到的条目构造成注入 LLM Prompt 的参考知识文本。
    lang 决定标题/说明用词以及取哪种语言的解释和例句，
    避免在日语 prompt 中混入中文段落而把输出语言带偏。
    """
    if not entries:
        return ""

    templates = {
        "ja": {
            "header": "【参考知識（ローカル知識ベースより）】",
            "intro": "以下は信頼できる用語情報です。difficultTermsの該当用語の説明には、"
                     "この情報を優先して使用してください。",
            "term": "・用語：{term}（読み：{reading}）",
            "expl_key": "explanation_ja", "expl_label": "  説明：",
            "ex_key": "example_ja", "ex_label": "  例文：",
            "src_label": "  出典：",
        },
        "zh": {
            "header": "【参考知识（来自本地知识库）】",
            "intro": "以下是可靠的术语信息。difficultTerms 中对应术语的解释，"
                     "请优先使用该信息。",
            "term": "・术语：{term}（读音：{reading}）",
            "expl_key": "explanation_zh", "expl_label": "  解释：",
            "ex_key": "example_zh", "ex_label": "  例句：",
            "src_label": "  出处：",
        },
        "en": {
            "header": "[Reference knowledge (from local knowledge base)]",
            "intro": "The following is reliable term information. "
                     "Prioritize it when explaining matching terms in difficultTerms.",
            "term": "- Term: {term} (reading: {reading})",
            "expl_key": "explanation_en", "expl_label": "  Meaning: ",
            "ex_key": "example_en", "ex_label": "  Example: ",
            "src_label": "  Source: ",
        },
    }
    tpl = templates.get(lang, templates["ja"])

    lines = [tpl["header"], tpl["intro"]]
    for e in entries:
        lines.append(tpl["term"].format(
            term=e.get("term", ""), reading=e.get("reading", "")
        ))
        expl = e.get(tpl["expl_key"], "")
        if expl:
            lines.append(tpl["expl_label"] + expl)
        example = e.get(tpl["ex_key"], "")
        if example:
            lines.append(tpl["ex_label"] + example)
        if e.get("source"):
            lines.append(tpl["src_label"] + e["source"])

    return "\n".join(lines)


def rebuild_embeddings() -> int:
    """
    手动重建全部知识库 embedding（删除旧缓存后重新嵌入）。
    返回成功嵌入的条目数。
    """
    global _embeddings, _embedding_ids, _embedding_matrix
    import os

    # 删除旧缓存
    from config import EMBEDDING_CACHE_FILE
    if os.path.exists(EMBEDDING_CACHE_FILE):
        os.remove(EMBEDDING_CACHE_FILE)
        logger.info("old embedding cache deleted")

    # 清空内存缓存
    _embeddings = None
    _embedding_ids = None
    _embedding_matrix = None

    entries = load_knowledge_base(force_reload=True)
    if not entries:
        return 0

    result = embedding.ensure_embeddings(entries)
    if result is None:
        return 0

    # 触发 _ensure_vectors 重建矩阵
    _ensure_vectors()
    return len(_embedding_ids)
