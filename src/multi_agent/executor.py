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
        """执行单个 Lesson — 完全 DOM 驱动, 零平台假设"""
        results: list[StepResult] = []
        t0 = time.time()
        ev = self._evaluator  # shorthand

        # 1. 导航到 Phase (Schema 驱动 + Self-Healing)
        if not self._navigate_to_phase(phase.phase_name):
            return [StepResult(phase_name=phase.phase_name, lesson_name=lesson.lesson_name,
                step_name="NAVIGATION", step_index=0, total_steps=self._total_steps,
                error=f"无法导航到 Phase: {phase.phase_name}")]

        # 2. 导航到 Lesson (Schema 驱动 + Self-Healing)
        if not self._navigate_to_lesson(lesson.lesson_name, lesson.day_index):
            return [StepResult(phase_name=phase.phase_name, lesson_name=lesson.lesson_name,
                step_name="NAVIGATION", step_index=0, total_steps=self._total_steps,
                error=f"无法导航到 Lesson: {lesson.lesson_name}")]

        # 3. 进入内容 — DOM 驱动: 找页面上最可能的"进入/开始"按钮
        ev._wait_stable(2)
        dom = ev._dump_dom_state()
        entered = self._click_by_intent(dom, intent="enter_content",
            hints=["进入", "开始", "Start", "Begin", "Enter", "Continue", "Go"],
            fallback_texts=[lesson.lesson_name])  # 回退: 点 Lesson 名称
        if not entered:
            # 没有明确的进入按钮→可能已直接进入内容页, 继续
            self._log("无进入按钮, 假设已进入内容页")

        # 4. DOM 驱动: 发现页面上的 Step 列表
        dom = ev._dump_dom_state()
        actual_steps = self._discover_steps_from_dom(dom, lesson)

        # 5. 逐 Step 执行 — DOM 驱动
        for i, step_target in enumerate(actual_steps):
            sr = self._execute_step_dom(phase, lesson, step_target, i + 1, len(actual_steps))
            results.append(sr)

            # 下一步 — DOM 驱动
            if i < len(actual_steps) - 1:
                dom = ev._dump_dom_state()
                self._click_by_intent(dom, intent="next_step",
                    hints=["下一步", "Next", "→", "»", "继续", "Continue"])

        # 6. Agent 对话 — DOM 驱动: 找帮助/聊天按钮
        if results:
            dom = ev._dump_dom_state()
            agent_triggered = self._click_by_intent(dom, intent="open_help",
                hints=["帮助", "Help", "Agent", "AI", "助教", "卡住", "Stuck", "?"])
            if agent_triggered:
                results[-1].agent_triggered = True
                # 尝试发消息
                agent_q = f"你好, 可以帮我理解'{lesson.lesson_name}'中的'{actual_steps[-1].step_name}'吗?"
                try:
                    ev.trigger_agent(agent_q)
                    results[-1].agent_response = "agent triggered"
                except Exception:
                    pass

        # 7. Quiz 检查
        body = ev._get_page_text()
        results[-1].quiz_triggered = any(
            kw in body.lower() for kw in ["quiz", "测验", "答题", "题目", "question"])

        duration = time.time() - t0
        for r in results:
            r.duration_seconds = round(duration / max(len(results), 1), 1)
        return results

    def _execute_step_dom(
        self, phase: PhaseTarget, lesson: LessonTarget,
        step_target: StepTarget, idx: int, total: int,
    ) -> StepResult:
        """执行单个 Step — DOM 驱动"""
        self._log(f"[{phase.phase_name}] {lesson.lesson_name} → {step_target.step_name} ({idx}/{total})")
        ev = self._evaluator

        # 勾选 checklist (如果有)
        try:
            for cb in ev.page.locator("input[type=checkbox]").all():
                if cb.is_visible() and not cb.is_checked():
                    cb.check(); time.sleep(0.2)
        except Exception:
            pass

        # 完成当前 Step — DOM 驱动: 找"完成/提交/标记"按钮
        dom = ev._dump_dom_state()
        self._click_by_intent(dom, intent="complete_step",
            hints=["完成", "Done", "Complete", "Finish", "Submit", "提交", "标记", "Mark", "✓"])

        # 截图
        ss_name = f"ma_{phase.phase_id}_{lesson.day_index}_step{idx}"
        ev._ss(ss_name)
        screenshot_path = str(self._screenshot_dir / f"{ev._ss_count:04d}_{ss_name}.png")

        dom = ev._dump_dom_state()
        return StepResult(
            phase_name=phase.phase_name, lesson_name=lesson.lesson_name,
            step_name=step_target.step_name, step_index=0, total_steps=0,
            screenshot_path=screenshot_path, dom_snapshot=dom,
        )

    # ── DOM 驱动: 语义按钮发现 ──

    def _click_by_intent(
        self, dom: dict, intent: str, hints: list[str], fallback_texts: list[str] = None
    ) -> bool:
        """
        根据语义意图点击页面上最可能的按钮 — 零硬编码。

        策略:
          1. 从 DOM 获取所有可见按钮
          2. 用 hints 关键词匹配 (多语言)
          3. 最匹配的按钮 → 点击
          4. 都不匹配 → 用 fallback_texts (如 Phase/Lesson 名称)
          5. 全部失败 → Self-Healing L3 (AI) 自动介入

        这是通用方法, 不包含任何平台特定的文本。
        """
        buttons = dom.get("buttons", [])
        if not buttons:
            return False

        # 1. 关键词匹配 (不区分大小写)
        candidates = []
        for b in buttons:
            if b.get("disabled"):
                continue
            text = (b.get("text", "") + " " + b.get("class", "")).lower()
            score = sum(1 for h in hints if h.lower() in text)
            if score > 0:
                candidates.append((b["text"], score))

        candidates.sort(key=lambda x: -x[1])

        # 2. 尝试点击最佳匹配
        for text, score in candidates:
            ok, _ = self._evaluator._find_and_click([text])
            if ok:
                self._log(f"[{intent}] {text[:60]} (score={score})")
                return True

        # 3. 回退: 用 fallback_texts (如 Lesson 名称)
        if fallback_texts:
            for t in fallback_texts:
                if t:
                    ok, _ = self._evaluator._find_and_click([t])
                    if ok:
                        self._log(f"[{intent}] fallback: {t[:60]}")
                        return True

        # 4. Self-Healing L3 会自动介入 (_find_and_click 内部)
        # 如果所有关键词都不匹配, 尝试点击第一个非禁用按钮
        for b in buttons:
            if not b.get("disabled") and b.get("text", "").strip():
                ok, _ = self._evaluator._find_and_click([b["text"]])
                if ok:
                    self._log(f"[{intent}] last-resort: {b['text'][:60]}")
                    return True

        self._log(f"[{intent}] no button found (hints={hints[:4]})", "warn")
        return False

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
        """从 平台Profile + Schema + 环境变量 获取登录凭证 (动态适配不同平台)"""
        creds = {}
        # 1. 从 platform_profile.json 读取 (最优先: 探索时保存的凭证)
        try:
            profile_path = Path("output/platform_probe/platform_profile.json")
            if profile_path.exists():
                import json as _json
                profile = _json.loads(profile_path.read_text(encoding="utf-8"))
                pc = profile.get("credentials", {})
                if pc.get("username"):
                    creds["username"] = pc["username"]
                if pc.get("password"):
                    creds["password"] = pc["password"]
                if pc.get("login_url"):
                    creds["login_url"] = pc["login_url"]
        except Exception:
            pass
        # 2. 环境变量覆盖
        if os.getenv("PLATFORM_USERNAME"):
            creds["username"] = os.getenv("PLATFORM_USERNAME")
        if os.getenv("PLATFORM_PASSWORD"):
            creds["password"] = os.getenv("PLATFORM_PASSWORD")
        # 3. 从 Schema 读取 login_url
        try:
            from src.schema_adapter import SchemaAdapter
            candidates = ["output/platform_probe/platform_schema.yaml", "output/platform_schema.yaml"]
            for c in candidates:
                if Path(c).exists():
                    adapter = SchemaAdapter(c)
                    auth = adapter.get_auth()
                    if auth.get("login_url") and "login_url" not in creds:
                        creds["login_url"] = auth["login_url"]
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
