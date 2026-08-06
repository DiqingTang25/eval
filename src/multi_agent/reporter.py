"""
Reporter Agent — Agent C

合成 Planner + Executor + Verifier 的全部产出 → 生成诊断报告。

与现有 Reporter 的区别:
  现有: 分数列表 + 对话记录 (数据堆砌)
  新增: 诊断洞察 — 不仅说"几分", 还说"为什么失败", "建议修什么"
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.multi_agent.models import (
    TestPlan, VerificationResult, Diagnosis, DiagnosticReport,
)

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("eval_output/multi_agent")


class ReporterAgent:
    """
    生成诊断报告。

    用法:
        reporter = ReporterAgent()
        report = reporter.generate(session_id, plan, verifications, coverage)
        path = reporter.save(report)
    """

    def __init__(self):
        self._last_report: Optional[DiagnosticReport] = None

    # ── 公开 API ──

    def generate(
        self,
        session_id: str,
        plan: TestPlan,
        verifications: list[VerificationResult],
        coverage: dict = None,
    ) -> DiagnosticReport:
        """
        生成完整诊断报告。

        :param session_id: 评测会话 ID
        :param plan: Planner 产出的 TestPlan
        :param verifications: Verifier 产出的验证结果列表
        :param coverage: Coverage Tracker 产出的覆盖率数据 (可选)
        """
        total = len(verifications)
        passed = sum(1 for v in verifications if v.verdict == "pass")
        failed = total - passed

        # 关键失败 (三通道全部 fail 或 text + visual 都 fail)
        critical = sum(
            1 for v in verifications
            if v.verdict == "fail" and not v.text_pass and not v.visual_pass
        )

        pass_rate = round(passed / max(total, 1), 3)

        # 生成诊断发现
        findings = self._generate_findings(verifications, plan)

        # 覆盖率变化
        coverage_delta = {}
        if coverage:
            coverage_delta = {
                "before": coverage.get("overall", {}).get("coverage_pct", 0),
                "after_note": "本次测试后覆盖已更新",
            }

        report = DiagnosticReport(
            session_id=session_id,
            strategy=plan.strategy,
            pass_rate=pass_rate,
            total_steps=total,
            failures=failed,
            critical_failures=critical,
            findings=findings,
            verification_results=verifications,
            coverage=coverage_delta,
        )
        self._last_report = report
        return report

    def save(self, report: DiagnosticReport = None) -> str:
        """保存报告到 JSON 文件"""
        if report is None:
            report = self._last_report
        if report is None:
            return ""

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = OUTPUT_DIR / f"multi_agent_report_{ts}.json"

        data = report.to_dict()
        data["evidence_summary"] = self._build_evidence_summary(report)

        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return str(path)

    def get_last_report(self) -> Optional[DiagnosticReport]:
        return self._last_report

    # ── 诊断生成 ──

    def _generate_findings(
        self, verifications: list[VerificationResult], plan: TestPlan,
    ) -> list[Diagnosis]:
        """从验证结果中提取诊断洞察"""
        findings: list[Diagnosis] = []

        for v in verifications:
            step_label = f"{v.phase_name} → {v.lesson_name} → {v.step_name}"

            if v.verdict == "fail":
                # 分类失败模式
                if not v.text_pass and not v.visual_pass:
                    findings.append(Diagnosis(
                        finding=f"严重失败: 文本评分和视觉验证均不通过 — {v.diagnosis}",
                        severity="high",
                        step=step_label,
                        evidence={
                            "text_score": v.text_score,
                            "visual_reasoning": v.visual_reasoning[:150],
                        },
                    ))
                elif not v.visual_pass and not v.visual_skipped:
                    findings.append(Diagnosis(
                        finding=f"视觉验证失败 (文本通过): {v.visual_reasoning[:150]}",
                        severity="medium",
                        step=step_label,
                        evidence={"visual_confidence": v.visual_confidence},
                    ))
                elif not v.text_pass:
                    findings.append(Diagnosis(
                        finding=f"文本评分偏低 ({v.text_score}): 回答可能不准确或不完整",
                        severity="medium",
                        step=step_label,
                        evidence={"text_score": v.text_score},
                    ))
                elif not v.api_pass and not v.api_skipped:
                    findings.append(Diagnosis(
                        finding=f"API验证失败: {v.api_response}",
                        severity="low",
                        step=step_label,
                    ))

        # 排序: high → medium → low
        findings.sort(key=lambda f: {"high": 0, "medium": 1, "low": 2}.get(f.severity, 3))
        return findings

    @staticmethod
    def _build_evidence_summary(report: DiagnosticReport) -> dict:
        """构建证据摘要 (供 Reports 页面展示)"""
        text_ok = sum(1 for v in report.verification_results if v.text_pass)
        visual_ok = sum(1 for v in report.verification_results if v.visual_pass and not v.visual_skipped)
        api_ok = sum(1 for v in report.verification_results if v.api_pass and not v.api_skipped)
        visual_skipped = sum(1 for v in report.verification_results if v.visual_skipped)
        api_skipped = sum(1 for v in report.verification_results if v.api_skipped)
        total = max(len(report.verification_results), 1)

        return {
            "channels": {
                "text": f"{text_ok}/{total}",
                "visual": f"{visual_ok}/{total - visual_skipped}" if visual_skipped < total else "skipped",
                "api": f"{api_ok}/{total - api_skipped}" if api_skipped < total else "skipped",
            },
            "degradation": {
                "visual_skipped": visual_skipped > 0,
                "api_skipped": api_skipped > 0,
            },
        }
