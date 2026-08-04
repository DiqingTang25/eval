"""KnowledgeBase / KBDocument — MySQL 兼容"""

from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, uuid_pk


class KnowledgeBase(Base, TimestampMixin):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = uuid_pk()
    dify_dataset_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)  # 火山引擎 KB Service ID
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sync_status: Mapped[str] = mapped_column(String(16), default="not_synced")
    error_message: Mapped[str] = mapped_column(Text, default="")

    documents: Mapped[list["KBDocument"]] = relationship(
        back_populates="knowledge_base", cascade="all, delete-orphan"
    )


class KBDocument(Base, TimestampMixin):
    __tablename__ = "kb_documents"

    id: Mapped[str] = uuid_pk()
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dify_document_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="available")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)

    knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="documents")
