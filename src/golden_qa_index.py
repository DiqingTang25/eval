"""
金标准QA向量索引 — Phase 2 检索增强生成 (RAG)

将 data/golden_qa_bank.json 中所有已批准的QA对构建为向量索引,
评测时检索与当前问题最相似的黄金QA, 注入 LLM Judge Prompt 作为评分参考。

设计:
  - 懒构建: 第一次 search() 时计算所有 embedding
  - 磁盘缓存: .npy (向量) + .json (元数据) 避免每次启动重新 embedding
  - 自动刷新: golden_qa_bank.json mtime 变化时重建索引
  - 内存占用: ~80条 × 1024维 × 4字节 ≈ 320KB
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """向量化余弦相似度: a是查询向量 (D,), b是矩阵 (N, D) → (N,)"""
    a_norm = a / (np.linalg.norm(a) + 1e-8)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-8)
    return np.dot(b_norm, a_norm)


class GoldenQAIndex:
    """金标准QA向量索引"""

    # 缓存路径
    CACHE_EMBED = "data/golden_qa_embeddings.npy"
    CACHE_META = "data/golden_qa_index.json"

    def __init__(
        self,
        bank_path: str = "data/golden_qa_bank.json",
        min_similarity: float = 0.65,
    ):
        self._bank_path = Path(bank_path)
        self._min_similarity = min_similarity
        self._embedding_client = None  # lazy init

        # ── 索引状态 ──
        self._qa_pairs: list[dict] = []
        self._embeddings: np.ndarray | None = None  # shape (N, D)
        self._bank_mtime: float = 0.0
        self._built: bool = False

    # ── 属性 ──

    @property
    def _embedder(self):
        if self._embedding_client is None:
            from src.metrics import EmbeddingSimilarity
            self._embedding_client = EmbeddingSimilarity()
        return self._embedding_client

    @property
    def is_ready(self) -> bool:
        return self._built and self._embeddings is not None and len(self._qa_pairs) > 0

    # ── Public API ──

    def search(self, question: str, top_k: int = 3) -> list[dict]:
        """
        余弦相似度检索 top_k 条最相似黄金QA

        Returns: [{qa_id, question, golden_answer, knowledge_points, phase, type,
                   difficulty, similarity}, ...] 按相似度降序
        """
        if not self._ensure_index():
            return []

        try:
            query_vec = np.array(self._embedder.embed_text(question), dtype=np.float32)
        except Exception as e:
            logger.warning("GoldenQAIndex: embedding failed for search: %s", e)
            return []

        similarities = _cosine_similarity(query_vec, self._embeddings)

        # 取 top_k, 且相似度 >= min_similarity
        top_indices = np.argsort(similarities)[::-1]
        results = []
        for idx in top_indices:
            sim = float(similarities[idx])
            if sim < self._min_similarity:
                continue
            if len(results) >= top_k:
                break
            qa = dict(self._qa_pairs[idx])
            qa["similarity"] = round(sim, 4)
            results.append(qa)

        return results

    def build_context(self, question: str, top_k: int = 2) -> str:
        """
        构建 Prompt 注入文本 (金标准案例参考)

        Returns: 格式化的 Markdown 文本, 无匹配时返回空字符串
        """
        results = self.search(question, top_k=top_k)
        if not results:
            return ""

        lines = [
            "【黄金参考答案（检索增强）】",
            "以下是与当前问题相似的、已人工审核的高质量QA对，请参考这些案例的评分尺度进行评分：",
            "",
        ]

        for i, r in enumerate(results, 1):
            sim = r.get("similarity", 0.0)
            phase = r.get("phase", "?")
            qa_type = r.get("type", "")
            q_text = r.get("question", "")[:300]
            g_answer = r.get("golden_answer", "")[:400]
            kps = r.get("knowledge_points", [])

            lines.append(f"--- 相似案例 #{i} (相似度: {sim:.2f}, Phase: {phase}, 类型: {qa_type}) ---")
            lines.append(f"问题: {q_text}")
            lines.append(f"参考答案: {g_answer}")
            if kps:
                lines.append(f"关键知识点: {', '.join(kps[:5])}")
            lines.append("")

        return "\n".join(lines)

    # ── 内部: 索引构建与缓存 ──

    def _ensure_index(self) -> bool:
        """确保索引已构建且是最新的"""
        # 检查是否需要重建
        if not self._bank_path.exists():
            logger.warning("GoldenQAIndex: bank file not found: %s", self._bank_path)
            return False

        current_mtime = self._bank_path.stat().st_mtime

        if self._built and current_mtime == self._bank_mtime:
            return self.is_ready

        # ── 优先从磁盘缓存加载 ──
        cache_embed = Path(self.CACHE_EMBED)
        cache_meta = Path(self.CACHE_META)

        if (
            cache_embed.exists()
            and cache_meta.exists()
            and cache_meta.stat().st_mtime >= current_mtime
        ):
            try:
                self._load_cache()
                self._bank_mtime = current_mtime
                self._built = True
                logger.info(
                    "GoldenQAIndex: loaded %d QAs from cache (%d dims)",
                    len(self._qa_pairs),
                    self._embeddings.shape[1] if self._embeddings is not None else 0,
                )
                return True
            except Exception as e:
                logger.warning("GoldenQAIndex: cache load failed, rebuilding: %s", e)

        # ── 从头构建 ──
        return self._build_index()

    def _build_index(self) -> bool:
        """从 golden_qa_bank.json 构建向量索引"""
        try:
            with open(self._bank_path, "r", encoding="utf-8") as f:
                all_qa = json.load(f)
        except Exception as e:
            logger.error("GoldenQAIndex: failed to load bank: %s", e)
            return False

        # 只取已批准的QA
        approved = [qa for qa in all_qa if qa.get("status") == "approved"]
        if not approved:
            logger.warning("GoldenQAIndex: no approved QAs found in bank")
            return False

        qa_pairs = []
        texts_to_embed = []

        for qa in approved:
            qa_pairs.append(qa)
            # 嵌入文本: 问题 + 黄金答案 (截断避 token limit)
            text = f"Q: {qa.get('question', '')}\nA: {qa.get('golden_answer', '')}"
            texts_to_embed.append(text[:6000])

        # ── 批量 embedding (逐条调用, API 无 batch 接口) ──
        vectors = []
        for i, text in enumerate(texts_to_embed):
            try:
                vec = self._embedder.embed_text(text)
                vectors.append(vec)
                if (i + 1) % 20 == 0:
                    logger.debug("GoldenQAIndex: embedded %d/%d QAs", i + 1, len(texts_to_embed))
            except Exception as e:
                logger.warning("GoldenQAIndex: embedding failed for QA #%d: %s", i, e)
                # 用零向量占位, 后续 search 自动过滤 (相似度接近0)
                dim = len(vectors[0]) if vectors else 1024
                vectors.append([0.0] * dim)

        if not vectors:
            return False

        self._qa_pairs = qa_pairs
        self._embeddings = np.array(vectors, dtype=np.float32)
        self._bank_mtime = self._bank_path.stat().st_mtime
        self._built = True

        # ── 保存磁盘缓存 ──
        try:
            self._save_cache()
        except Exception as e:
            logger.warning("GoldenQAIndex: failed to save cache: %s", e)

        logger.info(
            "GoldenQAIndex: built index with %d QAs, %d dims (%.1f KB memory)",
            len(qa_pairs),
            self._embeddings.shape[1],
            self._embeddings.nbytes / 1024,
        )
        return True

    def _save_cache(self):
        """保存向量和元数据到磁盘缓存"""
        Path(self.CACHE_EMBED).parent.mkdir(parents=True, exist_ok=True)
        np.save(self.CACHE_EMBED, self._embeddings)

        meta = [
            {
                "qa_id": qa.get("qa_id"),
                "phase": qa.get("phase"),
                "question": qa.get("question"),
                "golden_answer": qa.get("golden_answer"),
            }
            for qa in self._qa_pairs
        ]
        with open(self.CACHE_META, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        logger.debug("GoldenQAIndex: cache saved to %s + %s", self.CACHE_EMBED, self.CACHE_META)

    def _load_cache(self):
        """从磁盘缓存加载"""
        self._embeddings = np.load(self.CACHE_EMBED)

        with open(self.CACHE_META, "r", encoding="utf-8") as f:
            meta_list = json.load(f)

        # 重建完整 QA pair (缓存只保存了关键字段)
        with open(self._bank_path, "r", encoding="utf-8") as f:
            all_qa = {qa["qa_id"]: qa for qa in json.load(f)}

        self._qa_pairs = []
        for meta in meta_list:
            qa_id = meta["qa_id"]
            full = all_qa.get(qa_id, meta)
            self._qa_pairs.append(full)


# ── 模块级单例 ──
_index: GoldenQAIndex | None = None


def get_golden_qa_index() -> GoldenQAIndex:
    global _index
    if _index is None:
        _index = GoldenQAIndex()
    return _index
