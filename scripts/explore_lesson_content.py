#!/usr/bin/env python3
"""进入 Day 学习模式后的内容结构探索"""
import json, time
from playwright.sync_api import sync_playwright

BASE = "http://124.174.108.70"
USER, PW = "student001", "123456"

def ss(p, n):
    try: p.screenshot(path=f"/home/jennifer07/agent_eval/explore_output/screenshots/999_{n}.png",
                      full_page=True, timeout=5000)
    except: pass

def dump(pg):
    return pg.evaluate("""() => {
        const info = {};
        info.bodyText = document.body.textContent.substring(0, 3000);
        info.title = document.title;
        info.url = location.href;
        info.buttons = [...document.querySelectorAll('button')]
            .filter(b => b.offsetParent)
            .map(b => ({
                text: b.textContent.trim().substring(0, 100),
                class: b.className.substring(0, 60),
                disabled: b.disabled
            }));
        info.inputs = [...document.querySelectorAll('input, textarea, [contenteditable=true]')]
            .filter(el => el.offsetParent)
            .map(el => ({
                tag: el.tagName, type: el.type || '',
                placeholder: el.placeholder || '',
                class: el.className?.substring(0, 60) || ''
            }));
        // Find specific containers
        info.containers = [...document.querySelectorAll(
            '[class*=step], [class*=content], [class*=checklist], ' +
            '[class*=panel], [class*=agent], [class*=chat], [class*=guide], ' +
            '[class*=self], [class*=module], [class*=task], [class*=body]'
        )]
            .filter(el => el.offsetParent)
            .map(el => ({
                class: el.className?.substring(0, 80) || '',
                text: el.textContent?.trim().substring(0, 200) || '',
                childCount: el.children.length,
            }));
        return info;
    }""")

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1440, "height": 900})

    # Login
    pg.goto(BASE, wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    for i in pg.locator("input:not([type=hidden])").all():
        t = i.get_attribute("type") or "text"
        if t == "text": i.fill(USER)
        elif t == "password": i.fill(PW)
    for btn in pg.locator("button").all():
        if btn.is_visible() and "登录" in (btn.text_content() or ""):
            btn.click(); break
    time.sleep(4)
    pg.wait_for_load_state("networkidle", timeout=15000)
    ss(pg, "login")

    # Click Phase 1
    for btn in pg.locator("button").all():
        if "Phase 01" in (btn.text_content() or ""):
            btn.click(); time.sleep(2); break

    # Click Day 1
    for btn in pg.locator("button").all():
        t = (btn.text_content() or "").strip()
        if t.startswith("Day 1") and not btn.is_disabled():
            btn.click(); time.sleep(3); break

    ss(pg, "mode_select")
    dom_mode = dump(pg)
    print("=== MODE SELECTION PAGE ===")
    print(f"Title: {dom_mode['title']}")
    print(f"Body ({len(dom_mode['bodyText'])} chars): {dom_mode['bodyText'][:400]}")
    print(f"Buttons:")
    for b in dom_mode['buttons']:
        flag = " [DISABLED]" if b['disabled'] else ""
        print(f"  [{b['class'][:40]}] {b['text'][:80]}{flag}")

    # Find and click "进入引导学习" or "进入自主探索"
    clicked = False
    for btn_text in ["进入引导学习", "进入自主探索", "帮帮我", "我自己来"]:
        for btn in pg.locator("button").all():
            t = (btn.text_content() or "").strip()
            if btn.is_visible() and btn_text in t and not btn.is_disabled():
                print(f"\n>>> Clicking: {t[:80]}")
                btn.click()
                time.sleep(5)
                pg.wait_for_load_state("networkidle", timeout=10000)
                clicked = True
                break
        if clicked:
            break

    if not clicked:
        print("WARNING: No enter button found, trying any button with '进入'")
        for btn in pg.locator("button").all():
            t = (btn.text_content() or "").strip()
            if "进入" in t and not btn.is_disabled():
                print(f">>> Clicking: {t[:80]}")
                btn.click(); time.sleep(5); clicked = True; break

    if clicked:
        ss(pg, "lesson_content")
        dom = dump(pg)
        print(f"\n=== LESSON CONTENT PAGE ===")
        print(f"Title: {dom['title']}")
        print(f"URL: {dom['url']}")
        print(f"Body ({len(dom['bodyText'])} chars):")
        print(dom['bodyText'][:800])
        print(f"\nButtons ({len(dom['buttons'])}):")
        for b in dom['buttons'][:20]:
            flag = " [DISABLED]" if b['disabled'] else ""
            print(f"  [{b['class'][:40]}] {b['text'][:80]}{flag}")
        print(f"\nInputs ({len(dom['inputs'])}):")
        for i in dom['inputs'][:10]:
            print(f"  [{i['class'][:40]}] {i['tag']} type={i['type']} ph='{i['placeholder']}'")
        print(f"\nContainers ({len(dom['containers'])}):")
        for c in dom['containers'][:20]:
            print(f"  [{c['class'][:60]}] ({c['childCount']} children)")
            if c['text']:
                print(f"    -> {c['text'][:150]}")

        # If there's a step list, try clicking first step
        step_btns = [b for b in dom['buttons'] if 'step' in b['class'].lower() or 'Step' in b['text']]
        if step_btns:
            print(f"\n>>> Found {len(step_btns)} step buttons, clicking first...")
            for btn in pg.locator("button").all():
                t = (btn.text_content() or "").strip()
                if btn.is_visible() and ("Step" in t or "step" in t.lower()) and not btn.is_disabled():
                    print(f"Clicking: {t[:60]}")
                    btn.click(); time.sleep(3); break
            ss(pg, "step_content")
            dom_step = dump(pg)
            print(f"\n=== STEP PAGE ===")
            print(f"Body ({len(dom_step['bodyText'])} chars): {dom_step['bodyText'][:600]}")
            for i in dom_step.get('inputs', []):
                print(f"  INPUT: [{i['class'][:40]}] {i['tag']} ph='{i['placeholder']}'")

    else:
        print("\nFAILED: Could not enter lesson content")
        # Dump what we see
        dom = dump(pg)
        print(f"Current page: {dom['title']}")
        print(f"Buttons:")
        for b in dom['buttons']:
            print(f"  [{b['class'][:40]}] {b['text'][:80]}")

    b.close()
