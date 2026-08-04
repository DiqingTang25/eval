"""v3.6: 报告内容直接存入MySQL — markdown_content + html_content

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-22

Changes:
  1. reports 表新增 markdown_content TEXT: 存储 Markdown 格式的完整报告
  2. reports 表新增 html_content TEXT: 存储 HTML 格式的完整报告, 前端直接展示
  3. 解决前端 viewReportDetail 忽略 reportId 只展示最新文件的问题
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reports",
        sa.Column("markdown_content", sa.Text(), nullable=True,
                  comment="Markdown格式的完整报告内容"))
    op.add_column("reports",
        sa.Column("html_content", sa.Text(), nullable=True,
                  comment="HTML格式的完整报告内容, 前端直接展示"))


def downgrade() -> None:
    op.drop_column("reports", "html_content")
    op.drop_column("reports", "markdown_content")
