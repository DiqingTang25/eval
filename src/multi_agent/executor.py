"""
Executor Agent — Agent C

包装 BrowserEvaluator，按 TestPlan 动态导航。
不调用 BrowserEvaluator.run() (硬编码) → 使用基础方法自建循环。

Schema 驱动: Phase/Lesson/Step 名称来自 TestPlan, 不是硬编码。
Self-Healing: _find_and_click 失败时自动四层回退。
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from src.browser_evaluator import BrowserEvaluator, StepResult as BEStepResult
from src.multi_agent.models import TestPlan, PhaseTarget, LessonTarget, StepTarget, StepResult

logger = logging.getLogger(__name__)


class ExecutorAgent:
    """
    按 TestPlan 执行浏览器测试。

    用法:
        executor = ExecutorAgent(headless=True)
        executor.set_plan(plan)
        for step_result in executor.execute():
            # 每个 Step 产出 StepResult + 截图
            ...
    """

    def __init__(self, headless: bool = True, mode: str = "guided", target_url: str = ""):
        self.headless = headless
        self.mode = mode
        self.target_url = target_url
        self._evaluator: Optional[BrowserEvaluator] = None
        self._plan: Optional[TestPlan] = None
        self._step_index = 0
        self._total_steps = 0
        self._screenshot_dir = Path("eval_output/screenshots")
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

    # ── 公开 API ──

    def set_plan(self, plan: TestPlan):
        self._plan = plan
        self._total_steps = plan.total_steps
        self._step_index = 0

    def execute(self):
        """
        生成器: 按 TestPlan 逐步执行, 每步 yield StepResult。

        调用方 (Orchestrator) 负责:
          - 接收 StepResult → 发给 Verifier
          - 发送 WebSocket 事件
        """
        if not self._plan or not self._plan.plan_available:
            yield StepResult(
                phase_name="", lesson_name="", step_name="",
                step_index=0, total_steps=0,
                error=self._plan.error if self._plan else "No plan",
            )
            return

        with self._init_browser() as page:
            self._evaluator.page = page

            # 1. 登录 — 传入 Schema 中的认证信息 (动态适配不同平台的登录方式)
            creds = self._get_auth_credentials()
            if not self._evaluator.login(credentials=creds):
                yield StepResult(
                    phase_name="LOGIN", lesson_name="", step_name="",
                    step_index=0, total_steps=self._total_steps,
                    error=f"登录失败 (url={self.target_url or self._evaluator.base_url})",
                )
                return

            # 2. 逐 Phase → Lesson → Step
            for phase in self._plan.phases:
                for lesson in phase.lessons:
                    results = self._execute_lesson(phase, lesson)
                    for r in results:
                        self._step_index += 1
                        r.step_index = self._step_index
                        r.total_steps = self._total_steps
                        yield r

    # ── Lesson 执行 ──

    def _execute_lesson(self, phase: PhaseTarget, lesson: LessonTarget) -> list[StepResult]:
        """执行单个 Lesson 的所有 Steps"""
        results: list[StepResult] = []
        t0 = time.time()

        # 1. 导航到 Phase
        if not self._navigate_to_phase(phase.phase_name):
            return [StepResult(
                phase_name=phase.phase_name,
                lesson_name=lesson.lesson_name,
                step_name="NAVIGATION",
                step_index=0, total_steps=self._total_steps,
                error=f"无法导航到 Phase: {phase.phase_name}",
            )]

        # 2. 导航到 Lesson (Day)
        if not self._navigate_to_lesson(lesson.lesson_name, lesson.day_index):
            return [StepResult(
                phase_name=phase.phase_name,
                lesson_name=lesson.lesson_name,
                step_name="NAVIGATION",
                step_index=0, total_steps=self._total_steps,
                error=f"无法导航到 Lesson: {lesson.lesson_name}",
            )]

        # 3. 进入学习模式
        if not self._evaluator.enter_learning_mode(self.mode):
            return [StepResult(
                phase_name=phase.phase_name,
                lesson_name=lesson.lesson_name,
                step_name="ENTER_MODE",
                step_index=0, total_steps=self._total_steps,
                error=f"无法进入 {self.mode} 模式",
            )]

        # 4. 获取页面当前 DOM 状态 → 发现实际 Steps
        dom = self._evaluator._dump_dom_state()

        # 5. 执行 Steps
        actual_steps = self._discover_steps_from_dom(dom, lesson)
        for i, step_target in enumerate(actual_steps):
            sr = self._execute_step(phase, lesson, step_target, i + 1, len(actual_steps))
            results.append(sr)

            # 如果不是最后一步, 点"下一步"
            if i < len(actual_steps) - 1:
                self._evaluator.go_next_step()

        # 6. 在最后一个 Step 触发 Agent 对话
        if lesson.steps and results:
            last_step = lesson.steps[-1]
            agent_q = (
                f"你好, 我在做 {phase.phase_name} 的 {lesson.lesson_name} 中的 "
                f"{last_step.step_name}, 可以帮我理解这部分内容吗?"
            )
            agent_result = self._evaluator.trigger_agent(agent_q)
            results[-1].agent_triggered = agent_result.get("ok", False)
            results[-1].agent_response = str(agent_result.get("body_delta", ""))

        # 7. 检查 Quiz
        body = self._evaluator._get_page_text()
        if any(kw in body.lower() for kw in ["quiz", "测验", "答题", "题目"]):
            results[-1].quiz_triggered = True
            self._evaluator._ss(f"quiz_{phase.phase_id}_{lesson.day_index}")

        duration = time.time() - t0
        for r in results:
            r.duration_seconds = round(duration / max(len(results), 1), 1)

        return results

    def _execute_step(
        self, phase: PhaseTarget, lesson: LessonTarget,
        step_target: StepTarget, idx: int, total: int,
    ) -> StepResult:
        """执行单个 Step"""
        self._log(f"[{phase.phase_name}] {lesson.lesson_name} → {step_target.step_name} ({idx}/{total})")

        # 勾选 checklist + 点"本步已完成"
        be_result: BEStepResult = self._evaluator.complete_step(idx)

        # 截图
        ss_name = f"ma_{phase.phase_id}_{lesson.day_index}_step{idx}"
        self._evaluator._ss(ss_name)

        screenshot_path = str(self._screenshot_dir / f"{self._evaluator._ss_count:04d}_{ss_name}.png")

        dom = self._evaluator._dump_dom_state()

        return StepResult(
            phase_name=phase.phase_name,
            lesson_name=lesson.lesson_name,
            step_name=step_target.step_name,
            step_index=0, total_steps=0,  # 由 execute() 填充
            screenshot_path=screenshot_path,
            dom_snapshot=dom,
            error=be_result.error,
        )

    # ── 动态导航 (Schema-driven, 不用硬编码文本) ──

    def _navigate_to_phase(self, phase_name: str) -> bool:
        """用 Schema 中的 Phase 名称导航"""
        # 回到首页 — 使用动态 URL (target_url > env > fallback)
        url = self.target_url or os.getenv("PLATFORM_URL", "")
        if not url:
            url = getattr(self._evaluator, 'base_url', None) or "http://124.174.108.70"
        self._evaluator.page.goto(url, timeout=60000)
        self._evaluator._wait_stable(2)

        # 用 Phase 名称点击 (Self-Healing 会自动回退)
        ok, text = self._evaluator._find_and_click([phase_name])
        if ok:
            self._log(f"Phase: {text}")
            return True

        # 回退: 用数字匹配 (如 "Phase 01")
        import re
        nums = re.findall(r'\d+', phase_name)
        if nums:
            for fmt in [f"Phase {nums[0]}", f"Phase 0{nums[0]}", f"0{nums[0]}"]:
                ok, text = self._evaluator._find_and_click([fmt])
                if ok:
                    self._log(f"Phase (fallback): {text}")
                    return True

        self._log(f"Phase NOT FOUND: {phase_name}", "error")
        return False

    def _navigate_to_lesson(self, lesson_name: str, day_index: int) -> bool:
        """用 Schema 中的 Lesson 名称导航"""
        self._evaluator._wait_stable(2)

        # 优先用 Lesson 名称
        ok, text = self._evaluator._find_and_click([lesson_name])
        if ok:
            self._log(f"Lesson: {text}")
            return True

        # 回退: Day N
        for fmt in [f"Day {day_index}", f"Day 0{day_index}"]:
            ok, text = self._evaluator._find_and_click([fmt])
            if ok:
                self._log(f"Lesson (fallback): {text}")
                return True

        # 回退: 按 CSS class (lesson-card)
        try:
            for btn in self._evaluator.page.locator("button.lesson-card, button[class*=lesson]").all():
                t = (btn.text_content() or "").strip()
                if f"Day {day_index}" in t and not btn.is_disabled():
                    btn.click()
                    self._log(f"Lesson (CSS): {t[:80]}")
                    return True
        except Exception:
            pass

        self._log(f"Lesson NOT FOUND: {lesson_name}", "error")
        return False

    @staticmethod
    def _discover_steps_from_dom(dom: dict, lesson: LessonTarget) -> list[StepTarget]:
        """
        从页面 DOM 动态发现 Steps。

        优先使用 schema 中的 step 数据; 如果 schema 没有 step 数据
        (Agent B: DOM-heavy 平台), 从 _dump_dom_state 提取。
        """
        # 优先: Schema 中的 steps
        if lesson.steps:
            return lesson.steps

        # 回退: 从 DOM 文本提取 step-like 模式
        visible = dom.get("visibleText", "")
        import re
        step_patterns = re.findall(
            r'(?:Step|步骤)\s*(\d+)\s*[:：]?\s*([^\n]{5,60})',
            visible, re.IGNORECASE,
        )
        if step_patterns:
            return [
                StepTarget(
                    step_id=f"dom_step_{num}",
                    step_name=f"Step {num}: {desc.strip()}",
                    order_index=int(num),
                )
                for num, desc in step_patterns[:20]
            ]

        # 回退: 从 interactive_elements 提取
        elements = dom.get("buttons", [])
        step_buttons = [
            b for b in elements
            if any(kw in (b.get("text", "") + b.get("class", "")).lower()
                   for kw in ["step", "checklist", "mini-step"])
        ]
        if step_buttons:
            return [
                StepTarget(
                    step_id=f"dom_btn_{i}",
                    step_name=b.get("text", f"Step {i+1}"),
                    order_index=i + 1,
                )
                for i, b in enumerate(step_buttons[:20])
            ]

        # 最终回退: 占位 Step
        return [
            StepTarget(
                step_id=f"placeholder_{i}",
                step_name=f"Step {i+1}",
                order_index=i + 1,
            )
            for i in range(5)  # 默认 5 Steps
        ]

    # ── 内部 ──

    def _init_browser(self):
        """初始化 Playwright 浏览器 (复用 BrowserEvaluator 的逻辑)"""
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        browser = p.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        self._browser = browser
        self._playwright = p
        # 创建 BrowserEvaluator 实例, 传入 target_url 覆盖硬编码 BASE_URL
        if self._evaluator is None:
            self._evaluator = BrowserEvaluator(headless=self.headless, base_url=self.target_url)
        return _BrowserContext(page, browser, p)

    def _get_auth_credentials(self) -> dict:
        """从 Schema + 环境变量 获取登录凭证 (动态适配不同平台)"""
        creds = {
            "username": os.getenv("PLATFORM_USERNAME", ""),
            "password": os.getenv("PLATFORM_PASSWORD", ""),
        }
        # 尝试从 Schema 读取
        try:
            from src.schema_adapter import SchemaAdapter
            candidates = ["output/platform_probe/platform_schema.yaml", "output/platform_schema.yaml"]
            for c in candidates:
                if Path(c).exists():
                    adapter = SchemaAdapter(c)
                    auth = adapter.get_auth()
                    creds["login_url"] = auth.get("login_url", "")
                    # Schema 中的 fields 可能包含字段名提示
                    for f in auth.get("fields", []):
                        if "user" in str(f).lower():
                            creds["username_field"] = str(f)
                        elif "pass" in str(f).lower():
                            creds["password_field"] = str(f)
                    break
        except Exception:
            pass
        return creds

    def _log(self, msg: str, level: str = "info"):
        prefix = {"info": "  [E]", "ok": "  [E] OK", "warn": "  [E] WARN", "error": "  [E] ERR"}
        print(f"{prefix.get(level, '  [E]')} {msg}")

    def close(self):
        if hasattr(self, '_browser') and self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if hasattr(self, '_playwright') and self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass

    @property
    def evaluator(self) -> BrowserEvaluator:
        if self._evaluator is None:
            self._evaluator = BrowserEvaluator(
                headless=self.headless,
                mode=self.mode,
                base_url=self.target_url,  # 动态 URL, 覆盖硬编码 BASE_URL
            )
            # 启用 Self-Healing
            from src.self_healing import apply_self_healing
            apply_self_healing(self._evaluator)
        return self._evaluator


class _BrowserContext:
    """轻量上下文管理器 — 提供 BrowserEvaluator 的 page 注入"""
    def __init__(self, page, browser, playwright):
        self.page = page
        self._browser = browser
        self._playwright = playwright

    def __enter__(self):
        return self.page

    def __exit__(self, *args):
        try:
            self._browser.close()
        except Exception:
            pass
        try:
            self._playwright.stop()
        except Exception:
            pass
