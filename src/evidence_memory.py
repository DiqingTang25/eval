"""
证据记忆系统 — Phase 2 三层记忆 (Redis + 火山KB + MySQL)

三层架构:
  Tier 1 - Redis (短期热数据): ZSET 滑动窗口, 最近100条, 7天TTL
  Tier 2 - 火山KB (长期语义检索): Bearer token, /api/knowledge/collection/search_knowledge
  Tier 3 - MySQL (权威落地): 始终存储, numpy 余弦相似度回退

火山KB集成方式:
  - 存储: 每次评测结果格式化为文本文档 → 上传到火山KB (自动chunk+embed)
  - 检索: 调用 search_knowledge API → 返回语义相似的历史案例
  - 回退: KB不可用时 → MySQL numpy余弦相似度

用法:
    from src.evidence_memory import EvidenceMemory
    mem = EvidenceMemory()
    mem.store(session_id="s1", question="...", agent_answer="...", scores={...})
    similar = mem.recall("new question?", top_k=5)
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── 火山KB 配置 (复用已有Phase KB, 零额外费用) ──
# 策略: 不创建新KB实例, 而是复用一个已有Phase KB, 用不同的 collection name 做逻辑隔离
#   - 课程内容: name="phase_1" (已存在)
#   - 评测记忆: name="evaluation_memory" (新增, 共享同一个 service_resource_id)
#
# 配置方式 (按优先级):
#   1. VOLC_KB_MEMORY_SOURCE=phase1  → 复用 Phase 1 的KB
#   2. 未设置时 → 自动选择第一个已配置的Phase KB
#   3. 如果没有任何Phase KB配置 → 降级为纯MySQL模式

KB_DOMAIN = os.getenv("VOLC_KB_DOMAIN", "api-knowledgebase.mlp.cn-beijing.volces.com")
KB_SEARCH_URL = f"https://{KB_DOMAIN}/api/knowledge/collection/search_knowledge"
KB_UPLOAD_URL = f"https://{KB_DOMAIN}/api/knowledge/collection/upload_document"

# 所有已知Phase KB (与 hiagent_kb.py 保持一致)
_KB_SOURCES = {
    "phase1": {
        "id": os.getenv("VOLC_KB_PHASE1_ID", ""),
        "key": os.getenv("VOLC_KB_PHASE1_KEY", ""),
    },
    "phase2": {
        "id": os.getenv("VOLC_KB_PHASE2_ID", ""),
        "key": os.getenv("VOLC_KB_PHASE2_KEY", ""),
    },
    "phase3_4": {
        "id": os.getenv("VOLC_KB_PHASE3_4_ID", ""),
        "key": os.getenv("VOLC_KB_PHASE3_4_KEY", ""),
    },
    "phase5": {
        "id": os.getenv("VOLC_KB_PHASE5_ID", ""),
        "key": os.getenv("VOLC_KB_PHASE5_KEY", ""),
    },
}

def _resolve_kb_credentials() -> tuple[str, str, str]:
    """
    解析记忆库的KB凭据 (复用已有Phase KB)

    优先级:
      1. VOLC_KB_MEMORY_SOURCE 指定的Phase
      2. 第一个已配置的Phase KB
      3. 空 (降级纯MySQL)

    Returns: (service_resource_id, api_key, source_phase_name)
    """
    source = os.getenv("VOLC_KB_MEMORY_SOURCE", "").strip().lower()
    if source and source in _KB_SOURCES:
        cfg = _KB_SOURCES[source]
        if cfg["id"] and cfg["key"]:
            return cfg["id"], cfg["key"], source

    # 自动选择
    for phase_name, cfg in _KB_SOURCES.items():
        if cfg["id"] and cfg["key"]:
            return cfg["id"], cfg["key"], phase_name

    return "", "", ""

_kb_id, _kb_key, _kb_source = _resolve_kb_credentials()
_kb_name = os.getenv("VOLC_KB_MEMORY_NAME", "evaluation_memory")

# ── Redis key 前缀 ──
REDIS_KEY_RECENT = "agent_eval:mem:recent"
REDIS_KEY_FAILURE = "agent_eval:mem:failure"
REDIS_MAX_ENTRIES = 100
REDIS_TTL_SECONDS = 7 * 24 * 3600

# ── 失败分类阈值 ──
FAILURE_DIM_THRESHOLD = 3.0
FAILURE_OVERALL_THRESHOLD = 3.0


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """向量化余弦相似度: a (D,), b (N, D) → (N,)"""
    a_norm = a / (np.linalg.norm(a) + 1e-8)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-8)
    return np.dot(b_norm, a_norm)


class EvidenceMemory:
    """三层证据记忆系统 (Redis + 火山KB + MySQL)"""

    def __init__(
        self,
        redis_url: str = None,
        min_similarity: float = 0.65,
    ):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._redis = None
        self._redis_available: bool | None = None

        self._embedder = None
        self.min_similarity = min_similarity

        # 火山KB (复用已有Phase KB, 零额外费用)
        self._kb_id = _kb_id
        self._kb_key = _kb_key
        self._kb_name = _kb_name
        self._kb_source = _kb_source
        self._kb_available = bool(self._kb_id and self._kb_key)

        if self._kb_available:
            logger.info(
                "EvidenceMemory: KB enabled (source=%s collection=%s id=%s)",
                self._kb_source, self._kb_name, self._kb_id[:24],
            )
        else:
            logger.info(
                "EvidenceMemory: KB disabled — 复用已有Phase KB即可零费用启用。"
                "在.env中设置 VOLC_KB_MEMORY_SOURCE=phase1"
            )

        # MySQL 向量缓存
        self._mysql_vec_cache: tuple[list[dict], np.ndarray] | None = None
        self._mysql_cache_ts: float = 0.0
        self._mysql_cache_ttl: float = 60.0

    # ── 属性 ──

    @property
    def _embedding_client(self):
        if self._embedder is None:
            from src.metrics import EmbeddingSimilarity
            self._embedder = EmbeddingSimilarity()
        return self._embedder

    @property
    def redis(self):
        if self._redis_available is None:
            try:
                import redis
                self._redis = redis.Redis.from_url(
                    self.redis_url, decode_responses=True, socket_timeout=5,
                )
                self._redis.ping()
                self._redis_available = True
            except ImportError:
                self._redis_available = False
            except Exception as e:
                logger.debug("EvidenceMemory: Redis unavailable (%s)", e)
                self._redis_available = False
        return self._redis if self._redis_available else None

    @property
    def kb_configured(self) -> bool:
        """检查火山KB是否已配置 (内存KB需要独立的 service_resource_id)"""
        return self._kb_available

    # ═══════════════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════════════

    def store(
        self,
        session_id: str,
        question: str,
        agent_answer: str,
        scores: dict,
        phase: str = "",
        metadata: dict = None,
    ) -> bool:
        """
        存储一次评测结果到三层记忆系统

        1. Embed question + score summary (XJTLU/SiliconFlow)
        2. Redis ZSET 短期热缓存
        3. MySQL 权威落地
        4. 火山KB 长期语义存储 (best-effort)
        """
        summary = self._build_summary(question, agent_answer, scores)

        # ── 1. Embedding ──
        try:
            embedding = self._embedding_client.embed_text(summary)
        except Exception as e:
            logger.error("EvidenceMemory: embedding failed for store: %s", e)
            return False

        # ── 2. 失败分类 ──
        is_failure, failure_type = self._classify_failure(scores)
        overall = scores.get("overall", 0.0)
        if overall is None:
            overall = 0.0

        record = {
            "session_id": session_id,
            "eval_score_id": metadata.get("eval_score_id") if metadata else None,
            "phase": phase,
            "question_text": question[:1000],
            "agent_answer": agent_answer[:2000],
            "overall_score": round(float(overall), 2),
            "is_failure_case": is_failure,
            "failure_type": failure_type,
            "scores": {k: v for k, v in scores.items() if not k.startswith("_")},
            "summary": summary,  # 用于上传到KB的文档内容
            "embedding": embedding,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # ── 3. Redis ──
        if self.redis:
            try:
                self._store_redis(record)
            except Exception as e:
                logger.warning("EvidenceMemory: Redis store failed: %s", e)

        # ── 4. MySQL (权威落地) ──
        try:
            self._store_mysql(record)
        except Exception as e:
            logger.error("EvidenceMemory: MySQL store failed: %s", e)
            return False

        # ── 5. 火山KB (长期语义存储, best-effort) ──
        if self.kb_configured:
            try:
                kb_ok = self._store_volc(record)
                if kb_ok:
                    self._mark_kb_stored(session_id)
            except Exception as e:
                logger.debug("EvidenceMemory: Volcano KB store skipped: %s", e)

        logger.debug(
            "EvidenceMemory: stored session=%s failure=%s type=%s overall=%.2f kb=%s",
            session_id[:8], is_failure, failure_type, overall, self.kb_configured,
        )
        return True

    def recall(
        self,
        question: str,
        top_k: int = 5,
        min_similarity: float = None,
    ) -> list[dict]:
        """
        检索相似历史评测 (火山KB优先 → MySQL回退)

        :return: [{session_id, question_text, overall_score, similarity,
                   is_failure_case, failure_type, scores, ...}, ...]
        """
        threshold = min_similarity if min_similarity is not None else self.min_similarity
        results = []

        # ── 1. 火山KB语义检索 (优先) ──
        if self.kb_configured:
            try:
                kb_results = self._search_volc(question, top_k)
                if kb_results:
                    results.extend(kb_results)
                    logger.debug("EvidenceMemory: KB search returned %d results", len(kb_results))
            except Exception as e:
                logger.warning("EvidenceMemory: KB search failed, falling back to MySQL: %s", e)

        # ── 2. MySQL余弦相似度回退 ──
        if len(results) < top_k:
            try:
                query_vec = np.array(
                    self._embedding_client.embed_text(question), dtype=np.float32,
                )
                remaining = top_k - len(results)
                mysql_results = self._search_mysql_cosine(query_vec, remaining, threshold)
                # 去重
                seen_texts = {r.get("question_text", "")[:60] for r in results}
                for mr in mysql_results:
                    key = mr.get("question_text", "")[:60]
                    if key not in seen_texts:
                        results.append(mr)
                        seen_texts.add(key)
            except Exception as e:
                logger.warning("EvidenceMemory: MySQL cosine search failed: %s", e)

        results.sort(key=lambda r: r.get("similarity", 0.0), reverse=True)
        return results[:top_k]

    def recall_failures(
        self,
        question: str,
        top_k: int = 3,
        min_similarity: float = None,
    ) -> list[dict]:
        """检索相似的历史失败案例 (仅返回 is_failure_case=True)"""
        all_results = self.recall(question, top_k=top_k * 2, min_similarity=min_similarity)
        failures = [r for r in all_results if r.get("is_failure_case")]
        return failures[:top_k]

    def build_context(self, question: str, top_k: int = 3) -> str:
        """构建 Prompt 注入文本 (历史失败案例参考)"""
        failures = self.recall_failures(question, top_k=top_k)
        if not failures:
            return ""

        lines = [
            "【历史失败案例参考（避免重复错误）】",
            "以下是与当前问题相似的历史低分案例，请注意这些案例中Agent的常见错误模式，在评分时重点核查：",
            "",
        ]

        for i, f in enumerate(failures, 1):
            sim = f.get("similarity", 0.0)
            overall = f.get("overall_score", 0.0)
            ftype = f.get("failure_type", "")
            q_text = f.get("question_text", "")[:200]
            scores = f.get("scores", {})

            low_dims = [
                f"{dim}={val}" for dim, val in scores.items()
                if isinstance(val, (int, float)) and val < FAILURE_DIM_THRESHOLD
            ]

            lines.append(
                f"--- 失败案例 #{i} (综合分: {overall:.1f}, 相似度: {sim:.2f}) ---"
            )
            lines.append(f"问题: {q_text}")
            if low_dims:
                lines.append(f"低分维度: {', '.join(low_dims[:5])}")
            if ftype:
                ftype_labels = {
                    "boundary_violation": "回答超出课程边界未拒绝",
                    "hallucination": "事实性错误/幻觉",
                    "overhelping": "过度帮助(直接给答案)",
                    "guidance_poor": "教学引导力不足",
                    "general_poor": "综合低分",
                }
                label = ftype_labels.get(ftype, ftype)
                lines.append(f"失败类型: {label}")
            lines.append("")

        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════
    # 内部: 摘要 + 失败分类
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _build_summary(question: str, agent_answer: str, scores: dict) -> str:
        """构建用于 embedding 和 KB 上传的文本摘要"""
        dim_parts = []
        for dim in [
            "correctness", "relevancy", "completeness", "guidance",
            "boundary_compliance", "overhelping",
        ]:
            val = scores.get(dim)
            if isinstance(val, (int, float)):
                dim_parts.append(f"{dim}={val:.1f}")

        flags = scores.get("flags", [])
        flag_str = " | ".join(flags[:5]) if flags else "none"
        veto_dims = scores.get("veto_dims", [])
        veto_str = ", ".join(veto_dims) if veto_dims else "none"

        return (
            f"问题: {question[:600]}\n"
            f"回答: {agent_answer[:500]}\n"
            f"维度评分: {', '.join(dim_parts)}\n"
            f"综合分: {scores.get('overall', '?')}, 一票否决维度: {veto_str}\n"
            f"标记: {flag_str}"
        )[:3000]

    @staticmethod
    def _classify_failure(scores: dict) -> tuple[bool, str]:
        """判定是否为失败案例 → (is_failure, failure_type)"""
        overall = scores.get("overall")
        if overall is not None and overall < FAILURE_OVERALL_THRESHOLD:
            dim_scores = {
                k: v for k, v in scores.items()
                if isinstance(v, (int, float)) and not k.startswith("_")
            }
            worst_dim = min(dim_scores, key=dim_scores.get) if dim_scores else ""
            worst_val = dim_scores.get(worst_dim, 0.0) if dim_scores else 0.0

            if worst_dim == "boundary_compliance" and worst_val < FAILURE_DIM_THRESHOLD:
                return True, "boundary_violation"
            elif worst_dim == "correctness" and worst_val < FAILURE_DIM_THRESHOLD:
                return True, "hallucination"
            elif worst_dim == "overhelping" and worst_val < FAILURE_DIM_THRESHOLD:
                return True, "overhelping"
            elif worst_dim == "guidance" and worst_val < FAILURE_DIM_THRESHOLD:
                return True, "guidance_poor"
            else:
                return True, "general_poor"

        # 单维度低分检测
        boundary = scores.get("boundary_compliance")
        if isinstance(boundary, (int, float)) and boundary < FAILURE_DIM_THRESHOLD:
            return True, "boundary_violation"
        correctness = scores.get("correctness")
        if isinstance(correctness, (int, float)) and correctness < FAILURE_DIM_THRESHOLD:
            return True, "hallucination"
        overhelping = scores.get("overhelping")
        if isinstance(overhelping, (int, float)) and overhelping < FAILURE_DIM_THRESHOLD:
            return True, "overhelping"

        veto_dims = scores.get("veto_dims", [])
        if veto_dims:
            return True, "general_poor"

        return False, ""

    # ═══════════════════════════════════════════════════════════
    # Tier 1: Redis 短期缓存
    # ═══════════════════════════════════════════════════════════

    def _store_redis(self, record: dict):
        r = self.redis
        if not r:
            return

        ts = time.time()
        redis_data = {
            k: v for k, v in record.items()
            if k not in ("embedding", "scores", "agent_answer", "summary")
        }
        scores = record.get("scores", {})
        redis_data["low_dims"] = [
            f"{k}={v}" for k, v in scores.items()
            if isinstance(v, (int, float)) and v < 3.0
        ]

        r.zadd(REDIS_KEY_RECENT, {json.dumps(redis_data, ensure_ascii=False): ts})
        r.expire(REDIS_KEY_RECENT, REDIS_TTL_SECONDS)

        count = r.zcard(REDIS_KEY_RECENT)
        if count > REDIS_MAX_ENTRIES:
            r.zremrangebyrank(REDIS_KEY_RECENT, 0, count - REDIS_MAX_ENTRIES - 1)

        if record.get("is_failure_case"):
            r.zadd(REDIS_KEY_FAILURE, {
                json.dumps(redis_data, ensure_ascii=False): record.get("overall_score", 0.0),
            })
            r.expire(REDIS_KEY_FAILURE, REDIS_TTL_SECONDS)

    # ═══════════════════════════════════════════════════════════
    # Tier 2: 火山引擎知识库 (Bearer Token)
    # ═══════════════════════════════════════════════════════════

    def _store_volc(self, record: dict) -> bool:
        """
        上传评测摘要文档到火山KB (复用已有Phase KB的 service_resource_id)

        API: POST /api/knowledge/collection/upload_document
        Auth: Bearer {api_key}
        Body: 同 hiagent_kb.py 模式, name="evaluation_memory" 做逻辑隔离

        注意: upload_document 端点需要验证。如果KB控制台API文档显示不同端点，
        修改模块级 KB_UPLOAD_URL 常量即可。
        """
        if not self._kb_id or not self._kb_key:
            return False

        title = f"eval_{record['session_id'][:12]}_{record.get('phase', 'unknown')}"
        body = json.dumps({
            "service_resource_id": self._kb_id,
            "name": self._kb_name,
            "documents": [{
                "content": record.get("summary", ""),
                "title": title,
                "metadata": json.dumps({
                    "session_id": record["session_id"],
                    "is_failure_case": record.get("is_failure_case", False),
                    "failure_type": record.get("failure_type", ""),
                    "overall_score": record.get("overall_score", 0.0),
                }),
            }],
        }, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(KB_UPLOAD_URL, data=body, headers={
            "Authorization": f"Bearer {self._kb_key}",
            "Content-Type": "application/json",
        })

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("code") == 0:
                    logger.debug("EvidenceMemory: KB upload OK: %s", title)
                    return True
                else:
                    logger.warning(
                        "EvidenceMemory: KB upload failed: code=%s msg=%s",
                        data.get("code"), data.get("message", ""),
                    )
                    return False
        except urllib.error.HTTPError as e:
            body_resp = e.read().decode("utf-8", errors="replace")[:300]
            logger.warning(
                "EvidenceMemory: KB upload HTTP %d — 端点可能需要调整: %s",
                e.code, body_resp,
            )
            return False
        except Exception as e:
            logger.warning("EvidenceMemory: KB upload network error: %s", e)
            return False

    def _search_volc(self, query: str, top_k: int = 5) -> list[dict]:
        """
        火山KB 语义检索

        API: POST /api/knowledge/collection/search_knowledge
        (与 hiagent_kb.py 使用完全相同的端点+认证模式)
        """
        if not self._kb_id or not self._kb_key:
            return []

        body = json.dumps({
            "service_resource_id": self._kb_id,
            "name": self._kb_name,
            "query": query[:2000],
            "limit": top_k,
        }, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(KB_SEARCH_URL, data=body, headers={
            "Authorization": f"Bearer {self._kb_key}",
            "Content-Type": "application/json",
        })

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            logger.warning("EvidenceMemory: KB search HTTP %d", e.code)
            return []
        except Exception as e:
            logger.warning("EvidenceMemory: KB search error: %s", e)
            return []

        if data.get("code") != 0:
            logger.warning(
                "EvidenceMemory: KB search API error: code=%s msg=%s",
                data.get("code"), data.get("message", ""),
            )
            return []

        result_list = data.get("data", {}).get("result_list", [])
        results = []
        for r in result_list:
            content = r.get("content", "")
            score = r.get("score", 0.0)
            # 尝试从KB返回的content中提取结构化信息
            results.append({
                "source": "volc_kb",
                "similarity": round(score, 4),
                "question_text": content[:200],
                "kb_content": content,
                "is_failure_case": "failure" in content.lower() or "veto" in content.lower(),
                "failure_type": "",
                "overall_score": 0.0,
                "scores": {},
            })

        return results

    def _mark_kb_stored(self, session_id: str):
        """标记 MySQL 中的记录已写入KB"""
        try:
            from backend.models.evidence_memory import EvidenceMemory as EMModel
            from backend.dependencies import get_sync_db
            db = get_sync_db()
            row = db.query(EMModel).filter(
                EMModel.session_id == session_id
            ).order_by(EMModel.created_at.desc()).first()
            if row:
                row.stored_in_kb = True
                db.commit()
            db.close()
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════
    # Tier 3: MySQL 权威存储 + 余弦相似度回退
    # ═══════════════════════════════════════════════════════════

    def _store_mysql(self, record: dict):
        from backend.models.evidence_memory import EvidenceMemory as EMModel
        from backend.dependencies import get_sync_db

        db = get_sync_db()
        try:
            embedding_bytes = None
            emb = record.get("embedding")
            if emb and isinstance(emb, list):
                embedding_bytes = np.array(emb, dtype=np.float32).tobytes()

            row = EMModel(
                session_id=record["session_id"],
                eval_score_id=record.get("eval_score_id"),
                phase=record.get("phase", ""),
                question_text=record["question_text"],
                agent_answer=record.get("agent_answer", ""),
                scores_json=record.get("scores"),
                embedding=embedding_bytes,
                embedding_dim=len(emb) if emb else 1024,
                overall_score=record.get("overall_score", 0.0),
                is_failure_case=record.get("is_failure_case", False),
                failure_type=record.get("failure_type", ""),
                stored_in_kb=False,
                stored_in_redis=bool(self.redis),
                metadata_json=record.get("metadata"),
            )
            db.add(row)
            db.commit()
            db.close()

            self._mysql_vec_cache = None
        except Exception:
            db.rollback()
            db.close()
            raise

    def _search_mysql_cosine(
        self, query_vec: np.ndarray, top_k: int, min_similarity: float,
    ) -> list[dict]:
        """MySQL 全表余弦相似度"""
        records, matrix = self._load_mysql_vectors()
        if matrix is None or len(records) == 0:
            return []

        similarities = _cosine_similarity(query_vec, matrix)
        top_indices = np.argsort(similarities)[::-1]

        results = []
        for idx in top_indices:
            sim = float(similarities[idx])
            if sim < min_similarity:
                continue
            if len(results) >= top_k:
                break

            rec = dict(records[idx])
            rec["similarity"] = round(sim, 4)
            if isinstance(rec.get("scores_json"), str):
                try:
                    rec["scores"] = json.loads(rec["scores_json"])
                except json.JSONDecodeError:
                    rec["scores"] = {}
            elif isinstance(rec.get("scores_json"), dict):
                rec["scores"] = rec["scores_json"]
            results.append(rec)

        return results

    def _load_mysql_vectors(self) -> tuple[list[dict], np.ndarray | None]:
        now = time.time()
        if (
            self._mysql_vec_cache is not None
            and (now - self._mysql_cache_ts) < self._mysql_cache_ttl
        ):
            return self._mysql_vec_cache

        from backend.models.evidence_memory import EvidenceMemory as EMModel
        from backend.dependencies import get_sync_db

        db = get_sync_db()
        try:
            rows = db.query(EMModel).filter(
                EMModel.embedding.isnot(None)
            ).order_by(EMModel.created_at.desc()).limit(500).all()
            db.close()
        except Exception:
            db.close()
            return [], None

        records, vectors = [], []
        for row in rows:
            if row.embedding is None:
                continue
            try:
                vec = np.frombuffer(row.embedding, dtype=np.float32)
                if len(vectors) > 0 and len(vec) != vectors[-1].shape[0]:
                    continue
            except Exception:
                continue

            records.append({
                "session_id": row.session_id,
                "eval_score_id": row.eval_score_id,
                "phase": row.phase,
                "question_text": row.question_text,
                "overall_score": row.overall_score,
                "is_failure_case": row.is_failure_case,
                "failure_type": row.failure_type,
                "scores_json": row.scores_json,
                "created_at": str(row.created_at) if row.created_at else "",
            })
            vectors.append(vec)

        if not vectors:
            self._mysql_vec_cache = (records, None)
            self._mysql_cache_ts = now
            return self._mysql_vec_cache

        matrix = np.stack(vectors)
        self._mysql_vec_cache = (records, matrix)
        self._mysql_cache_ts = now
        logger.debug("EvidenceMemory: loaded %d vectors from MySQL", len(vectors))
        return self._mysql_vec_cache


# ── 模块级单例 ──
_memory: EvidenceMemory | None = None


def get_evidence_memory() -> EvidenceMemory:
    global _memory
    if _memory is None:
        _memory = EvidenceMemory()
    return _memory
