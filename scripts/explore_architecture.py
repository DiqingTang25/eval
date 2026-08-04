#!/usr/bin/env python3
"""
教学平台 Phase 3 架构级探索 — 搞清楚真实交互模式
目标: 理解 SPA 真实数据流 → 指导测评架构重构

核心问题:
  1. Day 卡片点击后内容在哪加载？（panel/drawer/modal/new page?）
  2. Agent 对话的真实触发方式是什么？
  3. Quiz 是如何被触发的？（step完成→next→done→quiz?）
  4. 网络请求模式 — 哪些 API 在什么时机被调用？
"""
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "http://124.174.108.70"
USERNAME, PASSWORD = "student001", "123456"
OUT = Path(__file__).parent.parent / "explore_output"
SC = OUT / "screenshots"
SC.mkdir(parents=True, exist_ok=True)

ss_n = [0]
def ss(page, name):
    ss_n[0] += 1
    try:
        page.screenshot(path=str(SC / f"{ss_n[0]:03d}_{name}.png"),
                       full_page=True, timeout=10000, animations="disabled")
    except: pass

# 网络请求收集
network_log = []
def on_request(request):
    try:
        url = request.url
        if any(p in url for p in ['/phase3-api/', '/api/', '/ws', 'socket']):
            network_log.append({
                "url": url[url.index('/api') if '/api' in url else 0:][:200],
                "method": request.method,
                "type": request.resource_type,
                "ts": time.time(),
            })
    except: pass

def login(page):
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    body = page.locator("body").first.text_content() or ""
    if "Phase" in body and "登录" not in body[:500]:
        return True
    for inp in page.locator("input:not([type='hidden'])").all():
        if not inp.is_visible(): continue
        t = inp.get_attribute("type") or "text"
        if t == "text": inp.fill(USERNAME)
        elif t == "password": inp.fill(PASSWORD)
    for btn in page.locator("button").all():
        if btn.is_visible() and "登录" in (btn.text_content() or ""):
            btn.click(); break
    time.sleep(4)
    page.wait_for_load_state("networkidle", timeout=15000)
    return True

def dump_dom(page):
    """导出页面关键 DOM 结构"""
    return page.evaluate("""() => {
        const info = {url: location.href, title: document.title};

        // 所有按钮
        info.buttons = [...document.querySelectorAll('button')]
            .filter(b => b.offsetParent !== null)
            .map(b => ({
                text: b.textContent.trim().substring(0, 80),
                class: b.className.substring(0, 60),
                disabled: b.disabled,
                visible: b.offsetParent !== null,
            }));

        // 输入框
        info.inputs = [...document.querySelectorAll('input, textarea, [contenteditable="true"]')]
            .filter(el => el.offsetParent !== null)
            .map(el => ({
                tag: el.tagName,
                type: el.type || '',
                placeholder: el.placeholder || '',
                class: el.className?.substring(0, 60) || '',
            }));

        // 主要容器 (可能是 panel/drawer/modal)
        info.containers = [...document.querySelectorAll(
            '[class*="panel"], [class*="drawer"], [class*="modal"], [class*="slide"], ' +
            '[class*="content"], [class*="chat"], [class*="agent"], [class*="lesson"], ' +
            '[class*="overlay"], [class*="side"], [role="dialog"], [class*="popup"]'
        )]
            .filter(el => el.offsetParent !== null)
            .map(el => ({
                class: el.className?.substring(0, 80) || '',
                text: el.textContent?.trim().substring(0, 100) || '',
                childCount: el.children.length,
            }));

        // localStorage
        info.storage = {};
        for (let i = 0; i < localStorage.length; i++) {
            const k = localStorage.key(i);
            info.storage[k] = localStorage.getItem(k)?.substring(0, 100);
        }

        return info;
    }""")

