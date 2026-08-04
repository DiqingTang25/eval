"""Phase 2: 证据记忆向量存储 — 历史测试结果 embedding + 失败案例检索

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-22

Changes:
  1. 新建 evidence_memory 表: 存储 (问题文本, embedding向量, 评分摘要, 失败分类)
  2. 支持三层记忆: Redis(短期) → Volcano KB(长期) → MySQL(权威落地)
  3. is_failure_case + failure_type 实现快速过滤低分案例
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    engine = op.get_bind()
    is_mysql = engine.dialect.name == "mysql"

    embedding_type = sa.LargeBinary(12288) if is_mysql else sa.LargeBinary(12288)
    json_type = sa.JSON() if is_mysql else sa.JSON()

    op.create_table(
        "evidence_memory",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(64), nullable=False, index=True),
        sa.Column("eval_score_id", sa.String(36), nullable=True),
        sa.Column("phase", sa.String(16), server_default="", index=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("agent_answer", sa.Text(), server_default=""),
        sa.Column("scores_json", json_type, nullable=True),
        sa.Column("embedding", embedding_type, nullable=True,
                  comment="numpy float32 .tobytes() serialized"),
        sa.Column("embedding_dim", sa.Integer(), server_default="1024"),
        sa.Column("overall_score", sa.Float(), server_default="0.0"),
        sa.Column("is_failure_case", sa.Boolean(), server_default=sa.text("FALSE"), index=True),
        sa.Column("failure_type", sa.String(32), server_default="", index=True),
        sa.Column("stored_in_kb", sa.Boolean(), server_default=sa.text("FALSE")),
        sa.Column("stored_in_redis", sa.Boolean(), server_default=sa.text("FALSE")),
        sa.Column("metadata_json", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(),
                  server_default=sa.text("CURRENT_TIMESTAMP"),
                  onupdate=sa.text("CURRENT_TIMESTAMP")),
    )

    # ── 复合索引 ──
    op.create_index("idx_mem_phase_fail", "evidence_memory", ["phase", "is_failure_case"])
    op.create_index("idx_mem_failure_type", "evidence_memory", ["failure_type"])


def downgrade() -> None:
    op.drop_table("evidence_memory")
