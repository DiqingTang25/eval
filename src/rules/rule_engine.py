"""
规则引擎编排器 (Rule Engine Orchestrator)

L1 固定规则层的总入口 — 在所有 LLM Judge 之前执行。

对齐:
  - CLEAR (arXiv:2511.14136): 30% 确定性门控 = Efficacy + Assurance 的预筛选
  - TEACH-AI (NeurIPS 2025): 结构化 checklist → 10维度的确定性基底
  - EduAgentBench (arXiv:2605.14322): 过程约束 + 确定性响应检查

架构:
  Layer 1 (此模块): 规则闸门 ~30%
  Layer 2 (metrics.py): 算法增强 ~10%
  Layer 3 (evaluator.py): LLM 多Judge ~60%

输出:
  - rule_score: 0-5 综合确定性分数
  - dimension_scores: 每个维度的确定性基底
  - skip_dims: 哪些维度不需要 LLM (规则层已可判定)
  - veto_dims: 哪些维度一票否决
  - evidence: 完整的可解释证据链
"""

from dataclasses import dataclass, field
from typing import Optional

from .structure_rules import StructureRules, StructureCheckResult
from .fact_rules import FactRules, FactCheckResult
from .sla_rules import SLARules, SLAResult
from .safety_rules import SafetyRules, SafetyCheckResult
from .overhelping_rules import OverhelpingRules, OverhelpingCheckResult  # v3.4


@dataclass
class RuleEngineResult:
    """规则引擎综合结果"""
    # ── 综合 ──
    rule_score: float = 0.0                # 0-5 综合规则分 (30%权重)
    overall_score: float = 0.0             # 加权后的确定性总分

    # ── 各子模块结果 ──
    structure: Optional[StructureCheckResult] = None
    facts: Optional[FactCheckResult] = None
    sla: Optional[SLAResult] = None
    safety: Optional[SafetyCheckResult] = None
    overhelping: Optional[OverhelpingCheckResult] = None  # v3.4

    # ── 维度映射 ──
    dimension_scores: dict[str, float] = field(default_factory=dict)
    skip_llm_dims: list[str] = field(default_factory=list)
    veto_dims: list[str] = field(default_factory=list)

    # ── 汇总 ──
    evidence: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    has_veto: bool = False


