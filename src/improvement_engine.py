"""
改进方案生成引擎 v3.4 — Improvement Proposal Engine

将评估结果（评分+证据链）转化为结构化、可执行的改进方案。
不止"发现问题"，更"给出解法"。

定位: 白皮书第五章"改进策略索引"的代码实现
对齐:
  - AHE (arXiv:2604.25850): 可证伪契约 — 每个方案含预期效果+验证方法
  - Self-Harness (arXiv:2606.09498): 行为证据驱动 — 基于失败模式聚类生成方案
  - PEBBLE (NeurIPS 2025): 按维度+严重级别分层生成
  - DSPy/GEPA: 方案质量可被LLM评估和迭代优化

工作流:
  eval_result + evidence
    → 1. 问题定位 (哪维/哪弱/为什么)
    → 2. 根因分析 (基于L1/L2证据链定位具体失败模式)
    → 3. 方案生成 (LLM驱动, 定制化方案)
    → 4. 结构化输出 (改什么/怎么改/预期效果/验证方法)
    → 5. 优先级排序 (按影响×紧急度)

用法:
    from src.improvement_engine import ImprovementEngine
    engine = ImprovementEngine(api_key="...")
    plan = engine.propose(eval_result, evidence, conversation_context)
    # plan.to_dict() → 结构化方案, 可直接写入报告
"""

import json
import os
from datetime import datetime
from dataclasses import dataclass, field
from openai import OpenAI


# ═══════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════

@dataclass
class RootCause:
    """根因分析结果"""
    dimension: str
    score: float
    severity: str               # "urgent" | "important" | "optimize"
    failure_pattern: str        # 具体失败模式
    evidence_from_l1: str       # L1层的证据
    evidence_from_l2: str       # L2层的证据
    evidence_from_l3: str       # L3 Judge的评语

@dataclass
class ImprovementAction:
    """单个改进措施"""
    category: str               # "prompt" | "tool" | "memory" | "rule" | "workflow" | "model"
    title: str
    description: str
    implementation: str         # 具体怎么改（含代码/Prompt模板）
    expected_effect: str        # 预期效果（可量化）
    validation_method: str      # 如何验证改进是否生效
    effort: str                 # "low" | "medium" | "high"
    risk: str                   # "low" | "medium" | "high"

