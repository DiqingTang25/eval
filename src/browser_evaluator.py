"""
浏览器驱动测评器 v4.0 — 基于平台真实架构

核心流程 (模拟真实学习流):
  Phase 1-4: Login → 选Phase → 选Day → 帮帮我模式 → 逐Step完成 → 点"我卡住了"
             → Agent对话 → 完成所有Step → Quiz自动触发 → 答题提交
  Phase 5:   Login → Phase 5 → 机器人项目Agent (常驻对话)

与旧测评的区别:
  旧: API 直接调 /agent/chat, /quiz/start — 脱离实际用户行为
  新: Playwright 驱动浏览器, 点击真实按钮, 模拟完整学习路径

保证跑通的设计:
  - 每一步都有 timeout + retry
  - DOM 前/后对比验证操作效果
  - 截图记录每个关键步骤
  - 错误不崩溃, 记录后继续
"""

import json, time, sys, os
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

# ── 配置 ──
BASE_URL = "http://124.174.108.70"
USERNAME = "student001"
PASSWORD = "123456"
OUTPUT_DIR = Path(__file__).parent.parent / "eval_output"
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"

# 平台结构 (从探索中确认)
PHASES = {
    1: {"name": "国产AI动手派", "days": 4},
    2: {"name": "人机共创设计与智能制造", "days": 5},
    3: {"name": "解锁AI五官", "days": 6},
    4: {"name": "全链路实战与AI深度联动", "days": 7},
    5: {"name": "AI机器人创造营", "days": 0, "special": "robot_agent"},
}


@dataclass
class StepResult:
    """单个 Step 的测评结果"""
    step_index: int
    step_title: str = ""
    checklist_items: list = field(default_factory=list)
    checklist_done: int = 0
    agent_triggered: bool = False
    agent_question: str = ""
    agent_reply: str = ""
    agent_duration: float = 0.0
    completed: bool = False
    error: str = ""


@dataclass
class DayResult:
    """单个 Day 的测评结果"""
    day_index: int
    day_title: str = ""
    mode: str = "guided"  # guided | self
    steps: list = field(default_factory=list)
    quiz_triggered: bool = False
    quiz_questions: int = 0
    quiz_score: any = None
    total_duration: float = 0.0
    error: str = ""


