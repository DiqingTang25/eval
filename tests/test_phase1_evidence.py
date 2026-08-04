"""
Phase 1 证据链地基 — 本地集成测试 (纯 MySQL 方案)

验证:
  1. EvidenceHasher: SHA-256 计算 + store_evidence + verify
  2. EvidenceQueue: 入队/降级同步处理
  3. DBRecorder: 证据哈希写入 eval_scores + evidence_trail
  4. Migration 0005: 字段重命名 + data_json 新增
  5. 模型完整性: EvidenceTrail 新字段

运行:
    cd /home/jennifer07/agent_eval
    python -m pytest tests/test_phase1_evidence.py -v
"""

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def setup_path():
    root = Path(__file__).parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.environ.setdefault("DB_TYPE", "sqlite")
    os.environ.setdefault("OPENAI_API_KEY", "sk-test")
    yield


# ═══════════════════════════════════════════════════
# Test 1: EvidenceHasher — 核心哈希 + MySQL 存储
# ═══════════════════════════════════════════════════

class TestEvidenceHasher:
    """证据哈希器: 离线功能验证"""

    def test_sha256_deterministic(self):
        from src.evidence_hasher import EvidenceHasher
        h = EvidenceHasher()
        h1 = h.sha256_hex("hello evidence chain")
        h2 = h.sha256_hex("hello evidence chain")
        h3 = h.sha256_hex("hello evidence chain!")
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 64

    def test_hash_conversation_deterministic(self):
        from src.evidence_hasher import EvidenceHasher
        h = EvidenceHasher()
        conv = {"full_conversation": "Q: PWM?\nA: 脉宽调制"}
        score = {"correctness": 4.5, "overall": 4.0}
        fp1 = h.hash_conversation(conv, score)
        fp2 = h.hash_conversation(conv, score)
        assert fp1 == fp2
        # 篡改检测
        score2 = dict(score, overall=5.0)
        fp3 = h.hash_conversation(conv, score2)
        assert fp3 != fp1, "篡改后指纹必须不同"

    def test_hash_artifact(self):
        from src.evidence_hasher import EvidenceHasher
        h = EvidenceHasher()
        a1 = h.hash_artifact([{"turn": 1, "q": "hi"}])
        a2 = h.hash_artifact([{"turn": 1, "q": "hi"}])
        a3 = h.hash_artifact([{"turn": 2, "q": "hi"}])
        assert a1 == a2
        assert a1 != a3

    def test_store_and_verify_evidence(self, tmp_path):
        """完整写入 → 验证 流程"""
        import os as _os
        _os.environ["DB_TYPE"] = "sqlite"
        db_path = tmp_path / "test_store.db"
        _os.environ["SQLITE_PATH"] = str(db_path)

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from backend.models.base import Base
        from backend.models import EvalScore, TestSession, TestScenario
        from src.evidence_hasher import EvidenceHasher

        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        db = sessionmaker(engine)()

        # 创建测试数据
        import uuid
        sid = str(uuid.uuid4())
        db.add(TestSession(id=sid, session_id="evid-001", agent_id="test",
                           profile="standard", status="success"))
        db.flush()
        sc_id = str(uuid.uuid4())
        db.add(TestScenario(id=sc_id, session_id=sid, scenario_index=1,
                            status="success", full_conversation="Q:test\nA:ok"))
        db.flush()
        score_id = str(uuid.uuid4())
        db.add(EvalScore(id=score_id, scenario_id=sc_id, overall=4.0))
        db.commit()

        # 写入证据
        hasher = EvidenceHasher()
        fp = hasher.store_evidence(
            db, "evid-001", score_id, 1,
            conversation_json={"full_conversation": "Q:test\nA:ok"},
            score_json={"overall": 4.0, "correctness": 4.5},
        )
        db.commit()

        # 验证 eval_scores 被更新
        score_row = db.query(EvalScore).filter(EvalScore.id == score_id).first()
        assert score_row.evidence_hash == fp
        assert "conversations/" in score_row.evidence_path

        # 验证 evidence_trail 有3条记录
        from backend.models.evidence_trail import EvidenceTrail
        trails = db.query(EvidenceTrail).filter(
            EvidenceTrail.eval_score_id == score_id
        ).all()
        assert len(trails) == 3
        types = {t.artifact_type for t in trails}
        assert types == {"conversation", "scoring", "hash_list"}

        # 审计验证: 所有文件通过
        result = hasher.verify(db, score_id)
        assert result["match"] is True
        assert result["artifacts_checked"] == 3
        assert result["artifacts_ok"] == 3
        assert result["tampered"] == []

        db.close()
        engine.dispose()

    def test_verify_detects_tampering(self, tmp_path):
        """审计验证: 篡改检测"""
        import os as _os
        _os.environ["DB_TYPE"] = "sqlite"
        db_path = tmp_path / "test_tamper.db"
        _os.environ["SQLITE_PATH"] = str(db_path)

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from backend.models.base import Base
        from backend.models import EvalScore, TestSession, TestScenario
        from backend.models.evidence_trail import EvidenceTrail
        from src.evidence_hasher import EvidenceHasher

        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        db = sessionmaker(engine)()

        import uuid
        sid = str(uuid.uuid4())
        db.add(TestSession(id=sid, session_id="tamper-001", agent_id="test",
                           profile="standard", status="success"))
        db.flush()
        sc_id = str(uuid.uuid4())
        db.add(TestScenario(id=sc_id, session_id=sid, scenario_index=1,
                            status="success"))
        db.flush()
        score_id = str(uuid.uuid4())
        db.add(EvalScore(id=score_id, scenario_id=sc_id, overall=4.0))
        db.commit()

        hasher = EvidenceHasher()
        hasher.store_evidence(db, "tamper-001", score_id, 1,
                              {"full_conversation": "original"},
                              {"overall": 4.0})
        db.commit()

        # 篡改: 修改 evidence_trail 的 data_json
        trail = db.query(EvidenceTrail).filter(
            EvidenceTrail.eval_score_id == score_id,
            EvidenceTrail.artifact_type == "conversation"
        ).first()
        trail.data_json = '{"full_conversation": "TAMPERED!"}'
        db.commit()

        # 验证应该检测到篡改
        result = hasher.verify(db, score_id)
        assert result["match"] is False
        assert len(result["tampered"]) >= 1

        db.close()
        engine.dispose()


