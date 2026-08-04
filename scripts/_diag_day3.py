"""快速诊断：Day 3 点击后的页面内容"""
import time, json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.goto("http://124.174.108.70", wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    for inp in pg.locator("input:not([type=hidden])").all():
        t = inp.get_attribute("type") or "text"
        if t == "text": inp.fill("student001")
        elif t == "password": inp.fill("123456")
    for btn in pg.locator("button").all():
        if btn.is_visible() and "登录" in (btn.text_content() or ""):
            btn.click(); break
    time.sleep(4)

    # Phase 1
    for btn in pg.locator("button").all():
        if "Phase 01" in (btn.text_content() or ""):
            btn.click(); time.sleep(2); break

    # Click Day 3
    for btn in pg.locator("button").all():
        t = (btn.text_content() or "").strip()
        if t.startswith("Day 3") and not btn.is_disabled():
            btn.click(); time.sleep(4); break

    # Dump
    dom = pg.evaluate("""() => ({
        body: document.body.textContent.substring(0, 1500),
        btns: [...document.querySelectorAll('button')]
            .filter(x => x.offsetParent)
            .map(x => ({t: x.textContent.trim().substring(0, 120), d: x.disabled}))
    })""")
    print("=== DAY 3 PAGE ===")
    print("Body:", dom["body"][:800])
    print("\nButtons:")
    for bt in dom["btns"][:15]:
        flag = " [DISABLED]" if bt["d"] else ""
        print(f"  {bt['t'][:100]}{flag}")
    b.close()