@dataclass
class ImprovementPlan:
    """综合改进方案"""
    # 总览
    overall_score: float
    score_verdict: str          # "优秀" | "良好" | "需改进" | "不合格"
    generated_at: str
    model_used: str

    # 短板分析
    weak_dimensions: list[dict] = field(default_factory=list)
    strong_dimensions: list[dict] = field(default_factory=list)

    # 根因
    root_causes: list[RootCause] = field(default_factory=list)

    # 改进措施 (按优先级排序)
    actions: list[ImprovementAction] = field(default_factory=list)

    # 紧急度分层
    urgent_actions: list[ImprovementAction] = field(default_factory=list)
    important_actions: list[ImprovementAction] = field(default_factory=list)
    optimize_actions: list[ImprovementAction] = field(default_factory=list)

    # 元信息
    raw_llm_response: str = ""
    generated_by: str = "improvement_engine_v3.4"

    def to_dict(self) -> dict:
        """转为可序列化的字典"""
        return {
            "overall_score": self.overall_score,
            "score_verdict": self.score_verdict,
            "generated_at": self.generated_at,
            "model_used": self.model_used,
            "weak_dimensions": self.weak_dimensions,
            "strong_dimensions": self.strong_dimensions,
            "root_causes": [
                {
                    "dimension": rc.dimension,
                    "score": rc.score,
                    "severity": rc.severity,
                    "failure_pattern": rc.failure_pattern,
                    "evidence_from_l1": rc.evidence_from_l1,
                    "evidence_from_l2": rc.evidence_from_l2,
                    "evidence_from_l3": rc.evidence_from_l3,
                }
                for rc in self.root_causes
            ],
            "actions": [
                {
                    "category": a.category,
                    "title": a.title,
                    "description": a.description,
                    "implementation": a.implementation,
                    "expected_effect": a.expected_effect,
                    "validation_method": a.validation_method,
                    "effort": a.effort,
                    "risk": a.risk,
                }
                for a in self.actions
            ],
            "urgent_actions_count": len(self.urgent_actions),
            "important_actions_count": len(self.important_actions),
            "optimize_actions_count": len(self.optimize_actions),
            "total_actions": len(self.actions),
            "generated_by": self.generated_by,
        }

    def to_markdown(self) -> str:
        """生成 Markdown 格式的改进方案报告"""
        lines = []
        lines.append(f"# 📋 AI教学助手改进方案")
        lines.append(f"")
        lines.append(f"**生成时间**: {self.generated_at}")
        lines.append(f"**综合得分**: {self.overall_score:.1f}/5.0 — **{self.score_verdict}**")
        lines.append(f"")

        # 短板总览
        if self.weak_dimensions:
            lines.append("## ⚠️ 主要短板")
            lines.append("")
            lines.append("| 维度 | 得分 | 严重级别 |")
            lines.append("|------|------|----------|")
            for wd in self.weak_dimensions:
                lines.append(f"| {wd['name']} | {wd['score']:.1f} | {wd['severity']} |")
            lines.append("")

        # 优势维度
        if self.strong_dimensions:
            lines.append("## ✅ 优势维度")
            lines.append("")
            for sd in self.strong_dimensions:
                lines.append(f"- **{sd['name']}** ({sd['score']:.1f}/5.0)")
            lines.append("")

        # 🔴 紧急改进
        if self.urgent_actions:
            lines.append("## 🔴 紧急改进方案 (< 2.5分)")
            lines.append("")
            for i, action in enumerate(self.urgent_actions):
                lines.extend(self._format_action(i + 1, action))
            lines.append("")

        # 🟡 重点改进
        if self.important_actions:
            lines.append("## 🟡 重点改进方案 (2.5-3.5分)")
            lines.append("")
            for i, action in enumerate(self.important_actions):
                lines.extend(self._format_action(i + 1, action))
            lines.append("")

        # 🟢 优化建议
        if self.optimize_actions:
            lines.append("## 🟢 优化建议 (> 3.5分)")
            lines.append("")
            for i, action in enumerate(self.optimize_actions):
                lines.extend(self._format_action(i + 1, action))
            lines.append("")

        return "\n".join(lines)

    def _format_action(self, index: int, a: ImprovementAction) -> list[str]:
        lines = []
        lines.append(f"### {index}. {a.title}")
        lines.append(f"")
        lines.append(f"**类别**: `{a.category}` | **工作量**: {a.effort} | **风险**: {a.risk}")
        lines.append(f"")
        lines.append(f"**问题描述**: {a.description}")
        lines.append(f"")
        lines.append(f"**实施方案**:")
        lines.append(f"")
        lines.append(f"```")
        lines.append(f"{a.implementation}")
        lines.append(f"```")
        lines.append(f"")
        lines.append(f"**预期效果**: {a.expected_effect}")
        lines.append(f"")
        lines.append(f"**验证方法**: {a.validation_method}")
        lines.append(f"")
        return lines


# ═══════════════════════════════════════════════════════════
# Engine
# ═══════════════════════════════════════════════════════════

