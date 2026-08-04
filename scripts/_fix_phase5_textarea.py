"""
Phase 5 textarea 修复验证 — 测试 page.fill() + Enter 发送

诊断结论 (from _diag_phase5.py):
  - .course-agent-composer textarea 可见, placeholder="输入当前问题，Enter 发送，Shift + Enter 换行"
  - "发送" 按钮 disabled (React 受控组件, JS nativeSetter 不触发 onChange)
  - placeholder 明确说 "Enter 发送" → Enter 键才是正确发送方式

修复方案:
  1. Playwright page.locator('textarea').fill(text) — 逐字输入, 触发 React 合成事件
  2. page.keyboard.press("Enter") — placeholder 说 Enter 发送
  3. 如果还是不行 → 直接用 API: POST /phase3-api/agent/chat
"""
import time, json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

BASE = "http://124.174.108.70"
USER, PW = "student001", "123456"
OUT = Path(__file__).parent.parent / "explore_output" / "phase5_diag"
OUT.mkdir(parents=True, exist_ok=True)

def login(page):
    page.goto(BASE, timeout=60000)
    time.sleep(3)
    # Check if already logged in
    body = page.locator("body").first.text_content() or ""
    if "Phase" in body[:600] and "登录" not in body[:500]:
        print("  已登录, 跳过")
        return True
    for inp in page.locator("input:not([type=hidden])").all():
        if not inp.is_visible():
            continue
        t = inp.get_attribute("type") or "text"
        if t in ("text", "email"):
            inp.fill(USER)
        elif t == "password":
            inp.fill(PW)
    for btn in page.locator("button").all():
        if btn.is_visible() and "登录" in (btn.text_content() or ""):
            btn.click()
            break
    time.sleep(4)
    return True


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # Network monitoring
    chat_api_calls = []
    def on_response(resp):
        url = resp.url
        if any(kw in url for kw in ["chat", "agent", "stream"]):
            try:
                body = resp.text()[:1000]
            except:
                body = "[unreadable]"
            chat_api_calls.append({
                "url": url[:200],
                "status": resp.status,
                "body": body,
            })

    page.on("response", on_response)

    print("=" * 60)
    print("🔧 Phase 5 textarea 修复验证")
    print("=" * 60)

    # ── 1. 登录 + 进入 Phase 5 ──
    login(page)

    # 点击 Phase 05
    for btn in page.locator("button").all():
        t = (btn.text_content() or "").strip()
        if "Phase 05" in t or "Phase 5" in t:
            btn.click()
            time.sleep(3)
            print(f"✅ 进入: {t[:60]}")
            break

    page.screenshot(path=str(OUT / "fix_01_landing.png"), full_page=True)

    # ── 2. 找到正确的 textarea ──
    dom = page.evaluate("""() => {
        const tas = [...document.querySelectorAll('textarea')].map(ta => ({
            placeholder: ta.placeholder || '',
            visible: ta.offsetParent !== null,
            class: ta.className?.substring?.(0, 80) || '',
            parentClass: ta.parentElement?.className?.substring?.(0, 80) || '',
        }));
        return tas;
    }""")

    print(f"\n📋 Textareas 状态:")
    for ta in dom:
        vis = "👁" if ta["visible"] else "👻"
        print(f"  {vis} class={ta['class'][:60]}")
        print(f"     placeholder='{ta['placeholder']}'")
        print(f"     parent={ta['parentClass']}")

    # ── 3. 方法1: page.fill() + Enter ──
    print("\n" + "=" * 60)
    print("📋 方法1: page.fill() + Enter")
    print("=" * 60)

    test_questions = [
        "你好，我想做一个避障小车，从哪里开始？",
        "Arduino和树莓派哪个更适合？",
    ]

    for i, q in enumerate(test_questions):
        print(f"\n── 对话 {i+1}: {q[:60]} ──")
        page.screenshot(path=str(OUT / f"fix_round{i+1}_before.png"), full_page=True)

        # 获取初始消息数量
        msgs_before = page.evaluate("""
            document.querySelectorAll('.course-agent-messages > *, '
                + '.course-agent-messages [class*=msg], '
                + '.course-agent-messages [class*=bubble]').length
        """)
        body_before = len(page.locator("body").first.text_content() or "")

        # 🎯 核心修复: Playwright fill() 替代 JS nativeSetter
        try:
            ta = page.locator(".course-agent-composer textarea").first
            ta.wait_for(state="visible", timeout=5000)
            ta.click()          # 先 focus
            time.sleep(0.3)
            ta.fill("")         # 清空
            ta.fill(q)          # Playwright fill = 逐字输入 + 触发所有事件
            time.sleep(0.5)

            # 检查发送按钮是否启用了
            btn_state = page.evaluate("""() => {
                const btns = [...document.querySelectorAll('button')];
                for (const b of btns) {
                    const t = b.textContent.trim();
                    if (t === '发送' || t.includes('发送')) {
                        return {found: true, disabled: b.disabled, text: t};
                    }
                }
                return {found: false};
            }""")
            print(f"  发送按钮状态: {json.dumps(btn_state, ensure_ascii=False)}")

            # 按 Enter 发送
            page.keyboard.press("Enter")
            print(f"  ✅ Enter 发送")

            # 等待回复
            time.sleep(4)
            waited = 0
            while waited < 20:
                status_text = page.evaluate("""() => {
                    const panel = document.querySelector('.course-agent-panel, .phase5-agent-page');
                    if (!panel) return 'no-panel';
                    const t = panel.textContent || '';
                    if (t.includes('正在回答') || t.includes('正在处理')) return 'thinking';
                    return 'ready';
                }""")
                if status_text == "ready":
                    break
                time.sleep(2)
                waited += 2
                print(f"  ⏳ 等待中... ({waited}s)")

            body_after = len(page.locator("body").first.text_content() or "")
            msgs_after = page.evaluate("""
                document.querySelectorAll('.course-agent-messages > *, '
                    + '.course-agent-messages [class*=msg], '
                    + '.course-agent-messages [class*=bubble]').length
            """)
            delta = body_after - body_before

            print(f"  body: {body_before} → {body_after} (Δ{delta})")
            print(f"  messages: {msgs_before} → {msgs_after}")

            page.screenshot(path=str(OUT / f"fix_round{i+1}_after.png"), full_page=True)

        except PwTimeout as e:
            print(f"  ❌ Timeout: {e}")
        except Exception as e:
            print(f"  ❌ Error: {e}")

    # ── 4. API fallback 探测 (如果前端还是不通, 直接调 API) ──
    print("\n" + "=" * 60)
    print("📋 Chat API 探测")
    print("=" * 60)

    # 查看已捕获的 API 调用
    chat_apis = [c for c in chat_api_calls if "chat" in c.get("url", "") or "agent" in c.get("url", "")]
    print(f"  Chat API 调用: {len(chat_apis)}")
    for c in chat_apis:
        print(f"    {c['status']} {c['url']}")
        print(f"    body: {c['body'][:300]}")

    # 尝试用 localStorage token 直接调 API
    token = page.evaluate("localStorage.getItem('aix_token') || localStorage.getItem('token') || ''")
    print(f"\n  Token: {'✅ 有' if token else '❌ 无'} ({len(token)} chars)")

    # ── 5. React 组件内部状态探测 ──
    print("\n" + "=" * 60)
    print("📋 React 内部状态探测")
    print("=" * 60)

    react_state = page.evaluate("""() => {
        // 尝试找到 React fiber
        const ta = document.querySelector('.course-agent-composer textarea');
        if (!ta) return {error: 'no textarea'};

        // 找 React 内部属性
        const reactKeys = Object.keys(ta).filter(k =>
            k.startsWith('__react') ||
            k.startsWith('__reactFiber') ||
            k.startsWith('__reactInternalInstance') ||
            k.startsWith('_react') ||
            k.startsWith('__reactProps')
        );

        return {
            reactKeys,
            textarea_value: ta.value?.substring?.(0, 100),
            textarea_textContent: ta.textContent?.substring?.(0, 100),
            disabled: ta.disabled,
            readOnly: ta.readOnly,
        };
    }""")
    print(f"  React keys: {react_state.get('reactKeys', [])}")
    print(f"  textarea value: {react_state.get('textarea_value', 'N/A')}")
    print(f"  textarea disabled: {react_state.get('disabled')}")
    print(f"  textarea readOnly: {react_state.get('readOnly')}")

    # ── 6. 如果上面都不行 → 直接用 fetch 调 API ──
    print("\n" + "=" * 60)
    print("📋 API 直接调用 (Fallback)")
    print("=" * 60)

    if token:
        # 用浏览器内的 fetch 直接调
        api_result = page.evaluate(f"""
            (async () => {{
                const token = localStorage.getItem('aix_token') || localStorage.getItem('token');
                const q = {json.dumps(test_questions[0])};
                try {{
                    const resp = await fetch('/phase3-api/agent/chat', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                            'Authorization': 'Bearer ' + token,
                        }},
                        body: JSON.stringify({{
                            message: q,
                            phase_id: 5,
                        }}),
                    }});
                    const data = await resp.json();
                    return {{
                        ok: resp.ok,
                        status: resp.status,
                        data: JSON.stringify(data).substring(0, 800),
                    }};
                }} catch(e) {{
                    return {{error: e.message}};
                }}
            }})()
        """)
        print(f"  API 直接调用结果: {json.dumps(api_result, ensure_ascii=False)[:500]}")

    # ── 最终截图 ──
    print("\n" + "=" * 60)
    print("📋 最终页面状态")
    body = page.locator("body").first.text_content() or ""
    # 只显示 Phase 5 Agent 相关的内容
    agent_section = page.evaluate("""() => {
        const panel = document.querySelector('.course-agent-panel, .phase5-agent-page');
        return panel ? panel.textContent?.substring?.(0, 1000) : 'no panel found';
    }""")
    print(f"  Agent 面板内容:\n{agent_section}")

    browser.close()
    print(f"\n✅ 截图: {OUT}/fix_*.png")