def main():
    print("🏗️ 教学平台架构级探索")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("request", on_request)

        login(page)
        print("✅ 登录\n")

        # ── 1. 首页 DOM 结构 ──
        print("1. 首页 DOM 分析")
        home_dom = dump_dom(page)
        ss(page, "home")
        print(f"   按钮: {len(home_dom['buttons'])}")
        for b in home_dom['buttons'][:10]:
            print(f"     [{b['class'][:40]}] {b['text'][:60]} {'⛔' if b['disabled'] else ''}")
        print(f"   容器: {len(home_dom['containers'])}")
        for c in home_dom['containers'][:10]:
            if c['text']:
                print(f"     [{c['class'][:50]}] {c['text'][:80]}")

        # ── 2. 点击 Day 卡片，看 DOM 变化 ──
        print("\n2. 点击 Day 卡片 — 追踪 DOM 变化")

        # 选 Phase 1
        for btn in page.locator("button").all():
            if btn.is_visible() and "Phase 01" in (btn.text_content() or ""):
                btn.click()
                time.sleep(2)
                break

        ss(page, "phase1_before_day")

        # 找到第一个可点击 Day (不是 disabled)
        day_buttons = page.locator("button").all()
        clicked_day = None
        for btn in day_buttons:
            if not btn.is_visible(): continue
            text = (btn.text_content() or "").strip()
            disabled = btn.is_disabled()
            if text.startswith("Day") and not disabled:
                print(f"   点击: {text[:80]}")
                btn.click()
                clicked_day = text
                time.sleep(3)
                page.wait_for_load_state("networkidle", timeout=10000)
                break

        if not clicked_day:
            print("   ⚠️ 未找到非disabled的Day按钮")
            # 尝试点击"进入"
            for btn in page.locator("button").all():
                t = (btn.text_content() or "").strip()
                if btn.is_visible() and "进入" in t:
                    print(f"   点击'进入': {t[:60]}")
                    btn.click()
                    time.sleep(3)
                    clicked_day = t
                    break

        if clicked_day:
            ss(page, "day_clicked")
            # Dump DOM after click
            dom_after = dump_dom(page)
            print(f"\n   点击后 DOM 变化:")
            print(f"   新按钮: {len(dom_after['buttons'])}")
            for b in dom_after['buttons']:
                if b['text'] not in [bb['text'] for bb in home_dom['buttons']]:
                    print(f"     🆕 [{b['class'][:40]}] {b['text'][:60]}")

            print(f"   新容器: {len(dom_after['containers'])}")
            for c in dom_after['containers']:
                if c['text'] and c['text'] not in [cc.get('text', '') for cc in home_dom['containers']]:
                    print(f"     🆕 [{c['class'][:50]}] {c['text'][:100]} children={c['childCount']}")

            # 特别检查有没有 panel/drawer 打开
            panels = [c for c in dom_after['containers'] if 'panel' in c['class'].lower() or 'drawer' in c['class'].lower()]
            print(f"   Panel/Drawer: {len(panels)}")

            # 检查有没有 iframe
            iframes = page.locator("iframe").all()
            print(f"   iframes: {len(iframes)}")

            # 页面总文本量
            body_text = page.locator("body").first.text_content() or ""
            print(f"   页面总文本: {len(body_text)} 字符 (之前Day卡片页 ~380)")

            # ── 3. 点击 Agent 按钮 ──
            print(f"\n3. 点击 Agent 按钮")
            agent_btns = page.locator("button:has-text('Agent')").all()
            print(f"   Agent按钮: {len(agent_btns)}")
            for ab in agent_btns:
                try:
                    if ab.is_visible():
                        t = ab.text_content() or ""
                        print(f"   点击: {t.strip()[:60]}")
                        ab.click()
                        time.sleep(3)

                        # 检查 DOM 变化
                        dom_agent = dump_dom(page)
                        # 找新出现的 textarea/input
                        new_inputs = dom_agent.get('inputs', [])
                        if new_inputs:
                            print(f"   输入框: {len(new_inputs)}")
                            for ni in new_inputs:
                                print(f"     [{ni['class'][:40]}] {ni['tag']} type={ni['type']} placeholder='{ni['placeholder']}'")

                        # 有没有 chat 容器打开
                        chats = [c for c in dom_agent.get('containers', []) if 'chat' in c['class'].lower() or 'agent' in c['class'].lower() or 'panel' in c['class'].lower()]
                        print(f"   Chat/Panel 容器: {len(chats)}")
                        for ch in chats:
                            print(f"     [{ch['class'][:60]}] children={ch['childCount']} text={ch['text'][:80]}")

                        ss(page, "agent_clicked")
                        break
                except Exception as e:
                    print(f"    ❌ {e}")

        # ── 4. 网络请求分析 ──
        print(f"\n4. 网络请求分析")
        from collections import Counter
        endpoints = Counter()
        for req in network_log:
            # Simplify URLs
            url = req['url']
            parts = url.split('/')
            if len(parts) >= 3:
                key = '/'.join(parts[:3])
                endpoints[key] += 1
        print(f"   总API请求: {len(network_log)}")
        for ep, count in endpoints.most_common(15):
            print(f"     {ep} ({count}x)")

        # 按时间线列出
        if network_log:
            start_ts = network_log[0]['ts']
            print(f"\n   请求时间线:")
            for req in network_log:
                t = req['ts'] - start_ts
                print(f"     +{t:.1f}s [{req['method']}] {req['url'][:80]}")

        # ── 5. Phase 5: 机器人Agent专项 ──
        print(f"\n5. Phase 5 机器人 Agent")
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)
        for btn in page.locator("button").all():
            if btn.is_visible() and "Phase 05" in (btn.text_content() or ""):
                btn.click()
                time.sleep(2)
                break

        ss(page, "phase5")
        dom_p5 = dump_dom(page)
        print(f"   按钮: {len(dom_p5['buttons'])}")
        for b in dom_p5['buttons']:
            print(f"     [{b['class'][:40]}] {b['text'][:60]} {'⛔' if b['disabled'] else ''}")

        # 找任何 Agent/Robot 相关按钮
        for btn_text in ["机器人", "Agent可用", "Agent", "项目"]:
            for btn in page.locator("button").all():
                t = (btn.text_content() or "").strip()
                if btn.is_visible() and btn_text in t and not btn.is_disabled():
                    print(f"\n   点击: {t[:80]}")
                    btn.click()
                    time.sleep(3)
                    page.wait_for_load_state("networkidle", timeout=10000)
                    ss(page, f"phase5_{btn_text}")
                    dom_after = dump_dom(page)
                    # 找新输入框
                    for ni in dom_after.get('inputs', []):
                        print(f"     🆕 input: [{ni['class'][:40]}] {ni['tag']} placeholder='{ni['placeholder']}'")
                    break

        browser.close()

        # ── 保存报告 ──
        report = {
            "home_dom": home_dom,
            "network_log": network_log,
        }
        (OUT / "architecture_exploration.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str))
        print(f"\n✅ 完成: {OUT / 'architecture_exploration.json'}")

if __name__ == "__main__":
    main()
