"""TestSession / TestScenario / ConversationTurn — MySQL 兼容"""

from datetime import datetime

from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, uuid_pk


class TestSession(Base, TimestampMixin):
    __tablename__ = "test_sessions"

    id: Mapped[str] = uuid_pk()
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    profile: Mapped[str] = mapped_column(String(32), default="standard", index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    config_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    total_scenarios: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    scenarios: Mapped[list["TestScenario"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    report: Mapped["Report | None"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )


class TestScenario(Base, TimestampMixin):
    __tablename__ = "test_scenarios"

    id: Mapped[str] = uuid_pk()
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scenario_index: Mapped[int] = mapped_column(Integer, nullable=False)
    qa_pair_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("qa_pairs.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending")
    error: Mapped[str] = mapped_column(Text, default="")
    full_conversation: Mapped[str] = mapped_column(Text, default="")

    session: Mapped["TestSession"] = relationship(back_populates="scenarios")
    turns: Mapped[list["ConversationTurn"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )
    scores: Mapped["EvalScore | None"] = relationship(
        back_populates="scenario", cascade="all, delete-orphan", uselist=False
    )
    eval_trace: Mapped["EvalTrace | None"] = relationship(
        back_populates="scenario", cascade="all, delete-orphan", uselist=False
    )


class ConversationTurn(Base, TimestampMixin):
    __tablename__ = "conversation_turns"

    id: Mapped[str] = uuid_pk()
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_scenarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    turn: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    response_status: Mapped[str] = mapped_column(String(16), default="")
    response_text: Mapped[str] = mapped_column(Text, default="")
    response_duration: Mapped[float] = mapped_column(Float, default=0.0)
    is_followup: Mapped[bool] = mapped_column(Boolean, default=False)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # ── 审计追踪字段 (migration 0002) ──
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    agent_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── Token 成本追踪 (migration 0003) ──
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0,
        comment="LLM 调用输入 token 数 (对 Agent 的提问 + system prompt)")
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0,
        comment="LLM 调用输出 token 数 (Agent 回复)")
    total_tokens: Mapped[int] = mapped_column(Integer, default=0,
        comment="prompt_tokens + completion_tokens")
    cost_estimate: Mapped[float] = mapped_column(Float, default=0.0,
        comment="估算成本 (USD), 基于 DeepSeek 定价: input $0.14/1M, output $0.28/1M")
    model_used: Mapped[str | None] = mapped_column(String(64), nullable=True,
        comment="实际调用的模型名, 如 deepseek-chat")

    scenario: Mapped["TestScenario"] = relationship(back_populates="turns")
