"""
EvidenceTrail — 文件级证据追踪 (纯 MySQL 存储)

每条记录 = 一份原始证据数据 + 其 SHA-256 指纹。
与 eval_scores 的 evidence_hash (场景级指纹) 形成两级校验:
  - 场景级: eval_scores.evidence_hash = SHA-256(conversation JSON + score JSON)
  - 文件级: evidence_trail.sha256 = SHA-256(individual artifact)

存储策略:
  - data_json (LONGTEXT): 直接存原始证据 JSON，最大 4GB
  - 大文件 (截图/录屏) 存本地磁盘路径，不入库

审计流程:
  1. 从 eval_scores 获取场景级哈希 → 验证整体完整性
  2. 从 evidence_trail 取出 data_json → 重新 SHA-256 → 比对指纹
"""

from sqlalchemy import String, Text, BigInteger, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_pk


class EvidenceTrail(Base, TimestampMixin):
    __tablename__ = "evidence_trail"

    id: Mapped[str] = uuid_pk()

    # ── 关联 ──
    session_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="冗余: 方便按Session聚合所有证据",
    )
    eval_score_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_scores.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # ── 文件类型 ──
    artifact_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="conversation | scoring | screenshot | recording | report",
    )
    artifact_path: Mapped[str] = mapped_column(
        String(512), default="",
        comment="逻辑路径, e.g. conversations/sess01/scen001.json",
    )

    # ── 完整性校验 (不可篡改核心) ──
    sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="SHA-256 fingerprint — 一旦写入永不修改",
    )
    file_size: Mapped[int] = mapped_column(
        BigInteger, default=0,
        comment="数据大小 (bytes)",
    )
    content_type: Mapped[str] = mapped_column(
        String(64), default="application/json",
    )

    # ── 原始证据数据 (MySQL 原生存储, 零额外成本) ──
    # MySQL: LONGTEXT (最大4GB); SQLite: TEXT → 跨引擎兼容
    data_json: Mapped[str | None] = mapped_column(
        Text(4294967295),  # 4GB max — MySQL maps to LONGTEXT, SQLite ignores
        nullable=True,
        comment="完整原始证据 JSON — 审计时取出重新 SHA-256 比对",
    )

    # ── 存储策略 (MySQL 表分区实现生命周期) ──
    storage_tier: Mapped[str] = mapped_column(
        String(16), default="hot",
        comment="hot (≤7d) | warm (≤90d) | cold (archive, WORM)",
    )
    worm_locked: Mapped[bool] = mapped_column(
        default=False,
        comment="应用层 WORM: 锁定后禁止 UPDATE/DELETE",
    )

    # ── 元数据 ──
    metadata_json: Mapped[dict | None] = mapped_column(
        name="metadata_json", type_=__import__("sqlalchemy").JSON, nullable=True,
        comment="Extra metadata: persona, lesson_id, judge_models",
    )

    # ── 复合索引 ──
    __table_args__ = (
        Index("idx_evidence_session_artifact", "session_id", "artifact_type"),
        Index("idx_evidence_storage_tier", "storage_tier"),
    )

    def lock(self):
        """应用层 WORM: 锁定后禁止修改"""
        self.worm_locked = True  # 业务代码检查此字段, locked=true 时拒绝 UPDATE
