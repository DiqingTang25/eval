"""Audit trail — EvalTrace + KBRetrievalLog + JudgeDecision

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    engine = op.get_bind()
    charset = "utf8mb4" if engine.dialect.server_version_info >= (5, 7) else "utf8"

    # ── eval_traces: 完整评测过程追踪 ──
    op.create_table(
        "eval_traces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("test_scenarios.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("session_id", sa.String(64), nullable=False),
        # 评测阶段
        sa.Column("eval_status", sa.String(16), server_default="pending"),
        sa.Column("eval_duration_ms", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        # L1 规则层
        sa.Column("l1_structure_score", sa.Float, nullable=True),
        sa.Column("l1_structure_details", sa.JSON, nullable=True),
        sa.Column("l1_fact_score", sa.Float, nullable=True),
        sa.Column("l1_fact_details", sa.JSON, nullable=True),
        sa.Column("l1_sla_score", sa.Float, nullable=True),
        sa.Column("l1_sla_details", sa.JSON, nullable=True),
        sa.Column("l1_safety_score", sa.Float, nullable=True),
        sa.Column("l1_safety_details", sa.JSON, nullable=True),
        sa.Column("l1_composite_score", sa.Float, nullable=True),
        sa.Column("l1_skip_dims", sa.JSON, nullable=True),
        sa.Column("l1_veto_dims", sa.JSON, nullable=True),
        sa.Column("l1_duration_ms", sa.Integer, server_default="0"),
        # L2 算法层
        sa.Column("l2_embedding_score", sa.Float, nullable=True),
        sa.Column("l2_structure_coverage", sa.Float, nullable=True),
        sa.Column("l2_boundary_kb_score", sa.Float, nullable=True),
        sa.Column("l2_boundary_kb_backend", sa.String(32), nullable=True),
        sa.Column("l2_keywords_matched", sa.JSON, nullable=True),
        sa.Column("l2_keyword_hit_rate", sa.Float, nullable=True),
        sa.Column("l2_duration_ms", sa.Integer, server_default="0"),
        # L3 LLM Judge层
        sa.Column("l3_judge_count", sa.Integer, server_default="0"),
        sa.Column("l3_judge_models", sa.JSON, nullable=True),
        sa.Column("l3_judge_variance", sa.Float, nullable=True),
        sa.Column("l3_needs_human_review", sa.Boolean, server_default=sa.text("FALSE")),
        sa.Column("l3_duration_ms", sa.Integer, server_default="0"),
        # 最终8维度
        sa.Column("final_correctness", sa.Float, nullable=True),
        sa.Column("final_relevancy", sa.Float, nullable=True),
        sa.Column("final_completeness", sa.Float, nullable=True),
        sa.Column("final_guidance", sa.Float, nullable=True),
        sa.Column("final_followup_quality", sa.Float, nullable=True),
        sa.Column("final_boundary_compliance", sa.Float, nullable=True),
        sa.Column("final_turn_consistency", sa.Float, nullable=True),
        sa.Column("final_knowledge_scaffolding", sa.Float, nullable=True),
        sa.Column("final_overall", sa.Float, nullable=True),
        # 原始数据
        sa.Column("raw_agent_response", sa.Text, nullable=True),
        sa.Column("raw_question", sa.Text, nullable=True),
        sa.Column("raw_golden_answer", sa.Text, nullable=True),
        sa.Column("raw_l3_prompts", sa.JSON, nullable=True),
        sa.Column("raw_l3_responses", sa.JSON, nullable=True),
        # 可复现
        sa.Column("reproducible", sa.Boolean, server_default=sa.text("TRUE")),
        sa.Column("trace_version", sa.String(16), server_default="3.3"),
        # Timestamps
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_traces_scenario", "eval_traces", ["scenario_id"])
    op.create_index("idx_traces_session", "eval_traces", ["session_id"])
    op.create_index("idx_traces_status", "eval_traces", ["eval_status"])

    # ── kb_retrieval_logs: KB检索日志 ──
    op.create_table(
        "kb_retrieval_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("eval_trace_id", sa.String(36),
                  sa.ForeignKey("eval_traces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("kb_id", sa.String(64), nullable=False),
        sa.Column("kb_name", sa.String(256), server_default=""),
        sa.Column("backend", sa.String(32), server_default="volcano"),
        # 查询信息
        sa.Column("query_text", sa.Text, nullable=False),
        sa.Column("top_k", sa.Integer, server_default="5"),
        sa.Column("query_duration_ms", sa.Integer, server_default="0"),
        # 结果
        sa.Column("result_count", sa.Integer, server_default="0"),
        sa.Column("top_score", sa.Float, server_default="0.0"),
        sa.Column("avg_score", sa.Float, server_default="0.0"),
        sa.Column("results_json", sa.JSON, nullable=True),
        # 错误
        sa.Column("error_message", sa.Text, nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_kb_logs_trace", "kb_retrieval_logs", ["eval_trace_id"])
    op.create_index("idx_kb_logs_phase", "kb_retrieval_logs", ["phase"])

    # ── judge_decisions: 多Judge独立评分记录 ──
    op.create_table(
        "judge_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("eval_trace_id", sa.String(36),
                  sa.ForeignKey("eval_traces.id", ondelete="CASCADE"), nullable=False),
        # Judge 信息
        sa.Column("judge_index", sa.Integer, nullable=False),
        sa.Column("judge_model", sa.String(64), nullable=False),
        sa.Column("judge_provider", sa.String(32), server_default="deepseek"),
        # 8维度独立评分
        sa.Column("correctness", sa.Float, nullable=True),
        sa.Column("relevancy", sa.Float, nullable=True),
        sa.Column("completeness", sa.Float, nullable=True),
        sa.Column("guidance", sa.Float, nullable=True),
        sa.Column("followup_quality", sa.Float, nullable=True),
        sa.Column("boundary_compliance", sa.Float, nullable=True),
        sa.Column("turn_consistency", sa.Float, nullable=True),
        sa.Column("knowledge_scaffolding", sa.Float, nullable=True),
        sa.Column("overall", sa.Float, nullable=True),
        # 置信度
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("duration_ms", sa.Integer, server_default="0"),
        # 完整推理
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("raw_prompt", sa.Text, nullable=True),
        sa.Column("raw_response", sa.Text, nullable=True),
        # 质量
        sa.Column("is_outlier", sa.Boolean, server_default=sa.text("FALSE")),
        sa.Column("excluded_from_final", sa.Boolean, server_default=sa.text("FALSE")),
        # Timestamps
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_judge_trace", "judge_decisions", ["eval_trace_id"])
    op.create_index("idx_judge_model", "judge_decisions", ["judge_model"])

    # ── 增强 conversation_turns ──
    op.add_column("conversation_turns", sa.Column("latency_ms", sa.Integer, server_default="0"))
    op.add_column("conversation_turns", sa.Column("retry_count", sa.Integer, server_default="0"))
    op.add_column("conversation_turns", sa.Column("agent_metadata", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("conversation_turns", "agent_metadata")
    op.drop_column("conversation_turns", "retry_count")
    op.drop_column("conversation_turns", "latency_ms")
    op.drop_table("judge_decisions")
    op.drop_table("kb_retrieval_logs")
    op.drop_table("eval_traces")
