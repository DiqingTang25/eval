"""0008_exploration_sessions — 平台探索会话表

为通用平台探索器(Platform Explorer)新增探索会话记录表。
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0008_exploration_sessions"
down_revision: Union[str, None] = "0007_report_content_mysql"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exploration_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("target_url", sa.String(512), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, index=True,
                  server_default="pending"),
        sa.Column("phases_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("lessons_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("steps_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("api_endpoints_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("hidden_endpoints_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("overall_confidence", sa.Float, nullable=False, server_default="0"),
        sa.Column("structure_confidence", sa.Float, nullable=False, server_default="0"),
        sa.Column("api_confidence", sa.Float, nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float, nullable=False, server_default="0"),
        sa.Column("schema_path", sa.String(512), nullable=True),
        sa.Column("report_path", sa.String(512), nullable=True),
        sa.Column("config_snapshot", sa.JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("warnings", sa.JSON, nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime, nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )


def downgrade() -> None:
    op.drop_table("exploration_sessions")
