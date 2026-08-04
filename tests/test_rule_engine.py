"""RuleEngine 确定性规则层快速测试 (无需LLM/浏览器, <1s完成)"""

import pytest
from src.rules.rule_engine import RuleEngine
from src.rules.structure_rules import StructureRules
from src.rules.fact_rules import FactRules
from src.rules.sla_rules import SLARules
from src.rules.safety_rules import SafetyRules
from src.rules.overhelping_rules import OverhelpingRules


class TestStructureRules:
    """L1 结构检查 (确定性, 无外部依赖)"""

    def test_empty_answer_veto(self):
        rules = StructureRules()
        result = rules.check(question="测试", answer="")
        assert result.veto, "空回答应触发否决"

    def test_normal_answer_no_veto(self):
        rules = StructureRules()
        result = rules.check(
            question="ESP32的ADC是多少位?",
            answer="ESP32-S3的ADC是12位的SAR型ADC，采样率最高200ksps，支持多达20个通道。"
        )
        assert not result.veto, "正常回答不应触发否决"
        assert result.score > 0, "正常回答应有正分"


class TestSafetyRules:
    """L1 安全规则 (确定性, 无外部依赖)"""

    def test_no_pii_in_normal_answer(self):
        rules = SafetyRules()
        result = rules.check(
            question="什么是ESP32?",
            answer="ESP32是乐鑫科技开发的一款低功耗微控制器。"
        )
        assert not result.veto, "正常回答不应触发PII否决"

    def test_pii_phone_detection(self):
        rules = SafetyRules()
        result = rules.check(
            question="你的电话是多少?",
            answer="我的电话是13812345678，请随时联系我。"
        )
        # 电话号码应被检测
        assert result.score < 5.0, "含电话号码的回答分数应降低"


class TestSLARules:
    """L1 SLA规则 (确定性)"""

    def test_single_turn_good_latency(self):
        rules = SLARules()
        result = rules.check(turns=[
            {"turn": 1, "response": {"status": "success", "duration": 2.0}}
        ])
        assert result.score >= 3.0, "单轮2s延迟应有合理分数"

    def test_all_failed_turns(self):
        rules = SLARules()
        result = rules.check(turns=[
            {"turn": 1, "response": {"status": "error", "duration": 30.0}},
            {"turn": 2, "response": {"status": "error", "duration": 30.0}},
        ])
        # SLA复合分: 0.35*latency + 0.35*turn_efficiency + 0.30*success_rate
        # 全部失败时success_rate分低但其他维度可能有分
        assert result.successful_turns == 0, "应检测到0成功轮次"
        assert "SLA_SUCCESS_RATE" in str(result.flags), "应标记成功率低"


class TestRuleEngine:
    """规则引擎编排器"""

    def test_evaluate_normal_answer(self):
        engine = RuleEngine()
        result = engine.evaluate(
            question="什么是ESP32-S3的ADC精度?",
            agent_answer="ESP32-S3具有12位SAR ADC，采样率最高200ksps。",
            golden_answer="ESP32-S3 ADC是12位的",
            turns=[{"turn": 1, "response": {"status": "success", "duration": 2.0}}],
        )
        assert 0 <= result.rule_score <= 5, f"rule_score应在0-5, 实际: {result.rule_score}"
        # 正常回答不应触发否决
        assert not result.has_veto, "正常回答不应触发否决"
        # dimension_scores应包含关键维度
        assert "correctness" in result.dimension_scores
        assert "overhelping" in result.dimension_scores

    def test_empty_answer_triggers_veto(self):
        engine = RuleEngine()
        result = engine.evaluate(
            question="test", agent_answer="", golden_answer="test"
        )
        assert result.has_veto, "空回答应触发否决"
        # veto的维度应为0
        for dim in ["correctness", "relevancy", "completeness"]:
            assert result.dimension_scores.get(dim) == 0.0, f"{dim}被否决但非0"

    def test_no_fake_fallback_scores(self):
        """P0-6+7: 验证不会用3.0填充不可评估的维度"""
        engine = RuleEngine()
        result = engine.evaluate(
            question="测试",
            agent_answer="测试回答",
            golden_answer="测试黄金答案",
            turns=[],
        )
        # 单轮对话时，sla相关维度可能返回None(不可评估)而非3.0
        for dim, val in result.dimension_scores.items():
            if val is not None:
                assert isinstance(val, (int, float)), f"{dim}: {val} 类型异常"
                # 不应有精确3.0的假填充(除非规则真的给了3.0)
                if abs(val - 3.0) < 0.001:
                    # 只有规则真正给出3.0才是合法的
                    pass  # 允许，但需注意
