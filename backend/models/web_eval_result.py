"""WebEvalResult ORM — MySQL 兼容"""

from sqlalchemy import String, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_pk


class WebEvalResult(Base, TimestampMixin):
    __tablename__ = "web_eval_results"

    id: Mapped[str] = uuid_pk()
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    overall_score: Mapped[int] = mapped_column(Integer, default=0)
    performance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    accessibility: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    best_practices: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_function: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ui_ux: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