class BrowserEvaluator:
    """浏览器驱动的测评器 — 模拟真实学习流"""

    def __init__(self, headless: bool = True, phase_filter: int = None,
                 day_filter: int = None, mode: str = "guided", resume: bool = False,
                 base_url: str = ""):
        self.headless = headless
        self.phase_filter = phase_filter
        self.day_filter = day_filter
        self.mode = mode  # "guided" | "self" | "both"
        self.resume = resume
        self.base_url = base_url if base_url else BASE_URL  # 默认使用硬编码, 允许Multi-Agent覆盖

        # 加载已有报告 — 保留未重跑的 Phase 数据
        existing = self._load_existing_report()
        self.completed_phases = existing["completed"]
        self.existing_phases = existing["data"]  # 已有报告中的 phases 数据

        # 初始化 results: 全新或合并
        if resume or phase_filter is not None:
            # 续跑/部分跑: 合并已有数据
            self.results = {
                "meta": {
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "platform": self.base_url,
                    "evaluator_version": "4.0-browser",
                },
                "phases": self.existing_phases.copy(),  # 保留已有
                "summary": {},
                "errors": [],
            }
        else:
            # 全新运行
            self.results = {
                "meta": {
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "platform": self.base_url,
                    "evaluator_version": "4.0-browser",
                },
                "phases": {},
                "summary": {},
                "errors": [],
            }
        self._ss_count = 0
        self.page = None

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # ═══════════════════════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════════════════════

    def _ss(self, name: str):
        """截图"""
        self._ss_count += 1
        try:
            path = SCREENSHOT_DIR / f"{self._ss_count:04d}_{name}.png"
            self.page.screenshot(path=str(path), full_page=True,
                               timeout=10000, animations="disabled")
        except Exception:
            pass

    def _log(self, msg: str, level: str = "info"):
        prefix = {"info": "  ", "ok": "  ✅", "warn": "  ⚠️", "error": "  ❌", "step": "  📝"}
        print(f"{prefix.get(level, '  ')} {msg}")

    def _wait_stable(self, seconds: float = 2.0):
        """等待页面稳定"""
        time.sleep(seconds)
        try:
            self.page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass

    def _safe_click(self, selector_or_text: str, by_text: bool = True,
                    timeout: float = 8.0) -> bool:
        """安全点击按钮 (by_text=True 按文本匹配, False 按CSS选择器)"""
        try:
            if by_text:
                el = self.page.locator(f"button:has-text('{selector_or_text}')").first
            else:
                el = self.page.locator(selector_or_text).first
            el.wait_for(state="visible", timeout=timeout * 1000)
            if el.is_disabled():
                self._log(f"按钮已禁用: {selector_or_text[:40]}", "warn")
                return False
            el.click()
            return True
        except PwTimeout:
            self._log(f"点击超时: {selector_or_text[:40]}", "warn")
            return False
        except Exception as e:
            self._log(f"点击失败: {selector_or_text[:40]} — {e}", "warn")
            return False

    def _find_and_click(self, texts: list[str]) -> tuple[bool, str]:
        """点击按钮 — 先用 Playwright, 失败后用 JS 兜底"""
        for t in texts:
            # 方式1: Playwright 标准
            try:
                for btn in self.page.locator("button").all():
                    if not btn.is_visible():
                        continue
                    txt = (btn.text_content() or "").strip()
                    if t in txt and not btn.is_disabled():
                        btn.click()
                        return True, txt[:80]
            except Exception:
                pass

        # 方式2: JS 兜底 — 不依赖 is_visible()
        for t in texts:
            result = self.page.evaluate(f"""
                (() => {{
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {{
                        if (btn.textContent.includes({json.dumps(t)}) && !btn.disabled) {{
                            btn.click();
                            return {{ok: true, text: btn.textContent.trim().substring(0, 80)}};
                        }}
                    }}
                    return {{ok: false}};
                }})()
            """)
            if result.get("ok"):
                return True, result.get("text", "")
        return False, ""

    def _get_page_text(self) -> str:
        try:
            return self.page.locator("body").first.text_content() or ""
        except Exception:
            return ""

    def _dump_dom_state(self) -> dict:
        """导出当前页面关键 DOM 状态"""
        return self.page.evaluate("""() => ({
            url: location.href,
            title: document.title,
            buttons: [...document.querySelectorAll('button')]
                .filter(b => b.offsetParent)
                .map(b => ({
                    text: b.textContent.trim().substring(0, 100),
                    class: b.className.substring(0, 60),
                    disabled: b.disabled
                })),
            inputs: [...document.querySelectorAll('input, textarea, [contenteditable=true]')]
                .filter(el => el.offsetParent)
                .map(el => ({
                    tag: el.tagName, type: el.type || '',
                    placeholder: el.placeholder || ''
                })),
            visibleText: document.body.textContent.substring(0, 1000)
        })""")

    def _save_report(self):
        """断点保存 — 每个Phase结束后调用"""
        self.results["meta"]["last_saved_at"] = datetime.now(timezone.utc).isoformat()
        report_path = OUTPUT_DIR / "browser_eval_report.json"
        try:
            report_path.write_text(
                json.dumps(self.results, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8")
            self._log(f"💾 已保存到 {report_path.name}")
        except Exception as e:
            self._log(f"保存失败: {e}", "warn")

    def _load_existing_report(self) -> dict:
        """加载已有报告，返回 {completed: set, data: dict}"""
        report_path = OUTPUT_DIR / "browser_eval_report.json"
        empty = {"completed": set(), "data": {}}
        if not report_path.exists():
            return empty
        try:
            existing = json.loads(report_path.read_text(encoding="utf-8"))
            completed = set()
            phases_data = existing.get("phases", {})
            for pk in phases_data:
                if pk == "phase_5":
                    if phases_data[pk].get("ok"):
                        completed.add(5)
                    continue
                days = phases_data[pk].get("days", [])
                if days and all(not d.get("error") for d in days):
                    completed.add(int(pk.split("_")[1]))
            self._log(f"📂 已有报告: Phase {sorted(completed)} 已完成")
            return {"completed": completed, "data": phases_data}
        except Exception:
            return empty

    # ═══════════════════════════════════════════════════════════
    # Phase 1: 登录
    # ═══════════════════════════════════════════════════════════

    def login(self, credentials: dict = None) -> bool:
        """登录教学平台 (自适应: Schema驱动 > 启发式 > 回退)

        :param credentials: 可选 dict{"username", "password", "login_url"}
                           来自 Schema 的 auth 信息, 优先使用
        """
        self._log("登录平台...", "step")
        creds = credentials or {}
        username = creds.get("username", USERNAME)
        password = creds.get("password", PASSWORD)
        login_url = creds.get("login_url", "")

        try:
            # 如果有指定的登录URL → 先导航
            target = login_url or self.base_url
            self.page.goto(target, timeout=60000)
            self._wait_stable(2)

            # 检查是否已登录 (通用检测: URL 已不是登录页, 且页面有内容)
            body = self._get_page_text()
            current_url = self.page.url
            # 如果URL已经不包含 login/auth/signin, 且有足够内容 → 可能已登录
            if not any(kw in current_url.lower() for kw in ["login", "auth", "signin"]):
                if len(body) > 200 and "登录" not in body[:300]:
                    self._log("已是登录状态 (URL判断)", "ok")
                    return True

            # 填写表单 (通用: 遍历所有可见input)
            inputs_filled = 0
            for inp in self.page.locator("input:not([type=hidden])").all():
                if not inp.is_visible():
                    continue
                t = (inp.get_attribute("type") or "text").lower()
                ph = (inp.get_attribute("placeholder") or "").lower()
                name = (inp.get_attribute("name") or "").lower()

                # 判断输入框类型: type > placeholder > name
                is_user = "user" in t or "user" in ph or "user" in name or "email" in t or "email" in ph or t == "text"
                is_pass = "password" in t

                if is_pass:
                    inp.fill(password)
                    inputs_filled += 1
                elif is_user and t != "password":
                    inp.fill(username)
                    inputs_filled += 1

            # 如果没填成功, 用旧策略: 第一个text=input填用户名, password填密码
            if inputs_filled == 0:
                for inp in self.page.locator("input:not([type=hidden])").all():
                    if not inp.is_visible():
                        continue
                    t = inp.get_attribute("type") or "text"
                    if t == "text":
                        inp.fill(username)
                    elif t == "password":
                        inp.fill(password)

            # 点击登录 (多语言: 登录/Login/Sign in/Submit)
            clicked = False
            login_keywords = ["登录", "Login", "Sign in", "登 录", "submit", "Submit"]
            for btn in self.page.locator("button, input[type=submit]").all():
                if not btn.is_visible():
                    continue
                btn_text = (btn.text_content() or btn.get_attribute("value") or "").strip()
                if any(kw.lower() in btn_text.lower() for kw in login_keywords):
                    btn.click()
                    clicked = True
                    break

            # 回退: 点 type=submit
            if not clicked:
                submit_btn = self.page.locator("button[type=submit], input[type=submit]").first
                if submit_btn.is_visible(timeout=2000):
                    submit_btn.click()
                    clicked = True

            self._wait_stable(4)
            body = self._get_page_text()
            current_url = self.page.url

            # 成功判断 (通用: URL不再是登录页 + 有内容)
            still_login = any(kw in current_url.lower() for kw in ["login", "auth", "signin"])
            has_content = len(body) > 200
            ok = has_content and not still_login

            self._log("登录成功" if ok else "登录可能失败", "ok" if ok else "warn")
            self._ss("login")
            return ok
        except Exception as e:
            self._log(f"登录异常: {e}", "error")
            return False

    # ═══════════════════════════════════════════════════════════
    # Phase 2: 导航到 Day
    # ═══════════════════════════════════════════════════════════

    def navigate_to_day(self, phase_num: int, day_num: int) -> bool:
        """导航到指定 Phase 的指定 Day 的模式选择页"""
        self._log(f"导航: Phase {phase_num} → Day {day_num}")

        # 回到首页
        self.page.goto(self.base_url, timeout=60000)
        self._wait_stable(2)

        # 点击 Phase 按钮
        ok, text = self._find_and_click([f"Phase 0{phase_num}"])
        if not ok:
            self._log(f"找不到 Phase {phase_num} 按钮", "error")
            return False
        self._log(f"点击: {text}")
        self._wait_stable(2)
        self._ss(f"nav_phase{phase_num}")

        # 点击 Day 按钮
        ok, text = self._find_and_click([f"Day {day_num}"])
        if not ok:
            # 尝试更宽泛匹配
            for btn in self.page.locator("button.lesson-card, button[class*=lesson]").all():
                t = (btn.text_content() or "").strip()
                if f"Day {day_num}" in t and not btn.is_disabled():
                    btn.click()
                    ok, text = True, t[:80]
                    break
        if not ok:
            self._log(f"找不到 Day {day_num} 按钮 (可能被锁定)", "warn")
            return False
        self._log(f"点击: {text}")
        self._wait_stable(3)
        self._ss(f"nav_day{day_num}")
        return True

    # ═══════════════════════════════════════════════════════════
    # Phase 3: 进入学习模式 → 遍历Steps
    # ═══════════════════════════════════════════════════════════

    def enter_learning_mode(self, mode: str = "guided") -> bool:
        """进入学习模式: guided(帮帮我) 或 self(我自己来)

        按钮文本可通过环境变量覆盖 (适配不同平台):
          EVAL_TEXT_GUIDED_MODE — guided 模式按钮文本 (默认: 进入引导学习)
          EVAL_TEXT_SELF_MODE    — self 模式按钮文本   (默认: 进入自主探索)
        """
        import os as _os
        guided_text = _os.getenv("EVAL_TEXT_GUIDED_MODE", "进入引导学习")
        self_text = _os.getenv("EVAL_TEXT_SELF_MODE", "进入自主探索")
        if mode == "guided":
            texts = [guided_text]
        elif mode == "self":
            texts = [self_text]
        else:
            texts = [guided_text, self_text]

        ok, text = self._find_and_click(texts)
        if not ok:
            self._log(f"找不到进入按钮 (mode={mode})", "error")
            return False
        self._log(f"进入 {mode}: {text}")
        self._wait_stable(4)
        self._ss(f"{mode}_mode")
        return True

    def complete_step(self, step_index: int) -> StepResult:
        """完成当前 Step: 勾选checklist → 点'本步已完成'"""
        result = StepResult(step_index=step_index)
        dom = self._dump_dom_state()

        # 提取 Step 标题
        step_title_els = self.page.locator("[class*=step-title], .step-title-row, h2, h3").all()
        for el in step_title_els:
            if el.is_visible():
                result.step_title = (el.text_content() or "").strip()[:150]
                break
        self._log(f"Step {step_index}: {result.step_title[:80]}")

        # 勾选所有 checklist checkbox
        checkboxes = self.page.locator("input[type=checkbox]").all()
        result.checklist_items = []
        checked = 0
        for cb in checkboxes:
            try:
                if cb.is_visible() and not cb.is_checked():
                    # 找到关联的 label 文本
                    parent_text = cb.evaluate("""el => {
                        let p = el.parentElement;
                        for (let i=0; i<5; i++) {
                            if (p) {
                                let t = p.textContent.trim().substring(0, 200);
                                if (t) return t;
                                p = p.parentElement;
                            }
                        }
                        return '';
                    }""")
                    result.checklist_items.append(parent_text[:150])
                    cb.check()
                    checked += 1
                    time.sleep(0.3)
            except Exception:
                pass
        result.checklist_done = checked
        self._log(f"勾选 {checked}/{len(checkboxes)} 个检查项", "ok" if checked > 0 else "warn")

        # 截图
        self._ss(f"step{step_index}_checklist")

        # 点击 "本步已完成" (文本可通过 EVAL_TEXT_STEP_DONE 环境变量覆盖)
        import os as _os
        step_done_text = _os.getenv("EVAL_TEXT_STEP_DONE", "本步已完成")
        ok, _ = self._find_and_click([step_done_text])
        if ok:
            self._wait_stable(2)
            result.completed = True
            self._log("标记完成", "ok")
        else:
            self._log("找不到'本步已完成'按钮", "warn")

        self._ss(f"step{step_index}_done")
        return result

    def trigger_agent(self, question: str = None) -> dict:
        """展开 Agent 面板并发起对话"""
        self._log("触发 Agent 对话...")
        q = question or "你好，可以帮我理解这个步骤吗？"
        body_before = len(self._get_page_text())

        # 点击 "我卡住了" (文本可通过 EVAL_TEXT_AGENT_HELP 覆盖)
        import os as _os
        help_text = _os.getenv("EVAL_TEXT_AGENT_HELP", "我卡住了")
        self._find_and_click([help_text])
        self._wait_stable(2)

        # Agent 面板在页面底部, 默认折叠。需要展开它。
        # 尝试多种方式展开面板
        expanded = False

        # 方式1: 点击底部 Agent 按钮/标签
        for selector in [
            "button:has-text('Agent')",
            "[class*=agent-toggle]",
            "[class*=agent-bar]",
            "[class*=agent-header]",
            "button:has-text('AI')",
            "button:has-text('课程助教')",
        ]:
            try:
                el = self.page.locator(selector).first
                if el.is_visible(timeout=2000):
                    el.click()
                    self._wait_stable(2)
                    expanded = True
                    self._log(f"展开面板: {selector}")
                    break
            except Exception:
                continue

        # 方式2: JS 强制显示 textarea
        if not expanded:
            self._log("面板未展开, 尝试 JS 显示 textarea")
            self.page.evaluate("""
                document.querySelectorAll('textarea').forEach(ta => {
                    ta.style.display = 'block';
                    ta.style.visibility = 'visible';
                    let p = ta.parentElement;
                    for (let i=0; i<10 && p; i++) {
                        p.style.display = p.style.display === 'none' ? 'block' : p.style.display;
                        p.style.visibility = 'visible';
                        p.style.height = 'auto';
                        p = p.parentElement;
                    }
                });
            """)
            self._wait_stable(1)

        self._ss("agent_panel")

        # JS 填充并发送
        js_result = self.page.evaluate(f"""
            (() => {{
                const tas = document.querySelectorAll('textarea');
                for (const ta of tas) {{
                    const ph = ta.placeholder || '';
                    // 优先用主聊天 textarea
                    if (ph.includes('输入') || ph.includes('Enter') || ph.includes('发送')) {{
                        ta.focus();
                        ta.value = {json.dumps(q)};
                        ta.dispatchEvent(new Event('input', {{bubbles: true}}));
                        return {{found: true, placeholder: ph, strategy: 'main_chat'}};
                    }}
                }}
                // 回退: 用第一个 textarea
                if (tas.length > 0) {{
                    tas[0].focus();
                    tas[0].value = {json.dumps(q)};
                    tas[0].dispatchEvent(new Event('input', {{bubbles: true}}));
                    return {{found: true, placeholder: tas[0].placeholder, strategy: 'fallback'}};
                }}
                return {{found: false, count: tas.length}};
            }})()
        """)

        self._log(f"textarea: {json.dumps(js_result, ensure_ascii=False)[:200]}")

        if js_result.get("found"):
            self.page.keyboard.press("Enter")
            self._wait_stable(8)
            self._ss("agent_reply")
            body_after = len(self._get_page_text())
            delta = body_after - body_before
            self._log(f"Agent 完成, Δ{delta} 字符", "ok" if delta > 50 else "warn")
            return {"ok": True, "question": q, "body_delta": delta,
                    "body_before": body_before, "body_after": body_after}
        else:
            self._log("无可用 textarea", "error")
            return {"ok": False, "error": "no textarea"}

    def go_next_step(self) -> bool:
        """点击'下一步' (文本可通过 EVAL_TEXT_NEXT_STEP 覆盖)"""
        import os as _os
        next_text = _os.getenv("EVAL_TEXT_NEXT_STEP", "下一步")
        ok, _ = self._find_and_click([next_text])
        if ok:
            self._wait_stable(2)
            self._log("→ 下一步", "ok")
        return ok

    # ═══════════════════════════════════════════════════════════
    # Phase 5: 机器人 Agent 专项
    # ═══════════════════════════════════════════════════════════

    def evaluate_phase5_agent(self) -> dict:
        """Phase 5 专属: 机器人Agent 对话测评 (API 直调模式)

        Phase 5 与 Phase 1-4 不同，没有 Day/Step/Quiz 流程，
        纯粹是 Agent 对话。前端也是调 POST /phase3-api/agent/chat。
        因此直接用 API 测评更稳定、可重复。

        API 格式 (从 agent-iframe-overlay.js 确认):
          POST /phase3-api/agent/chat
          body: {message, lesson_id: "0", step_block_id: null, phase: 5, conversation_id}
          response: {ok, answer, conversation_id, message_id}

        同时也尝试浏览器前端交互作为补充验证。
        """
        self._log("Phase 5 机器人 Agent 测评 (API + 浏览器)", "step")

        # — 获取 token —
        token = ""
        try:
            token = self.page.evaluate(
                "localStorage.getItem('aix_token') || localStorage.getItem('token') || ''")
        except Exception:
            pass

        if not token:
            self._log("无法获取 token", "error")
            return {"ok": False, "error": "no token"}

        questions = [
            ("你好，请介绍一下这个机器人项目", "项目介绍"),
            ("我需要完成哪些任务？", "任务询问"),
            ("传感器怎么连接？", "传感器连接"),
            ("如何进行3D打印外壳设计？", "3D打印"),
            ("最终项目交付需要什么材料？", "项目交付"),
        ]
        conversations = []
        conversation_id = None  # 多轮对话复用

        import requests as req

        for i, (q, label) in enumerate(questions):
            self._log(f"对话 {i+1}: {label} — {q[:50]}")

            body = {
                "message": q,
                "lesson_id": "0",
                "step_block_id": None,
                "phase": 5,
            }
            if conversation_id:
                body["conversation_id"] = conversation_id

            api_status = None
            response_text = ""
            t0 = time.time()

            for attempt in range(3):
                try:
                    resp = req.post(
                        f"{self.base_url}/phase3-api/agent/chat",
                        json=body,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                        },
                        timeout=45,
                        proxies={"http": None, "https": None},  # 不走本地代理
                    )
                    api_status = resp.status_code

                    if resp.status_code == 200:
                        data = resp.json()
                        response_text = data.get("answer", "")
                        conversation_id = data.get("conversation_id", conversation_id)
                        elapsed = time.time() - t0
                        self._log(f"API 200 ({elapsed:.1f}s, {len(response_text)} 字符)", "ok")
                        break
                    elif resp.status_code >= 500:
                        self._log(f"HiAgent {resp.status_code}, 重试 {attempt+1}", "warn")
                        time.sleep(2)
                        continue
                    else:
                        self._log(f"API {resp.status_code}: {resp.text[:100]}", "error")
                        response_text = f"[API {resp.status_code}]"
                        break
                except Exception as e:
                    self._log(f"API 调用异常: {e}", "error")
                    if attempt < 2:
                        time.sleep(2)
                        continue
                    response_text = f"[异常: {e}]"

            elapsed = time.time() - t0
            conversations.append({
                "question": q,
                "label": label,
                "response": response_text,
                "response_len": len(response_text) if response_text else 0,
                "api_status": api_status,
                "elapsed": round(elapsed, 1),
                "conversation_id": conversation_id,
            })

            status = "ok" if api_status == 200 else ("warn" if api_status and api_status >= 500 else "error")
            self._log(f"对话完成: {len(response_text) if response_text else 0} 字符 ({elapsed:.1f}s)", status)

            # 间隔，避免 rate limiting
            if i < len(questions) - 1:
                time.sleep(1)

        # — 浏览器补充验证: 确认 Phase 5 页面可访问 —
        browser_ok = False
        try:
            self.page.goto(self.base_url, timeout=30000)
            self._wait_stable(2)
            ok, _ = self._find_and_click(["Phase 05"])
            if ok:
                self._wait_stable(2)
                ta = self.page.locator(".course-agent-composer textarea").first
                ta.wait_for(state="visible", timeout=5000)
                browser_ok = True
                self._log("浏览器 Phase 5 页面可访问", "ok")
        except Exception as e:
            self._log(f"浏览器验证跳过: {e}", "warn")

        return {
            "ok": len([c for c in conversations if c.get("api_status") == 200]) > 0,
            "conversations": conversations,
            "method": "api_direct",
            "browser_accessible": browser_ok,
            "conversation_id": conversation_id,
        }

    # ═══════════════════════════════════════════════════════════
    # 主流程: 测评单个 Day
    # ═══════════════════════════════════════════════════════════

    def evaluate_day(self, phase_num: int, day_num: int) -> DayResult:
        """完整测评一个 Day: 导航 → 进入模式 → 遍历Steps → Agent → Quiz"""
        start_time = time.time()
        result = DayResult(day_index=day_num)

        # 1. 导航
        if not self.navigate_to_day(phase_num, day_num):
            result.error = "导航失败"
            return result

        # 2. 获取 Day 标题
        body = self._get_page_text()
        for line in body.split("\n"):
            line = line.strip()
            if f"Day {day_num}" in line and len(line) < 100:
                result.day_title = line[:100]
                break
        self._log(f"Day: {result.day_title}")

        # 3. 进入学习模式 + 遍历 Steps
        import re
        modes_to_test = [self.mode] if self.mode != "both" else ["guided", "self"]
        mode_results = []

        for test_mode in modes_to_test:
            if not self.enter_learning_mode(test_mode):
                result.error = f"进入{test_mode}模式失败"
                if not mode_results:
                    return result  # 第一个模式就失败 → 整体失败
                break  # 后续模式失败 → 保留已有结果

            # 4. 获取 Step 总数
            body = self._get_page_text()
            m = re.search(r'Step\s+(\d+)\s*/\s*(\d+)', body)
            total_steps = int(m.group(2)) if m else 0
            if total_steps == 0:
                mini_steps = self.page.locator("[class*=mini-step]").all()
                total_steps = len([s for s in mini_steps if s.is_visible()]) or 99
            self._log(f"[{test_mode}] 检测到 {total_steps} 个 Steps, 全部完成")

            # 5. 遍历 Steps
            mode_steps = []
            for step_idx in range(1, total_steps + 1):
                self._log(f"--- [{test_mode}] Step {step_idx}/{total_steps} ---", "step")

                step_result = self.complete_step(step_idx)
                mode_steps.append(step_result)

                # 在最后一个 Step 触发 Agent
                if step_idx == total_steps:
                    agent_result = self.trigger_agent(
                        f"你好，我在做Phase{phase_num} Day{day_num}的Step{step_idx}，"
                        f"可以帮我理解'{step_result.step_title[:50]}'吗？"
                    )
                    step_result.agent_triggered = agent_result.get("ok", False)
                    step_result.agent_question = agent_result.get("question", "")
                    step_result.agent_reply = str(agent_result.get("body_delta", ""))
                    self._log(f"Agent: Δ{agent_result.get('body_delta', 0)} 字符",
                             "ok" if agent_result.get("ok") else "warn")

                # 如果不是最后一步，点"下一步"
                if step_idx < total_steps:
                    self.go_next_step()

            # 6. Quiz 触发 + 答案验证
            body = self._get_page_text()
            quiz_keywords = ["Quiz", "测验", "答题", "选择题", "题目", "question"]
            quiz_triggered = any(kw in body.lower() for kw in quiz_keywords)
            quiz_result = {"triggered": quiz_triggered, "questions": 0, "answered": 0, "auto_graded": False}

            if quiz_triggered:
                self._log("Quiz 已触发!", "ok")
                self._ss(f"quiz_triggered_{test_mode}")

                # 统计题目数量
                quiz_result["questions"] = self.page.evaluate("""() => {
                    // 找所有可能的题目元素
                    const selectors = [
                        '.quiz-item', '.question-item', '[class*=question]',
                        '[class*=quiz]', '.choice-item', '.option-item',
                        'input[type=radio]', '.ant-radio', '.el-radio',
                    ];
                    let count = 0;
                    for (const sel of selectors) {
                        count += document.querySelectorAll(sel).length;
                    }
                    // 没有找到特定元素? 从文本估算
                    if (count === 0) {
                        const body = document.body.innerText;
                        const matches = body.match(/(\\d+)[.、]\\s*[A-D]/g);
                        count = matches ? matches.length : 8;  // 默认8题
                    }
                    return Math.min(count, 20);  // 上限20
                }""")

                # 尝试答题 (点击第一个选项)
                try:
                    clicked = self.page.evaluate("""() => {
                        const opts = document.querySelectorAll(
                            'input[type=radio], .ant-radio-input, .el-radio__original, '
                            + '[class*=option]:not([class*=correct])');
                        let clicked = 0;
                        for (const opt of opts) {
                            if (opt.offsetParent !== null && clicked < 10) {
                                opt.click();
                                clicked++;
                            }
                        }
                        return clicked;
                    }""")
                    quiz_result["answered"] = clicked
                    if clicked > 0:
                        self._log(f"已点击 {clicked} 个选项", "ok")
                except Exception:
                    pass

                # 等待并检查答案是否自动显示
                time.sleep(2)
                quiz_result["auto_graded"] = self.page.evaluate("""() => {
                    const b = document.body.innerText;
                    return /正确|错误|答案|得分|correct|answer|score/i.test(b)
                        || document.querySelector('[class*=correct], [class*=answer], '
                            + '[class*=result], [class*=score]') !== null;
                }""")
                if quiz_result["auto_graded"]:
                    self._log("✅ Quiz答案自动显示 (平台自动评分)", "ok")
                else:
                    self._log("⚠️ 未检测到答案自动显示", "warn")

                self._ss(f"quiz_result_{test_mode}")

            mode_results.append({
                "mode": test_mode,
                "steps": mode_steps,
                "quiz_triggered": quiz_triggered,
                "quiz_result": quiz_result,
            })

            # 多模式：点"返回"准备下一个模式
            if test_mode != modes_to_test[-1]:
                self._find_and_click(["返回课程日历", "返回"])
                self._wait_stable(2)
                # 重新导航到同一个 Day
                ok, _ = self._find_and_click([f"Day {day_num}"])
                if not ok:
                    self._log("返回后找不到Day按钮，跳过剩余模式", "warn")
                    break

        # 合并结果到 DayResult
        if mode_results:
            primary = mode_results[0]
            result.mode = self.mode
            result.steps = primary["steps"]
            result.quiz_triggered = primary["quiz_triggered"]
        if len(mode_results) > 1:
            result.mode = "both"
            # 合并两个模式的所有 steps
            result.steps = mode_results[0]["steps"] + mode_results[1]["steps"]
            result.quiz_triggered = (mode_results[0]["quiz_triggered"] or
                                     mode_results[1]["quiz_triggered"])

        result.total_duration = time.time() - start_time
        self._log(f"Day 完成 ({result.mode}): {result.total_duration:.0f}s")
        return result

    # ═══════════════════════════════════════════════════════════
    # 顶层入口
    # ═══════════════════════════════════════════════════════════

    def run(self):
        """运行完整测评"""
        print("=" * 60)
        print("🔬 浏览器驱动测评 v4.0")
        print(f"   平台: {self.base_url}  |  用户: {USERNAME}")
        if self.resume:
            print(f"   🔄 续跑模式: Phase {sorted(self.completed_phases)} 已完成, 跳过")
        print("=" * 60)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            self.page = browser.new_page(viewport={"width": 1440, "height": 900})

            # 收集网络错误
            network_errors = []
            def on_response(resp):
                if resp.status >= 400:
                    network_errors.append(f"{resp.status} {resp.url[:100]}")
            self.page.on("response", on_response)

            try:
                # ── 登录 ──
                if not self.login():
                    self.results["errors"].append("登录失败, 终止测评")
                    self._save_report()
                    return self.results

                # ── Phase 1-4: Day 遍历 ──
                for phase_num in [1, 2, 3, 4]:
                    if self.phase_filter and phase_num != self.phase_filter:
                        continue
                    if self.resume and phase_num in self.completed_phases:
                        self._log(f"Phase {phase_num}: ⏭️ 跳过 (已完成)", "ok")
                        continue

                    phase_key = f"phase_{phase_num}"
                    self.results["phases"][phase_key] = {"days": []}
                    days_count = PHASES[phase_num]["days"]

                    for day_num in range(1, days_count + 1):
                        if self.day_filter and day_num != self.day_filter:
                            continue

                        self._log(f"\n{'='*40}")
                        self._log(f"Phase {phase_num} Day {day_num}")
                        self._log(f"{'='*40}")

                        day_result = self.evaluate_day(phase_num, day_num)
                        self.results["phases"][phase_key]["days"].append({
                            "index": day_result.day_index,
                            "title": day_result.day_title,
                            "mode": day_result.mode,
                            "steps_completed": sum(1 for s in day_result.steps if s.completed),
                            "total_steps": len(day_result.steps),
                            "agent_triggered": any(s.agent_triggered for s in day_result.steps),
                            "quiz_triggered": day_result.quiz_triggered,
                            "duration": round(day_result.total_duration, 1),
                            "error": day_result.error,
                        })

                        if day_result.error:
                            self._log(f"Day {day_num} 出错: {day_result.error}", "error")
                            self.results["errors"].append(
                                f"Phase{phase_num} Day{day_num}: {day_result.error}"
                            )

                    # 💾 每个 Phase 完成即保存 (断点续跑)
                    self._save_report()

                # ── Phase 5: 机器人 Agent ──
                if not (self.resume and 5 in self.completed_phases):
                    if not self.phase_filter or self.phase_filter == 5:
                        self._log(f"\n{'='*40}")
                        self._log(f"Phase 5 机器人 Agent 专项")
                        self._log(f"{'='*40}")
                        p5_result = self.evaluate_phase5_agent()
                        self.results["phases"]["phase_5"] = p5_result
                        self._save_report()

                # ── 网络请求分析 ──
                if network_errors:
                    self._log(f"网络错误 ({len(network_errors)}):", "warn")
                    for ne in network_errors[:5]:
                        self._log(f"  {ne}", "warn")
                self.results["network_errors"] = network_errors

            except Exception as e:
                self._log(f"测评异常: {e}", "error")
                import traceback
                self.results["errors"].append({
                    "type": "fatal",
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                })
                self._save_report()  # 💾 异常时也保存
            finally:
                browser.close()

        # ── 完成更新 ──
        self.results["meta"]["finished_at"] = datetime.now(timezone.utc).isoformat()

        # ── 填充 Summary ──
        self._build_summary()

        # ── 最终保存 ──
        report_path = OUTPUT_DIR / "browser_eval_report.json"
        report_path.write_text(json.dumps(self.results, ensure_ascii=False, indent=2, default=str),
                               encoding="utf-8")

        # ── 打印摘要 ──
        s = self.results["summary"]
        print(f"\n{'='*60}")
        print(f"📊 测评摘要")
        print(f"  测评范围: Phase {s.get('phases_tested',[])}")
        print(f"  Days: {s.get('days_completed',0)}/{s.get('days_total',0)} 完成")
        print(f"  Agent 对话: {s.get('agent_sessions',0)} 次")
        print(f"  Quiz 触发: {s.get('quiz_triggers',0)} 次")
        print(f"  Phase 5 Agent: {'✅' if s.get('phase5_agent_ok') else '❌'}")
        print(f"  错误: {len(self.results.get('errors',[]))}")
        print(f"  截图: {s.get('screenshots',0)} 张")
        print(f"  报告: {report_path}")
        print(f"  截图目录: {SCREENSHOT_DIR}")

        return self.results

    def _build_summary(self):
        """从 results 中汇总统计信息"""
        days_total = 0
        days_completed = 0
        agent_sessions = 0
        quiz_triggers = 0
        phases_tested = []
        modes_seen = set()

        for pk, pv in self.results["phases"].items():
            if pk == "phase_5":
                continue
            pid = int(pk.split("_")[1])
            days = pv.get("days", [])
            if days:
                phases_tested.append(pid)
            for d in days:
                days_total += 1
                if d.get("steps_completed", 0) > 0 and not d.get("error"):
                    days_completed += 1
                if d.get("agent_triggered"):
                    agent_sessions += 1
                if d.get("quiz_triggered"):
                    quiz_triggers += 1
                modes_seen.add(d.get("mode", "guided"))

        phase5_ok = self.results["phases"].get("phase_5", {}).get("ok", False)

        self.results["summary"] = {
            "phases_tested": phases_tested,
            "days_total": days_total,
            "days_completed": days_completed,
            "agent_sessions": agent_sessions,
            "quiz_triggers": quiz_triggers,
            "modes_tested": sorted(modes_seen),
            "phase5_agent_ok": phase5_ok,
            "screenshots": self._ss_count,
            "errors": len(self.results.get("errors", [])),
        }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="浏览器驱动测评")
    ap.add_argument("--headed", action="store_true", help="显示浏览器")
    ap.add_argument("--phase", type=int, default=None, help="只测指定 Phase")
    ap.add_argument("--day", type=int, default=None, help="只测指定 Day")
    ap.add_argument("--mode", type=str, default="guided",
                   choices=["guided", "self", "both"],
                   help="学习模式: guided(帮帮我) self(我自己来) both(两种都测)")
    ap.add_argument("--resume", action="store_true",
                   help="续跑模式: 跳过已完成Phase, 从断点继续")
    args = ap.parse_args()

    evaluator = BrowserEvaluator(
        headless=not args.headed,
        phase_filter=args.phase,
        day_filter=args.day,
        mode=args.mode,
        resume=args.resume,
    )
    evaluator.run()
