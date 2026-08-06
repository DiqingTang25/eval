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

        # 3. 进入内容 — AI从DOM实时发现
        ev._wait_stable(2)
        dom = ev._dump_dom_state()
        entered = self._click_by_intent(dom, intent="enter the learning content for this lesson")
        if not entered:
            # 可能已直接进入内容页, 继续
            self._log("no enter button found, assuming content page")

        # 4. DOM 驱动: 发现页面上的 Step 列表
        dom = ev._dump_dom_state()
        actual_steps = self._discover_steps_from_dom(dom, lesson)

        # 5. 逐 Step 执行 — DOM 驱动
        for i, step_target in enumerate(actual_steps):
            sr = self._execute_step_dom(phase, lesson, step_target, i + 1, len(actual_steps))
            results.append(sr)

            # 下一步 — AI从DOM实时发现
            if i < len(actual_steps) - 1:
                dom = ev._dump_dom_state()
                self._click_by_intent(dom, intent="go to the next step or page")

        # 6. Agent 对话 — AI从DOM实时发现
        if results:
            dom = ev._dump_dom_state()
            agent_triggered = self._click_by_intent(dom, intent="open the AI assistant or help chat")
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

        # 完成当前 Step — AI从DOM实时发现
        dom = ev._dump_dom_state()
        self._click_by_intent(dom, intent="mark the current step as complete or done")

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

    # ── DOM 驱动: AI 语义按钮发现 (零预设, 零 hints) ──

    def _click_by_intent(self, dom: dict, intent: str) -> bool:
        """
        实时抓取页面所有按钮 → AI 语义理解 → 点击目标按钮。

        不预设任何 hint。所有判断来自当前页面的真实 DOM + LLM 语义理解。

        策略:
          1. 从 DOM 获取所有可见按钮 (text + class + 周围文本)
          2. 交给 LLM: "这些按钮中, 哪一个的语义是 '{intent}'?"
          3. LLM 返回按钮 text → 点击
          4. LLM 不可用时 → 逐个尝试所有按钮 (覆盖率优先)
        """
        buttons = dom.get("buttons", [])
        if not buttons:
            return False

        # 构建按钮清单
        btn_list = []
        for i, b in enumerate(buttons):
            if b.get("disabled"):
                continue
            btn_list.append({
                "index": i,
                "text": b.get("text", "")[:80],
                "class": b.get("class", "")[:40],
            })

        if not btn_list:
            return False

        # 1. AI 语义匹配: 让 LLM 从按钮清单中选
        chosen_text = self._ai_pick_button(btn_list, intent, dom.get("visibleText", "")[:800])
        if chosen_text:
            ok, _ = self._evaluator._find_and_click([chosen_text])
            if ok:
                self._log(f"[{intent}] AI selected: {chosen_text[:60]}")
                return True

        # 2. LLM 不可用或选择失败 → Self-Healing L3 逐按钮尝试
        for b in btn_list:
            ok, _ = self._evaluator._find_and_click([b["text"]])
            if ok:
                self._log(f"[{intent}] brute-force: {b['text'][:60]}")
                return True

        self._log(f"[{intent}] failed — {len(btn_list)} buttons tried", "warn")
        return False

    def _ai_pick_button(self, buttons: list[dict], intent: str, page_text: str) -> str:
        """
        LLM 语义匹配: 从按钮清单中选出语义最接近 intent 的按钮。

        输入: 完整按钮清单 + 页面文本上下文
        输出: 目标按钮的 text (供 _find_and_click 使用)
        失败: 返回 "" → 调用方回退到逐按钮尝试
        """
        try:
            from src.llm_client import get_llm_client
            client, model, _ = get_llm_client()
            if not client:
                return ""

            import json as _json
            btn_json = _json.dumps(buttons, ensure_ascii=False)
            prompt = f"""你是Web自动化专家。当前页面上有以下按钮:

{btn_json}

页面文本片段:
{page_text[:600]}

请找出语义最接近 "{intent}" 的按钮, 输出其 text。
- 如果找到 → {{"text": "按钮文字", "reason": "一句话解释"}}
- 如果找不到 → {{"text": "", "reason": "解释"}}
只输出JSON。"""

            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150, temperature=0.1, timeout=15,
            )
            content = resp.choices[0].message.content.strip()
            data = _json.loads(content)
            return data.get("text", "")
        except Exception:
            return ""

    # ── 动态导航 (Schema-driven, 不用硬编码文本) ──

    def _navigate_to_phase(self, phase_name: str) -> bool:
        """三层降级导航到 Phase (Agent A 4.1 P0)

        L1: URL 直接导航 — 尝试 Schema 中的 URL 模式
        L2: DOM 全元素搜索 — _find_and_click (已扩展为所有可点击元素)
        L3: AI 语义理解 — _click_by_intent (LLM 从完整 DOM 判断)
        全失败 → 返回 False, 不阻塞整个测试
        """
        # 首先生成候选 URL 列表
        url = self.target_url or os.getenv("PLATFORM_URL", "")
        if not url:
            url = getattr(self._evaluator, 'base_url', None)
            if not url:
                self._log("No URL configured", "error")
                return False

        # 提取 phase_id (从 plan 中查找, 用于 URL 构造)
        phase_id = ""
        phase_order = 0
        if self._plan:
            for p in self._plan.phases:
                if p.phase_name == phase_name:
                    phase_id = p.phase_id
                    phase_order = p.order
                    break

        # ── L1: URL 直接导航 ──────────────────────
        url_candidates = [
            url,
            f"{url.rstrip('/')}/{phase_id}" if phase_id else None,
            f"{url.rstrip('/')}/phase/{phase_id}" if phase_id else None,
            f"{url.rstrip('/')}/courses/{phase_id}" if phase_id else None,
            f"{url.rstrip('/')}?phase={phase_id}" if phase_id else None,
        ]
        for candidate in [u for u in url_candidates if u]:
            try:
                self._evaluator.page.goto(candidate, timeout=10000)
                self._evaluator._wait_stable(2)
                body = self._evaluator._get_page_text()
                if len(body) > 200 and phase_name[:4] in body:
                    self._log(f"Phase (URL): {candidate}")
                    return True
            except Exception:
                continue

        # 回到首页做 DOM 搜索
        self._evaluator.page.goto(url, timeout=30000)
        self._evaluator._wait_stable(2)

        # ── L2: DOM 全元素搜索 ────────────────────
        # 尝试完整名称
        ok, text = self._evaluator._find_and_click([phase_name])
        if ok:
            self._log(f"Phase (DOM): {text}")
            return True
        # 尝试部分匹配 (取前10个字符, 忽略后缀差异)
        if len(phase_name) > 10:
            ok, text = self._evaluator._find_and_click([phase_name[:10]])
            if ok:
                self._log(f"Phase (DOM partial): {text}")
                return True

        # ── L3: AI 语义理解 ───────────────────────
        dom = self._evaluator._dump_dom_state()
        if self._click_by_intent(dom, intent=f"navigate to the phase or course named '{phase_name}'"):
            return True

        # ── 全失败 → 跳过, 不阻塞 ──────────────────
        available = [b["text"][:50] for b in dom.get("buttons", [])[:8]]
        self._log(f"Phase SKIP: '{phase_name}' not found. Available: {available}", "warn")
        return False

    def _navigate_to_lesson(self, lesson_name: str, day_index: int) -> bool:
        """三层降级导航到 Lesson (同 Phase 逻辑)"""
        self._evaluator._wait_stable(2)

        # L1: 尝试完整 Lesson 名称
        ok, text = self._evaluator._find_and_click([lesson_name])
        if ok:
            self._log(f"Lesson (DOM): {text}")
            return True

        # L2: 部分匹配
        if len(lesson_name) > 10:
            ok, text = self._evaluator._find_and_click([lesson_name[:10]])
            if ok:
                self._log(f"Lesson (DOM partial): {text}")
                return True

        # L3: AI 语义理解
        dom = self._evaluator._dump_dom_state()
        if self._click_by_intent(dom, intent=f"navigate to the lesson or day named '{lesson_name}'"):
            return True

        available = [b["text"][:50] for b in dom.get("buttons", [])[:8]]
        self._log(f"Lesson SKIP: '{lesson_name}' not found. Available: {available}", "warn")
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
        """初始化 Playwright 浏览器"""
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        browser = p.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        # 立即导航到目标平台 (4.2 P1: 确保后续 login() 在正确的页面上)
        if self.target_url:
            try:
                page.goto(self.target_url, timeout=15000, wait_until="domcontentloaded")
            except Exception:
                pass
        self._browser = browser
        self._playwright = p
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
        """关闭浏览器并清理残留进程 (4.3 P1)"""
        import subprocess as _sp
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
        # 强制清理残留 Chrome/Playwright 进程
        import time as _time
        _time.sleep(1)
        for proc in ["chrome-headless-shell", "chromium", "playwright/driver"]:
            try:
                _sp.run(["pkill", "-f", proc], capture_output=True, timeout=5)
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
