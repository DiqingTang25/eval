"""
Multi-Agent Orchestrator — Agent C

协调 Planner → Executor → Verifier → Reporter 四 Agent 流水线。
发送 WebSocket 事件 (格式锁定, 对齐 Agent A 要求)。

降级控制:
  - Schema 缺失 → Planner 返回 plan_available=false → 中止
  - MCP 不可用 → Verifier 跳过 API 通道
  - Visual 不可用 → Verifier 跳过 Visual 通道
  - 全部降级 → 回退到现有 BrowserEvaluator.run()

用法:
    orch = MultiAgentOrchestrator(ws_callback=..., strategy="spot_check")
    report = orch.run()
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from src.multi_agent.planner import PlannerAgent
from src.multi_agent.executor import ExecutorAgent
from src.multi_agent.verifier import VerifierAgent
from src.multi_agent.reporter import ReporterAgent
from src.multi_agent.models import TestPlan, DiagnosticReport

logger = logging.getLogger(__name__)


class MultiAgentOrchestrator:
    """
    Multi-Agent 测试编排器。

    :param ws_callback: WebSocket 事件回调 (async callable)
    :param strategy: "full" | "spot_check" | "risk_driven"
    :param phases_filter: 可选的 Phase ID 白名单
    :param headless: 浏览器是否无头
    :param mode: "guided" | "self"
    """

    def __init__(
        self,
        ws_callback: Callable = None,
        strategy: str = "spot_check",
        phases_filter: list[str] = None,
        headless: bool = True,
        mode: str = "guided",
        target_url: str = "",
    ):
        self.ws_callback = ws_callback
        self.strategy = strategy
        self.phases_filter = phases_filter
        self.headless = headless
        self.mode = mode
        self.target_url = target_url
        self.session_id = f"multi_agent_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    # ── 公开 API ──

    def run(self) -> DiagnosticReport:
        """
        执行完整的 Multi-Agent 流水线。

        :return: DiagnosticReport
        """
        # ── Phase 1: Plan ──────────────────────────────
        self._emit("multi_agent:plan_ready", {"status": "generating"})

        planner = PlannerAgent()
        plan = planner.generate(
            strategy=self.strategy,
            phases_filter=self.phases_filter,
        )

        if not plan.plan_available:
            self._emit("multi_agent:done", {
                "error": plan.error,
                "report_path": "",
                "pass_rate": 0,
                "total_steps": 0,
                "failures": 0,
            })
            return DiagnosticReport(
                session_id=self.session_id,
                strategy=self.strategy,
            )

        # DIAG: 记录 plan 详情到 /tmp
        try:
            import json as _json, os as _os
            _d = plan.to_ws_dict()
            _d["_phase_count"] = len(plan.phases)
            _d["_total_lessons"] = sum(len(p.lessons) for p in plan.phases)
            _d["_cwd"] = _os.getcwd()
            _path = __import__('tempfile').gettempdir() + '/orchestrator_plan.json'
            with open(_path, 'w') as _f:
                _json.dump(_d, _f, indent=2, default=str)
        except Exception as _e:
            import traceback as _tb
            logger.error(f"Plan diag write failed: {_e}\n{_tb.format_exc()}")

        self._emit("multi_agent:plan_ready", plan.to_ws_dict())

        # ── Phase 2: Execute ───────────────────────────
        executor = ExecutorAgent(headless=self.headless, mode=self.mode, target_url=self.target_url)
        executor.set_plan(plan)

        step_results = []
        verifications = []

        verifier = VerifierAgent()

        for step in executor.execute():
            if step.error:
                self._emit("multi_agent:diagnosis", {
                    "finding": step.error,
                    "severity": "high",
                    "step": f"{step.phase_name} → {step.step_name}",
                })
                continue

            step_results.append(step)

            self._emit("multi_agent:step_start", {
                "phase": step.phase_name,
                "lesson": step.lesson_name,
                "step": step.step_name,
                "step_index": step.step_index,
                "total_steps": step.total_steps,
            })

            # 验证
            v = verifier.verify(step)
            verifications.append(v)

            self._emit("multi_agent:verify_done", {
                "text_pass": v.text_pass,
                "visual_pass": v.visual_pass,
                "api_pass": v.api_pass,
                "verdict": v.verdict,
                "text_score": v.text_score,
            })

            if v.verdict == "fail":
                self._emit("multi_agent:diagnosis", {
                    "finding": v.diagnosis,
                    "severity": "medium" if v.text_pass else "high",
                    "step": f"{v.phase_name} → {v.step_name}",
                })

        executor.close()

        # ── Phase 3: Coverage ──────────────────────────
        coverage = {}
        try:
            from src.coverage_tracker import compute_coverage_after_eval
            cov_report = compute_coverage_after_eval()
            if cov_report.get("schema_available"):
                coverage = cov_report
        except Exception as e:
            logger.warning(f"Coverage unavailable: {e}")

        # ── Phase 4: Report ────────────────────────────
        reporter = ReporterAgent()
        report = reporter.generate(
            session_id=self.session_id,
            plan=plan,
            verifications=verifications,
            coverage=coverage,
        )
        report_path = reporter.save(report)

        self._emit("multi_agent:done", {
            "report_path": report_path,
            "pass_rate": report.pass_rate,
            "total_steps": report.total_steps,
            "failures": report.failures,
        })

        return report

    # ── 内部 ──

    def _emit(self, event_type: str, data: dict):
        """发送 WebSocket 事件 (Agent A 格式)"""
        if self.ws_callback:
            try:
                self.ws_callback(event_type, data)
            except Exception as e:
                logger.warning(f"WS emit failed: {e}")
