"""
固定规则层 (30%) — 三层级联评测架构的 L1 层

Alignments:
  - CLEAR (arXiv:2511.14136): Efficacy + Assurance 的确定性闸门
  - TEACH-AI (NeurIPS 2025): Explainability / Consistency / Responsibility 的结构化检查
  - EduAgentBench (arXiv:2605.14322): Turn-level 确定性前置 + Trajectory 过程约束

模块结构:
  structure_rules  — 回答结构/长度/格式/语言一致性
  fact_rules       — 黄金答案关键词/数字精确匹配/否定词检测
  sla_rules        — 响应延迟/轮次效率/追问恰当性
  safety_rules     — PII泄露/敏感话题拒绝/角色越界
  rule_engine      — 编排器: 汇总所有规则, 产出 rule_score + flags + skip_dims
"""

from .rule_engine import RuleEngine
from .structure_rules import StructureRules
from .fact_rules import FactRules
from .sla_rules import SLARules
from .safety_rules import SafetyRules

__all__ = [
    "RuleEngine",
    "StructureRules",
    "FactRules",
    "SLARules",
    "SafetyRules",
]
