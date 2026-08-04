"""EvalScore ORM — MySQL 兼容"""

from sqlalchemy import String, Text, Float, Integer, Boolean, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, uuid_pk


class EvalScore(Base, TimestampMixin):
    __tablename__ = "eval_scores"

    id: Mapped[str] = uuid_pk()
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_scenarios.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )

    correctness: Mapped[float] = mapped_column(Float, default=0.0)
    relevancy: Mapped[float] = mapped_column(Float, default=0.0)
    completeness: Mapped[float] = mapped_column(Float, default=0.0)
    guidance: Mapped[float] = mapped_column(Float, default=0.0)
    followup_quality: Mapped[float] = mapped_column(Float, default=0.0)
    boundary_compliance: Mapped[float] = mapped_column(Float, default=0.0)
    turn_consistency: Mapped[float] = mapped_column(Float, default=0.0)
    knowledge_scaffolding: Mapped[float] = mapped_column(Float, default=0.0)
    overall: Mapped[float] = mapped_column(Float, default=0.0)

    boundary_status: Mapped[str] = mapped_column(String(32), default="")
    boundary_evidence: Mapped[str] = mapped_column(Text, default="")
    boundary_score_raw: Mapped[float] = mapped_column(Float, default=0.0)

    n_judges: Mapped[int] = mapped_column(Integer, default=1)
    judge_variance: Mapped[float] = mapped_column(Float, default=0.0)
    flags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    needs_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
    confidences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score_explanations: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── Phase 1: 证据链字段 ──
    evidence_hash: Mapped[str] = mapped_column(
        String(64), default="",
        comment="SHA-256 of full conversation + score JSON (immutable fingerprint)",
    )
    evidence_path: Mapped[str] = mapped_column(
        String(512), default="",
        comment="Logical evidence path, e.g. conversations/{session_id}/scenario_001.json",
    )
    merkle_root: Mapped[str] = mapped_column(
        String(64), default="",
        comment="Merkle tree root of all evidence in this session (pre-blockchain)",
    )
    chain_tx_hash: Mapped[str] = mapped_column(
        String(128), default="",
        comment="Blockchain transaction hash (reserved for Phase 4)",
    )

    scenario: Mapped["TestScenario"] = relationship(back_populates="scores")
