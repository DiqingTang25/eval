"""
Phase 5 深度诊断 — 理解机器人Agent的真实交互机制

Phase 5 不同於 Phase 1-4，不是"选Day→Step→Agent"的流程，
而是独立的"机器人项目Agent"常驻对话页面。

本脚本用 Playwright 深入探索：
1. 页面 DOM 结构 (Agent 面板在哪，用什么组件)
2. 网络 API 请求 (聊天用什么 endpoint)
3. WebSocket 连接 (是否有实时通信)
4. 实际交互测试 (JS 注入 vs 原生点击)
"""
import time, json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://124.174.108.70"
USER, PW = "student001", "123456"
SCREENSHOT = Path(__file__).parent.parent / "explore_output" / "phase5_diag"
SCREENSHOT.mkdir(parents=True, exist_ok=True)

def ss(page, name):
    page.screenshot(path=str(SCREENSHOT / f"{name}.png"), full_page=True)
    print(f"  📸 {name}")

def login(page):
    page.goto(BASE, timeout=60000)
    time.sleep(2)
    body = page.locator("body").first.text_content() or ""
    if "Phase" in body and "登录" not in body[:500]:
        return True
    for inp in page.locator("input:not([type=hidden])").all():
        if not inp.is_visible(): continue
        t = inp.get_attribute("type") or "text"
        if t == "text": inp.fill(USER)
        elif t == "password": inp.fill(PW)
    for btn in page.locator("button").all():
        if btn.is_visible() and "登录" in (btn.text_content() or ""):
            btn.click(); break
    time.sleep(4)
    return True

