# api/embedding.py
"""
Embedding 向量化模块。

设计：
- 使用日语专用 sentence-transformers 模型
  sonoisa/sentence-bert-base-ja-mean-tokens-v2（768维，BERT-base，
  针对日语文本的语义相似度优化，能识别活用形差异）。
- 嵌入文本只取日语字段（术语/读音/日语解释/日语例句/同义词），
  避免中/英文字段干扰日语模型。
- 通过清华 HuggingFace 镜像（hf-mirror.com）下载模型。
- 增量更新：知识库新增条目时只嵌入新条目，已缓存的向量直接复用。
- 缓存中记录生成向量的模型名，换模型后旧缓存自动失效重建。
- 向量缓存存储为 .npz 文件（numpy 格式）。
- 降级策略：sentence-transformers 未安装或模型加载失败时，
  返回 None，调用方回退为纯字符串匹配。

对外接口：
- get_model() -> SentenceTransformer | None
- embed_texts(texts) -> np.ndarray | None
- ensure_embeddings(entries) -> dict[id -> np.ndarray] | None
- cosine_similarity(query_vec, mat) -> np.ndarray
"""
import os
import json
import shutil
import threading

import numpy as np

from config import (
    EMBEDDING_MODEL, EMBEDDING_CACHE_FILE, EMBEDDING_CACHE_SEED,
    HF_ENDPOINT,
)
from logger import logger

_model = None
_model_failed = False
_model_lock = threading.Lock()


def get_model():
    """
    懒加载 sentence-transformers 模型。
    失败时设 _model_failed=True，后续不再重试。
    双重检查锁，防止启动预热线程与分析线程并发重复加载。
    """
    global _model, _model_failed
    if _model is not None or _model_failed:
        return _model

    with _model_lock:
        # 拿到锁后再次检查，可能已被其他线程加载
        if _model is not None or _model_failed:
            return _model
        try:
            # 设置 HuggingFace 镜像（清华）
            os.environ["HF_ENDPOINT"] = HF_ENDPOINT

            from sentence_transformers import SentenceTransformer
            # 手动构建模块，绕过 ST 6.x 对旧日语模型 sentence_bert_config.json
            # 中 do_lower_case 的属性写入兼容问题
            try:
                from sentence_transformers.sentence_transformer.modules \
                    import Transformer, Pooling
            except ImportError:  # 旧版 sentence-transformers
                from sentence_transformers import Transformer, Pooling

            base = Transformer(EMBEDDING_MODEL)
            get_dim = (getattr(base, "get_embedding_dimension", None)
                       or getattr(base, "get_word_embedding_dimension"))
            pool = Pooling(get_dim(), pooling_mode="mean")
            _model = SentenceTransformer(modules=[base, pool])
            logger.info(f"embedding model loaded: {EMBEDDING_MODEL}")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed, "
                "RAG will use string-only matching"
            )
            _model_failed = True
        except Exception as e:
            logger.warning(f"load embedding model failed: {e}")
            _model_failed = True

    return _model


def _build_entry_text(entry: dict) -> str:
    """
    把知识库条目拼成待嵌入的日语文本。
    日语专用模型只取日语字段，不混入中/英文解释。
    """
    parts = [entry.get("term", "")]
    reading = entry.get("reading", "")
    if reading:
        parts.append(reading)
    if entry.get("explanation_ja"):
        parts.append(entry["explanation_ja"])
    if entry.get("example_ja"):
        parts.append(entry["example_ja"])
    for syn in entry.get("synonyms", []):
        parts.append(syn)
    return " ".join(p for p in parts if p)


def embed_texts(texts: list) -> np.ndarray | None:
    """批量嵌入文本列表，返回 (n, dim) 的 numpy 数组。失败返回 None。"""
    model = get_model()
    if model is None or not texts:
        return None
    try:
        vecs = model.encode(texts, show_progress_bar=False,
                           convert_to_numpy=True)
        # L2 归一化，方便后续直接做点积 = 余弦相似度
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vecs = vecs / norms
        return vecs.astype(np.float32)
    except Exception as e:
        logger.warning(f"embed_texts failed: {e}")
        return None


