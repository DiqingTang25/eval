"""Phase 1: Evidence chain — TOS fingerprints + evidence_trail table + index fixes

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-22

Changes:
  1. eval_scores: +evidence_hash, +evidence_tos_key, +evidence_tos_url,
                   +merkle_root, +chain_tx_hash
  2. NEW: evidence_trail — per-file evidence tracking
  3. test_sessions: +idx on (agent_id), (profile), (session_id)
  4. test_scenarios: +idx on (qa_pair_id)
  5. conversation_turns: +idx on (turn_index)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. eval_scores: 证据链字段 ──
    op.add_column("eval_scores",
        sa.Column("evidence_hash", sa.String(64), server_default="",
                  comment="SHA-256 of full conversation + score JSON"))
    op.add_column("eval_scores",
        sa.Column("evidence_tos_key", sa.String(512), server_default="",
                  comment="TOS object key"))
    op.add_column("eval_scores",
        sa.Column("evidence_tos_url", sa.String(2048), server_default="",
                  comment="TOS presigned URL with expiry"))
    op.add_column("eval_scores",
        sa.Column("merkle_root", sa.String(64), server_default="",
                  comment="Merkle tree root of all evidence in session"))
    op.add_column("eval_scores",
        sa.Column("chain_tx_hash", sa.String(128), server_default="",
                  comment="Blockchain transaction hash (Phase 4)"))
    op.create_index("idx_evidence_hash", "eval_scores", ["evidence_hash"])

    # ── 2. NEW: evidence_trail ──
    op.create_table(
        "evidence_trail",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("eval_score_id", sa.String(36),
                  sa.ForeignKey("eval_scores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", sa.String(32), nullable=False,
                  comment="conversation | screenshot | recording | report | hash_list"),
        sa.Column("tos_key", sa.String(512), nullable=False),
        sa.Column("tos_bucket", sa.String(128), server_default="agent-eval-evidence"),
        sa.Column("tos_etag", sa.String(64), server_default=""),
        sa.Column("tos_url", sa.String(2048), server_default=""),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("file_size", sa.BigInteger, server_default="0"),
        sa.Column("content_type", sa.String(64), server_default="application/json"),
        sa.Column("storage_tier", sa.String(16), server_default="hot",
                  comment="hot | warm | cold"),
        sa.Column("worm_locked", sa.Boolean, server_default=sa.text("FALSE")),
        sa.Column("metadata_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_evidence_session", "evidence_trail", ["session_id"])
    op.create_index("idx_evidence_score", "evidence_trail", ["eval_score_id"])
    op.create_index("idx_evidence_sha256", "evidence_trail", ["sha256"])
    op.create_index("idx_evidence_session_artifact", "evidence_trail",
                    ["session_id", "artifact_type"])
    op.create_index("idx_evidence_storage_tier", "evidence_trail", ["storage_tier"])

    # ── 3. Index fixes ──
    # test_sessions: agent_id, profile, session_id
    op.create_index("idx_sessions_agent", "test_sessions", ["agent_id"])
    op.create_index("idx_sessions_profile", "test_sessions", ["profile"])
    # session_id already has UNIQUE → implicit index, but explicit for clarity
    # (skip: UNIQUE constraint already creates an index)

    # test_scenarios: qa_pair_id
    op.create_index("idx_scenarios_qa_pair", "test_scenarios", ["qa_pair_id"])

    # conversation_turns: turn_index
    op.create_index("idx_turns_turn_index", "conversation_turns", ["turn_index"])


def downgrade() -> None:
    # conversation_turns
    op.drop_index("idx_turns_turn_index", "conversation_turns")

    # test_scenarios
    op.drop_index("idx_scenarios_qa_pair", "test_scenarios")

    # test_sessions
    op.drop_index("idx_sessions_profile", "test_sessions")
    op.drop_index("idx_sessions_agent", "test_sessions")

    # evidence_trail
    op.drop_index("idx_evidence_storage_tier", "evidence_trail")
    op.drop_index("idx_evidence_session_artifact", "evidence_trail")
    op.drop_index("idx_evidence_sha256", "evidence_trail")
    op.drop_index("idx_evidence_score", "evidence_trail")
    op.drop_index("idx_evidence_session", "evidence_trail")
    op.drop_table("evidence_trail")

    # eval_scores
    op.drop_index("idx_evidence_hash", "eval_scores")
    op.drop_column("eval_scores", "chain_tx_hash")
    op.drop_column("eval_scores", "merkle_root")
    op.drop_column("eval_scores", "evidence_tos_url")
    op.drop_column("eval_scores", "evidence_tos_key")
    op.drop_column("eval_scores", "evidence_hash")