class ImprovementEngine:
    """
    改进方案生成引擎

    将评估结果转化为结构化、可执行的改进方案。
    使用 LLM 生成定制化方案（可后续用 DSPy/GEPA 优化生成Prompt）。

    用法:
        engine = ImprovementEngine(api_key="...")
        plan = engine.propose(
            eval_result={...},    # evaluator.evaluate() 的输出
            evidence={...},       # L1/L2/L3 的证据链
        )
        print(plan.to_markdown())
    """

    # ── 严重级别阈值 ──
    URGENT_THRESHOLD = 2.5
    IMPORTANT_THRESHOLD = 3.5

    # ── 维度中文名 ──
    DIM_NAMES = {
        "correctness": "事实正确性",
        "relevancy": "答案相关性",
        "completeness": "内容完整性",
        "guidance": "教学引导力",
        "followup_quality": "追问响应质量",
        "boundary_compliance": "边界合规性",
        "turn_consistency": "跨轮一致性",
        "knowledge_scaffolding": "知识递进性",
        "overhelping": "过度帮助",
        "fairness_bias": "公平性与偏见",
    }

    # ── 改进类别及对应模板 ──
    IMPROVEMENT_CATEGORIES = {
        "prompt": "System Prompt / 指令优化 — 调整Agent的角色定义、行为约束、输出格式要求",
        "tool": "工具/函数调用优化 — 调整工具定义、参数描述、返回值格式、调用策略",
        "memory": "记忆/上下文优化 — 调整对话历史管理、长期记忆检索、上下文窗口策略",
        "rule": "规则/阈值调整 — 调整L1确定性规则、L2算法阈值、安全策略",
        "workflow": "编排/工作流优化 — 调整ReAct循环、多Agent协作、任务分解策略",
        "model": "模型选择优化 — 调整底层LLM模型、temperature、max_tokens等",
    }

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
    ):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    # ═══════════════════════════════════════════════════
    # 主接口
    # ═══════════════════════════════════════════════════

    def propose(
        self,
        eval_result: dict,
        rule_evidence: list[str] = None,
        l2_scores: dict = None,
        conversation_context: str = "",
        adversarial_type: str = None,
        generate_llm: bool = True,
    ) -> ImprovementPlan:
        """
        生成改进方案

        :param eval_result: evaluator.evaluate() 的返回值
        :param rule_evidence: L1规则层的证据列表
        :param l2_scores: L2算法层的分数
        :param conversation_context: 对话上下文
        :param adversarial_type: 对抗性测试类型
        :param generate_llm: 是否调用LLM生成方案（False=仅基于规则生成）
        :return: ImprovementPlan
        """
        dim_scores = {
            k: v for k, v in eval_result.items()
            if k in self.DIM_NAMES
        }

        overall = eval_result.get("overall", 3.0)

        # 1. 短板/优势识别
        weak_dims, strong_dims = self._classify_dimensions(dim_scores)

        # 2. 根因分析
        root_causes = self._analyze_root_causes(
            dim_scores, rule_evidence or [], l2_scores or {}, conversation_context
        )

        # 3. 方案生成 (LLM或规则)
        if generate_llm:
            actions = self._generate_with_llm(
                dim_scores=dim_scores,
                weak_dims=weak_dims,
                root_causes=root_causes,
                rule_evidence=rule_evidence or [],
                conversation_context=conversation_context,
                adversarial_type=adversarial_type,
            )
        else:
            actions = self._generate_with_rules(
                dim_scores=dim_scores,
                weak_dims=weak_dims,
                root_causes=root_causes,
            )

        # 4. 按严重级别分层
        urgent = [a for a in actions if self._severity_from_dim(a.title, weak_dims) == "urgent"]
        important = [a for a in actions if self._severity_from_dim(a.title, weak_dims) == "important"]
        optimize = [a for a in actions if self._severity_from_dim(a.title, weak_dims) == "optimize"]

        # 5. 优先级排序 (影响×紧急度)
        actions.sort(key=lambda a: (
            0 if self._severity_from_dim(a.title, weak_dims) == "urgent" else
            1 if self._severity_from_dim(a.title, weak_dims) == "important" else 2,
            0 if a.effort == "low" else 1 if a.effort == "medium" else 2,
        ))

        # 6. 综合评定
        if overall >= 4.0:
            verdict = "优秀"
        elif overall >= 3.0:
            verdict = "良好"
        elif overall >= 2.0:
            verdict = "需改进"
        else:
            verdict = "不合格"

        return ImprovementPlan(
            overall_score=overall,
            score_verdict=verdict,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            model_used=self.model,
            weak_dimensions=weak_dims,
            strong_dimensions=strong_dims,
            root_causes=root_causes,
            actions=actions,
            urgent_actions=urgent,
            important_actions=important,
            optimize_actions=optimize,
        )

    # ═══════════════════════════════════════════════════
    # 维度分类
    # ═══════════════════════════════════════════════════

    def _classify_dimensions(self, dim_scores: dict) -> tuple[list[dict], list[dict]]:
        """按分数分类维度为短板/优势"""
        weak = []
        strong = []
        for dim, score in dim_scores.items():
            entry = {
                "name": self.DIM_NAMES.get(dim, dim),
                "dimension": dim,
                "score": score,
                "severity": (
                    "🔴 紧急" if score < self.URGENT_THRESHOLD else
                    "🟡 重要" if score < self.IMPORTANT_THRESHOLD else
                    "🟢 优化"
                ),
            }
            if score < self.IMPORTANT_THRESHOLD:
                weak.append(entry)
            elif score >= 4.0:
                strong.append(entry)

        # 按分数排序
        weak.sort(key=lambda x: x["score"])
        strong.sort(key=lambda x: x["score"], reverse=True)
        return weak, strong

    def _severity_from_dim(self, title: str, weak_dims: list[dict]) -> str:
        """从改进标题推断严重级别"""
        for wd in weak_dims:
            if wd["dimension"] in title or wd["name"] in title:
                if "🔴" in wd["severity"]:
                    return "urgent"
                elif "🟡" in wd["severity"]:
                    return "important"
        return "optimize"

    # ═══════════════════════════════════════════════════
    # 根因分析
    # ═══════════════════════════════════════════════════

    def _analyze_root_causes(
        self,
        dim_scores: dict,
        rule_evidence: list[str],
        l2_scores: dict,
        conversation_context: str,
    ) -> list[RootCause]:
        """基于L1/L2/L3证据链分析根因"""
        causes = []

        for dim, score in dim_scores.items():
            if score >= self.IMPORTANT_THRESHOLD:
                continue  # 不分析表现好的维度

            # 从证据链提取相关信息
            l1_evidence = self._extract_dim_evidence(dim, rule_evidence)
            l2_evidence = self._extract_dim_evidence(dim, [str(v) for v in l2_scores.values()])
            l3_evidence = ""  # LLM评判证据在prompt中获取

            # 推断失败模式
            failure = self._infer_failure_pattern(dim, score, l1_evidence, l2_evidence)

            severity = (
                "urgent" if score < self.URGENT_THRESHOLD else "important"
            )

            causes.append(RootCause(
                dimension=dim,
                score=score,
                severity=severity,
                failure_pattern=failure,
                evidence_from_l1=l1_evidence,
                evidence_from_l2=l2_evidence,
                evidence_from_l3=l3_evidence,
            ))

        # 按分数排序（最低分先）
        causes.sort(key=lambda x: x.score)
        return causes

    def _extract_dim_evidence(self, dim: str, evidence: list[str]) -> str:
        """从证据列表中提取与特定维度相关的证据"""
        dim_keywords = {
            "correctness": ["事实", "correctness", "fact", "关键词命中", "数字匹配"],
            "relevancy": ["相关", "relevancy", "embedding", "相似度"],
            "completeness": ["完整", "completeness", "覆盖", "structure"],
            "guidance": ["引导", "guidance", "教学", "结构"],
            "followup_quality": ["追问", "followup", "SLA", "延迟"],
            "boundary_compliance": ["边界", "boundary", "安全", "合规", "PII"],
            "turn_consistency": ["一致", "consistency", "矛盾"],
            "knowledge_scaffolding": ["递进", "scaffolding", "关键词"],
            "overhelping": ["过度帮助", "overhelping", "泄露", "主导", "引导性提问"],
        }
        keywords = dim_keywords.get(dim, [dim])

        relevant = []
        for line in evidence:
            for kw in keywords:
                if kw.lower() in line.lower():
                    relevant.append(line[:200])
                    break

        return "; ".join(relevant[:5]) if relevant else f"{dim}维度无直接证据"

    def _infer_failure_pattern(
        self,
        dim: str,
        score: float,
        l1_evidence: str,
        l2_evidence: str,
    ) -> str:
        """基于证据推断具体失败模式"""
        patterns = {
            "correctness": {
                (0, 2.0): "严重事实错误或幻觉 — Agent声称了不存在的事实/参数/API",
                (2.0, 3.0): "多处事实错误 — Agent混淆了相似概念或给出了错误的技术参数",
                (3.0, 3.5): "少量错误 — 有1-2处技术细节偏差",
            },
            "relevancy": {
                (0, 2.0): "答非所问 — Agent完全偏离了用户问题的核心",
                (2.0, 3.0): "多次偏离 — 回答扩散到不相关领域",
                (3.0, 3.5): "部分偏离 — 30-50%内容与问题不直接相关",
            },
            "completeness": {
                (0, 2.0): "严重不完整 — 仅覆盖<20%关键知识点",
                (2.0, 3.0): "较多遗漏 — 大量关键信息缺失",
                (3.0, 3.5): "部分遗漏 — 覆盖了40-60%知识点",
            },
            "guidance": {
                (0, 2.0): "无教学引导 — 直接给答案/代码，无解释无提问",
                (2.0, 3.0): "引导混乱 — 逻辑不清，信息堆砌",
                (3.0, 3.5): "引导不足 — 有结构但跳跃，偏向灌输式",
            },
            "followup_quality": {
                (0, 2.0): "失忆现象 — 完全无视追问内容，与前轮几乎相同",
                (2.0, 3.0): "重复式回应 — 大量重复前轮内容",
                (3.0, 3.5): "追问质量下降 — 回应深度不足",
            },
            "boundary_compliance": {
                (0, 2.0): "完全越界 — 回答脱离课程体系，调用通用知识",
                (2.0, 3.0): "大量越界 — 回答主要基于通用模型能力",
                (3.0, 3.5): "部分越界 — 课程知识与通用知识混杂",
            },
            "turn_consistency": {
                (0, 2.0): "严重失忆 — 每轮都在推翻前轮陈述",
                (2.0, 3.0): "多处矛盾 — 前后多处不一致",
                (3.0, 3.5): "轻微矛盾 — 1-2处术语不统一",
            },
            "knowledge_scaffolding": {
                (0, 2.0): "完全无递进 — 每轮重复相同层次内容",
                (2.0, 3.0): "退步/重复 — 后轮信息量更少",
                (3.0, 3.5): "缺乏递进 — 各轮回答独立",
            },
            "overhelping": {
                (0, 2.0): "严重过度帮助 — 所有回答直接给答案/代码，无引导",
                (2.0, 3.0): "明显过度帮助 — 多次直接给出答案/代码",
                (3.0, 3.5): "轻度过度帮助 — 部分回答直接暴露关键信息",
            },
        }

        dim_patterns = patterns.get(dim, {})
        for (lo, hi), pattern in dim_patterns.items():
            if lo <= score < hi:
                return pattern

        return f"{self.DIM_NAMES.get(dim, dim)}得分{score:.1f}，表现可接受但仍可优化"

    # ═══════════════════════════════════════════════════
    # 基于规则的方案生成 (无LLM)
    # ═══════════════════════════════════════════════════

    def _generate_with_rules(
        self,
        dim_scores: dict,
        weak_dims: list[dict],
        root_causes: list[RootCause],
    ) -> list[ImprovementAction]:
        """基于预定义规则生成改进方案（备用方案，无需LLM调用）"""
        actions = []

        # 预定义的改进方案库（对应白皮书第五章）
        RULE_BASED_ACTIONS = {
            "correctness": {
                "urgent": ImprovementAction(
                    category="prompt", title="接入知识库RAG检索+事实校验规则",
                    description="Agent回答存在严重事实错误。需要在Prompt中注入课程知识库检索结果作为事实校验基准。",
                    implementation="1. 在System Prompt中加入: '在回答前，请先检索课程知识库中的相关内容'\n"
                                   "2. 接入RAG检索: response = rag.retrieve(question, top_k=3)\n"
                                   "3. 在Prompt中注入: '请基于以下课程资料回答，不要使用预训练知识'\n"
                                   "4. 在输出前对关键数值做正则校验，匹配课程知识库中的技术参数",
                    expected_effect="预期事实错误率降低50-70%，correctness从{dim_scores['correctness']}提升至3.5+",
                    validation_method="用已知正确答案的100道题目进行回归测试，correctness≥3.5即为验证通过",
                    effort="high", risk="low",
                ),
                "important": ImprovementAction(
                    category="prompt", title="优化Prompt中的数据引用要求",
                    description="Agent存在少量事实偏差。在Prompt中强化数据引用要求可以改善。",
                    implementation="1. 在Prompt中加入: '引用技术参数时请确认数值精确性'\n"
                                   "2. 添加示例: 正例'ADC为12位(0-4095)' vs 误例'ADC约12位'\n"
                                   "3. 设置输出后处理: 扫描常见技术参数，发现数字问题时标注",
                    expected_effect="预期纠正90%的关键数值偏差",
                    validation_method="测试50道包含技术参数的题目，数值精度≥95%",
                    effort="low", risk="low",
                ),
            },
            "guidance": {
                "urgent": ImprovementAction(
                    category="prompt", title="注入Socratic教学策略+禁止直接给答案",
                    description="Agent缺乏教学引导，直接给出答案或代码。需从Prompt层面重构教学行为模式。",
                    implementation="1. 在System Prompt中加入Socratic教学法指令:\n"
                                   "   '你是Socratic导师。规则:\n"
                                   "    ① 永远先问学生目前的理解水平\n"
                                   "    ② 给出提示而非直接答案\n"
                                   "    ③ 引导学生自己推导出结论\n"
                                   "    ④ 学生卡住时给最小提示\n"
                                   "    ⑤ 确认学生理解后再进入下一层'\n"
                                   "2. 设置输出约束:\n"
                                   "   '禁止在第1轮给出完整代码。禁止在引导前给出最终答案。'\n"
                                   "3. 在Prompt末尾加入引导性提问模板:\n"
                                   "   '你之前学过[前置知识]吗？我们来一步步分析[当前问题]...'",
                    expected_effect="预期guidance从{dim_scores['guidance']}提升至3.0+，引导性提问出现率>80%",
                    validation_method="用20道教学场景题目测试，人工评估Socratic行为覆盖率≥70%",
                    effort="high", risk="medium",
                ),
                "important": ImprovementAction(
                    category="prompt", title="优化教学结构模板+增设引导性提问",
                    description="Agent有引导意识但不够系统。通过结构模板化可以稳定教学行为。",
                    implementation="1. 建立教学回答结构模板:\n"
                                   "   [诊断提问] → [概念讲解] → [引导推导] → [确认理解] → [递进提问]\n"
                                   "2. 每轮回答末尾强制包含≥2个引导性提问\n"
                                   "3. 使用few-shot示例展示理想教学模式",
                    expected_effect="预期教学引导力得分提升0.5-1.0分",
                    validation_method="统计连续10轮对话中引导性提问的覆盖率",
                    effort="medium", risk="low",
                ),
            },
            "overhelping": {
                "urgent": ImprovementAction(
                    category="prompt", title="遏制过度帮助: 设置引导优先规则",
                    description="Agent严重过度帮助，几乎所有回答都直接给出答案。需设置硬约束。",
                    implementation="1. System Prompt硬约束:\n"
                                   "   '严禁在第1-2轮直接给出完整答案或代码。\n"
                                   "    必须先: ①提问→②提示→③引导→④确认后→⑤才给示例'\n"
                                   "2. 输出后检测:\n"
                                   "   '如果回答中包含```代码块且前面<100字，自动重生成加入引导'\n"
                                   "3. 对话比控制:\n"
                                   "   '每次回答后必须有≥1个反向提问，确保学生输出>你输出的40%'",
                    expected_effect="预期过度帮助得分从{dim_scores['overhelping']}提升至3.5+",
                    validation_method="测试10道引导类题目，Agent回答中引导性提问覆盖率≥80%，直接给答案率<20%",
                    effort="medium", risk="medium",
                ),
            },
            "boundary_compliance": {
                "urgent": ImprovementAction(
                    category="rule", title="建立课程知识边界清单+统一拒答模板",
                    description="Agent无法识别课程边界，对所有问题都用通用知识回答。",
                    implementation="1. 从课程大纲/知识库提取知识边界清单(核心术语70个+5阶段)\n"
                                   "2. 在Prompt中注入: '只回答以下范围内的内容:{边界清单}'\n"
                                   "3. 配置KB检索阈值: 分数<0.15→触发拒答模板\n"
                                   "4. 统一拒答话术: '这个问题超出了当前课程范围。[返回课程引导]'",
                    expected_effect="预期边界合规从{dim_scores['boundary_compliance']}提升至3.5+, 越界正确识别率>90%",
                    validation_method="用20道越界测试题验证，正确拒绝率≥85%",
                    effort="medium", risk="low",
                ),
            },
            "followup_quality": {
                "urgent": ImprovementAction(
                    category="memory", title="实现多轮对话状态追踪+追问意图分类",
                    description="Agent无法有效响应追问，表现出失忆现象。需建立对话状态追踪系统。",
                    implementation="1. 维护对话状态字典:\n"
                                   "   state = {'topics_covered': [...], 'student_level': '...', 'last_question': '...'}\n"
                                   "2. 追问意图分类: 深入理解/补充细节/纠正误解/转向新话题\n"
                                   "3. 在Prompt中注入当前对话状态摘要\n"
                                   "4. 追问前先确认: '你刚才问的是[复述], 你想了解[意图]对吗?'",
                    expected_effect="预期追问响应从{dim_scores['followup_quality']}提升至3.5+",
                    validation_method="用10组多轮追问对话测试，追问响应准确率≥80%",
                    effort="high", risk="medium",
                ),
            },
        }

        for wd in weak_dims:
            dim = wd["dimension"]
            score = wd["score"]
            severity = "urgent" if score < self.URGENT_THRESHOLD else "important"

            dim_actions = RULE_BASED_ACTIONS.get(dim, {}).get(severity)
            if dim_actions:
                # 个性化替换占位符
                action = dim_actions
                if "{dim_scores" in action.expected_effect:
                    action.expected_effect = action.expected_effect.replace(
                        f"{{dim_scores['{dim}']}}", str(score)
                    )
                if "{dim_scores" in action.description:
                    action.description = action.description.replace(
                        f"{{dim_scores['{dim}']}}", str(score)
                    )
                actions.append(action)

        # 如果没有规则匹配的维度，生成通用建议
        for wd in weak_dims:
            dim = wd["dimension"]
            if not any(dim in a.title for a in actions):
                actions.append(ImprovementAction(
                    category="prompt",
                    title=f"优化{self.DIM_NAMES.get(dim, dim)}相关Prompt",
                    description=f"{self.DIM_NAMES.get(dim, dim)}得分{wd['score']:.1f}，需要针对性优化。",
                    implementation=f"1. 分析当前Prompt中与{dim}相关的指令\n"
                                   f"2. 添加{dim}的评估标准和约束\n"
                                   f"3. 提供正反例参考",
                    expected_effect=f"预期{dim}得分提升0.5-1.0分",
                    validation_method=f"用10道题目回归测试{dim}维度",
                    effort="medium", risk="low",
                ))

        return actions

    # ═══════════════════════════════════════════════════
    # LLM驱动的方案生成
    # ═══════════════════════════════════════════════════

    def _generate_with_llm(
        self,
        dim_scores: dict,
        weak_dims: list[dict],
        root_causes: list[RootCause],
        rule_evidence: list[str],
        conversation_context: str,
        adversarial_type: str = None,
    ) -> list[ImprovementAction]:
        """使用LLM生成定制化改进方案"""
        # 先尝试LLM生成，失败则降级为规则生成
        try:
            return self._llm_generate(
                dim_scores, weak_dims, root_causes,
                rule_evidence, conversation_context, adversarial_type,
            )
        except Exception as e:
            print(f"  ⚠️ LLM方案生成失败({e})，降级为规则生成")
            return self._generate_with_rules(dim_scores, weak_dims, root_causes)

    def _llm_generate(
        self,
        dim_scores: dict,
        weak_dims: list[dict],
        root_causes: list[RootCause],
        rule_evidence: list[str],
        conversation_context: str,
        adversarial_type: str = None,
    ) -> list[ImprovementAction]:
        """LLM驱动的方案生成核心"""
        prompt = self._build_improvement_prompt(
            dim_scores, weak_dims, root_causes,
            rule_evidence, conversation_context, adversarial_type,
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        data = json.loads(raw)
        return self._parse_llm_response(data)

    def _build_improvement_prompt(
        self,
        dim_scores: dict,
        weak_dims: list[dict],
        root_causes: list[RootCause],
        rule_evidence: list[str],
        conversation_context: str,
        adversarial_type: str = None,
    ) -> str:
        """构建方案生成的Prompt"""
        dim_lines = []
        for dim, score in dim_scores.items():
            name = self.DIM_NAMES.get(dim, dim)
            severity = (
                "🔴 紧急" if score < self.URGENT_THRESHOLD else
                "🟡 重要" if score < self.IMPORTANT_THRESHOLD else
                "🟢 优化"
            )
            dim_lines.append(f"- {name} ({dim}): {score:.1f}/5.0 {severity}")

        weak_lines = []
        for wd in weak_dims:
            weak_lines.append(f"- {wd['name']}: {wd['score']:.1f} — {wd['severity']}")

        cause_lines = []
        for rc in root_causes:
            cause_lines.append(
                f"- [{rc.severity}] {self.DIM_NAMES.get(rc.dimension, rc.dimension)} "
                f"({rc.score:.1f}): {rc.failure_pattern}\n"
                f"  证据: {rc.evidence_from_l1[:200]}"
            )

        adversarial_note = ""
        if adversarial_type:
            adversarial_note = f"\n⚠️ 本次为对抗性测试(类型: {adversarial_type})，请注意方案的适用性。\n"

        prompt = f"""你是AI教学系统优化专家。基于以下多维度评估结果，为被评测的AI教学助手制定具体、可执行的改进方案。

【评分总览】
{dim_lines}

【短板维度】
{weak_lines}

【根因分析】
{cause_lines}

【L1规则层证据摘要】
{chr(10).join(f"- {e[:300]}" for e in (rule_evidence or [])[:10])}

【对话上下文】
{conversation_context[:500]}

{adversarial_note}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

请为每个短板维度（得分<3.5）生成1-3条具体的改进措施。每条措施必须包含：

1. **标题**: 简洁的改进名称
2. **类别**: prompt / tool / memory / rule / workflow / model 之一
3. **问题描述**: 当前存在什么具体问题
4. **实施方案**: 具体怎么改 — 给出可直接使用的代码或Prompt模板。不要只说"优化XXX"，要给出具体的修改内容
5. **预期效果**: 可量化的预期改善（如"correctness从2.5提升至3.5+"）
6. **验证方法**: 如何验证改进是否生效
7. **工作量**: low / medium / high
8. **风险**: low / medium / high

特别关注:
- 对于guidance维度: 方案应包含Socratic教学法指令、禁止直接给答案的约束
- 对于correctness维度: 方案应包含RAG接入或事实校验机制
- 对于overhelping维度: 方案应包含引导优先规则和对话比控制
- 对于boundary_compliance维度: 方案应包含知识边界清单和统一拒答模板

输出JSON格式:
{{
  "actions": [
    {{
      "category": "prompt",
      "title": "方案标题",
      "description": "问题描述",
      "implementation": "具体怎么改（含代码/Prompt模板）",
      "expected_effect": "预期效果",
      "validation_method": "验证方法",
      "effort": "low|medium|high",
      "risk": "low|medium|high"
    }}
  ]
}}

只输出JSON。"""
        return prompt

    def _parse_llm_response(self, data: dict) -> list[ImprovementAction]:
        """解析LLM返回的方案"""
        actions = []
        for item in data.get("actions", []):
            category = item.get("category", "prompt")
            if category not in self.IMPROVEMENT_CATEGORIES:
                category = "prompt"

            actions.append(ImprovementAction(
                category=category,
                title=item.get("title", "未命名方案"),
                description=item.get("description", ""),
                implementation=item.get("implementation", ""),
                expected_effect=item.get("expected_effect", ""),
                validation_method=item.get("validation_method", ""),
                effort=item.get("effort", "medium"),
                risk=item.get("risk", "low"),
            ))
        return actions


# ── 简单自测 ──
if __name__ == "__main__":
    # 模拟评估结果
    fake_eval = {
        "correctness": 4.2,
        "relevancy": 3.8,
        "completeness": 3.0,
        "guidance": 1.8,
        "followup_quality": 3.5,
        "boundary_compliance": 4.5,
        "turn_consistency": 3.8,
        "knowledge_scaffolding": 2.5,
        "overhelping": 1.5,
        "overall": 3.2,
    }
    fake_evidence = [
        "[结构检查] 得分=4.0",
        "[事实锚点] 得分=4.5 — 关键词命中: 6/8 (75%)",
        "[SLA性能] 得分=3.5 — 延迟: 5.2s",
        "[安全合规] 得分=5.0 — PII检查通过",
        "[过度帮助] 得分=1.5 — ⚠️ 答案泄露: 关键词重叠率85% — ⚠️ 无引导性提问",
    ]

    # 测试规则生成模式（无需API key）
    engine = ImprovementEngine(api_key="fake_key")
    plan = engine.propose(
        eval_result=fake_eval,
        rule_evidence=fake_evidence,
        generate_llm=False,  # 规则模式
    )

    print(plan.to_markdown())
    print(f"\n方案数量: {len(plan.actions)}")
    print(f"  🔴 紧急: {len(plan.urgent_actions)}")
    print(f"  🟡 重点: {len(plan.important_actions)}")
    print(f"  🟢 优化: {len(plan.optimize_actions)}")
