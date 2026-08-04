#!/usr/bin/env python3
"""
教学平台 Phase 2 深入探索 — 点击 Day → Agent → 聊天 → 分身
在 Phase 1 基础之上，深入每个 Day 的内容区域和 Agent 交互
"""
import json, os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "http://124.174.108.70"
USERNAME = "student001"
PASSWORD = "123456"
OUTPUT_DIR = Path(__file__).parent.parent / "explore_output"
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
ss_count = [0]

def ss(page, name):
    ss_count[0] += 1
    try:
        page.screenshot(path=str(SCREENSHOT_DIR / f"{ss_count[0]:03d}_{name}.png"),
                       full_page=True, timeout=10000, animations="disabled")
    except Exception:
        pass

def api_fetch(page, url, method="GET", body=None):
    """通过浏览器 JS fetch"""
    body_json = json.dumps(body) if body else "{}"
    code = f"""
        (async () => {{
            const token = localStorage.getItem('token') || localStorage.getItem('auth_token') || '';
            const headers = {{ 'Content-Type': 'application/json' }};
            if (token) headers['Authorization'] = 'Bearer ' + token;
            const opts = {{ method: '{method}', headers }};
            if ('{method}' === 'POST') opts.body = JSON.stringify({body_json});
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
        r = page.evaluate(code)
        if r and r.get("body"):
            try: r["json"] = json.loads(r["body"])
            except: pass
        return r
    except Exception as e:
        return {"ok": False, "error": str(e)}

def login(page):
    """登录到平台"""
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    body_text = page.locator("body").first.text_content() or ""
    if "Phase" in body_text and "登录" not in body_text[:500]:
        print("  已是登录状态 ✅")
        return True

    print("  执行登录...")
    # Fill form
    all_inputs = page.locator("input:not([type='hidden'])").all()
    username_el = password_el = None
    for inp in all_inputs:
        if not inp.is_visible(): continue
        t = inp.get_attribute("type") or "text"
        if t == "password": password_el = inp
        elif t == "text": username_el = inp

    if username_el and password_el:
        username_el.fill(USERNAME)
        password_el.fill(PASSWORD)
        # Click login button
        for btn in page.locator("button").all():
            if btn.is_visible() and "登录" in (btn.text_content() or ""):
                btn.click()
                break
        time.sleep(4)
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(2)

    body_text = page.locator("body").first.text_content() or ""
    return "Phase" in body_text and "登录" not in body_text[:500]


def explore_deep():
    """深入探索：Day详情 + Agent + 分身"""
    print("=" * 60)
    print("🔬 教学平台 Phase 2 深入探索")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        if not login(page):
            print("❌ 登录失败")
            browser.close()
            return

        ss(page, "00_home")
        all_findings = {}

        # ── 1. Click "用户画像" ──
        print("\n📊 1. 用户画像")
        for btn in page.locator("button").all():
            if btn.is_visible() and "用户画像" in (btn.text_content() or ""):
                btn.click()
                time.sleep(2)
                ss(page, "01_profile_open")
                # Get panel content
                profile_text = page.locator("body").first.text_content() or ""
                # Extract relevant portion
                for marker in ["我的画像", "能力维度", "知识", "画像"]:
                    idx = profile_text.find(marker)
                    if idx > 0:
                        print(f"  画像内容: ...{profile_text[idx:idx+300]}")
                        break
                # API call
                r = api_fetch(page, f"{BASE_URL}/phase3-api/profile/me")
                print(f"  API: status={r.get('status')}, has_json={bool(r.get('json'))}")
                if r.get("json"):
                    print(f"  Profile data: {json.dumps(r['json'], ensure_ascii=False)[:300]}")
                break

        # Close any modal
        for btn in page.locator("button:has-text('关闭'), button:has-text('取消'), [class*='close']").all():
            if btn.is_visible():
                btn.click()
                time.sleep(0.5)
                break
        ss(page, "01_profile_closed")

        # ── 2. For each Phase, click into Phase, then click first Day, explore content ──
        phases_data = {}
        for phase_num in range(1, 6):
            print(f"\n{'─'*40}")
            print(f"📚 Phase {phase_num} 深入")
            phase_info = {"num": phase_num}

            # Go home
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)

            # Click Phase button
            phase_clicked = False
            for btn in page.locator("button").all():
                if btn.is_visible() and f"Phase 0{phase_num}" in (btn.text_content() or ""):
                    btn.click()
                    time.sleep(2)
                    page.wait_for_load_state("networkidle", timeout=10000)
                    phase_clicked = True
                    break

            if not phase_clicked:
                print(f"  ⚠️ 未找到Phase {phase_num}按钮")
                continue

            ss(page, f"02_phase{phase_num}")

            # Collect Day buttons
            day_btns = []
            for btn in page.locator("button").all():
                if btn.is_visible():
                    t = (btn.text_content() or "").strip()
                    if t.startswith("Day "):
                        day_btns.append({"text": t, "el": btn})
            print(f"  Days: {len(day_btns)}")

            phase_info["days"] = []

            # Click each Day
            for di, db in enumerate(day_btns):
                day_info = {"text": db["text"][:100]}
                print(f"    ➤ {db['text'][:80]}")

                try:
                    db["el"].click()
                    time.sleep(3)
                    page.wait_for_load_state("networkidle", timeout=10000)
                    ss(page, f"03_phase{phase_num}_day{di+1}")

                    # Analyze Day page
                    page_text = page.locator("body").first.text_content() or ""
                    day_info["page_length"] = len(page_text)

                    # Search for key elements
                    # Agent chat input
                    chat_inputs = page.locator(
                        "textarea, input[type='text'], [contenteditable]"
                    ).all()
                    visible_inputs = [i for i in chat_inputs if i.is_visible()]
                    day_info["chat_inputs"] = len(visible_inputs)

                    # Step/Navigation buttons
                    nav_btns = []
                    for btn in page.locator("button").all():
                        t = (btn.text_content() or "").strip()
                        if t in ["上一", "下一", "上一步", "下一步", "完成", "prev", "next"]:
                            nav_btns.append(t)
                    day_info["nav_buttons"] = nav_btns

                    # "Agent" button
                    agent_btns = page.locator("button:has-text('Agent')").all()
                    day_info["agent_buttons"] = len(agent_btns)

                    # Quiz
                    quiz_refs = any(kw in page_text for kw in ["Quiz", "测验", "答题", "测试"])

                    # Content structure
                    h2_count = len(page.locator("h2").all())
                    h3_count = len(page.locator("h3").all())
                    img_count = len(page.locator("img").all())
                    canvas_count = len(page.locator("canvas").all())

                    print(f"      长度={len(page_text)}, chat输入={len(visible_inputs)}, "
                          f"Agent按钮={len(agent_btns)}, 导航={nav_btns}, "
                          f"quiz={quiz_refs}, h2={h2_count}, img={img_count}")
                    day_info["stats"] = {
                        "h2": h2_count, "h3": h3_count, "img": img_count,
                        "canvas": canvas_count, "has_quiz": quiz_refs
                    }

                    # If Agent button found, click it!
                    if agent_btns:
                        print(f"      🤖 点击Agent按钮...")
                        try:
                            agent_btns[0].click()
                            time.sleep(3)
                            ss(page, f"04_phase{phase_num}_day{di+1}_agent")
                            # Find chat input now
                            for sel in ["textarea", "input[type='text']", "[contenteditable]"]:
                                for el in page.locator(sel).all():
                                    if el.is_visible():
                                        day_info["agent_chat_found"] = True
                                        day_info["chat_selector"] = sel
                                        # Send a test message
                                        el.fill("你好，介绍一下这个阶段的主要内容")
                                        page.keyboard.press("Enter")
                                        time.sleep(5)
                                        ss(page, f"04_phase{phase_num}_day{di+1}_chat_sent")
                                        # Check for reply
                                        page_text2 = page.locator("body").first.text_content() or ""
                                        day_info["after_chat_length"] = len(page_text2)
                                        day_info["reply_received"] = len(page_text2) > len(page_text) + 50
                                        print(f"        发送消息, 回复={'有' if day_info['reply_received'] else '无'}")
                                        break
                                if day_info.get("agent_chat_found"):
                                    break
                        except Exception as e:
                            day_info["agent_click_error"] = str(e)[:200]

                    # If "分身" button, click
                    clone_btns = page.locator("button:has-text('分身')").all()
                    if clone_btns:
                        print(f"      👥 点击分身按钮...")
                        try:
                            clone_btns[0].click()
                            time.sleep(2)
                            ss(page, f"05_phase{phase_num}_day{di+1}_clone")
                            clone_text = page.locator("body").first.text_content() or ""
                            day_info["clone_panel"] = clone_text[page_text.find("分身"):page_text.find("分身")+300] if "分身" in clone_text else ""
                        except Exception as e:
                            day_info["clone_error"] = str(e)[:200]

                    # Go back to Phase view
                    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
                    time.sleep(1)
                    # Re-click Phase
                    for btn in page.locator("button").all():
                        if btn.is_visible() and f"Phase 0{phase_num}" in (btn.text_content() or ""):
                            btn.click()
                            time.sleep(2)
                            break

                except Exception as e:
                    day_info["error"] = str(e)[:200]
                    print(f"      ❌ {e}")

                phase_info["days"].append(day_info)

            phases_data[f"phase_{phase_num}"] = phase_info

        # ── 3. Phase 5: Robot Agent ──
        print(f"\n{'─'*40}")
        print("🤖 Phase 5 Robot Agent 专项")
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)
        for btn in page.locator("button").all():
            if btn.is_visible() and "Phase 05" in (btn.text_content() or ""):
                btn.click()
                time.sleep(2)
                break

        ss(page, "06_phase5_robot")

        # Click "机器人项目 Agent"
        for btn in page.locator("button").all():
            t = (btn.text_content() or "").strip()
            if btn.is_visible() and ("机器人" in t or "Agent可用" in t):
                print(f"  点击: {t}")
                btn.click()
                time.sleep(3)
                ss(page, "06_phase5_agent_clicked")
                # Find chat
                for sel in ["textarea", "input[type='text']"]:
                    for el in page.locator(sel).all():
                        if el.is_visible():
                            el.fill("你好，介绍机器人项目的目标")
                            page.keyboard.press("Enter")
                            print("  ✅ Agent消息已发送")
                            time.sleep(8)
                            ss(page, "06_phase5_agent_reply")
                            page_text = page.locator("body").first.text_content() or ""
                            print(f"  回复长度: {len(page_text)}")
                            break
                    break
                break

        # ── 4. "课程日历" ──
        print(f"\n{'─'*40}")
        print("📅 课程日历")
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)
        for btn in page.locator("button").all():
            if btn.is_visible() and "课程日历" in (btn.text_content() or ""):
                btn.click()
                time.sleep(2)
                ss(page, "07_calendar")
                page_text = page.locator("body").first.text_content() or ""
                print(f"  日历内容: {page_text[page_text.find('课程日历'):][:300]}")
                break

        browser.close()

        # ── Save report ──
        report = {
            "platform": BASE_URL,
            "structure": "Phase → Day (not Lesson)",
            "phases": phases_data,
        }
        report_path = OUTPUT_DIR / "deep_exploration.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                               encoding="utf-8")
        print(f"\n✅ 深入探索完成: {report_path}")

        # ── Summary ──
        print(f"\n📊 摘要:")
        for pn, pdata in phases_data.items():
            days = pdata.get("days", [])
            if days:
                has_chat = sum(1 for d in days if d.get("agent_chat_found"))
                has_reply = sum(1 for d in days if d.get("reply_received"))
                print(f"  {pn}: {len(days)} Days, Agent对话={has_chat}可用, "
                      f"有回复={has_reply}, 按钮: {days[0].get('nav_buttons', []) if days else []}")


if __name__ == "__main__":
    explore_deep()
