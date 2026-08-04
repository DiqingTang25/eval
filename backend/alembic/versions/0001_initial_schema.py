"""Initial schema — MySQL 5.7/8 compatible tables

Revision ID: 0001
Revises: None
Create Date: 2026-07-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    engine = op.get_bind()
    # MySQL 5.7 兼容: 用 utf8mb4
    charset = "utf8mb4" if engine.dialect.server_version_info >= (5, 7) else "utf8"

    # ── qa_pairs ──
    op.create_table(
        "qa_pairs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("qa_id", sa.String(64), unique=True, nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("difficulty", sa.String(16), server_default="中等"),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("golden_answer", sa.Text, nullable=False),
        sa.Column("knowledge_points", sa.JSON, nullable=True),
        sa.Column("goal", sa.Text, nullable=True),
        sa.Column("knowledge_based", sa.Boolean, server_default=sa.text("TRUE")),
        sa.Column("adversarial_type", sa.String(32), nullable=True),
        sa.Column("source_document", sa.String(256), nullable=True),
        sa.Column("source_sheet", sa.String(128), nullable=True),
        sa.Column("source_excerpt", sa.Text, nullable=True),
        sa.Column("status", sa.String(16), server_default="pending"),
        sa.Column("reviewer_notes", sa.Text, nullable=True),
        sa.Column("approved_at", sa.DateTime, nullable=True),
        sa.Column("turns", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_qa_phase", "qa_pairs", ["phase"])
    op.create_index("idx_qa_status", "qa_pairs", ["status"])
    op.create_index("idx_qa_type", "qa_pairs", ["type"])

    # ── test_sessions ──
    op.create_table(
        "test_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(64), unique=True, nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("profile", sa.String(32), server_default="standard"),
        sa.Column("status", sa.String(16), server_default="pending"),
        sa.Column("config_snapshot", sa.JSON, nullable=True),
        sa.Column("total_scenarios", sa.Integer, server_default="0"),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_sessions_status", "test_sessions", ["status"])
    op.create_index("idx_sessions_created", "test_sessions", ["created_at"])

    # ── test_scenarios ──
    op.create_table(
        "test_scenarios",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("test_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scenario_index", sa.Integer, nullable=False),
        sa.Column("qa_pair_id", sa.String(36), sa.ForeignKey("qa_pairs.id"), nullable=True),
        sa.Column("status", sa.String(16), server_default="pending"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("full_conversation", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_scenarios_session", "test_scenarios", ["session_id"])

    # ── conversation_turns ──
    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36), sa.ForeignKey("test_scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("turn", sa.Integer, nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("response_status", sa.String(16), server_default=""),
        sa.Column("response_text", sa.Text, nullable=True),
        sa.Column("response_duration", sa.Float, server_default="0.0"),
        sa.Column("is_followup", sa.Boolean, server_default=sa.text("FALSE")),
        sa.Column("turn_index", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_turns_scenario", "conversation_turns", ["scenario_id"])

    # ── eval_scores ──
    op.create_table(
        "eval_scores",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36), sa.ForeignKey("test_scenarios.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("correctness", sa.Float, server_default="0.0"),
        sa.Column("relevancy", sa.Float, server_default="0.0"),
        sa.Column("completeness", sa.Float, server_default="0.0"),
        sa.Column("guidance", sa.Float, server_default="0.0"),
        sa.Column("followup_quality", sa.Float, server_default="0.0"),
        sa.Column("boundary_compliance", sa.Float, server_default="0.0"),
        sa.Column("turn_consistency", sa.Float, server_default="0.0"),
        sa.Column("knowledge_scaffolding", sa.Float, server_default="0.0"),
        sa.Column("overall", sa.Float, server_default="0.0"),
        sa.Column("boundary_status", sa.String(32), server_default=""),
        sa.Column("boundary_evidence", sa.Text, nullable=True),
        sa.Column("boundary_score_raw", sa.Float, server_default="0.0"),
        sa.Column("n_judges", sa.Integer, server_default="1"),
        sa.Column("judge_variance", sa.Float, server_default="0.0"),
        sa.Column("flags", sa.JSON, nullable=True),
        sa.Column("needs_human_review", sa.Boolean, server_default=sa.text("FALSE")),
        sa.Column("confidences", sa.JSON, nullable=True),
        sa.Column("score_explanations", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # ── reports ──
    op.create_table(
        "reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("test_sessions.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("timestamp", sa.String(32), nullable=False),
        sa.Column("summary_json", sa.JSON, nullable=False),
        sa.Column("markdown_path", sa.String(256), nullable=True),
        sa.Column("json_path", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_reports_created", "reports", ["created_at"])

    # ── web_eval_results ──
    op.create_table(
        "web_eval_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("overall_score", sa.Integer, server_default="0"),
        sa.Column("performance", sa.JSON, nullable=True),
        sa.Column("accessibility", sa.JSON, nullable=True),
        sa.Column("best_practices", sa.JSON, nullable=True),
        sa.Column("ai_function", sa.JSON, nullable=True),
        sa.Column("ui_ux", sa.JSON, nullable=True),
        sa.Column("content", sa.JSON, nullable=True),
        sa.Column("raw_result", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_web_eval_created", "web_eval_results", ["created_at"])

    # ── knowledge_bases ──
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dify_dataset_id", sa.String(128), unique=True, nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("document_count", sa.Integer, server_default="0"),
        sa.Column("last_synced_at", sa.DateTime, nullable=True),
        sa.Column("sync_status", sa.String(16), server_default="not_synced"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # ── kb_documents ──
    op.create_table(
        "kb_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("knowledge_base_id", sa.String(36), sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dify_document_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("status", sa.String(16), server_default="available"),
        sa.Column("chunk_count", sa.Integer, server_default="0"),
        sa.Column("tokens", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_kb_docs_base", "kb_documents", ["knowledge_base_id"])


def downgrade() -> None:
    op.drop_table("kb_documents")
    op.drop_table("knowledge_bases")
    op.drop_table("web_eval_results")
    op.drop_table("reports")
    op.drop_table("eval_scores")
    op.drop_table("conversation_turns")
    op.drop_table("test_scenarios")
    op.drop_table("test_sessions")
    op.drop_table("qa_pairs")
