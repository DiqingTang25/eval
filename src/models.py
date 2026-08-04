"""
统一数据模型

评测系统中所有数据结构的标准定义。
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
from enum import Enum


class BoundaryStatus(str, Enum):
    IN_SCOPE = "in_scope"
    PARTIAL_MATCH = "partial_match"
    OUT_OF_SCOPE = "out_of_scope"
    UNKNOWN = "unknown"
    ERROR = "error"


class TestStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"


class AgentType(str, Enum):
    BROWSER = "browser"
    API = "api"


# ── 问题数据 ─────────────────────────────────────

@dataclass
class QuestionData:
    """测试问题 + 黄金答案"""
    question: str
    golden_answer: str
    phase: str = ""
    type: str = ""                      # 概念解释 / 操作步骤 / 对比分析 / 应用场景
    difficulty: str = "中等"
    goal: str = ""                       # 教学目标
    knowledge_based: bool = True         # 是否基于知识库生成
    kb_sources: list[dict] = field(default_factory=list)


# ── Agent 交互 ───────────────────────────────────

@dataclass
class ConversationTurn:
    """单轮对话"""
    turn: int
    question: str
    response_status: str = ""           # success / timeout / error
    response_text: str = ""
    response_duration: float = 0.0


# ── 评测结果 ─────────────────────────────────────

@dataclass
class EvalScores:
    """6维度评分"""
    correctness: float = 0.0
    relevancy: float = 0.0
    completeness: float = 0.0
    guidance: float = 0.0
    followup_quality: float = 0.0
    boundary_compliance: float = 0.0
    overall: float = 0.0

    # 边界检测附加字段
    boundary_status: str = ""
    boundary_evidence: str = ""
    boundary_score_raw: float = 0.0


@dataclass
class BoundaryResult:
    """边界检测结果"""
    status: BoundaryStatus = BoundaryStatus.UNKNOWN
    max_score: float = 0.0
    avg_score: float = 0.0
    matched_count: int = 0
    total_retrieved: int = 0
    matched_knowledge: list = field(default_factory=list)
    evidence: str = ""
    recommendation: str = ""

    @property
    def is_in_scope(self) -> bool:
        return self.status == BoundaryStatus.IN_SCOPE


# ── 测试场景 ─────────────────────────────────────

@dataclass
class TestResult:
    """单个测试场景的完整结果"""
    question_data: QuestionData = field(default_factory=QuestionData)
    conversation_turns: list[ConversationTurn] = field(default_factory=list)
    full_conversation: str = ""
    scores: Optional[EvalScores] = None
    boundary: Optional[BoundaryResult] = None
    error: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def is_success(self) -> bool:
        return self.scores is not None and self.error == ""


# ── 评测会话 ─────────────────────────────────────

@dataclass
class TestSession:
    """一次完整的评测会话"""
    session_id: str = ""
    agent_id: str = ""
    profile: str = "standard"
    status: TestStatus = TestStatus.PENDING
    results: list[TestResult] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "profile": self.profile,
            "status": self.status.value,
            "results": [asdict(r) for r in self.results],
            "summary": self.summary,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
