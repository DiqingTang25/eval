#!/usr/bin/env python3
"""环4: BrowserEvaluator 登录测试 — 单独测试浏览器导航和登录"""
import sys, os, time, json

os.chdir("/opt/agent_eval")
sys.path.insert(0, "/opt/agent_eval")

from playwright.sync_api import sync_playwright

target = "http://124.174.108.70/personalized-secure"
print(f"Target: {target}")

p = sync_playwright().start()
browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
page = browser.new_page(viewport={"width": 1440, "height": 900})

try:
    # Step 1: Navigate
    print("Step 1: Navigating...")
    page.goto(target, timeout=20000)
    page.wait_for_load_state("domcontentloaded", timeout=10000)
    time.sleep(3)
    print(f"  URL: {page.url}")
    print(f"  Title: {page.title()}")

    # Step 2: Check page content
    body_text = page.locator("body").first.text_content() or ""
    print(f"  Body: {len(body_text)} chars")
    print(f"  has login: {('login' in body_text.lower() or '登录' in body_text)}")
    print(f"  has Phase: {('Phase' in body_text)}")
    print(f"  first 200: {body_text[:200]}")

    # Step 3: Find inputs
    inputs = page.locator("input:not([type=hidden])").all()
    print(f"  Inputs: {len(inputs)} total")
    for inp in inputs:
        try:
            if inp.is_visible():
                t = inp.get_attribute("type") or "text"
                ph = inp.get_attribute("placeholder") or ""
                nm = inp.get_attribute("name") or ""
                print(f"    visible: type={t} name={nm} placeholder={ph}")
        except Exception:
            pass

    # Step 4: Find buttons
    buttons = page.locator("button").all()
    print(f"  Buttons: {len(buttons)} total")
    for btn in buttons:
        try:
            if btn.is_visible():
                txt = (btn.text_content() or "").strip()[:80]
                if txt:
                    print(f"    visible: {txt}")
        except Exception:
            pass

    # Step 5: Try BrowserEvaluator login
    print("\nStep 2: Testing BrowserEvaluator.login()...")
    from src.browser_evaluator import BrowserEvaluator
    evaluator = BrowserEvaluator(headless=True, base_url=target)
    evaluator.page = page
    ok = evaluator.login()
    print(f"  login() returned: {ok}")
    print(f"  Final URL: {page.url}")

finally:
    browser.close()
    p.stop()
    print("Browser closed")