# ═══════════════════════════════════════
# 主诊断流程
# ═══════════════════════════════════════
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # 收集所有网络请求
    network_log = []
    ws_log = []
    def on_request(req):
        url = req.url
        # 只关注 API 和 WebSocket
        if any(kw in url for kw in ["/api/", "/phase3-api/", "chat", "agent", "stream"]):
            network_log.append({
                "type": req.resource_type,
                "method": req.method,
                "url": url[:200],
                "headers": dict(list(req.headers.items())[:5]) if hasattr(req, 'headers') else None,
            })
    def on_response(resp):
        url = resp.url
        if any(kw in url for kw in ["/api/", "/phase3-api/", "chat", "agent"]):
            try:
                body = resp.text()[:500]
            except:
                body = "[unreadable]"
            network_log.append({
                "type": "response",
                "status": resp.status,
                "url": url[:200],
                "body_preview": body[:300],
            })
    def on_ws(ws):
        ws_log.append({"event": "open", "url": ws.url})
        ws.on("framereceived", lambda payload: ws_log.append(
            {"event": "recv", "data": str(payload)[:500]}))
        ws.on("framesent", lambda payload: ws_log.append(
            {"event": "send", "data": str(payload)[:500]}))

    page.on("request", on_request)
    page.on("response", on_response)
    page.on("websocket", on_ws)

    # ── 1. 登录并导航到 Phase 5 ──
    print("=" * 60)
    print("🔬 Phase 5 深度诊断")
    print("=" * 60)

    login(page)
    ss(page, "01_after_login")

    # 点击 Phase 05
    for btn in page.locator("button").all():
        t = (btn.text_content() or "").strip()
        if "Phase 05" in t or "Phase 5" in t:
            btn.click()
            time.sleep(3)
            print(f"✅ 点击: {t[:60]}")
            break
    ss(page, "02_phase5_landing")

    # ── 2. 导出完整 DOM ──
    print("\n📋 1. Phase 5 页面 DOM 结构")
    dom = page.evaluate("""() => ({
        url: location.href,
        title: document.title,
        bodyText: document.body.innerText.substring(0, 2000),
        allButtons: [...document.querySelectorAll('button')]
            .filter(b => b.offsetParent || b.offsetWidth > 0)
            .map(b => ({
                text: b.textContent.trim().substring(0, 120),
                class: b.className?.substring?.(0, 80) || '',
                disabled: b.disabled,
                visible: b.offsetParent !== null,
            })),
        allInputs: [...document.querySelectorAll('input, textarea, [contenteditable=true]')]
            .map(el => ({
                tag: el.tagName,
                type: el.type || '',
                placeholder: (el.placeholder || '').substring(0, 80),
                visible: el.offsetParent !== null,
                parentClass: el.parentElement?.className?.substring?.(0, 80) || '',
            })),
        iframes: [...document.querySelectorAll('iframe')].map(f => ({
            src: f.src?.substring?.(0, 200) || '',
            id: f.id,
            name: f.name,
        })),
        // 特别关注: Agent 面板区域
        agentPanel: (() => {
            const selectors = [
                '[class*=agent]', '[class*=chat]', '[class*=panel]',
                '[class*=drawer]', '[class*=sidebar]', '[class*=dialog]',
                '[id*=agent]', '[id*=chat]', '[id*=panel]',
            ];
            const found = [];
            for (const sel of selectors) {
                document.querySelectorAll(sel).forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0) {
                        found.push({
                            selector: sel,
                            tag: el.tagName,
                            class: el.className?.substring?.(0, 100) || '',
                            size: `${Math.round(rect.width)}x${Math.round(rect.height)}`,
                            pos: `${Math.round(rect.top)},${Math.round(rect.left)}`,
                            text: el.textContent?.trim?.()?.substring?.(0, 200) || '',
                        });
                    }
                });
            }
            return found;
        })(),
        // WebSocket 相关信息
        wsHints: (() => {
            const scripts = [...document.querySelectorAll('script')];
            const hints = [];
            for (const s of scripts) {
                const txt = s.textContent || s.src || '';
                if (/[Ww]eb[Ss]ocket/.test(txt) || txt.includes('wss://') || txt.includes('ws://')) {
                    hints.push(txt.substring(0, 500));
                }
            }
            return hints;
        })(),
    })""")

    print(f"  URL: {dom['url']}")
    print(f"  Title: {dom['title']}")
    print(f"  Buttons: {len(dom['allButtons'])}")
    for b in dom['allButtons'][:15]:
        vis = "👁" if b['visible'] else "👻"
        dis = " [DISABLED]" if b['disabled'] else ""
        print(f"    {vis} {b['text'][:80]}{dis}")
    print(f"  Inputs: {len(dom['allInputs'])}")
    for inp in dom['allInputs']:
        vis = "👁" if inp['visible'] else "👻"
        print(f"    {vis} <{inp['tag']}> type={inp['type']} placeholder='{inp['placeholder']}' parent={inp['parentClass'][:50]}")
    print(f"  iFrames: {len(dom['iframes'])}")
    for f in dom['iframes']:
        print(f"    src={f['src'][:100]} id={f['id']}")

    print(f"\n  🔍 Agent 面板探测:")
    for ap in dom['agentPanel'][:10]:
        print(f"    [{ap['selector']}] {ap['tag']}.{ap['class'][:60]} {ap['size']} @{ap['pos']}")
        print(f"      内容: {ap['text'][:150]}")

    print(f"\n  🔌 WebSocket 提示:")
    for h in dom['wsHints']:
        print(f"    {h[:200]}")

    # ── 3. 展开 Agent 面板 (尝试多种方式) ──
    print("\n" + "=" * 60)
    print("📋 2. Agent 面板展开尝试")

    # 方式1: 点击 Agent 按钮
    ss(page, "03_before_agent_click")
    clicked = False
    for btn_text in ["Agent", "AI", "机器人", "课程助教", "聊天", "Chat"]:
        for btn in page.locator("button").all():
            t = (btn.text_content() or "").strip()
            if btn_text in t and btn.is_visible():
                try:
                    btn.click()
                    time.sleep(2)
                    print(f"  ✅ 点击 '{t[:60]}'")
                    clicked = True
                    break
                except:
                    pass
        if clicked:
            break

    if not clicked:
        print("  ⚠️ 没找到Agent按钮，尝试JS强制展开")
        # 强制展开所有可能的面板
        page.evaluate("""
            document.querySelectorAll('[class*=panel], [class*=drawer], [class*=sidebar], [class*=chat]')
                .forEach(el => {
                    el.style.display = 'block';
                    el.style.visibility = 'visible';
                    el.style.opacity = '1';
                    el.style.transform = 'none';
                    el.style.height = 'auto';
                });
        """)
        time.sleep(1)

    ss(page, "04_after_agent_expand")

    # 重新扫 DOM
    dom2 = page.evaluate("""() => ({
        textareas: [...document.querySelectorAll('textarea')].map(ta => ({
            placeholder: ta.placeholder || '',
            visible: ta.offsetParent !== null,
            class: ta.className?.substring?.(0, 80) || '',
            parentHTML: ta.parentElement?.outerHTML?.substring?.(0, 300) || '',
        })),
        allInputs: [...document.querySelectorAll('input[type=text], input:not([type]), textarea, [contenteditable=true]')]
            .map(el => ({
                tag: el.tagName,
                type: el.type || '',
                placeholder: (el.placeholder || '').substring(0, 80),
                visible: el.offsetParent !== null,
                class: el.className?.substring?.(0, 80) || '',
            })),
        bodyAfter: document.body.innerText.substring(0, 1500),
    })""")

    print(f"\n  Textareas: {len(dom2['textareas'])}")
    for ta in dom2['textareas']:
        vis = "👁" if ta['visible'] else "👻"
        print(f"    {vis} placeholder='{ta['placeholder']}' class={ta['class'][:60]}")
        print(f"       parent: {ta['parentHTML'][:200]}")

    print(f"\n  所有可输入元素:")
    for inp in dom2['allInputs'][:10]:
        vis = "👁" if inp['visible'] else "👻"
        print(f"    {vis} <{inp['tag']}> type={inp['type']} placeholder='{inp['placeholder']}'")

    ss(page, "05_textarea_state")

    # ── 4. 尝试 JS 发送消息 ──
    print("\n" + "=" * 60)
    print("📋 3. 尝试发送消息")

    test_questions = [
        "你好，请介绍一下这个机器人项目",
        "我需要完成哪些任务？",
        "传感器怎么连接？",
    ]

    for i, q in enumerate(test_questions):
        print(f"\n  ── 对话 {i+1}: {q[:60]} ──")
        body_before = len(page.locator("body").first.text_content() or "")

        # 尝试: JS 找到 textarea → 填值 → dispatchEvent → 找send按钮
        send_result = page.evaluate(f"""
            (() => {{
                const q = {json.dumps(q)};

                // 找 textarea
                const tas = document.querySelectorAll('textarea');
                let target = null;
                for (const ta of tas) {{
                    const ph = ta.placeholder || '';
                    if (ph.includes('输入') || ph.includes('Enter') || ph.includes('发送') || ph.includes('消息')) {{
                        target = ta;
                        break;
                    }}
                }}
                if (!target && tas.length > 0) target = tas[0];

                if (!target) return {{ok: false, reason: 'no textarea found'}};

                // 原生 setter 填值 + 事件
                const nativeSetter = Object.getOwnPropertyDescriptor(
                    HTMLTextAreaElement.prototype, 'value'
                );
                if (nativeSetter && nativeSetter.set) {{
                    nativeSetter.set.call(target, q);
                }} else {{
                    target.value = q;
                }}
                target.dispatchEvent(new Event('input', {{bubbles: true, composed: true}}));
                target.dispatchEvent(new Event('change', {{bubbles: true, composed: true}}));
                target.focus();

                return {{
                    ok: true,
                    placeholder: target.placeholder,
                    value: target.value?.substring?.(0, 80),
                    visible: target.offsetParent !== null,
                    parentTag: target.parentElement?.tagName,
                }};
            }})()
        """)
        print(f"    填值: {json.dumps(send_result, ensure_ascii=False)[:300]}")

        if send_result.get("ok"):
            # 找发送按钮
            btn_result = page.evaluate("""
                (() => {
                    const btns = [...document.querySelectorAll('button')];
                    for (const b of btns) {
                        const t = b.textContent.trim();
                        if (/发送|Send|submit|→|send/i.test(t) && b.offsetParent) {
                            b.click();
                            return {ok: true, text: t.substring(0, 60)};
                        }
                    }
                    // 没找到按钮 → 试试 Enter
                    return {ok: false, reason: 'no send button', fallback: 'Enter'};
                })()
            """)
            print(f"    发送按钮: {json.dumps(btn_result, ensure_ascii=False)[:200]}")

            if not btn_result.get("ok"):
                # Enter 发送
                page.keyboard.press("Enter")
                print(f"    使用 Enter 键发送")

            time.sleep(8)  # 等回复

            body_after = len(page.locator("body").first.text_content() or "")
            delta = body_after - body_before
            print(f"    body变化: {body_before} → {body_after} (Δ{delta})")

            ss(page, f"06_chat_round_{i+1}")

    # ── 5. 检查是否有 iframe 内的聊天 ──
    print("\n" + "=" * 60)
    print("📋 4. iFrame 探索")
    iframes = page.locator("iframe").all()
    print(f"  iFrame 数量: {len(iframes)}")
    for idx, f in enumerate(iframes):
        try:
            src = f.get_attribute("src") or ""
            fid = f.get_attribute("id") or ""
            print(f"  iframe[{idx}]: id={fid} src={src[:150]}")
            # 尝试进入 iframe
            if src:
                frame = page.frame(name=fid) or page.frame(url=src)
                if frame:
                    content = frame.locator("body").first.text_content() or ""
                    print(f"    内容预览: {content[:200]}")
        except Exception as e:
            print(f"    error: {e}")

    # ── 6. 最终 DOM 快照 ──
    print("\n" + "=" * 60)
    print("📋 5. 最终状态")
    body = page.locator("body").first.text_content() or ""
    print(f"  页面文本长度: {len(body)}")
    print(f"  页面文本预览:\n{body[:800]}")

    # ── 7. 网络/WS 总结 ──
    print("\n" + "=" * 60)
    print("📋 6. 网络请求总结")
    api_requests = [r for r in network_log if r.get("type") != "response"]
    api_responses = [r for r in network_log if r.get("type") == "response"]
    chat_related = [r for r in network_log
                    if any(kw in str(r.get("url","")).lower()
                           for kw in ["chat", "agent", "stream", "message"])]

    print(f"  API 请求: {len(api_requests)}")
    for r in api_requests[:10]:
        print(f"    {r['method']} {r['url'][:120]}")
    print(f"  API 响应: {len(api_responses)}")
    print(f"  聊天相关: {len(chat_related)}")
    for r in chat_related[:5]:
        body = r.get("body_preview", "")[:200]
        print(f"    {r.get('status')} {r['url'][:120]}")
        print(f"    body: {body}")

    print(f"  WebSocket 连接: {len(ws_log)}")
    for w in ws_log[:10]:
        print(f"    {w['event']}: {str(w.get('url', w.get('data', '')))[:200]}")

    # ── 保存完整诊断报告 ──
    report = {
        "page_url": dom["url"],
        "buttons": dom["allButtons"],
        "inputs": dom["allInputs"],
        "iframes": dom["iframes"],
        "agent_panel_hints": dom["agentPanel"],
        "ws_hints": dom["wsHints"],
        "textarea_state": dom2["textareas"],
        "network_log": network_log,
        "ws_log": ws_log,
    }
    report_path = SCREENSHOT / "diagnosis_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                          encoding="utf-8")

    browser.close()
    print(f"\n✅ 诊断报告: {report_path}")
    print(f"  截图: {SCREENSHOT}/")
