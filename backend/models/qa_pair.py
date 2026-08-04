"""QA Pair ORM 模型 — MySQL 兼容"""

from datetime import datetime

from sqlalchemy import String, Text, Boolean, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_pk


class QAPair(Base, TimestampMixin):
    __tablename__ = "qa_pairs"

    id: Mapped[str] = uuid_pk()
    qa_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    phase: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    difficulty: Mapped[str] = mapped_column(String(16), default="中等")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    golden_answer: Mapped[str] = mapped_column(Text, nullable=False)
    knowledge_points: Mapped[list | None] = mapped_column(JSON, nullable=True)
    goal: Mapped[str] = mapped_column(Text, default="")
    knowledge_based: Mapped[bool] = mapped_column(Boolean, default=True)
    adversarial_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    source_document: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_sheet: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    reviewer_notes: Mapped[str] = mapped_column(Text, default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    turns: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "qa_id": self.qa_id,
            "phase": self.phase,
            "type": self.type,
            "difficulty": self.difficulty,
            "question": self.question,
            "golden_answer": self.golden_answer,
            "knowledge_points": self.knowledge_points or [],
            "goal": self.goal,
            "knowledge_based": self.knowledge_based,
            "adversarial_type": self.adversarial_type,
            "source": {
                "document": self.source_document or "",
                "sheet": self.source_sheet or "",
                "excerpt": self.source_excerpt or "",
            },
            "status": self.status,
            "reviewer_notes": self.reviewer_notes,
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }
