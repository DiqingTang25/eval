"""
Planner Agent — Agent C

读 platform_schema.yaml → 生成动态 TestPlan。
三种策略: full (全量) | spot_check (抽查) | risk_driven (高风险优先)

零硬编码: Phase/Lesson/Step 名称全部来自 Schema。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from src.schema_adapter import SchemaAdapter
from src.multi_agent.models import (
    TestPlan, PhaseTarget, LessonTarget, StepTarget,
)

logger = logging.getLogger(__name__)


class PlannerAgent:
    """
    从 Schema 生成测试计划。

    用法:
        planner = PlannerAgent()
        plan = planner.generate(strategy="spot_check")
        # → TestPlan(phases=[...], estimated_minutes=5)
    """

    def __init__(self, schema_path: str = ""):
        self.schema_path = schema_path
        self._adapter: Optional[SchemaAdapter] = None

    # ── 公开 API ──

    def generate(self, strategy: str = "full", phases_filter: list[str] = None) -> TestPlan:
        """
        生成测试计划。

        :param strategy: "full" | "spot_check" | "risk_driven"
        :param phases_filter: 可选的 Phase ID 白名单 (如 ["phase_1", "phase_2"])
        :return: TestPlan
        """
        # 1. 加载 Schema
        adapter = self._load_schema()
        if adapter is None:
            return TestPlan(
                plan_available=False,
                error="platform_schema.yaml 不存在 — 请先运行 Explorer",
            )

        # 2. 读结构
        structure = adapter.raw.get("structure", {})
        schema_phases = structure.get("phases", [])
        schema_lessons = structure.get("lessons", [])
        schema_steps = structure.get("steps", [])

        if not schema_phases:
            return TestPlan(
                plan_available=False,
                error="Schema 中无 Phase 数据 — Explorer 可能未完成",
            )

        # 3. 过滤
        if phases_filter:
            schema_phases = [p for p in schema_phases if p.get("id") in phases_filter]

        # 4. 构建 PhaseTarget 列表
        phase_targets: list[PhaseTarget] = []
        for phase in sorted(schema_phases, key=lambda p: p.get("order", 0)):
            phase_id = phase.get("id", "")
            phase_name = phase.get("name", "")

            # 该 Phase 下的 Lessons
            phase_lessons = [
                l for l in schema_lessons
                if l.get("phase_id") == phase_id
            ]
            lesson_targets: list[LessonTarget] = []

            for lesson in sorted(phase_lessons, key=lambda l: l.get("order", 0)):
                lesson_id = lesson.get("id", "")
                lesson_name = lesson.get("name", lesson.get("title", ""))

                # 该 Lesson 下的 Steps
                lesson_steps = [
                    s for s in schema_steps
                    if s.get("lesson_id") == lesson_id
                ]
                step_targets: list[StepTarget] = []
                for step in sorted(lesson_steps, key=lambda s: s.get("order_index", 0)):
                    step_targets.append(StepTarget(
                        step_id=step.get("id", ""),
                        step_name=step.get("title", step.get("name", "")),
                        order_index=step.get("order_index", 0),
                    ))

                lesson_targets.append(LessonTarget(
                    lesson_id=lesson_id,
                    lesson_name=lesson_name,
                    day_index=lesson.get("order", len(lesson_targets) + 1),
                    order=lesson.get("order", 0),
                    steps=step_targets,
                    priority=self._calc_priority(phase, lesson),
                ))

            phase_targets.append(PhaseTarget(
                phase_id=phase_id,
                phase_name=phase_name,
                order=phase.get("order", 0),
                lessons=lesson_targets,
                priority=self._calc_priority(phase),
            ))

        # 5. 按策略裁剪
        if strategy == "spot_check":
            phase_targets = self._spot_check(phase_targets)
        elif strategy == "risk_driven":
            phase_targets = self._risk_driven(phase_targets)

        # 6. 估算时间
        total_lessons = sum(len(p.lessons) for p in phase_targets)
        estimated = max(1, round(total_lessons * 0.8))

        # 7. 风险区域 (从 Coverage Tracker 读取)
        risk_areas = self._load_risk_areas()

        return TestPlan(
            phases=phase_targets,
            strategy=strategy,
            estimated_minutes=estimated,
            risk_areas=risk_areas,
            plan_available=True,
        )

    # ── 策略: 抽查 ──

    @staticmethod
    def _spot_check(phases: list[PhaseTarget]) -> list[PhaseTarget]:
        """每条只保留 1-2 Day"""
        for p in phases:
            if len(p.lessons) > 2:
                # 取第一条和最后一条 (首尾抽查)
                kept = [p.lessons[0]]
                if len(p.lessons) > 1:
                    kept.append(p.lessons[-1])
                p.lessons = kept
        return phases

    # ── 策略: 风险驱动 ──

    def _risk_driven(self, phases: list[PhaseTarget]) -> list[PhaseTarget]:
        """优先测试高风险区域 (从 Coverage Tracker 读取)"""
        risk_areas = self._load_risk_areas()
        if not risk_areas:
            return self._spot_check(phases)  # 回退到抽查

        # 标记包含风险关键词的 Phase 为 high priority
        for p in phases:
            for risk in risk_areas:
                area = risk.get("area", "")
                if p.phase_name in area or p.phase_id in area:
                    p.priority = "high"
                    for l in p.lessons:
                        l.priority = "high"
                    break

        # high 优先排序
        phases.sort(key=lambda p: (0 if p.priority == "high" else 1, p.order))
        return phases

    # ── 内部 ──

    def _load_schema(self) -> Optional[SchemaAdapter]:
        if self._adapter:
            return self._adapter

        candidates = [
            self.schema_path,
            "output/platform_probe/platform_schema.yaml",
            "output/platform_schema.yaml",
        ]
        for c in candidates:
            if c and Path(c).exists():
                try:
                    self._adapter = SchemaAdapter(c)
                    return self._adapter
                except Exception as e:
                    logger.warning(f"Schema load failed from {c}: {e}")

        # 尝试 session 子目录
        probe_dir = Path("output/platform_probe")
        if probe_dir.exists():
            for subdir in sorted(probe_dir.iterdir(), reverse=True):
                if subdir.is_dir():
                    sf = subdir / "platform_schema.yaml"
                    if sf.exists():
                        try:
                            self._adapter = SchemaAdapter(str(sf))
                            return self._adapter
                        except Exception:
                            continue

        return None

    @staticmethod
    def _calc_priority(phase: dict, lesson: dict = None) -> str:
        """从 schema 推断优先级 (低覆盖率 → 高优先级)"""
        # 简单规则: 没有 step 数据的 lesson → high (需要更多探索)
        if lesson and lesson.get("step_count", 1) == 0:
            return "high"
        return "medium"

    @staticmethod
    def _load_risk_areas() -> list[dict]:
        """从 Coverage Tracker 读取风险区域"""
        try:
            import json
            report_path = Path("data/coverage_report.json")
            if report_path.exists():
                data = json.loads(report_path.read_text(encoding="utf-8"))
                return data.get("risk_areas", [])
        except Exception:
            pass
        return []
