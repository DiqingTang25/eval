"""
EvidenceMemory — 历史测试结果向量记忆 (Phase 2)

三层记忆系统:
  - Redis (短期热数据): ZSET, 7天TTL, 最近100条
  - Volcano KB (长期语义检索): 可选, 通过现有 /api/knowledge/v1/search
  - MySQL (始终落地): 权威存储, 应用层余弦相似度回退

每条记录 = 一次评测的 (问题 + 回答 + 评分摘要) 的 embedding 向量。
检索时: Redis → KB → MySQL cosine fallback。

与 EvidenceTrail 的关系:
  - EvidenceTrail: 证据链不可篡改指纹 (Phase 1)
  - EvidenceMemory: 相似案例检索 + 失败模式学习 (Phase 2)
"""

from sqlalchemy import String, Text, Float, Boolean, JSON, LargeBinary, Index
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_pk


class EvidenceMemory(Base, TimestampMixin):
    __tablename__ = "evidence_memory"

    id: Mapped[str] = uuid_pk()

    # ── 关联 ──
    session_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="FK to test_sessions",
    )
    eval_score_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
        comment="FK to eval_scores (可能为None, 异步写入时延)",
    )

    # ── 课程阶段 ──
    phase: Mapped[str] = mapped_column(
        String(16), default="", index=True,
        comment="课程阶段: PHASE_01 ~ PHASE_05",
    )

    # ── 原始文本 (用于降级时的关键词检索) ──
    question_text: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    agent_answer: Mapped[str] = mapped_column(
        Text, default="",
    )

    # ── 评分摘要 ──
    scores_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="完整评分字典 (同 evaluator.evaluate() 返回)",
    )

    # ── 向量 embedding ──
    # 存储: numpy float32 array → .tobytes() → LargeBinary
    # 反序列化: np.frombuffer(blob, dtype=np.float32).tolist()
    embedding: Mapped[bytes | None] = mapped_column(
        LargeBinary(4 * 3072),  # 最多 3072 维 × 4 bytes = 12KB
        nullable=True,
        comment="numpy float32 array serialized via .tobytes()",
    )
    embedding_dim: Mapped[int] = mapped_column(
        default=1024,
        comment="实际维度: 1024 (bge-m3) 或 3072 (text-embedding-3-large)",
    )

    # ── 失败分类 ──
    overall_score: Mapped[float] = mapped_column(
        Float, default=0.0,
        comment="综合评分 (0-5), 用于快速过滤低分案例",
    )
    is_failure_case: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True,
        comment="是否是失败案例 (overall<3 或 有VETO标记)",
    )
    failure_type: Mapped[str] = mapped_column(
        String(32), default="", index=True,
        comment="boundary_violation | hallucination | overhelping | guidance_poor | general_poor",
    )

    # ── 存储状态追踪 ──
    stored_in_kb: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="是否已写入火山引擎知识库",
    )
    stored_in_redis: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="是否已写入 Redis 热缓存",
    )

    # ── 元数据 ──
    metadata_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Extra: scenario_index, adversarial_type, persona",
    )

    # ── 索引 ──
    __table_args__ = (
        Index("idx_mem_phase_fail", "phase", "is_failure_case"),
        Index("idx_mem_failure_type", "failure_type"),
    )