# ═══════════════════════════════════════════════════
# Test 2: EvidenceQueue — 降级同步模式
# ═══════════════════════════════════════════════════

class TestEvidenceQueue:
    def test_queue_offline(self):
        from src.async_queue import EvidenceQueue
        q = EvidenceQueue(redis_url="redis://localhost:99999/0")
        assert not q.available

    def test_enqueue_sync_fallback(self):
        from src.async_queue import EvidenceQueue
        q = EvidenceQueue(redis_url="redis://localhost:99999/0")
        # 无 Redis → 降级同步处理, 不抛异常
        msg_id = q.enqueue(
            session_id="test-sess-001",
            scenario_index=1,
            eval_score_id="test-score-001",
            conversation_json={"turns": [{"q": "hi", "a": "hello"}]},
            score_json={"correctness": 4.5, "overall": 4.2},
        )
        assert msg_id is None  # Redis 不可用返回 None


# ═══════════════════════════════════════════════════
# Test 3: DB Models — 模型完整性
# ═══════════════════════════════════════════════════

class TestModels:
    def test_evidence_trail_no_tos_fields(self):
        from backend.models.evidence_trail import EvidenceTrail
        assert hasattr(EvidenceTrail, "data_json"), "缺 data_json"
        assert hasattr(EvidenceTrail, "artifact_path"), "缺 artifact_path"
        assert not hasattr(EvidenceTrail, "tos_key"), "tos_key 应已删除"
        assert not hasattr(EvidenceTrail, "tos_bucket"), "tos_bucket 应已删除"
        assert not hasattr(EvidenceTrail, "tos_url"), "tos_url 应已删除"

    def test_eval_score_no_tos_fields(self):
        from backend.models.eval_score import EvalScore
        assert hasattr(EvalScore, "evidence_hash")
        assert hasattr(EvalScore, "evidence_path")
        assert not hasattr(EvalScore, "evidence_tos_key"), "evidence_tos_key 应已删除"
        assert not hasattr(EvalScore, "evidence_tos_url"), "evidence_tos_url 应已删除"

    def test_new_indexes_present(self):
        from backend.models.test_session import TestSession, TestScenario, ConversationTurn
        assert TestSession.__table__.columns["agent_id"].index
        assert TestSession.__table__.columns["profile"].index
        assert TestScenario.__table__.columns["qa_pair_id"].index
        assert ConversationTurn.__table__.columns["turn_index"].index


# ═══════════════════════════════════════════════════
# Test 4: Migration 0005
# ═══════════════════════════════════════════════════

class TestMigration0005:
    def test_migration_file_has_keywords(self):
        path = Path(__file__).parent.parent / "backend/alembic/versions/0005_mysql_evidence_store.py"
        assert path.exists()
        content = path.read_text()
        assert "def upgrade()" in content
        assert "def downgrade()" in content
        assert "evidence_path" in content
        assert "data_json" in content
        assert "artifact_path" in content


# ═══════════════════════════════════════════════════
# Test 5: 端到端证据链
# ═══════════════════════════════════════════════════

class TestEvidenceE2E:
    def test_full_evidence_chain_integrity(self):
        """对话→评分→SHA-256→写入→审计校验"""
        from src.evidence_hasher import EvidenceHasher
        h = EvidenceHasher()

        conv = {"turns": [
            {"turn": 1, "question": "LED?", "answer": "发光二极管"},
            {"turn": 2, "question": "PWM?", "answer": "脉宽调制"},
        ]}
        scores = {"correctness": 4.0, "relevancy": 4.5, "overall": 4.2}

        # 计算指纹
        fp = h.hash_conversation(conv, scores)

        # 验证确定性
        assert h.hash_conversation(conv, scores) == fp

        # 篡改检测
        scores_tampered = dict(scores, overall=5.0)
        assert h.hash_conversation(conv, scores_tampered) != fp

        # 文件级哈希一致性
        a1 = h.hash_artifact(conv)
        a2 = h.hash_artifact(conv)
        assert a1 == a2
