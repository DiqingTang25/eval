"""Phase 1 (v2): 纯MySQL证据存储 — 去掉TOS依赖, 证据JSON直接入库

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-22

Changes:
  1. eval_scores: RENAME evidence_tos_key → evidence_path
                  DROP evidence_tos_url (不需要预签名链接)
  2. evidence_trail: RENAME tos_key → artifact_path
                     DROP tos_bucket, tos_etag, tos_url
                     ADD data_json LONGTEXT (原始证据JSON)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    engine = op.get_bind()
    is_mysql = engine.dialect.name == "mysql"

    # ── 1. eval_scores: 字段重命名 + 删除 ──
    if is_mysql:
        op.alter_column("eval_scores", "evidence_tos_key",
                        new_column_name="evidence_path",
                        existing_type=sa.String(512))
    else:
        # SQLite 不支持 RENAME COLUMN, 用 add+drop 模拟
        op.add_column("eval_scores",
                      sa.Column("evidence_path", sa.String(512), server_default=""))
        op.execute("UPDATE eval_scores SET evidence_path = evidence_tos_key")
        op.drop_column("eval_scores", "evidence_tos_key")

    op.drop_column("eval_scores", "evidence_tos_url")

    # ── 2. evidence_trail: 重命名 tos_key → artifact_path ──
    if is_mysql:
        op.alter_column("evidence_trail", "tos_key",
                        new_column_name="artifact_path",
                        existing_type=sa.String(512))
    else:
        op.add_column("evidence_trail",
                      sa.Column("artifact_path", sa.String(512), server_default=""))
        op.execute("UPDATE evidence_trail SET artifact_path = tos_key")
        op.drop_column("evidence_trail", "tos_key")

    # ── 3. evidence_trail: 删除 TOS 专用字段 ──
    op.drop_column("evidence_trail", "tos_bucket")
    op.drop_column("evidence_trail", "tos_etag")
    op.drop_column("evidence_trail", "tos_url")

    # ── 4. evidence_trail: 新增 data_json (LONGTEXT) ──
    if is_mysql:
        op.add_column("evidence_trail",
                      sa.Column("data_json", sa.dialects.mysql.LONGTEXT, nullable=True,
                                comment="完整原始证据JSON — 审计时取出重新SHA-256比对"))
    else:
        op.add_column("evidence_trail",
                      sa.Column("data_json", sa.Text, nullable=True))


def downgrade() -> None:
    engine = op.get_bind()
    is_mysql = engine.dialect.name == "mysql"

    # 4. data_json
    op.drop_column("evidence_trail", "data_json")

    # 3. tos 字段恢复
    op.add_column("evidence_trail",
                  sa.Column("tos_url", sa.String(2048), server_default=""))
    op.add_column("evidence_trail",
                  sa.Column("tos_etag", sa.String(64), server_default=""))
    op.add_column("evidence_trail",
                  sa.Column("tos_bucket", sa.String(128), server_default="agent-eval-evidence"))

    # 2. artifact_path → tos_key
    if is_mysql:
        op.alter_column("evidence_trail", "artifact_path",
                        new_column_name="tos_key",
                        existing_type=sa.String(512))
    else:
        op.add_column("evidence_trail",
                      sa.Column("tos_key", sa.String(512), server_default=""))
        op.execute("UPDATE evidence_trail SET tos_key = artifact_path")
        op.drop_column("evidence_trail", "artifact_path")

    # 1. eval_scores 恢复
    op.add_column("eval_scores",
                  sa.Column("evidence_tos_url", sa.String(2048), server_default=""))

    if is_mysql:
        op.alter_column("eval_scores", "evidence_path",
                        new_column_name="evidence_tos_key",
                        existing_type=sa.String(512))
    else:
        op.add_column("eval_scores",
                      sa.Column("evidence_tos_key", sa.String(512), server_default=""))
        op.execute("UPDATE eval_scores SET evidence_tos_key = evidence_path")
        op.drop_column("eval_scores", "evidence_path")
