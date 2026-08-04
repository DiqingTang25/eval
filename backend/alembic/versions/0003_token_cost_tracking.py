"""Token cost tracking + model_used fields

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── conversation_turns: token cost tracking ──
    op.add_column("conversation_turns",
        sa.Column("prompt_tokens", sa.Integer, server_default="0",
                  comment="LLM 调用输入 token 数"))
    op.add_column("conversation_turns",
        sa.Column("completion_tokens", sa.Integer, server_default="0",
                  comment="LLM 调用输出 token 数"))
    op.add_column("conversation_turns",
        sa.Column("total_tokens", sa.Integer, server_default="0",
                  comment="prompt_tokens + completion_tokens"))
    op.add_column("conversation_turns",
        sa.Column("cost_estimate", sa.Float, server_default="0.0",
                  comment="估算成本 (USD)"))
    op.add_column("conversation_turns",
        sa.Column("model_used", sa.String(64), nullable=True,
                  comment="实际调用的模型名"))

    # ── eval_traces: L3 Judge 成本追踪 ──
    op.add_column("eval_traces",
        sa.Column("l3_total_prompt_tokens", sa.Integer, server_default="0",
                  comment="所有 Judge 的 prompt token 总和"))
    op.add_column("eval_traces",
        sa.Column("l3_total_completion_tokens", sa.Integer, server_default="0",
                  comment="所有 Judge 的 completion token 总和"))
    op.add_column("eval_traces",
        sa.Column("l3_total_cost", sa.Float, server_default="0.0",
                  comment="所有 Judge 调用的估算总成本 (USD)"))


def downgrade() -> None:
    op.drop_column("eval_traces", "l3_total_cost")
    op.drop_column("eval_traces", "l3_total_completion_tokens")
    op.drop_column("eval_traces", "l3_total_prompt_tokens")
    op.drop_column("conversation_turns", "model_used")
    op.drop_column("conversation_turns", "cost_estimate")
    op.drop_column("conversation_turns", "total_tokens")
    op.drop_column("conversation_turns", "completion_tokens")
    op.drop_column("conversation_turns", "prompt_tokens")