class RuleEngine:
    """
    规则引擎编排器 — L1 确定性评分层

    用法:
        engine = RuleEngine()
        result = engine.evaluate(
            question="...",
            agent_answer="...",
            golden_answer="...",
            turns=[...],
        )
        # result.rule_score: 0-5 确定性综合分
        # result.skip_llm_dims: LLM不需要评的维度
        # result.dimension_scores: 每维度确定性基底
    """

    # ── 维度 → 规则模块 映射 ──
    # 定义了每个维度由哪些规则模块的哪些分数组成
    DIMENSION_MAPPING = {
        "correctness": {
            "primary": "facts",           # 事实锚点是正确性的主基底
            "weight": 0.7,
            "fallback_score": 3.0,
        },
        "relevancy": {
            "primary": "facts",           # 关键词匹配 → 回答与黄金答案的内容相关性
            "secondary": "structure",     # 格式良好是加分项
            "weight": 0.5,
            "fallback_score": 3.0,
        },
        "completeness": {
            "primary": "structure",       # 长度/格式 → 完整性基底
            "secondary": "facts",          # 关键词覆盖也影响
            "weight": 0.5,
            "fallback_score": 3.0,
        },
        "guidance": {
            "primary": "structure",       # 格式结构 → 引导力基底(标题/列表/代码块)
            "secondary": "facts",          # 内容质量也反映引导力
            "weight": 0.4,
            "fallback_score": 3.0,
        },
        "followup_quality": {
            "primary": "sla",             # SLA是追问质量的主基底
            "weight": 0.6,
            "fallback_score": 3.0,
        },
        "boundary_compliance": {
            "primary": "safety",          # 安全合规 → 边界合规基底
            "weight": 0.5,
            "fallback_score": 3.0,
        },
        "turn_consistency": {
            "primary": "sla",             # 轮次成功率 → 一致性基底
            "weight": 0.4,
            "fallback_score": 3.0,
        },
        "knowledge_scaffolding": {
            "primary": "facts",           # 关键词递进 → 知识递进基底
            "weight": 0.35,
            "fallback_score": 3.0,
        },
        # ── v3.4 新增 ──
        "overhelping": {
            "primary": "overhelping",     # 过度帮助检测 → 独立维度
            "weight": 0.7,
            "fallback_score": 4.0,        # 默认无过度帮助
        },
    }

    def __init__(self):
        self.structure = StructureRules()
        self.facts = FactRules()
        self.sla = SLARules()
        self.safety = SafetyRules()
        self.overhelping = OverhelpingRules()  # v3.4

    def evaluate(
        self,
        question: str = "",
        agent_answer: str = "",
        golden_answer: str = "",
        turns: list[dict] = None,
        is_adversarial: bool = False,
    ) -> RuleEngineResult:
        """
        执行全规则层评估

        :param question: 用户问题
        :param agent_answer: Agent 完整回答
        :param golden_answer: 黄金标准答案
        :param turns: 对话轮次列表
        :param is_adversarial: 是否对抗性测试
        :return: RuleEngineResult
        """
        all_evidence: list[str] = []
        all_flags: list[str] = []
        veto_dims: list[str] = []
        skip_dims: list[str] = []
        dimension_scores: dict[str, float] = {}

        # ═══════════════════════════════════════════
        # 1. 结构完整性检查
        # ═══════════════════════════════════════════
        struct_result = self.structure.check(
            question=question,
            answer=agent_answer,
        )
        all_evidence.append(f"[结构检查] 得分={struct_result.score:.1f}")
        all_evidence.extend(f"  • {e}" for e in struct_result.evidence)
        all_flags.extend(struct_result.flags)

        if struct_result.veto:
            # 空回答 → 所有维度一票否决
            veto_dims.extend([
                "correctness", "relevancy", "completeness", "guidance",
                "followup_quality", "boundary_compliance",
                "turn_consistency", "knowledge_scaffolding",
            ])
            all_evidence.append("⛔ 空回答触发全维度一票否决")

        # ═══════════════════════════════════════════
        # 2. 事实锚点检查
        # ═══════════════════════════════════════════
        fact_result = self.facts.check(
            golden_answer=golden_answer,
            agent_answer=agent_answer,
        )
        all_evidence.append(f"[事实锚点] 得分={fact_result.score:.1f}")
        all_evidence.extend(f"  • {e}" for e in fact_result.evidence)
        all_flags.extend(fact_result.flags)

        # 事实锚点高分 → correctness 可跳过 LLM
        if fact_result.score >= 4.5 and not veto_dims:
            skip_dims.append("correctness")

        # ═══════════════════════════════════════════
        # 3. SLA 性能检查
        # ═══════════════════════════════════════════
        sla_result = self.sla.check(turns=turns or [])
        all_evidence.append(f"[SLA性能] 得分={sla_result.score:.1f}")
        all_evidence.extend(f"  • {e}" for e in sla_result.evidence)
        all_flags.extend(sla_result.flags)

        # ═══════════════════════════════════════════
        # 4. 安全合规检查
        # ═══════════════════════════════════════════
        safety_result = self.safety.check(
            question=question,
            answer=agent_answer,
            is_adversarial=is_adversarial,
        )
        all_evidence.append(f"[安全合规] 得分={safety_result.score:.1f}")
        all_evidence.extend(f"  • {e}" for e in safety_result.evidence)
        all_flags.extend(safety_result.flags)

        if safety_result.veto:
            veto_dims.append("boundary_compliance")
            veto_dims.append("relevancy")
            all_evidence.append("⛔ PII泄露触发 boundary_compliance + relevancy 一票否决")

        if safety_result.score >= 5.0 and not veto_dims:
            # 安全合规满分 → boundary_compliance 确定性高，可跳过LLM
            skip_dims.append("boundary_compliance")

        # ═══════════════════════════════════════════
        # 5. 过度帮助检测 (v3.4)
        # ═══════════════════════════════════════════
        # 提取当前轮的学生输入
        student_input = question
        current_turn = len(turns) if turns else 1
        overhelping_result = self.overhelping.check(
            agent_answer=agent_answer,
            golden_answer=golden_answer,
            student_input=student_input,
            turn_number=current_turn,
            total_turns=current_turn,
        )
        all_evidence.append(f"[过度帮助] 得分={overhelping_result.score:.1f}")
        all_evidence.extend(f"  • {e}" for e in overhelping_result.evidence)
        all_flags.extend(overhelping_result.flags)

        # ═══════════════════════════════════════════
        # 6. 维度分数映射
        # ═══════════════════════════════════════════
        # 将各规则模块的分数映射到8个测评维度
        rule_scores = {
            "structure": struct_result.score,
            "facts": fact_result.score,
            "sla": sla_result.score,
            "safety": safety_result.score,
            "overhelping": overhelping_result.score,  # v3.4
        }

        for dim, mapping in self.DIMENSION_MAPPING.items():
            if dim in veto_dims:
                dimension_scores[dim] = 0.0
                continue

            # 主规则分数 — 规则模块不可用时标记为None(非3.0填充)
            primary_key = mapping["primary"]
            primary_score = rule_scores.get(primary_key)

            if primary_score is None:
                # 该规则模块对此维度不适用 → 标记为不可评估
                dimension_scores[dim] = None  # type: ignore
                continue

            # 次规则分数 (如果有)
            if "secondary" in mapping:
                secondary_key = mapping["secondary"]
                secondary_score = rule_scores.get(secondary_key)
                if secondary_score is not None:
                    dim_score = primary_score * 0.7 + secondary_score * 0.3
                else:
                    dim_score = primary_score
            else:
                dim_score = primary_score

            # 规则层给出确定性分数, 不再用fallback=3.0填充未知部分
            # L1/L3融合在evaluator中处理: final = w_rule * L1 + w_llm * L3
            dim_score = min(5.0, max(0.0, dim_score))
            dimension_scores[dim] = round(dim_score, 1)

        # ═══════════════════════════════════════════
        # 6. 综合规则分 (0-5)
        # ═══════════════════════════════════════════
        # 五个模块等权平均 (v3.4 新增 overhelping)
        module_scores = [
            struct_result.score,
            fact_result.score,
            sla_result.score,
            safety_result.score,
            overhelping_result.score,
        ]
        rule_score = sum(module_scores) / len(module_scores)

        # ── 去重 ──
        veto_dims = list(set(veto_dims))
        skip_dims = [d for d in skip_dims if d not in veto_dims]

        return RuleEngineResult(
            rule_score=round(rule_score, 1),
            overall_score=round(rule_score, 1),  # 当前等同; 未来可加入加权
            structure=struct_result,
            facts=fact_result,
            sla=sla_result,
            safety=safety_result,
            overhelping=overhelping_result,  # v3.4
            dimension_scores=dimension_scores,
            skip_llm_dims=skip_dims,
            veto_dims=veto_dims,
            evidence=all_evidence,
            flags=all_flags,
            has_veto=len(veto_dims) > 0,
        )
