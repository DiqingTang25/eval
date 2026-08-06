"""
Multi-Agent 共享数据模型 — Agent C

所有 Phase/Lesson/Step 名称来自 Schema, 零硬编码。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class StepTarget:
    """Planner 生成的单个 Step 测试目标"""
    step_id: str                      # schema: steps[].id
    step_name: str                    # schema: steps[].title
    order_index: int                  # 排序
    expected_action: str = ""         # "checklist_complete" | "agent_chat" | "quiz_verify"


@dataclass
class LessonTarget:
    """Planner 生成的单个 Lesson 测试目标"""
    lesson_id: str                    # schema: lessons[].id
    lesson_name: str                  # schema: lessons[].name
    day_index: int                    # Day N
    order: int
    steps: list[StepTarget] = field(default_factory=list)
    priority: str = "medium"          # high | medium | low


@dataclass
class PhaseTarget:
    """Planner 生成的单个 Phase 测试目标"""
    phase_id: str                     # schema: phases[].id
    phase_name: str                   # schema: phases[].name
    order: int
    lessons: list[LessonTarget] = field(default_factory=list)
    priority: str = "medium"


@dataclass
class TestPlan:
    """Planner 产出的完整测试计划"""
    phases: list[PhaseTarget] = field(default_factory=list)
    strategy: str = "full"            # full | spot_check | risk_driven
    estimated_minutes: int = 0
    risk_areas: list[str] = field(default_factory=list)
    plan_available: bool = True
    error: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def total_steps(self) -> int:
        n = sum(len(l.steps) for p in self.phases for l in p.lessons)
        if n > 0:
            return n
        # 如果无 step 数据, 按 lesson 计数
        return sum(1 for p in self.phases for _ in p.lessons)

    @property
    def total_lessons(self) -> int:
        return sum(len(p.lessons) for p in self.phases)

    def to_ws_dict(self) -> dict:
        return {
            "phases": [
                {"id": p.phase_id, "name": p.phase_name, "lessons": len(p.lessons)}
                for p in self.phases
            ],
            "strategy": self.strategy,
            "estimated_minutes": self.estimated_minutes,
            "risk_areas": self.risk_areas,
        }


@dataclass
class StepResult:
    """Executor 产出的单个 Step 执行结果"""
    phase_name: str
    lesson_name: str
    step_name: str
    step_index: int
    total_steps: int
    screenshot_path: str = ""
    dom_snapshot: dict = field(default_factory=dict)
    agent_triggered: bool = False
    agent_response: str = ""
    quiz_triggered: bool = False
    error: str = ""
    duration_seconds: float = 0.0


@dataclass
class VerificationResult:
    """Verifier 产出的单个 Step 验证结果"""
    phase_name: str
    lesson_name: str
    step_name: str
    text_pass: bool = False
    visual_pass: bool = False
    visual_skipped: bool = False
    api_pass: bool = False
    api_skipped: bool = False
    verdict: str = "pending"           # pass | fail
    text_score: Optional[float] = None
    visual_confidence: float = 0.0
    visual_reasoning: str = ""
    api_response: dict = field(default_factory=dict)
    diagnosis: str = ""


@dataclass
class Diagnosis:
    """Reporter 产出的诊断报告洞察"""
    finding: str
    severity: str                      # high | medium | low
    step: str                          # 人类可读的 Step 标识
    evidence: dict = field(default_factory=dict)


@dataclass
class DiagnosticReport:
    """Reporter 产出的完整诊断报告"""
    session_id: str = ""
    strategy: str = ""
    pass_rate: float = 0.0
    total_steps: int = 0
    failures: int = 0
    critical_failures: int = 0
    findings: list[Diagnosis] = field(default_factory=list)
    verification_results: list[VerificationResult] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "strategy": self.strategy,
            "pass_rate": self.pass_rate,
            "total_steps": self.total_steps,
            "failures": self.failures,
            "critical_failures": self.critical_failures,
            "diagnosis": {
                "pass_rate": self.pass_rate,
                "critical_failures": self.critical_failures,
                "findings": [
                    {
                        "step": f.step,
                        "verdict": "fail",
                        "severity": f.severity,
                        "reason": f.finding,
                        "evidence": f.evidence,
                    }
                    for f in self.findings
                ],
            },
            "verification_details": [
                {
                    "phase": v.phase_name,
                    "lesson": v.lesson_name,
                    "step": v.step_name,
                    "text_pass": v.text_pass,
                    "visual_pass": v.visual_pass,
                    "api_pass": v.api_pass,
                    "verdict": v.verdict,
                    "text_score": v.text_score,
                    "visual_reasoning": v.visual_reasoning[:200],
                }
                for v in self.verification_results
            ],
            "generated_at": self.generated_at,
        }
