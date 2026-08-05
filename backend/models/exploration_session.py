"""ExplorationSession — 平台探索会话模型"""

from datetime import datetime

from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_pk


class ExplorationSession(Base, TimestampMixin):
    """平台探索会话 — 记录每次 Platform Explorer 运行"""
    __tablename__ = "exploration_sessions"

    id: Mapped[str] = uuid_pk()
    session_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    target_url: Mapped[str] = mapped_column(
        String(512), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default="pending", index=True
    )  # pending | running | completed | failed | cancelled

    # ── 探索结果 ──
    phases_found: Mapped[int] = mapped_column(Integer, default=0)
    lessons_found: Mapped[int] = mapped_column(Integer, default=0)
    steps_found: Mapped[int] = mapped_column(Integer, default=0)
    api_endpoints_found: Mapped[int] = mapped_column(Integer, default=0)
    hidden_endpoints_found: Mapped[int] = mapped_column(Integer, default=0)

    # 置信度
    overall_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    structure_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    api_confidence: Mapped[float] = mapped_column(Float, default=0.0)

    # 耗时
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    # ── 文件路径 ──
    schema_path: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )  # platform_schema.yaml 路径
    report_path: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )  # exploration_report.md 路径

    # ── 配置快照 ──
    config_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # {max_depth, max_pages, api_threshold, auth_type, headless, ...}

    # ── 错误/警告 ──
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── 时间 ──
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def is_ready(self) -> bool:
        """schema 是否足够完整以驱动测评"""
        return self.status == "completed" and self.overall_confidence >= 0.5

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "target_url": self.target_url,
            "status": self.status,
            "phases_found": self.phases_found,
            "lessons_found": self.lessons_found,
            "steps_found": self.steps_found,
            "api_endpoints_found": self.api_endpoints_found,
            "hidden_endpoints_found": self.hidden_endpoints_found,
            "overall_confidence": round(self.overall_confidence, 2),
            "structure_confidence": round(self.structure_confidence, 2),
            "api_confidence": round(self.api_confidence, 2),
            "duration_seconds": round(self.duration_seconds, 1),
            "schema_path": self.schema_path,
            "report_path": self.report_path,
            "config_snapshot": self.config_snapshot,
            "error": self.error,
            "warnings": self.warnings,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "is_ready": self.is_ready,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
