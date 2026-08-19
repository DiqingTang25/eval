"""全链路诊断测试 — 从 HTTP API 到 Browser 逐环检测"""
import subprocess, sys, time, json, urllib.request

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def test(step, fn):
    print(f"\n{'='*50}\n  Test: {step}\n{'='*50}")
    try:
        fn()
        print(f"  ✅ {step} PASSED")
    except Exception as e:
        print(f"  ❌ {step} FAILED: {e}")

# ── 环 1: 平台可达性 ──
def test1():
    req = urllib.request.Request("http://124.174.108.70/personalized-secure")
    with urllib.request.urlopen(req, timeout=10) as r:
        body = r.read().decode()[:200]
        assert len(body) > 50, f"Page too short: {len(body)} chars"
        assert "<!DOCTYPE" in body or "<html" in body, "Not HTML"
    print(f"  Page starts: {body[:100]}")

# ── 环 2: API 端点 ──
def test2():
    body = json.dumps({"strategy": "spot_check", "target_url": "http://124.174.108.70/personalized-secure"}).encode()
    req = urllib.request.Request("http://127.0.0.1:8000/api/tests/run-multi-agent",
        data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
        assert data.get("status") == "started", f"Not started: {data}"
        print(f"  Session: {data.get('session_id')}")

# ── 环 3: Planner 独立测试 ──
def test3():
    import os
    os.chdir("/opt/agent_eval")
    sys.path.insert(0, "/opt/agent_eval")
    from src.multi_agent.planner import PlannerAgent
    p = PlannerAgent()
    plan = p.generate(strategy="spot_check")
    assert plan.plan_available, f"Plan not available: {plan.error}"
    assert len(plan.phases) > 0, "0 phases"
    print(f"  Phases: {len(plan.phases)}, Lessons: {sum(len(ph.lessons) for ph in plan.phases)}")

# ── 环 4: BrowserEvaluator 登录测试 ──
def test4():
    import os, sys
    os.chdir("/opt/agent_eval")
    sys.path.insert(0, "/opt/agent_eval")
    from src.browser_evaluator import BrowserEvaluator
    from playwright.sync_api import sync_playwright

    target = "http://124.174.108.70/personalized-secure"
    print(f"  Target: {target}")

    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # Navigate to target
    print("  Navigating...")
    page.goto(target, timeout=15000)
    page.wait_for_load_state("domcontentloaded", timeout=10000)
    time.sleep(3)

    body_text = page.locator("body").first.text_content() or ""
    print(f"  Page title: {page.title()}")
    print(f"  Body length: {len(body_text)} chars")
    print(f"  Has login: {'登录' in body_text or 'login' in body_text.lower()}")
    print(f"  Has Phase: {'Phase' in body_text}")

    # Find input fields
    inputs = page.locator("input:not([type=hidden])").all()
    for inp in inputs:
        if inp.is_visible():
            t = inp.get_attribute("type") or "text"
            placeholder = inp.get_attribute("placeholder") or ""
            print(f"  Input: type={t}, placeholder={placeholder}")

    # Find buttons
    buttons = page.locator("button").all()
    for btn in buttons:
        if btn.is_visible():
            txt = (btn.text_content() or "").strip()[:60]
            if txt:
                print(f"  Button: {txt}")

    browser.close()
    p.stop()

# ── 环 5: WS 事件完整性 ──
def test5():
    import asyncio
    import websockets

    async def ws_test():
        uri = "ws://127.0.0.1:8000/ws"
        async with websockets.connect(uri) as ws:
            # Start test
            body = json.dumps({"strategy": "spot_check", "target_url": "http://124.174.108.70/personalized-secure"})
            req = urllib.request.Request("http://127.0.0.1:8000/api/tests/run-multi-agent",
                data=body.encode(), headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as r:
                print(f"  Started: {json.loads(r.read()).get('session_id','?')}")

            events = []
            for _ in range(90):  # 90 second timeout
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                msg = json.loads(raw)
                t = msg.get("type", "")
                if t not in events[-3:]:  # dedup consecutive
                    events.append(t)
                    d = msg.get("data", {})
                    info = ""
                    if t == "multi_agent:plan_ready" and d.get("phases"):
                        info = f" ({len(d['phases'])} phases)"
                    elif t == "multi_agent:step_start":
                        info = f" ({d.get('phase','')} -> {d.get('step','')})"
                    elif t == "multi_agent:verify_done":
                        info = f" (verdict={d.get('verdict','')})"
                    elif t == "multi_agent:diagnosis":
                        info = f" ({d.get('finding','')[:60]})"
                    elif t == "multi_agent:done":
                        info = f" (pass_rate={d.get('pass_rate',0)})"
                    print(f"  WS ({len(events)}): {t}{info}")
                if t == "multi_agent:done":
                    break

    asyncio.run(ws_test())

# ── Run tests ──
if __name__ == "__main__":
    test("环1: 平台可达性", test1)
    test("环2: API 端点", test2)
    test("环3: Planner 独立测试", test3)
    test("环4: Browser 登录探测", test4)
    test("环5: WS 全链路", test5)
