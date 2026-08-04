"""Report ORM — MySQL 兼容"""

from sqlalchemy import String, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, uuid_pk


class Report(Base, TimestampMixin):
    __tablename__ = "reports"

    id: Mapped[str] = uuid_pk()
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_sessions.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    timestamp: Mapped[str] = mapped_column(String(32), nullable=False)
    summary_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    markdown_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    json_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # v3.6: 报告内容直接存入MySQL, 不再依赖文件系统
    markdown_content: Mapped[str | None] = mapped_column(Text, nullable=True,
        comment="Markdown格式的完整报告内容")
    html_content: Mapped[str | None] = mapped_column(Text, nullable=True,
        comment="HTML格式的完整报告内容, 前端直接展示")

    session: Mapped["TestSession"] = relationship(back_populates="report")
