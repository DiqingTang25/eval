"""
Multi-Agent 测试编排系统 — Agent C

Planner → Executor → Verifier → Reporter
Schema 驱动, 零硬编码, 三通道验证 (Text/Visual/API)

用法:
    from src.multi_agent import MultiAgentOrchestrator
    orch = MultiAgentOrchestrator(strategy="spot_check")
    report = orch.run()
"""
from src.multi_agent.orchestrator import MultiAgentOrchestrator
from src.multi_agent.models import TestPlan, DiagnosticReport

__all__ = ["MultiAgentOrchestrator", "TestPlan", "DiagnosticReport"]
