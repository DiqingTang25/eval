#!/usr/bin/env python3
"""
教学平台 Playwright 全功能探索脚本 v2.0
═══════════════════════════════════════════════════════
用真实浏览器完整探索 http://124.174.108.70 的每一项功能，
不只是 API 调用，而是实际渲染页面、点击按钮、截图记录。

探索清单 (20+ 项):
  1. 登录流程 (页面结构 + 表单验证)
  2. 首页/课程总览
  3. 6个 Phase 页面
  4. 26个 Lesson 详情 (Steps 内容 + render_payload)
  5. Agent 对话 UI (发消息→看回复→标记解决)
  6. Quiz 完整流程 (启动→答题→提交→看分数)
  7. Step 进度导航 (上一个/下一个/done触发Quiz)
  8. 学生画像 (6维雷达图)
  9. 知识搜索 UI
  10. 资源下载
  11. 学习模式切换 ("我自己来" vs "帮帮我")
  12. 视频播放
  13. 跨Step完整学习流
  14. 页面性能 (加载时间/资源大小)
  15. UI 状态转换 (loading/empty/error/success)
  16. 移动端响应式
  17. 所有可点击元素检测
  18. JavaScript 报错收集
  19. Network 请求分析
  20. 综合健康度评分

输出:
  - explore_output/ 目录下的截图和 HTML
  - explore_output/exploration_report.json 结构化报告
  - 控制台实时输出

用法:
    python scripts/explore_platform_playwright.py              # 全功能探索
    python scripts/explore_platform_playwright.py --headed     # 有头模式(看过程)
    python scripts/explore_platform_playwright.py --phase 1    # 只探索Phase 1
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

# ── 配置 ──
BASE_URL = "http://124.174.108.70"
USERNAME = "student001"
PASSWORD = "123456"
OUTPUT_DIR = Path(__file__).parent.parent / "explore_output"
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"
HTML_DIR = OUTPUT_DIR / "html"

# 已知路由 (从平台探索中总结)
PLATFORM_ROUTES = [
    "/",                          # 首页
    "/login",                     # 登录页
    "/courses",                   # 课程列表
    "/phases",                    # 阶段列表
    "/phases/1", "/phases/2", "/phases/3",
    "/phases/4", "/phases/5", "/phases/6",
    "/lessons/1", "/lessons/2",   # ... 动态探索
    "/profile",                   # 学生画像
    "/knowledge",                 # 知识库
    "/resources",                 # 资源
    "/settings",                  # 设置
]


class PlatformExplorer:
    """教学平台全功能浏览器探索器"""

    def __init__(self, headed: bool = False, phase_filter: int = None):
        self.headed = headed
        self.phase_filter = phase_filter
        self.report = {
            "meta": {
                "started_at": datetime.now(timezone.utc).isoformat(),
                "base_url": BASE_URL,
                "username": USERNAME,
            },
            "pages": {},           # 每个页面的探索结果
            "features": {},        # 每项功能的测试结果
            "errors": [],          # 收集到的错误
            "network_summary": {}, # 网络请求统计
            "health_score": 0.0,   # 综合健康度
        }
        self.js_errors = []
        self.network_requests = []
        self.screenshots_taken = 0

        # 确保输出目录存在
        OUTPUT_DIR.mkdir(exist_ok=True)
        SCREENSHOT_DIR.mkdir(exist_ok=True)
        HTML_DIR.mkdir(exist_ok=True)

    # ═══════════════════════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════════════════════

    def _ss(self, page, name: str):
        """截图并保存"""
        self.screenshots_taken += 1
        filename = f"{self.screenshots_taken:03d}_{name}.png"
        path = SCREENSHOT_DIR / filename
        try:
            # 禁用字体等待，避免超时
            page.screenshot(path=str(path), full_page=True, timeout=10000,
                          animations="disabled", caret="hide")
        except Exception:
            try:
                page.screenshot(path=str(path), full_page=False, timeout=5000)
            except Exception:
                pass  # 截图失败不阻塞探索
        return str(path)

    def _save_html(self, page, name: str):
        """保存页面HTML"""
        filename = f"{name}.html"
        path = HTML_DIR / filename
        try:
            html = page.content()
            path.write_text(html, encoding="utf-8")
        except Exception:
            pass

    def _api_fetch(self, page, url: str, method: str = "GET", body: dict = None) -> dict:
        """通过浏览器 JS fetch 调用 API (避免 Python requests 网络问题)"""
        js_code = f"""
            (async () => {{
                const token = localStorage.getItem('token') || localStorage.getItem('auth_token') || '';
                const headers = {{ 'Content-Type': 'application/json' }};
                if (token) headers['Authorization'] = 'Bearer ' + token;
                const opts = {{ method: '{method}', headers }};
                if ('{method}' === 'POST' || '{method}' === 'PATCH') {{
                    opts.body = JSON.stringify({json.dumps(body) if body else '{}'});
                }}
                try {{
                    const resp = await fetch('{url}', opts);
                    const text = await resp.text();
                    return {{ ok: resp.ok, status: resp.status, body: text }};
                }} catch(e) {{
                    return {{ ok: false, status: 0, error: e.message }};
                }}
            }})()
        """
        try:
            result = page.evaluate(js_code)
            if result and result.get("body"):
                try:
                    result["json"] = json.loads(result["body"])
                except Exception:
                    pass
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _record(self, category: str, key: str, data: dict):
        """记录探索结果"""
        if category not in self.report:
            self.report[category] = {}
        self.report[category][key] = data

    def _safe_click(self, page, selector: str, timeout: float = 5.0) -> bool:
        """安全点击，找不到元素不报错"""
        try:
            el = page.locator(selector).first
            el.wait_for(state="visible", timeout=timeout * 1000)
            el.click()
            page.wait_for_load_state("networkidle", timeout=10000)
            return True
        except Exception:
            return False

    def _safe_text(self, page, selector: str) -> str:
        """安全获取文本"""
        try:
            el = page.locator(selector).first
            if el.is_visible():
                return (el.text_content() or "").strip()[:500]
        except Exception:
            pass
        return ""

    def _page_text(self, page) -> str:
        """获取页面body文本内容"""
        try:
            return page.locator("body").first.text_content() or ""
        except Exception:
            return ""

    def _collect_visible_text(self, page) -> dict:
        """收集页面可见文本的结构化摘要"""
        info = {}
        # 标题
        info["title"] = page.title()
        info["url"] = page.url
        # h1/h2
        h1s = [el.text_content().strip() for el in page.locator("h1").all() if el.is_visible()]
        h2s = [el.text_content().strip() for el in page.locator("h2").all() if el.is_visible()]
        info["h1"] = h1s[:5]
        info["h2"] = h2s[:10]
        # 导航
        nav_text = self._safe_text(page, "nav")
        info["nav_items"] = nav_text[:200] if nav_text else ""
        # 链接
        links = []
        for a in page.locator("a[href]").all():
            try:
                href = a.get_attribute("href")
                text = (a.text_content() or "").strip()
                if href and text:
                    links.append({"href": href[:200], "text": text[:100]})
            except Exception:
                pass
        info["links"] = links[:30]
        return info

    # ═══════════════════════════════════════════════════════════
    # 1. 登录流程
    # ═══════════════════════════════════════════════════════════

    def explore_login(self, page):
        """完整测试登录流程 — 增强版：检测真实登录状态"""
        print("\n" + "=" * 60)
        print("🔑 1. 登录流程探索")
        print("=" * 60)

        result = {"status": "unknown", "steps": []}

        # 1a. 访问首页
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        result["initial_url"] = page.url
        self._ss(page, "01_login_page")
        result["steps"].append({
            "step": "visit_homepage",
            "url": page.url,
            "title": page.title(),
        })

        # 1b. 检测页面类型
        page_text = page.locator("body").first.text_content() or ""
        is_login_page = any(kw in page_text for kw in ["登录", "注册", "用户名", "密码"])
        has_phase_content = any(kw in page_text for kw in ["Phase", "AI+硬件", "用户画像", "退出"])
        result["is_login_page"] = is_login_page
        result["has_phase_content"] = has_phase_content
        print(f"  页面类型: {'登录页' if is_login_page else '已登录'} | "
              f"含Phase内容: {has_phase_content}")

        # 1c. 如果已登录，直接返回
        if has_phase_content and not is_login_page:
            result["status"] = "already_logged_in"
            result["login_success"] = True
            print(f"  ✅ 已经是登录状态")
            self._record("features", "login", result)
            return True

        # 1d. 未登录 → 执行登录
        # 找所有输入框
        all_inputs = page.locator("input:not([type='hidden'])").all()
        login_ok = False

        print(f"  页面输入框: {len(all_inputs)} 个")
        for inp in all_inputs:
            try:
                if inp.is_visible():
                    t = inp.get_attribute("type") or "text"
                    ph = inp.get_attribute("placeholder") or ""
                    print(f"    type={t} placeholder='{ph}'")
            except Exception:
                pass

        try:
            # 精确识别：用户名/邮箱/手机号输入框
            username_input = None
            password_input = None

            for inp in all_inputs:
                if not inp.is_visible():
                    continue
                t = inp.get_attribute("type") or "text"
                ph = (inp.get_attribute("placeholder") or "").lower()
                name = (inp.get_attribute("name") or "").lower()
                auto = (inp.get_attribute("autocomplete") or "").lower()

                if t == "password":
                    password_input = inp
                elif any(kw in ph + name + auto for kw in
                        ["user", "用户", "账号", "手机", "email", "邮箱", "username"]):
                    username_input = inp

            # 回退策略
            if not username_input:
                for inp in all_inputs:
                    if inp.is_visible() and (inp.get_attribute("type") or "text") != "password":
                        username_input = inp
                        break
            if not password_input:
                for inp in all_inputs:
                    if inp.is_visible() and (inp.get_attribute("type") or "") == "password":
                        password_input = inp
                        break

            if username_input and password_input:
                username_input.click()
                username_input.fill(USERNAME)
                time.sleep(0.3)
                password_input.click()
                password_input.fill(PASSWORD)
                print(f"  填写: {USERNAME} / *** (精确识别)")

                # 找登录按钮
                login_btn = None
                for btn in page.locator("button, input[type='submit']").all():
                    try:
                        if btn.is_visible():
                            text = (btn.text_content() or btn.get_attribute("value") or "").strip()
                            if any(kw in text for kw in ["登录", "登入", "进入", "Login", "Sign"]):
                                login_btn = btn
                                print(f"  登录按钮: '{text}'")
                                break
                    except Exception:
                        pass

                if login_btn:
                    login_btn.click()
                else:
                    page.keyboard.press("Enter")

                # 等待登录完成
                time.sleep(5)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                time.sleep(2)

                # 验证登录: 检查页面内容是否改变
                post_text = page.locator("body").first.text_content() or ""
                has_phase = any(kw in post_text for kw in
                               ["Phase", "phase", "AI+硬件", "用户画像", "退出", "Day", "课时"])
                has_login_form = any(kw in post_text for kw in ["登录", "用户名", "密码"])

                login_ok = has_phase and not has_login_form
                result["post_login"] = {
                    "has_phase": has_phase,
                    "still_login": has_login_form,
                    "url": page.url,
                    "title": page.title(),
                }
                print(f"  登录验证: Phase内容={has_phase}, 仍有登录={has_login_form}"
                      f" → {'✅ 成功' if login_ok else '❌ 可能失败'}")
            else:
                print(f"  ⚠️ 未找到用户名/密码输入框 (找到 {len(all_inputs)} 个输入框)")
        except Exception as e:
            result["login_error"] = str(e)
            print(f"  ❌ 登录异常: {e}")

        # 如果表单登录失败，尝试 API 登录+注入 token
        if not login_ok:
            print("  尝试 API 登录...")
            api_ok = False
            for prefix in ["/phase3-api", "/api"]:
                login_result = self._api_fetch(
                    page,
                    f"{BASE_URL}{prefix}/auth/login",
                    method="POST",
                    body={"username": USERNAME, "password": PASSWORD},
                )
                if login_result.get("ok") and login_result.get("json"):
                    token = login_result["json"].get("token", "")
                    if token:
                        page.evaluate(f"""
                            localStorage.setItem('token', '{token}');
                            localStorage.setItem('auth_token', '{token}');
                        """)
                        print(f"  ✅ API登录 ({prefix}) token已注入")
                        api_ok = True
                        break
                else:
                    print(f"  {prefix}: HTTP {login_result.get('status')}")

            if api_ok:
                page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
                time.sleep(3)
                post_text = page.locator("body").first.text_content() or ""
                login_ok = any(kw in post_text for kw in
                              ["Phase", "phase", "AI+硬件", "用户画像", "退出", "Day"])

        result["login_success"] = login_ok
        result["status"] = "logged_in" if login_ok else "login_failed"
        self._ss(page, "01_after_login")
        self._record("features", "login", result)
        return login_ok

    # ═══════════════════════════════════════════════════════════
    # 2. 首页/课程总览
    # ═══════════════════════════════════════════════════════════

    def explore_homepage(self, page):
        """探索首页内容"""
        print("\n" + "=" * 60)
        print("🏠 2. 首页/课程总览")
        print("=" * 60)

        page.goto(BASE_URL, wait_until="networkidle", timeout=20000)
        time.sleep(2)

        info = self._collect_visible_text(page)
        self._ss(page, "03_homepage")
        self._save_html(page, "homepage")

        # 检测首页元素
        # Phase 卡片
        phase_cards = page.locator("[class*='phase'], [class*='Phase'], [class*='card'], [class*='course']").all()
        phase_texts = []
        for card in phase_cards:
            try:
                if card.is_visible():
                    text = (card.text_content() or "").strip()[:200]
                    if text:
                        phase_texts.append(text)
            except Exception:
                pass
        info["phase_card_texts"] = phase_texts[:10]

        # 可点击元素
        clickable = page.locator("a, button, [role='button'], [onclick]").all()
        clickable_info = []
        for el in clickable[:30]:
            try:
                if el.is_visible():
                    tag = el.evaluate("el => el.tagName.toLowerCase()")
                    text = (el.text_content() or "").strip()[:100]
                    href = el.get_attribute("href") or ""
                    clickable_info.append({"tag": tag, "text": text, "href": href[:200]})
            except Exception:
                pass
        info["clickable_elements"] = clickable_info

        print(f"  标题: {info['title']}")
        print(f"  导航: {info['nav_items'][:100]}")
        print(f"  可点击元素: {len(clickable_info)}")
        for ci in clickable_info[:10]:
            print(f"    [{ci['tag']}] {ci['text'][:60]} → {ci['href'][:60]}")

        self._record("pages", "homepage", info)

    # ═══════════════════════════════════════════════════════════
    # 3. 所有 Phase 页面 — 真实点击交互
    # ═══════════════════════════════════════════════════════════

    def explore_phases(self, page):
        """通过点击 Phase 按钮探索所有阶段"""
        print("\n" + "=" * 60)
        print("📚 3. 课程阶段 (Phases) — 真实点击交互")
        print("=" * 60)

        # API: 通过浏览器 fetch 获取 phases
        api_result = self._api_fetch(page, f"{BASE_URL}/api/phases")
        if api_result.get("json"):
            phases_data = api_result["json"]
            if isinstance(phases_data, list):
                print(f"  API /api/phases: {len(phases_data)} phases")
                for p in phases_data:
                    print(f"    Phase {p.get('id')}: {p.get('name', p.get('title', '?'))}")

        # 获取 phase3-api 数据
        api2_result = self._api_fetch(page, f"{BASE_URL}/phase3-api/phases")
        if api2_result.get("json"):
            print(f"  API /phase3-api/phases: OK")

        # 回到首页，点击 Phase 按钮
        page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
        time.sleep(2)
        self._ss(page, "04_home_before_phases")

        # 基于第一次运行发现的页面结构: Phase 按钮格式 "Phase 0X 标题"
        phase_buttons = page.locator("button").all()
        phase_info = []
        for btn in phase_buttons:
            try:
                if not btn.is_visible():
                    continue
                text = (btn.text_content() or "").strip()
                if text and ("Phase" in text or "phase" in text.lower()):
                    phase_info.append({"text": text, "element": btn})
                    print(f"  发现 Phase 按钮: {text[:80]}")
            except Exception:
                pass

        if not phase_info:
            # 更宽的搜索
            all_elements = page.locator("button, a, [role='button'], [class*='card'], [class*='tab']").all()
            for el in all_elements:
                try:
                    if not el.is_visible():
                        continue
                    text = (el.text_content() or "").strip()
                    if text and len(text) > 5 and len(text) < 80:
                        phase_info.append({"text": text, "element": el})
                except Exception:
                    pass

        print(f"\n  共识别 {len(phase_info)} 个可点击卡片/按钮")

        # 逐个点击探索
        for i, pi in enumerate(phase_info[:8]):  # 最多8个
            print(f"\n  ── 点击 [{i+1}]: {pi['text'][:60]} ──")
            phase_result = {"click_text": pi["text"], "changes": []}

            try:
                # 记录点击前的页面状态
                before_url = page.url
                before_title = page.title()

                # 点击
                pi["element"].click()
                time.sleep(2)
                page.wait_for_load_state("networkidle", timeout=10000)

                after_url = page.url
                after_title = page.title()
                phase_result["url_changed"] = before_url != after_url
                phase_result["after_url"] = after_url
                phase_result["after_title"] = after_title
                print(f"    URL变化: {before_url != after_url}")
                print(f"    标题: {after_title}")

                # 截图
                safe_name = pi["text"][:20].replace(" ", "_").replace("/", "_")
                self._ss(page, f"04_phase_click_{i+1}_{safe_name}")

                # 检测页面变化: 新增的可见文本
                new_elements = page.locator(
                    "button, a, h1, h2, h3, [class*='title'], [class*='card'], "
                    "[class*='lesson'], [class*='day'], li, [class*='list']"
                ).all()
                visible_texts = []
                for el in new_elements[:30]:
                    try:
                        if el.is_visible():
                            t = (el.text_content() or "").strip()
                            if t and len(t) > 3 and len(t) < 200:
                                visible_texts.append(t)
                    except Exception:
                        pass
                phase_result["visible_content"] = visible_texts[:20]
                for vt in visible_texts[:10]:
                    print(f"    → {vt[:100]}")

                # 如果是 Phase 页面，找 lesson/day 按钮
                day_buttons = page.locator(
                    "button:has-text('Day'), button:has-text('day'), "
                    "button:has-text('课时'), a:has-text('Day')"
                ).all()
                phase_result["day_buttons"] = len(day_buttons)
                if day_buttons:
                    print(f"    📖 {len(day_buttons)} 个 Day/课时按钮")

            except Exception as e:
                phase_result["error"] = str(e)[:200]
                print(f"    ❌ 点击失败: {e}")

            self._record("pages", f"phase_click_{i+1}", phase_result)

    # ═══════════════════════════════════════════════════════════
    # 4. Lesson 详情 + Steps 内容
    # ═══════════════════════════════════════════════════════════

    def explore_lessons(self, page):
        """深入探索课时内容"""
        print("\n" + "=" * 60)
        print("📖 4. 课时详情探索")
        print("=" * 60)

        # 获取所有 lessons (API)
        token = page.evaluate("localStorage.getItem('token') || localStorage.getItem('auth_token') || ''")
        all_lessons = []
        try:
            import requests
            s = requests.Session()
            s.trust_env = False
            s.proxies = {"http": None, "https": None}
            for pid in range(1, 7):
                r = s.get(f"{BASE_URL}/api/lessons?phase_id={pid}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list):
                        lessons = data
                    elif isinstance(data, dict):
                        lessons = data.get("lessons", data.get("data", []))
                    else:
                        lessons = []
                    for l in lessons:
                        l["_api_phase_id"] = pid
                    all_lessons.extend(lessons)
        except Exception as e:
            print(f"  ⚠️ API获取失败: {e}")

        print(f"  API 返回 {len(all_lessons)} 个课时")

        # 选取代表性课时进行浏览器深入探索
        # 策略: 每个Phase选第一个和最后一个; 加上有quiz的课时
        sample_lessons = []
        seen_phases = set()
        for l in all_lessons:
            pid = l.get("_api_phase_id", l.get("phase_id"))
            if pid not in seen_phases:
                sample_lessons.append(l)
                seen_phases.add(pid)
            # 也加最后一个
        # 每个Phase最多2个
        if len(all_lessons) > 6:
            # 加几个中间的
            sample_lessons.append(all_lessons[len(all_lessons)//3])
            sample_lessons.append(all_lessons[2*len(all_lessons)//3])

        print(f"  浏览器深入探索 {len(sample_lessons)} 个代表性课时")

        for l in sample_lessons[:8]:  # 最多8个
            lid = l.get("id")
            ltitle = l.get("title", l.get("name", f"Lesson {lid}"))
            print(f"\n  ── L{lid}: {ltitle} ──")

            lesson_result = {"id": lid, "title": ltitle, "steps": [], "resources": []}

            # 浏览器访问
            lesson_urls = [
                f"{BASE_URL}/lessons/{lid}",
                f"{BASE_URL}/lesson/{lid}",
                f"{BASE_URL}/course/{lid}",
            ]
            for url in lesson_urls:
                try:
                    page.goto(url, wait_until="networkidle", timeout=20000)
                    time.sleep(2)
                    lesson_result["url"] = page.url
                    lesson_result["page_title"] = page.title()
                    break
                except Exception:
                    continue

            # 截图
            self._ss(page, f"05_lesson_{lid}")

            # 检测 Steps
            step_elements = page.locator(
                "[class*='step'], [class*='Step'], [class*='lesson-step'], "
                "li, .step-item, .lesson-item"
            ).all()
            steps_found = []
            for el in step_elements[:30]:
                try:
                    if el.is_visible():
                        text = (el.text_content() or "").strip()
                        cls = el.get_attribute("class") or ""
                        if len(text) > 5:
                            steps_found.append({"text": text[:200], "class": cls[:80]})
                except Exception:
                    pass
            lesson_result["steps_visible"] = steps_found[:10]
            print(f"    Steps (可见): {len(steps_found)}")

            # 检测内容区域 (render_payload)
            content_selectors = [
                "[class*='content']", "[class*='render']", "[class*='markdown']",
                "[class*='article']", "main", "article", ".lesson-body",
                "[class*='lesson-content']",
            ]
            for sel in content_selectors:
                try:
                    content_el = page.locator(sel).first
                    if content_el.is_visible():
                        text = (content_el.text_content() or "").strip()[:500]
                        if len(text) > 50:
                            lesson_result["content_preview"] = text
                            print(f"    内容: ({sel}) {text[:150]}...")
                            break
                except Exception:
                    pass

            # 检测资源文件
            resource_links = []
            for a in page.locator("a[href*='.pdf'], a[href*='.zip'], a[href*='.doc'], "
                                   "a[href*='download'], a[href*='resource'], "
                                   "a[href*='.pptx'], a[href*='.xlsx']").all():
                try:
                    href = a.get_attribute("href")
                    text = (a.text_content() or "").strip()
                    if href:
                        resource_links.append({"href": href[:200], "text": text[:100]})
                except Exception:
                    pass
            lesson_result["resource_links"] = resource_links
            if resource_links:
                print(f"    资源: {len(resource_links)} 个文件")

            # 检测视频
            videos = page.locator("video, iframe[src*='video'], [class*='video']").all()
            lesson_result["has_video"] = len(videos) > 0

            self._record("pages", f"lesson_{lid}", lesson_result)

    # ═══════════════════════════════════════════════════════════
    # 5. Agent 对话 UI
    # ═══════════════════════════════════════════════════════════

    def explore_agent_chat(self, page):
        """在浏览器中测试 Agent 对话"""
        print("\n" + "=" * 60)
        print("🤖 5. Agent 对话 UI 测试")
        print("=" * 60)

        chat_result = {"tests": []}

        # 需要在一个有 Agent 的 lesson 页面
        test_cases = [
            {"phase": 1, "lesson": 20, "label": "Phase1-触觉交互"},
            {"phase": 5, "lesson": 26, "label": "Phase5-具身智能"},
        ]

        for tc in test_cases:
            lid = tc["lesson"]
            label = tc["label"]
            print(f"\n  ── {label} (L{lid}) ──")

            test = {"lesson_id": lid, "label": label, "messages": []}

            # 导航到 lesson 页面
            page.goto(f"{BASE_URL}/lessons/{lid}", wait_until="networkidle", timeout=15000)
            time.sleep(2)
            self._ss(page, f"06_chat_before_{label}")

            # 找聊天输入框
            chat_input = None
            input_selectors = [
                "textarea", "input[type='text']", "[contenteditable='true']",
                "[class*='chat'] textarea", "[class*='chat'] input",
                "[class*='message'] textarea", "[class*='agent'] textarea",
                "[role='textbox']", "[placeholder*='输入']", "[placeholder*='提问']",
                "[placeholder*='消息']",
            ]
            for sel in input_selectors:
                try:
                    el = page.locator(sel).first
                    if el.is_visible():
                        chat_input = el
                        test["input_selector"] = sel
                        print(f"    输入框: {sel}")
                        break
                except Exception:
                    continue

            if not chat_input:
                # 最后手段：截图看页面长什么样
                print("    ⚠️ 未找到聊天输入框")
                self._ss(page, f"06_chat_noinput_{label}")
                test["status"] = "no_input_found"
                chat_result["tests"].append(test)
                continue

            # 发送测试消息
            test_messages = [
                "你好，请介绍一下这个阶段的学习目标",
                "这个阶段需要哪些前置知识？",
            ]

            for i, msg in enumerate(test_messages):
                try:
                    chat_input.click()
                    chat_input.fill(msg)
                    page.keyboard.press("Enter")
                    print(f"    发送[{i+1}]: {msg[:50]}...")

                    # 等待回复
                    time.sleep(5)
                    page.wait_for_load_state("networkidle", timeout=10000)

                    # 收集回复内容
                    # 找消息列表
                    reply_selectors = [
                        "[class*='message']", "[class*='chat'] [class*='bubble']",
                        "[class*='agent-reply']", "[class*='ai']", "[class*='bot']",
                        "[class*='response']", "[class*='assistant']",
                    ]
                    reply_text = ""
                    for rsel in reply_selectors:
                        try:
                            all_msgs = page.locator(rsel).all()
                            if all_msgs:
                                # 取最后几条消息
                                for m in all_msgs[-3:]:
                                    t = (m.text_content() or "").strip()
                                    if len(t) > 20:
                                        reply_text += t[:300] + "\n---\n"
                                if reply_text:
                                    break
                        except Exception:
                            pass

                    test["messages"].append({
                        "question": msg,
                        "reply_preview": reply_text[:500],
                        "reply_length": len(reply_text),
                    })

                    # 检测限流/QPS错误
                    page_text = (page.text_content() or "").lower()
                    if any(kw in page_text for kw in ["qps", "限流", "频率", "rate limit"]):
                        test["rate_limited"] = True
                        print(f"    ⚠️ QPS限流检测到")
                        break

                except Exception as e:
                    test["messages"].append({"question": msg, "error": str(e)})
                    print(f"    ❌ 发送失败: {e}")
                    break

            test["status"] = "ok" if test["messages"] else "failed"
            self._ss(page, f"06_chat_after_{label}")

            # 检测是否有 Agent 反馈按钮（✅解决/❌未解决）
            resolve_btns = page.locator(
                "button:has-text('解决'), button:has-text('resolve'), "
                "[class*='resolve'], [class*='feedback']"
            ).all()
            test["has_resolve_buttons"] = len(resolve_btns) > 0
            if resolve_btns:
                print(f"    反馈按钮: {len(resolve_btns)} 个")

            chat_result["tests"].append(test)

        self._record("features", "agent_chat", chat_result)

    # ═══════════════════════════════════════════════════════════
    # 6. Quiz 完整流程
    # ═══════════════════════════════════════════════════════════

    def explore_quiz(self, page):
        """浏览器中测试 Quiz — 通过导航到 lesson 页面看能否触发 Quiz"""
        print("\n" + "=" * 60)
        print("📝 6. Quiz 流程测试 (浏览器)")
        print("=" * 60)

        quiz_result = {"tests": []}
        # 已知有 Quiz 的课时
        quiz_lessons = [20, 26]

        for lid in quiz_lessons:
            print(f"\n  ── L{lid} Quiz ──")
            test = {"lesson_id": lid}

            # 导航到 lesson 页面
            page.goto(f"{BASE_URL}/lessons/{lid}", wait_until="domcontentloaded", timeout=15000)
            time.sleep(3)
            self._ss(page, f"06_quiz_lesson_{lid}")
            test["url"] = page.url
            test["title"] = page.title()

            page_text = self._page_text(page)
            # 检测 Quiz 相关元素
            has_quiz_btn = "quiz" in page_text.lower() or "测验" in page_text or "答题" in page_text
            test["quiz_references"] = has_quiz_btn

            # 找 Quiz/答题 按钮
            quiz_btns = page.locator(
                "button:has-text('Quiz'), button:has-text('测验'), "
                "button:has-text('答题'), button:has-text('开始'), "
                "[class*='quiz'] button"
            ).all()
            test["quiz_buttons_found"] = len(quiz_btns)
            for btn in quiz_btns:
                try:
                    if btn.is_visible():
                        t = (btn.text_content() or "").strip()
                        test[f"quiz_btn_text"] = t
                        print(f"    发现Quiz按钮: '{t}'")
                        # 尝试点击
                        btn.click()
                        time.sleep(3)
                        self._ss(page, f"06_quiz_clicked_{lid}")
                        page_text2 = self._page_text(page)
                        test["after_click"] = page_text2[:500]
                        print(f"    点击后: {page_text2[:150]}")
                        break
                except Exception as e:
                    print(f"    ❌ 点击失败: {e}")

            # 通过 API 启动Quiz (浏览器内 fetch)
            for prefix in ["/phase3-api", "/api"]:
                qr = self._api_fetch(
                    page,
                    f"{BASE_URL}{prefix}/quiz/start",
                    method="POST",
                    body={"lesson_id": lid},
                )
                test[f"quiz_api_{prefix.replace('/', '_')}"] = {
                    "status": qr.get("status"),
                    "ok": qr.get("ok"),
                }
                if qr.get("json"):
                    qs = qr["json"].get("questions", [])
                    test["questions_count"] = len(qs)
                    test["has_session_id"] = bool(qr["json"].get("quiz_session_id"))
                    print(f"    {prefix}/quiz/start: {len(qs)} 题, "
                          f"session={test['has_session_id']}")
                    break

            # 课时内容分析
            print(f"    页面长度: {len(page_text)} 字符")
            print(f"    含Quiz关键词: {has_quiz_btn}")

            quiz_result["tests"].append(test)

        self._record("features", "quiz", quiz_result)

    # ═══════════════════════════════════════════════════════════
    # 7. 完整学习流 — 点击交互
    # ═══════════════════════════════════════════════════════════

    def explore_step_navigation(self, page):
        """回到首页，点击第一个Phase的第一个Day，遍历完整学习流"""
        print("\n" + "=" * 60)
        print("⏭️ 7. 完整学习流 (点击交互)")
        print("=" * 60)

        flow = {"steps": []}

        # 回到首页
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
        time.sleep(3)
        self._ss(page, "07_flow_home")
        flow["steps"].append({"action": "goto_home", "title": page.title()})

        # 找 Phase 按钮
        phase_btns = page.locator("button").all()
        phase_clicked = False
        for btn in phase_btns:
            try:
                if not btn.is_visible():
                    continue
                text = (btn.text_content() or "").strip()
                if "Phase 01" in text or "Phase" in text:
                    print(f"  点击 Phase: {text[:60]}")
                    btn.click()
                    time.sleep(3)
                    page.wait_for_load_state("networkidle", timeout=10000)
                    self._ss(page, "07_flow_phase_selected")
                    flow["steps"].append({"action": "click_phase", "text": text[:60],
                                          "url": page.url, "title": page.title()})
                    phase_clicked = True
                    break
            except Exception:
                pass

        if not phase_clicked:
            print("  ⚠️ 未找到Phase按钮，尝试导航")
            # 直接导航到 API 获取的 phase 页面
            for url in [f"{BASE_URL}/phases/1", f"{BASE_URL}/lessons/4"]:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                time.sleep(2)
                flow["steps"].append({"action": "navigate", "url": url, "title": page.title()})

        # 找 Day/课时 按钮
        day_btns = page.locator(
            "button:has-text('Day'), button:has-text('day'), "
            "button:has-text('课时'), a:has-text('Day'), "
            "[class*='lesson'] button, [class*='card']"
        ).all()
        print(f"  Day/课时按钮: {len(day_btns)}")
        for btn in day_btns[:5]:
            try:
                if btn.is_visible():
                    text = (btn.text_content() or "").strip()
                    print(f"    {text[:80]}")
            except Exception:
                pass

        # 点击第一个 Day 按钮
        day_clicked = False
        for btn in day_btns:
            try:
                if btn.is_visible():
                    text = (btn.text_content() or "").strip()
                    print(f"  点击 Day: {text[:60]}")
                    btn.click()
                    time.sleep(3)
                    page.wait_for_load_state("networkidle", timeout=10000)
                    self._ss(page, "07_flow_day_selected")
                    flow["steps"].append({"action": "click_day", "text": text[:60],
                                          "url": page.url, "title": page.title()})
                    day_clicked = True
                    break
            except Exception:
                pass

        # 在 Day/Lesson 页面找 Agent 聊天框、Step 导航、Quiz 按钮
        if day_clicked:
            page_text = self._page_text(page)
            flow["lesson_page_text"] = page_text[:500]

            # 找聊天输入框
            chat_input = None
            for sel in ["textarea", "input[type='text']", "[contenteditable]"]:
                for el in page.locator(sel).all():
                    if el.is_visible():
                        chat_input = el
                        break
                if chat_input:
                    break

            if chat_input:
                flow["has_chat_input"] = True
                print(f"  找到聊天输入框 ✅")
                # 发送消息
                chat_input.fill("你好，这个阶段要学什么？")
                page.keyboard.press("Enter")
                time.sleep(5)
                self._ss(page, "07_flow_chat_sent")
                flow["steps"].append({"action": "send_chat"})
            else:
                flow["has_chat_input"] = False
                print(f"  未找到聊天输入框")

            # 找 Step 导航按钮
            nav_texts = []
            for btn in page.locator("button").all():
                try:
                    if btn.is_visible():
                        t = (btn.text_content() or "").strip()
                        if t in ["上一", "下一", "上一步", "下一步", "prev", "next",
                                  "Previous", "Next", "完成", "Done"]:
                            nav_texts.append(t)
                except Exception:
                    pass
            flow["nav_buttons"] = nav_texts
            print(f"  导航按钮: {nav_texts}")

            # 点击"下一步"
            for btn_text in nav_texts:
                try:
                    btn = page.locator(f"button:has-text('{btn_text}')").first
                    if btn.is_visible():
                        btn.click()
                        time.sleep(2)
                        self._ss(page, f"07_flow_step_{btn_text}")
                        flow["steps"].append({"action": f"click_{btn_text}"})
                        break
                except Exception:
                    pass

        self._record("features", "learning_flow", flow)

    # ═══════════════════════════════════════════════════════════
    # 8. 用户画像 + 知识搜索 + 其他 (合并快速探索)
    # ═══════════════════════════════════════════════════════════

    def explore_remaining(self, page):
        """快速探索画像、搜索、资源等功能"""
        print("\n" + "=" * 60)
        print("👤 8. 画像 + 搜索 + 资源")
        print("=" * 60)

        # 回到首页
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)

        # 找并点击"用户画像"按钮
        profile_btns = page.locator("button:has-text('画像'), button:has-text('用户'), "
                                     "button:has-text('Profile'), button:has-text('数据')").all()
        for btn in profile_btns:
            try:
                if btn.is_visible():
                    text = (btn.text_content() or "").strip()
                    print(f"  点击: {text}")
                    btn.click()
                    time.sleep(2)
                    self._ss(page, "08_profile_clicked")
                    break
            except Exception:
                pass

        # API 画像数据
        for prefix in ["/phase3-api", "/api"]:
            pr = self._api_fetch(page, f"{BASE_URL}{prefix}/profile/me")
            if pr.get("json"):
                pd = pr["json"]
                dims = pd if isinstance(pd, list) else list(pd.keys())
                print(f"  API画像 ({prefix}): {len(dims)} keys → {dims[:8]}")
                self._record("features", "profile", {"prefix": prefix, "keys": dims[:15]})
                break
        else:
            print(f"  API画像: ❌")

        # 知识搜索 (浏览器内 API)
        for q in ["AI", "传感器"]:
            for prefix in ["/phase3-api", "/api"]:
                kr = self._api_fetch(page, f"{BASE_URL}{prefix}/knowledge/search?q={q}")
                if kr.get("json"):
                    chunks = kr["json"].get("chunks", kr["json"].get("results", []))
                    print(f"  搜索'{q}' ({prefix}): {len(chunks)} 条")
                    break

        # 所有可见按钮 (全局扫描)
        all_btns = page.locator("button").all()
        btn_texts = []
        for btn in all_btns:
            try:
                if btn.is_visible():
                    t = (btn.text_content() or "").strip()
                    if t and len(t) > 1:
                        btn_texts.append(t[:80])
            except Exception:
                pass
        print(f"\n  首面全部按钮 ({len(btn_texts)}):")
        for bt in btn_texts[:15]:
            print(f"    [{bt}]")
        self._record("features", "all_buttons", {"buttons": btn_texts})

        self._ss(page, "08_home_overview")

    # ═══════════════════════════════════════════════════════════
    # 10. 其他功能收集
    # ═══════════════════════════════════════════════════════════

    def explore_misc(self, page):
        """探索剩余功能: 资源/视频/学习模式/设置等"""
        print("\n" + "=" * 60)
        print("📦 10. 其他功能探索")
        print("=" * 60)

        misc = {}

        # 学习模式切换
        print("\n  ── 学习模式 ──")
        mode_btns = page.locator(
            "button:has-text('我自己来'), button:has-text('帮帮我'), "
            "button:has-text('guide'), button:has-text('standard'), "
            "button:has-text('detailed'), [class*='mode-btn'], "
            "[class*='learning-mode'] button"
        ).all()
        mode_texts = []
        for btn in mode_btns:
            try:
                if btn.is_visible():
                    mode_texts.append((btn.text_content() or "").strip())
            except Exception:
                pass
        misc["learning_modes"] = mode_texts
        print(f"  学习模式按钮: {mode_texts}")

        # 尝试切换模式
        if mode_btns:
            try:
                mode_btns[0].click()
                time.sleep(1.5)
                self._ss(page, "10_mode_switched")
                misc["mode_switch_tested"] = True
                print(f"  切换模式: ✅")
            except Exception as e:
                misc["mode_switch_error"] = str(e)

        # 视频播放
        print("\n  ── 视频播放 ──")
        page.goto(f"{BASE_URL}/lessons/1", wait_until="networkidle", timeout=15000)
        time.sleep(1)
        videos = page.locator("video, iframe[src*='video'], iframe[src*='youtube'], "
                              "iframe[src*='bilibili'], [class*='video-player']").all()
        misc["video_elements"] = len(videos)
        if videos:
            print(f"  视频元素: {len(videos)}")
            for v in videos:
                try:
                    src = v.get_attribute("src") or v.get_attribute("data-src") or ""
                    misc["video_srcs"] = src[:200]
                except Exception:
                    pass
        else:
            print("  ⚠️ 未发现视频元素")

        # 资源下载
        print("\n  ── 资源下载 ──")
        resource_urls = [f"{BASE_URL}/resources", f"{BASE_URL}/downloads",
                         f"{BASE_URL}/files"]
        for url in resource_urls:
            try:
                page.goto(url, wait_until="networkidle", timeout=10000)
                misc["resources_url"] = page.url
                misc["resources_title"] = page.title()
                # 找文件列表
                file_links = []
                for a in page.locator("a[href]").all():
                    try:
                        href = a.get_attribute("href") or ""
                        if any(href.endswith(ext) for ext in
                               ['.pdf','.zip','.doc','.docx','.xlsx','.pptx','.png','.jpg']):
                            text = (a.text_content() or "").strip()
                            file_links.append({"name": text[:80], "url": href[:200]})
                    except Exception:
                        pass
                misc["downloadable_files"] = file_links
                print(f"  可下载文件: {len(file_links)}")
                if file_links:
                    for fl in file_links[:3]:
                        print(f"    {fl['name']}: {fl['url']}")
                break
            except Exception:
                continue

        # 设置页面
        print("\n  ── 设置页面 ──")
        set_urls = [f"{BASE_URL}/settings", f"{BASE_URL}/user/settings",
                    f"{BASE_URL}/account"]
        for url in set_urls:
            try:
                page.goto(url, wait_until="networkidle", timeout=10000)
                misc["settings_url"] = page.url
                misc["settings_title"] = page.title()
                self._ss(page, "10_settings")
                print(f"  设置页: {page.title()}")
                break
            except Exception:
                continue

        self._record("features", "misc", misc)

    # ═══════════════════════════════════════════════════════════
    # 11. 跨Step完整学习流
    # ═══════════════════════════════════════════════════════════

    def explore_full_learning_flow(self, page):
        """模拟完整学习流"""
        print("\n" + "=" * 60)
        print("🔄 11. 跨Step完整学习流")
        print("=" * 60)

        flow = {"steps": []}
        token = page.evaluate("localStorage.getItem('token') || localStorage.getItem('auth_token') || ''")

        # 选一个典型lesson (Phase 1, 有多个steps)
        lid = 4  # Phase 1 的早期课时
        print(f"  使用 L{lid} 模拟完整流程")

        page.goto(f"{BASE_URL}/lessons/{lid}", wait_until="networkidle", timeout=15000)
        time.sleep(2)
        self._ss(page, "11_flow_start")
        flow["steps"].append({"action": "open_lesson", "lid": lid})

        # 依次遍历 steps
        for step_id in range(1, 8):
            print(f"  Step {step_id}...")
            step_result = {"step_id": step_id}

            try:
                import requests
                s = requests.Session()
                s.trust_env = False
                s.proxies = {"http": None, "https": None}

                # 标记完成
                sp_r = s.post(f"{BASE_URL}/phase3-api/steps/{step_id}/progress",
                            headers={"Authorization": f"Bearer {token}"},
                            json={"status": "completed"}, timeout=10)
                step_result["mark_progress"] = sp_r.status_code

                # 获取下一步
                ns_r = s.post(f"{BASE_URL}/phase3-api/lessons/{lid}/next-step",
                            headers={"Authorization": f"Bearer {token}"},
                            json={"from_step_block_id": step_id}, timeout=10)
                step_result["next_step_status"] = ns_r.status_code
                if ns_r.status_code == 200:
                    ns_data = ns_r.json()
                    step_result["done"] = ns_data.get("done", False)
                    step_result["has_next"] = bool(ns_data.get("step"))
                    if ns_data.get("done"):
                        step_result["quiz_triggered"] = True
                        print(f"    → done! Quiz 应该被触发")
                        flow["steps"].append(step_result)
                        break

            except Exception as e:
                step_result["error"] = str(e)

            flow["steps"].append(step_result)

        print(f"  流程: {len(flow['steps'])} 步")

        # 检测是否触发了 Quiz
        page_text = self._page_text(page)
        if any(kw in page_text for kw in ["quiz", "Quiz", "测验", "答题"]):
            flow["quiz_surface"] = True
            print(f"  ✅ Quiz 被触发")
            self._ss(page, "11_flow_quiz_triggered")

        self._record("features", "learning_flow", flow)

    # ═══════════════════════════════════════════════════════════
    # 12. 页面性能 + 错误 + 网络分析
    # ═══════════════════════════════════════════════════════════

    def analyze_performance(self, page):
        """收集性能指标和JS错误"""
        print("\n" + "=" * 60)
        print("⚡ 12. 性能 + 错误分析")
        print("=" * 60)

        perf = {}

        # Performance API
        try:
            timing = page.evaluate("""() => {
                const t = performance.timing;
                const nav = performance.getEntriesByType('navigation')[0];
                return {
                    domContentLoaded: t.domContentLoadedEventEnd - t.navigationStart,
                    loadComplete: t.loadComplete - t.navigationStart,
                    domInteractive: t.domInteractive - t.navigationStart,
                    firstPaint: performance.getEntriesByType('paint')
                        .find(e => e.name === 'first-contentful-paint')?.startTime || 0,
                    resourceCount: performance.getEntriesByType('resource').length,
                };
            }""")
            perf["timing"] = timing
            print(f"  DOMContentLoaded: {timing.get('domContentLoaded', '?')}ms")
            print(f"  LoadComplete: {timing.get('loadComplete', '?')}ms")
            print(f"  FirstPaint: {timing.get('firstPaint', '?')}ms")
            print(f"  Resources: {timing.get('resourceCount', '?')}")
        except Exception as e:
            perf["timing_error"] = str(e)

        # JS 错误
        perf["js_errors"] = self.js_errors
        if self.js_errors:
            print(f"  JS错误: {len(self.js_errors)}")
            for err in self.js_errors[:5]:
                print(f"    {err.get('message', '')[:120]}")
        else:
            print(f"  JS错误: 0")

        # 网络请求汇总
        api_calls = [r for r in self.network_requests if '/api/' in r.get('url', '')]
        perf["api_calls_count"] = len(api_calls)
        # 按URL分组统计
        from collections import Counter
        url_bases = Counter()
        for r in self.network_requests:
            url = r.get('url', '')
            # 提取路径
            for prefix in ['/phase3-api/', '/api/', '/resources/', '/static/']:
                if prefix in url:
                    idx = url.index(prefix)
                    url_bases[url[idx:idx+60]] += 1
                    break
        perf["api_endpoints"] = [{"path": k, "count": v} for k, v in url_bases.most_common(20)]
        print(f"  API调用: {len(api_calls)}")
        for ep in perf["api_endpoints"][:10]:
            print(f"    {ep['path']} ({ep['count']}次)")

        # 响应状态分布
        status_counts = Counter(r.get('status', 0) for r in self.network_requests)
        perf["status_distribution"] = dict(status_counts)
        error_count = sum(v for k, v in status_counts.items() if k >= 400)
        perf["error_requests"] = error_count
        print(f"  错误请求(4xx/5xx): {error_count}")

        self._record("pages", "performance", perf)

    # ═══════════════════════════════════════════════════════════
    # 主流程
    # ═══════════════════════════════════════════════════════════

    def run(self):
        print("=" * 60)
        print("🔍 教学平台 Playwright 全功能探索 v2.0")
        print(f"   平台: {BASE_URL}")
        print(f"   用户: {USERNAME}")
        print(f"   输出: {OUTPUT_DIR}")
        print("=" * 60)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=not self.headed,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="zh-CN",
            )
            page = context.new_page()

            # 监听 JS 错误
            page.on("pageerror", lambda err: self.js_errors.append({
                "message": err.message,
                "name": err.name,
            }))

            # 监听网络请求
            def on_response(response):
                try:
                    self.network_requests.append({
                        "url": response.url[:300],
                        "status": response.status,
                        "type": response.request.resource_type,
                    })
                except Exception:
                    pass
            page.on("response", on_response)

            try:
                # ── 执行探索 (简化流程 — 侧重真实点击交互) ──
                logged_in = self.explore_login(page)

                if logged_in:
                    self.explore_homepage(page)
                    self.explore_phases(page)
                    self.explore_quiz(page)
                    self.explore_step_navigation(page)
                    self.explore_remaining(page)
                else:
                    print("\n⚠️ 登录失败，只做未登录态探索")
                    self.explore_homepage(page)

                self.analyze_performance(page)

            except Exception as e:
                print(f"\n❌ 探索异常: {e}")
                import traceback
                traceback.print_exc()
                self.report["errors"].append({"phase": "run", "error": str(e)})

            finally:
                # ── 计算健康度 ──
                self._calculate_health()
                browser.close()

        # ── 保存报告 ──
        self.report["meta"]["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.report["meta"]["screenshots_taken"] = self.screenshots_taken
        self.report["meta"]["total_features"] = len(self.report.get("features", {}))

        report_path = OUTPUT_DIR / "exploration_report.json"
        report_path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2, default=str),
                               encoding="utf-8")

        # ── 生成人类可读摘要 ──
        self._print_summary()

        print(f"\n📄 完整报告: {report_path}")
        print(f"📸 截图目录: {SCREENSHOT_DIR}")
        print(f"📁 HTML目录: {HTML_DIR}")
        return self.report

    def _calculate_health(self):
        """计算综合健康度评分"""
        score = 0.0
        total = 0

        features = self.report.get("features", {})

        # Login: 30分
        if features.get("login", {}).get("status") in ("logged_in", "api_logged_in"):
            score += 30
        total += 30

        # Agent Chat: 20分
        chat_tests = features.get("agent_chat", {}).get("tests", [])
        if chat_tests:
            ok_count = sum(1 for t in chat_tests if t.get("status") == "ok")
            score += 20 * (ok_count / len(chat_tests))
        total += 20

        # Quiz: 20分
        quiz_tests = features.get("quiz", {}).get("tests", [])
        if quiz_tests:
            ok_count = sum(1 for t in quiz_tests if t.get("quiz_start_phase3", {}).get("status_code") == 200)
            score += 20 * (ok_count / len(quiz_tests))
        total += 20

        # Profile: 10分
        if features.get("profile", {}).get("api_data_keys"):
            score += 10
        total += 10

        # Knowledge Search: 10分
        ks_tests = features.get("knowledge_search", {}).get("tests", [])
        if ks_tests:
            ok_count = sum(1 for t in ks_tests if t.get("result_count", 0) > 0)
            score += 10 * (ok_count / len(ks_tests))
        total += 10

        # Step Navigation: 5分
        nav_tests = features.get("step_navigation", {}).get("tests", [])
        if nav_tests:
            score += 5
        total += 5

        # Misc (modes + video + resources): 5分
        misc = features.get("misc", {})
        if misc:
            score += 5 * min(1.0, len([v for v in misc.values() if v]) / 3)
        total += 5

        self.report["health_score"] = round(score / total, 3) if total > 0 else 0.0

    def _print_summary(self):
        """打印人类可读摘要"""
        print("\n" + "=" * 60)
        print("📊 探索结果摘要")
        print("=" * 60)

        features = self.report.get("features", {})

        # 登录
        login = features.get("login", {})
        print(f"\n🔑 登录: {'✅' if login.get('status') in ('logged_in', 'api_logged_in') else '❌'}"
              f" ({login.get('status', '?')})")

        # Phase
        pages = self.report.get("pages", {})
        phase_count = len([k for k in pages if k.startswith("phase_")])
        lesson_count = len([k for k in pages if k.startswith("lesson_")])
        print(f"📚 Phases: {phase_count} | Lessons: {lesson_count}")

        # Agent Chat
        chat = features.get("agent_chat", {})
        chat_tests = chat.get("tests", [])
        if chat_tests:
            ok = sum(1 for t in chat_tests if t.get("status") == "ok")
            print(f"🤖 Agent对话: {ok}/{len(chat_tests)} 可用")

        # Quiz
        quiz = features.get("quiz", {})
        quiz_tests = quiz.get("tests", [])
        if quiz_tests:
            started = sum(1 for t in quiz_tests
                         if t.get("quiz_start_phase3", {}).get("status_code") == 200)
            print(f"📝 Quiz: {started}/{len(quiz_tests)} 可启动")

        # Profile
        profile = features.get("profile", {})
        print(f"👤 学生画像: {'✅' if profile.get('api_data_keys') else '❌'} "
              f"({profile.get('dimensions_count', 0)} 维度)")

        # Knowledge Search
        ks = features.get("knowledge_search", {})
        ks_tests = ks.get("tests", [])
        if ks_tests:
            with_results = sum(1 for t in ks_tests if t.get("result_count", 0) > 0)
            print(f"🔍 知识搜索: {with_results}/{len(ks_tests)} 查询有结果")

        # Misc
        misc = features.get("misc", {})
        print(f"🎓 学习模式: {misc.get('learning_modes', [])}")
        print(f"🎬 视频元素: {misc.get('video_elements', 0)}")
        print(f"📁 可下载文件: {len(misc.get('downloadable_files', []))}")

        # 性能
        perf = self.report.get("pages", {}).get("performance", {})
        timing = perf.get("timing", {})
        print(f"\n⚡ 性能:"
              f" DOM={timing.get('domContentLoaded', '?')}ms"
              f" Load={timing.get('loadComplete', '?')}ms"
              f" FCP={timing.get('firstPaint', '?')}ms")
        print(f"   API调用: {perf.get('api_calls_count', '?')} | "
              f"JS错误: {len(perf.get('js_errors', []))} | "
              f"HTTP错误: {perf.get('error_requests', '?')}")

        # 健康度
        print(f"\n🏥 综合健康度: {self.report.get('health_score', 0):.1%}")

        # 发现
        errors = self.report.get("errors", [])
        if errors:
            print(f"\n⚠️ {len(errors)} 个异常:")
            for e in errors[:5]:
                print(f"   {e.get('phase', '')}: {e.get('error', '')[:120]}")

        # 未覆盖功能
        not_tested = [
            "视频播放 (浏览器)",
            "学习内容展示 (render_payload渲染)",
            "前端UI交互 (所有按钮/链接功能)",
            "移动端响应式",
            "离线/弱网",
            "Token刷新",
        ]
        print(f"\n❓ 本次未深度覆盖: {len(not_tested)} 项")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="教学平台 Playwright 全功能探索")
    parser.add_argument("--headed", action="store_true",
                        help="有头模式 (可视化浏览器)")
    parser.add_argument("--phase", type=int, default=None,
                        help="只探索指定Phase")
    args = parser.parse_args()

    explorer = PlatformExplorer(headed=args.headed, phase_filter=args.phase)
    explorer.run()
