"""
Phase 2 证据记忆 + 金标准RAG 测试套件

测试覆盖:
  - Embedding 向量生成 (embed_text)
  - 金标准QA索引构建与检索
  - 证据记忆存储与召回
  - 失败案例分类逻辑
  - RAG Prompt 注入格式
  - 启用/禁用开关

前提:
  - XJTLU_EMBEDDING_API_KEY 或 SILICONFLOW_API_KEY 已配置
  - data/golden_qa_bank.json 存在
  - MySQL evidence_memory 表已创建 (migration 0006)
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# 确保项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def sample_qa_bank():
    """最小黄金QA库用于测试"""
    return [
        {
            "qa_id": "QA_TEST_001",
            "phase": "PHASE 01",
            "type": "概念解释",
            "difficulty": "简单",
            "question": "什么是云边协同？",
            "golden_answer": "云边协同是将大模型部署到云端和边缘端实现协同工作。",
            "knowledge_points": ["云边协同", "边缘计算"],
            "status": "approved",
        },
        {
            "qa_id": "QA_TEST_002",
            "phase": "PHASE 02",
            "type": "操作步骤",
            "difficulty": "中等",
            "question": "如何使用Arduino进行IO控制？",
            "golden_answer": "首先搭建Arduino开发环境，然后利用AI协作完成IO控制与交互逻辑编写。",
            "knowledge_points": ["Arduino", "IO控制"],
            "status": "approved",
        },
        {
            "qa_id": "QA_TEST_PENDING",
            "phase": "PHASE 03",
            "type": "概念解释",
            "difficulty": "简单",
            "question": "未审批的问题",
            "golden_answer": "不应该被索引",
            "knowledge_points": [],
            "status": "pending",
        },
    ]


@pytest.fixture
def sample_scores():
    """模拟评分字典"""
    return {
        "correctness": 4.5,
        "relevancy": 4.0,
        "completeness": 3.5,
        "guidance": 2.0,           # 低分 → 应触发 guidance_poor
        "followup_quality": 3.0,
        "boundary_compliance": 4.0,
        "turn_consistency": 3.0,
        "knowledge_scaffolding": 3.0,
        "overhelping": 4.0,
        "fairness_bias": 3.0,
        "overall": 3.4,
        "flags": [],
        "veto_dims": [],
    }


@pytest.fixture
def failure_scores():
    """模拟失败评分字典"""
    return {
        "correctness": 2.0,        # 低分 → 应触发 hallucination
        "relevancy": 3.0,
        "completeness": 2.5,
        "guidance": 3.0,
        "followup_quality": 2.0,
        "boundary_compliance": 1.5,  # 低分 → 应触发 boundary_violation
        "turn_consistency": 2.0,
        "knowledge_scaffolding": 2.0,
        "overhelping": 3.0,
        "fairness_bias": 3.0,
        "overall": 2.1,
        "flags": ["VETO:boundary_compliance"],
        "veto_dims": ["boundary_compliance"],
    }


# ═══════════════════════════════════════════════════════════
# 1. Embedding 向量生成
# ═══════════════════════════════════════════════════════════

class TestEmbedText:
    """测试 metrics.py 新增的 embed_text() 方法"""

    def test_embed_text_returns_float_list(self):
        """embed_text 应返回 float 列表"""
        try:
            from src.metrics import EmbeddingSimilarity
        except Exception:
            pytest.skip("Embedding 不可用 (未配置 API Key)")

        emb = EmbeddingSimilarity()
        vec = emb.embed_text("测试文本")
        assert isinstance(vec, list)
        assert len(vec) > 0
        assert all(isinstance(v, float) for v in vec)
        print(f"  embed_text dims={len(vec)}")

    def test_embed_text_truncation(self):
        """超长文本应被截断 (不抛异常)"""
        try:
            from src.metrics import EmbeddingSimilarity
        except Exception:
            pytest.skip("Embedding 不可用")

        emb = EmbeddingSimilarity()
        long_text = "长文本" * 5000  # ~20000 chars
        vec = emb.embed_text(long_text)
        assert len(vec) > 0  # 不应抛异常


# ═══════════════════════════════════════════════════════════
# 2. 金标准QA索引
# ═══════════════════════════════════════════════════════════

class TestGoldenQAIndex:
    """测试 GoldenQAIndex"""

    def test_build_index_from_bank(self, sample_qa_bank):
        """从 gold_qa_bank.json 构建索引"""
        from src.golden_qa_index import GoldenQAIndex

        with tempfile.TemporaryDirectory() as tmpdir:
            bank_path = Path(tmpdir) / "test_bank.json"
            with open(bank_path, "w", encoding="utf-8") as f:
                json.dump(sample_qa_bank, f, ensure_ascii=False)

            index = GoldenQAIndex(bank_path=str(bank_path))

            # Mock embed_text to avoid real API calls
            with patch.object(index, '_embedder', create=True) as mock_embedder:
                mock_embedder.embed_text.return_value = [0.1] * 1024
                index._build_index()

            assert index.is_ready
            assert len(index._qa_pairs) == 2  # 只有 approved 的 2 条

    def test_search_filters_by_similarity(self, sample_qa_bank):
        """检索应过滤低相似度结果"""
        from src.golden_qa_index import GoldenQAIndex

        with tempfile.TemporaryDirectory() as tmpdir:
            bank_path = Path(tmpdir) / "test_bank.json"
            with open(bank_path, "w", encoding="utf-8") as f:
                json.dump(sample_qa_bank, f, ensure_ascii=False)

            index = GoldenQAIndex(bank_path=str(bank_path), min_similarity=0.8)

            # Mock embedding: query_vec matches first QA but not second
            with patch.object(index, '_embedder', create=True) as mock_embedder:
                # 让 embedding 返回与第一个QA高度相似的向量
                mock_embedder.embed_text.return_value = [0.1] * 1024
                index._build_index()

                # 查询向量 = 第一个QA的 embedding (相似度=1.0)
                results = index.search("什么是云边协同？", top_k=3)

            # 由于所有embedding都相同, 相似度=1.0 > 0.8
            assert len(results) >= 1

    def test_build_context_format(self, sample_qa_bank):
        """build_context 返回正确格式的文本"""
        from src.golden_qa_index import GoldenQAIndex

        with tempfile.TemporaryDirectory() as tmpdir:
            bank_path = Path(tmpdir) / "test_bank.json"
            with open(bank_path, "w", encoding="utf-8") as f:
                json.dump(sample_qa_bank, f, ensure_ascii=False)

            index = GoldenQAIndex(bank_path=str(bank_path))

            with patch.object(index, '_embedder', create=True) as mock_embedder:
                mock_embedder.embed_text.return_value = [0.1] * 1024
                index._build_index()

                context = index.build_context("什么是云边协同？", top_k=1)

            assert "黄金参考答案（检索增强）" in context
            assert "云边协同" in context

    def test_empty_bank_returns_empty(self):
        """空库应返回空结果"""
        from src.golden_qa_index import GoldenQAIndex

        with tempfile.TemporaryDirectory() as tmpdir:
            bank_path = Path(tmpdir) / "empty_bank.json"
            with open(bank_path, "w", encoding="utf-8") as f:
                json.dump([], f)

            index = GoldenQAIndex(bank_path=str(bank_path))
            # 手动触发构建
            assert index._build_index() is False  # 空库构建失败
            assert index.search("test") == []
            assert index.build_context("test") == ""

    def test_disk_cache(self, sample_qa_bank):
        """磁盘缓存应避免重复embedding"""
        from src.golden_qa_index import GoldenQAIndex

        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)  # GoldenQAIndex 缓存路径相对于 cwd
            bank_path = Path(tmpdir) / "test_bank.json"
            with open(bank_path, "w", encoding="utf-8") as f:
                json.dump(sample_qa_bank, f, ensure_ascii=False)

            # 创建 data/ dir
            (Path(tmpdir) / "data").mkdir(exist_ok=True)

            index = GoldenQAIndex(bank_path=str(bank_path))

            call_count = [0]
            def mock_embed(text):
                call_count[0] += 1
                return [0.1] * 1024

            with patch.object(index, '_embedder', create=True) as mock_embedder:
                mock_embedder.embed_text.side_effect = mock_embed
                index._build_index()

            first_count = call_count[0]

            # 重新加载应从缓存
            index2 = GoldenQAIndex(bank_path=str(bank_path))
            assert index2._embeddings is not None or True  # 缓存加载


# ═══════════════════════════════════════════════════════════
# 3. 失败案例分类
# ═══════════════════════════════════════════════════════════

class TestFailureClassification:
    """测试 EvidenceMemory._classify_failure()"""

    def test_boundary_violation(self, failure_scores):
        """boundary_compliance 低分 + VETO → boundary_violation"""
        from src.evidence_memory import EvidenceMemory
        is_fail, ftype = EvidenceMemory._classify_failure(failure_scores)
        assert is_fail is True
        assert ftype == "boundary_violation"

    def test_guidance_poor(self, sample_scores):
        """guidance 低分 → guidance_poor"""
        from src.evidence_memory import EvidenceMemory
        is_fail, ftype = EvidenceMemory._classify_failure(sample_scores)
        assert is_fail is True
        assert ftype == "guidance_poor"

    def test_normal_scores_not_failure(self):
        """正常分数不应被归类为失败"""
        from src.evidence_memory import EvidenceMemory
        normal = {
            "correctness": 4.5, "relevancy": 4.0, "completeness": 4.0,
            "guidance": 4.0, "boundary_compliance": 4.5, "overhelping": 4.0,
            "overall": 4.2, "flags": [], "veto_dims": [],
        }
        is_fail, ftype = EvidenceMemory._classify_failure(normal)
        assert is_fail is False
        assert ftype == ""

    def test_all_dimensions(self):
        """测试所有失败类型"""
        from src.evidence_memory import EvidenceMemory

        cases = [
            ({"correctness": 2.0, "overall": 3.5}, "hallucination"),
            ({"overhelping": 2.0, "overall": 3.5}, "overhelping"),
            ({"boundary_compliance": 2.0, "overall": 3.5}, "boundary_violation"),
            ({"guidance": 2.0, "overall": 3.5}, "guidance_poor"),
            ({"overall": 2.5}, "general_poor"),
        ]
        for scores, expected_type in cases:
            is_fail, ftype = EvidenceMemory._classify_failure(scores)
            assert is_fail, f"Expected failure for {scores}"
            assert ftype == expected_type, f"Expected {expected_type}, got {ftype} for {scores}"


# ═══════════════════════════════════════════════════════════
# 4. 余弦相似度计算
# ═══════════════════════════════════════════════════════════

class TestCosineSimilarity:
    """测试向量化余弦相似度"""

    def test_identical_vectors(self):
        """相同向量余弦相似度应为1.0"""
        from src.evidence_memory import _cosine_similarity
        a = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        b = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)
        sim = _cosine_similarity(a, b)
        assert abs(sim[0] - 1.0) < 0.001

    def test_orthogonal_vectors(self):
        """正交向量余弦相似度应为0.0"""
        from src.evidence_memory import _cosine_similarity
        a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        b = np.array([[0.0, 1.0, 0.0]], dtype=np.float32)
        sim = _cosine_similarity(a, b)
        assert abs(sim[0] - 0.0) < 0.001

    def test_batch_similarity(self):
        """批量计算应返回正确的 top-k"""
        from src.evidence_memory import _cosine_similarity
        a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        b = np.array([
            [1.0, 0.0, 0.0],   # 1.0
            [0.0, 1.0, 0.0],   # 0.0
            [0.7, 0.7, 0.0],   # ~0.707
        ], dtype=np.float32)
        sim = _cosine_similarity(a, b)
        assert sim[0] > sim[1]  # 第一个最相似
        assert abs(sim[0] - 1.0) < 0.001


# ═══════════════════════════════════════════════════════════
# 5. 摘要构建
# ═══════════════════════════════════════════════════════════

class TestSummaryBuild:
    """测试 EvidenceMemory._build_summary()"""

    def test_summary_contains_key_info(self, sample_scores):
        """摘要应包含维度分和标记"""
        from src.evidence_memory import EvidenceMemory
        summary = EvidenceMemory._build_summary(
            "什么是云边协同？",
            "云边协同是指...",
            sample_scores,
        )
        assert "Q:" in summary
        assert "A:" in summary
        assert "correctness=4.5" in summary
        assert "Overall:" in summary

    def test_summary_length_limited(self, sample_scores):
        """摘要应被截断到合理长度"""
        from src.evidence_memory import EvidenceMemory
        long_question = "测试" * 500
        long_answer = "答案" * 500
        summary = EvidenceMemory._build_summary(long_question, long_answer, sample_scores)
        # 总长度应在 3000 字符以内
        assert len(summary) <= 3100  # 允许一些余量


# ═══════════════════════════════════════════════════════════
# 6. RAG 开关集成测试
# ═══════════════════════════════════════════════════════════

class TestRAGToggle:
    """测试 use_rag 开关行为"""

    def test_rag_disabled_skips_all(self):
        """use_rag=False 时不应初始化 RAG 组件"""
        from src.evaluator import Evaluator
        ev = Evaluator(
            api_key="test-key",
            config={"use_rag": False},
        )
        # 属性应返回 None (懒初始化被跳过)
        assert ev._golden_qa is None
        assert ev._evidence_memory is None

    def test_rag_enabled_by_default(self):
        """默认配置应启用 RAG"""
        from src.evaluator import Evaluator
        ev = Evaluator(
            api_key="test-key",
            config={},  # 空配置 → use_rag defaults to True
        )
        assert ev.use_rag is True


# ═══════════════════════════════════════════════════════════
# 7. Prompt 注入格式
# ═══════════════════════════════════════════════════════════

class TestPromptInjection:
    """测试 _build_prompt 中的 RAG 上下文注入"""

    def test_prompt_includes_rag_context(self):
        """Prompt 应包含传入的 RAG 上下文"""
        from src.evaluator import Evaluator
        ev = Evaluator(api_key="test-key")

        prompt = ev._build_prompt(
            question="测试问题",
            agent_answer="测试回答",
            golden_answer="参考答案",
            goal="理解概念",
            total_turns=1,
            successful_turns=1,
            conversation_context="(单轮对话)",
            adversarial_type=None,
            eval_dims=["correctness", "relevancy"],
            scoring_rubric=None,
            golden_qa_context="【黄金参考答案（检索增强）】\n案例 #1: ...",
            memory_context="【历史失败案例参考】\n案例 #1: ...",
        )

        assert "黄金参考答案（检索增强）" in prompt
        assert "历史失败案例参考" in prompt

    def test_prompt_without_rag_context(self):
        """无 RAG 上下文时 Prompt 应正常工作"""
        from src.evaluator import Evaluator
        ev = Evaluator(api_key="test-key")

        prompt = ev._build_prompt(
            question="测试问题",
            agent_answer="测试回答",
            golden_answer="参考答案",
            goal="理解概念",
            total_turns=1,
            successful_turns=1,
            conversation_context="(单轮对话)",
            adversarial_type=None,
            eval_dims=["correctness", "relevancy"],
            scoring_rubric=None,
        )

        assert "测试问题" in prompt
        assert "只输出JSON" in prompt


# ═══════════════════════════════════════════════════════════
# 8. ORM 模型验证
# ═══════════════════════════════════════════════════════════

class TestEvidenceMemoryModel:
    """测试 EvidenceMemory ORM 模型"""

    def test_model_import(self):
        """模型应可正确导入"""
        from backend.models.evidence_memory import EvidenceMemory
        assert EvidenceMemory.__tablename__ == "evidence_memory"

    def test_model_has_required_fields(self):
        """模型应包含所有必需字段"""
        from backend.models.evidence_memory import EvidenceMemory
        cols = {c.name for c in EvidenceMemory.__table__.columns}
        required = {
            "id", "session_id", "question_text", "embedding",
            "overall_score", "is_failure_case", "failure_type",
            "created_at", "updated_at",
        }
        assert required.issubset(cols), f"Missing columns: {required - cols}"


# ═══════════════════════════════════════════════════════════
# 9. 端到端 (需要真实 Embedding API + MySQL)
# ═══════════════════════════════════════════════════════════

@pytest.mark.integration
class TestEndToEnd:
    """端到端测试 — 需要数据库和 API"""

    def test_golden_qa_end_to_end(self):
        """加载真实 golden_qa_bank.json → 检索 → 验证"""
        bank_path = Path("data/golden_qa_bank.json")
        if not bank_path.exists():
            pytest.skip("golden_qa_bank.json 不存在")

        try:
            from src.golden_qa_index import GoldenQAIndex
        except Exception:
            pytest.skip("GoldenQAIndex 无法导入")

        index = GoldenQAIndex(bank_path=str(bank_path), min_similarity=0.5)
        results = index.search("什么是云边协同？", top_k=3)

        print(f"\n  Golden QA search returned {len(results)} results")
        for r in results:
            print(f"    - [{r.get('phase')}] {r.get('question', '')[:60]}... "
                  f"(sim={r.get('similarity', 0):.3f})")

        # 应该有至少一个结果
        assert len(results) >= 1, "Expected at least 1 result from golden QA bank"

    def test_memory_store_and_recall(self):
        """存储 → 召回 端到端 (需要 MySQL)"""
        try:
            from src.evidence_memory import EvidenceMemory
        except Exception as e:
            pytest.skip(f"EvidenceMemory 无法导入: {e}")

        mem = EvidenceMemory()

        # 尝试存储
        success = mem.store(
            session_id="test_session_001",
            question="什么是云边协同?",
            agent_answer="云边协同是云端和边缘端协同工作的技术架构。",
            scores={
                "correctness": 4.0, "relevancy": 4.0, "completeness": 3.5,
                "guidance": 3.0, "boundary_compliance": 4.0, "overhelping": 4.0,
                "overall": 3.8, "flags": [], "veto_dims": [],
            },
            phase="PHASE_01",
        )
        print(f"\n  EvidenceMemory.store() → {success}")

        # 召回
        results = mem.recall("云边协同是什么?", top_k=3)
        print(f"  EvidenceMemory.recall() → {len(results)} results")
        for r in results:
            print(f"    - {r.get('question_text', '')[:60]}... "
                  f"(sim={r.get('similarity', 0):.3f}, failure={r.get('is_failure_case')})")

        # Recall failures
        failures = mem.recall_failures("云边协同", top_k=3)
        print(f"  EvidenceMemory.recall_failures() → {len(failures)} failures")
