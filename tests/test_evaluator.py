"""
Evaluator 评分逻辑测试（无浏览器）

测试10维度评分系统的正确性。
"""

import pytest


@pytest.mark.llm
class TestEvaluatorScoring:
    """Evaluator 评分测试"""

    def test_evaluate_basic_question(self, evaluator):
        """基本问题评分"""
        result = evaluator.evaluate(
            question="什么是机器学习",
            agent_answer="机器学习是人工智能的一个分支，通过数据和算法让计算机从经验中学习",
            golden_answer="机器学习是利用数据训练模型，使计算机在没有显式编程的情况下进行预测或决策的技术",
        )
        assert "overall" in result, "评分结果应包含 overall"
        assert 0 <= result["overall"] <= 5, f"overall 应在 0-5，实际: {result['overall']}"
        assert "correctness" in result
        assert "relevancy" in result
        assert "completeness" in result

    def test_evaluate_perfect_answer(self, evaluator):
        """完美答案应得高分"""
        golden = "ESP32-S3 是一款由乐鑫科技开发的低功耗AIoT芯片，集成2.4GHz Wi-Fi和Bluetooth 5.0"
        result = evaluator.evaluate(
            question="ESP32-S3是什么",
            agent_answer=golden,
            golden_answer=golden,
        )
        assert result["overall"] >= 3.0, f"完全匹配的答案应 ≥ 3.0，实际: {result['overall']}"

    def test_evaluate_irrelevant_answer(self, evaluator):
        """不相关答案应得低分"""
        result = evaluator.evaluate(
            question="什么是CNN卷积神经网络",
            agent_answer="今天天气很好，适合出去玩",
            golden_answer="CNN是一种包含卷积层的前馈神经网络，用于图像处理",
        )
        assert result["relevancy"] <= 3.0, f"不相关答案 relevancy 应 ≤ 3.0，实际: {result['relevancy']}"

    def test_evaluate_empty_answer(self, evaluator):
        """空答案应得最低分"""
        result = evaluator.evaluate(
            question="什么是深度学习",
            agent_answer="",
            golden_answer="深度学习是机器学习的分支",
        )
        assert result["overall"] <= 2.0, f"空答案 overall 应 ≤ 2.0，实际: {result['overall']}"

    def test_batch_evaluate(self, evaluator):
        """批量评分应返回一致结构"""
        questions = [
            {"question": "什么是AI", "answer": "AI是人工智能", "golden": "人工智能是计算机科学的分支"},
            {"question": "Python是什么", "answer": "一种编程语言", "golden": "Python是一种高级编程语言"},
        ]
        for q in questions:
            result = evaluator.evaluate(
                question=q["question"],
                agent_answer=q["answer"],
                golden_answer=q["golden"],
            )
            assert "overall" in result
            for dim in ["correctness", "relevancy", "completeness"]:
                assert dim in result, f"应包含 {dim} 维度"


@pytest.mark.llm
class TestEvaluatorBoundary:
    """评分中的边界检测"""

    def test_in_scope_answer_boundary_score(self, evaluator):
        """在课程范围内的答案"""
        result = evaluator.evaluate(
            question="ESP32的ADC精度是多少",
            agent_answer="ESP32-S3具有12位SAR ADC，支持最多20个通道",
            golden_answer="ESP32的ADC是12位",
            boundary_result={"in_scope": True, "status": "in_scope"},
        )
        # boundary_compliance 应存在且为合理值
        assert "boundary_compliance" in result or "boundary_status" in result

    def test_out_of_scope_answer_boundary_score(self, evaluator):
        """超出范围的答案（边界检测）"""
        result = evaluator.evaluate(
            question="如何做红烧肉",
            agent_answer="红烧肉的做法是...（详细烹饪步骤）",
            golden_answer="",
            boundary_result={"in_scope": False, "status": "out_of_scope"},
        )
        assert "boundary_compliance" in result or "boundary_status" in result


@pytest.mark.llm
class TestEvaluatorEdgeCases:
    """评分边界情况"""

    def test_very_long_answer(self, evaluator):
        """超长答案不应出错"""
        long_answer = "这是一个测试答案。" * 100  # ~1000 字符
        result = evaluator.evaluate(
            question="请解释什么是嵌入式系统",
            agent_answer=long_answer,
            golden_answer="嵌入式系统是专用计算机系统",
        )
        assert "overall" in result

    def test_special_characters(self, evaluator):
        """特殊字符不应导致评分崩溃"""
        result = evaluator.evaluate(
            question="Python中lambda函数的使用 ## C++",
            agent_answer="<div>lambda x: x*2</div>\n```python\nprint('hello')\n```",
            golden_answer="lambda是匿名函数",
        )
        assert "overall" in result
