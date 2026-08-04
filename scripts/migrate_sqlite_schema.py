#!/usr/bin/env python3
"""P0-fix: 补上 SQLite 数据库缺失的列和表"""
import sqlite3
import sys
import os

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "agent_eval.db"
)
print(f"Target: {DB_PATH}")
conn = sqlite3.connect(DB_PATH)

# ── conversation_turns 缺失列 ──
existing = {r[1] for r in conn.execute('PRAGMA table_info(conversation_turns)')}
needed = {
    'latency_ms': 'FLOAT DEFAULT 0',
    'retry_count': 'INTEGER DEFAULT 0',
    'prompt_tokens': 'INTEGER DEFAULT 0',
    'completion_tokens': 'INTEGER DEFAULT 0',
    'total_tokens': 'INTEGER DEFAULT 0',
    'cost_estimate': 'FLOAT DEFAULT 0.0',
    'model_used': 'VARCHAR(64)',
}

for col, typedef in needed.items():
    if col not in existing:
        conn.execute(f'ALTER TABLE conversation_turns ADD COLUMN {col} {typedef}')
        print(f'  + conversation_turns.{col}')
    else:
        print(f'  = conversation_turns.{col} (already exists)')

# ── evidence_memory 表 ──
conn.execute('''
CREATE TABLE IF NOT EXISTS evidence_memory (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(128),
    eval_score_id VARCHAR(36),
    phase VARCHAR(16),
    question_text TEXT,
    agent_answer TEXT,
    scores_json TEXT,
    embedding BLOB,
    embedding_dim INTEGER DEFAULT 3072,
    overall_score FLOAT,
    is_failure_case BOOLEAN DEFAULT 0,
    failure_type VARCHAR(32),
    stored_in_kb BOOLEAN DEFAULT 0,
    stored_in_redis BOOLEAN DEFAULT 0,
    metadata_json TEXT DEFAULT '{}',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')
print('  + evidence_memory table')

conn.commit()
conn.close()
print('Schema migration complete.')
