"""
黄金QA Schema 定义与验证

严格约束 LLM 输出格式，确保问答对可追溯、可审核
"""

import json
import uuid
from datetime import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum


class QAStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Phase(str, Enum):
    P1 = "PHASE 01"
    P2 = "PHASE 02"
    P3 = "PHASE 03"
    P4 = "PHASE 04"
    P5 = "PHASE 05"


class QuestionType(str, Enum):
    CONCEPT = "概念解释"
    PROCEDURE = "操作步骤"
    COMPARISON = "对比分析"
    SCENARIO = "应用场景"


class Difficulty(str, Enum):
    EASY = "简单"
    MEDIUM = "中等"
    HARD = "困难"


@dataclass
class Source:
    """知识来源追溯"""
    document: str = ""          # 文件名
    sheet: str = ""             # Sheet名
    excerpt: str = ""           # 原文引用


@dataclass
class QAPair:
    """黄金问答对"""
    qa_id: str = ""
    phase: str = ""
    type: str = ""
    difficulty: str = "中等"
    question: str = ""
    golden_answer: str = ""
    knowledge_points: list[str] = field(default_factory=list)
    source: Source = field(default_factory=Source)
    status: str = QAStatus.PENDING.value
    reviewer_notes: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.qa_id:
            self.qa_id = f"QA_{uuid.uuid4().hex[:8].upper()}"
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if isinstance(self.source, dict):
            self.source = Source(**self.source)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source"] = asdict(self.source) if isinstance(self.source, Source) else self.source
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "QAPair":
        return cls(**data)

    # ── 验证 ──────────────────────────────────────

    def validate(self) -> list[str]:
        """验证 QA 对是否符合规范，返回错误列表"""
        errors = []

        if not self.qa_id or not self.qa_id.startswith("QA_"):
            errors.append("qa_id 必须以 QA_ 开头")

        valid_phases = [p.value for p in Phase]
        if self.phase not in valid_phases:
            errors.append(f"phase 必须在 {valid_phases} 中")

        valid_types = [t.value for t in QuestionType]
        if self.type not in valid_types:
            errors.append(f"type 必须在 {valid_types} 中")

        if len(self.question) < 10:
            errors.append("问题太短（<10字符）")
        if len(self.golden_answer) < 20:
            errors.append("答案太短（<20字符）")
        if len(self.knowledge_points) == 0:
            errors.append("knowledge_points 不能为空")
        if not self.source.document:
            errors.append("source.document 不能为空")
        if not self.source.excerpt:
            errors.append("source.excerpt 不能为空（需要原文引用）")

        return errors

    @property
    def is_valid(self) -> bool:
        return len(self.validate()) == 0


# ── LLM Prompt 模板 ──────────────────────────────

QA_GENERATION_PROMPT = """
你是一个课程评测专家。请严格基于以下课程原文内容，生成一道测试问题和标准答案。

【课程原文】
{source_text}

【要求】
1. 问题必须涉及阶段：{phase}
2. 问题类型：{type}
3. 难度：{difficulty}
4. 问题必须完全基于以上【课程原文】内容，禁止编造或引入原文中没有的知识
5. 答案必须准确，直接引用或紧密改写原文内容
6. 标注答案涉及的知识点和原文出处

【输出格式】严格JSON（不要额外文字）：
{{
    "phase": "{phase}",
    "type": "{type}",
    "difficulty": "{difficulty}",
    "question": "问题（基于原文）",
    "golden_answer": "标准答案（基于原文）",
    "knowledge_points": ["知识点1", "知识点2"],
    "source_excerpt": "答案的原文依据（从课程原文中摘录）"
}}
"""

QA_GENERATION_PROMPT_BATCH = """
你是一个课程评测专家。请严格基于以下课程原文内容，生成{count}道测试问题和标准答案。

【课程原文】
{source_text}

【要求】
1. 问题必须涉及阶段：{phase}
2. 问题类型随机覆盖：{types}
3. 难度：{difficulty}
4. 问题必须完全基于以上【课程原文】内容，禁止编造或引入原文中没有的知识
5. 答案必须准确，直接引用或紧密改写原文内容

【输出格式】严格JSON数组（不要额外文字）：
[
    {{
        "phase": "{phase}",
        "type": "概念解释|操作步骤|对比分析|应用场景",
        "difficulty": "{difficulty}",
        "question": "问题文本",
        "golden_answer": "标准答案",
        "knowledge_points": ["知识点"],
        "source_excerpt": "原文依据"
    }},
    ...
]
"""
