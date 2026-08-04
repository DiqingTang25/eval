"""诊断每个Day有多少Step，以及两种模式的差异"""
import time, json
from playwright.sync_api import sync_playwright

BASE, USER, PW = "http://124.174.108.70", "student001", "123456"

def login(pg):
    pg.goto(BASE, wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    for inp in pg.locator("input:not([type=hidden])").all():
        t = inp.get_attribute("type") or "text"
        if t == "text": inp.fill(USER)
        elif t == "password": inp.fill(PW)
    for btn in pg.locator("button").all():
        if btn.is_visible() and "登录" in (btn.text_content() or ""): btn.click(); break
    time.sleep(4)

def check_day(pg, phase, day):
    """进入Day，选择模式，看有多少Step"""
    pg.goto(BASE, wait_until="domcontentloaded", timeout=15000)
    time.sleep(1.5)
    # Phase
    for btn in pg.locator("button").all():
        if f"Phase 0{phase}" in (btn.text_content() or ""): btn.click(); time.sleep(2); break
    # Day
    for btn in pg.locator("button").all():
        t = (btn.text_content() or "").strip()
        if t.startswith(f"Day {day}") and not btn.is_disabled(): btn.click(); time.sleep(3); break

    # Dump mode selection page
    body = pg.locator("body").first.text_content() or ""
    # Check for mode buttons
    has_guided = "帮帮我" in body or "进入引导学习" in body
    has_self = "我自己来" in body or "进入自主探索" in body
    print(f"  Phase{phase} Day{day}: guided={has_guided} self={has_self}")

    # Enter guided mode
    for btn in pg.locator("button").all():
        t = (btn.text_content() or "").strip()
        if ("进入引导学习" in t or "帮帮我" in t) and not btn.is_disabled():
            btn.click(); time.sleep(4); break

    body2 = pg.locator("body").first.text_content() or ""
    import re
    m = re.search(r'Step\s+(\d+)\s*/\s*(\d+)', body2)
    total_guided = int(m.group(2)) if m else 0
    print(f"    帮帮我模式: {total_guided} Steps")

    # Get step titles from sidebar
    steps_guided = pg.evaluate("""() => {
        return [...document.querySelectorAll('[class*=mini-step], [class*=step-title-row], [class*=step-num]')]
            .map(el => el.textContent.trim().substring(0, 80));
    }""")
    for s in steps_guided[:8]: print(f"      {s}")

    # Go back and try self mode
    for btn in pg.locator("button").all():
        t = (btn.text_content() or "").strip()
        if "返回课程日历" in t: btn.click(); time.sleep(2); break

    # Re-click Day
    for btn in pg.locator("button").all():
        t = (btn.text_content() or "").strip()
        if t.startswith(f"Day {day}") and not btn.is_disabled(): btn.click(); time.sleep(3); break

    # Enter self mode
    for btn in pg.locator("button").all():
        t = (btn.text_content() or "").strip()
        if ("进入自主探索" in t or "我自己来" in t) and not btn.is_disabled():
            btn.click(); time.sleep(4); break

    body3 = pg.locator("body").first.text_content() or ""
    m2 = re.search(r'Step\s+(\d+)\s*/\s*(\d+)', body3)
    total_self = int(m2.group(2)) if m2 else 0
    print(f"    我自己来模式: {total_self} Steps")
    steps_self = pg.evaluate("""() => {
        return [...document.querySelectorAll('[class*=mini-step], [class*=step-title-row]')]
            .map(el => el.textContent.trim().substring(0, 80));
    }""")
    for s in steps_self[:8]: print(f"      {s}")

    # Check mode differences
    has_checklist = "检查清单" in body3 or "checklist" in body3.lower()
    has_agent_btn = "我卡住了" in body3
    print(f"    自己模式: checklist={has_checklist} agent_btn={has_agent_btn}")
    print(f"    内容预览: {body3[body3.find('Step'):][:300]}")

    return total_guided, total_self

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    login(pg)

    results = {}
    for phase in [1]:
        print(f"\n=== Phase {phase} ===")
        for day in range(1, 5):
            g, s = check_day(pg, phase, day)
            results[f"p{phase}d{day}"] = {"guided_steps": g, "self_steps": s}

    print(f"\n=== SUMMARY ===")
    print(json.dumps(results, indent=2))
    b.close()