def _seed_cache() -> None:
    """把内置种子向量缓存复制到用户目录（仅首次运行时触发）。"""
    if not os.path.exists(EMBEDDING_CACHE_SEED):
        return
    try:
        os.makedirs(os.path.dirname(EMBEDDING_CACHE_FILE), exist_ok=True)
        shutil.copy2(EMBEDDING_CACHE_SEED, EMBEDDING_CACHE_FILE)
        logger.info("embedding cache seeded from bundled file")
    except Exception as e:
        logger.warning(f"seed embedding cache failed: {e}")


def _load_cache() -> dict:
    """
    从 .npz 文件加载缓存。返回 {id: vector} 或空 dict。
    若缓存由其他模型生成（模型名不一致），视为过期返回空 dict。
    用户目录缓存不存在时，从内置种子文件（随包分发）复制，
    因此打包后首次运行无需重新计算 embedding。
    """
    if not os.path.exists(EMBEDDING_CACHE_FILE):
        _seed_cache()
    if not os.path.exists(EMBEDDING_CACHE_FILE):
        return {}
    try:
        data = np.load(EMBEDDING_CACHE_FILE, allow_pickle=False)
        cached_model = str(data["model"].item()) if "model" in data else ""
        if cached_model != EMBEDDING_MODEL:
            logger.info(
                f"embedding cache model mismatch "
                f"(cache={cached_model}, current={EMBEDDING_MODEL}), rebuild"
            )
            return {}
        ids = data["ids"].tolist()
        vecs = data["embeddings"]
        return {str(i): v for i, v in zip(ids, vecs)}
    except Exception as e:
        logger.warning(f"load embedding cache failed: {e}")
        return {}


def _save_cache(cache: dict) -> None:
    """保存缓存到 .npz 文件（同时记录生成向量的模型名）。"""
    if not cache:
        return
    try:
        os.makedirs(os.path.dirname(EMBEDDING_CACHE_FILE), exist_ok=True)
        ids = np.array(list(cache.keys()))
        vecs = np.array(list(cache.values()), dtype=np.float32)
        np.savez(
            EMBEDDING_CACHE_FILE,
            ids=ids, embeddings=vecs,
            model=np.array(EMBEDDING_MODEL),
        )
        logger.info(f"embedding cache saved: {len(cache)} entries")
    except Exception as e:
        logger.warning(f"save embedding cache failed: {e}")


def ensure_embeddings(entries: list) -> dict | None:
    """
    确保所有知识库条目都有 embedding。
    增量更新：只嵌入缓存中缺失的新条目。
    返回 {entry_id: np.ndarray} 字典，失败返回 None。
    """
    model = get_model()
    if model is None:
        return None

    cache = _load_cache()

    # 找出需要嵌入的新条目
    new_entries = [
        e for e in entries
        if str(e.get("id", "")) not in cache
    ]

    if new_entries:
        logger.info(f"embedding {len(new_entries)} new entries...")
        texts = [_build_entry_text(e) for e in new_entries]
        vecs = embed_texts(texts)
        if vecs is not None:
            for i, entry in enumerate(new_entries):
                cache[str(entry.get("id", ""))] = vecs[i]
            _save_cache(cache)
        else:
            logger.warning("embedding new entries failed, using cache only")

    # 按 entries 顺序整理结果
    result = {}
    for entry in entries:
        eid = str(entry.get("id", ""))
        if eid in cache:
            result[eid] = cache[eid]

    return result if result else None


def cosine_similarity(query_vec: np.ndarray, mat: np.ndarray) -> np.ndarray:
    """
    计算查询向量与矩阵各行的余弦相似度。
    假设输入已 L2 归一化（embed_texts 中完成）。
    返回 (n,) 形状的相似度数组。
    """
    if query_vec is None or mat is None or mat.size == 0:
        return np.array([])
    # query_vec: (dim,), mat: (n, dim)
    return np.dot(mat, query_vec)


def embed_query(text: str) -> np.ndarray | None:
    """嵌入用户查询文本，返回归一化的 (dim,) 一维向量。"""
    vecs = embed_texts([text])
    if vecs is None:
        return None
    return vecs[0]
