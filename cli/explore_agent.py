#!/usr/bin/env python3
"""
Agent 页面探查工具

自动检测目标 Agent 页面的输入框、消息元素和交互模式，
生成对应的 CSS selector 配置。

用法:
    python cli/explore_agent.py --url http://124.174.108.70
    python cli/explore_agent.py --url http://124.174.108.70 --login
"""

import argparse
import time
import json
import os
from playwright.sync_api import sync_playwright


def do_login(page):
    """自动登录（前端demo，输入任意内容即可）"""
    print("🔑 执行自动登录...")
    try:
        # 填写姓名
        name_input = page.locator("input[placeholder*='姓名'], input[placeholder*='账号']").first
        if name_input.is_visible(timeout=3000):
            name_input.click()
            name_input.fill("测评系统")
            print("  ✅ 已填写姓名")

        # 填写学号
        id_input = page.locator("input[placeholder*='学号'], input[placeholder*='工号']").first
        if id_input.is_visible(timeout=3000):
            id_input.click()
            id_input.fill("20240001")
            print("  ✅ 已填写学号")

        # 点击登录按钮
        submit_btn = page.locator(".lc-submit, button:has-text('进入'), button:has-text('登录'), [class*='submit']").first
        if submit_btn.is_visible(timeout=3000):
            submit_btn.click()
            print("  ✅ 已点击登录")
        else:
            # 尝试按Enter
            page.keyboard.press("Enter")
            print("  ✅ 已按Enter提交")

        time.sleep(3)
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        print(f"  📍 登录后URL: {page.url}")
        return True
    except Exception as e:
        print(f"  ⚠️ 登录失败: {e}")
        return False


def explore(url: str, auth_file: str = None, headless: bool = False, do_login_flag: bool = False):
    print(f"🔍 探查 Agent 页面: {url}")
    print(f"{'='*60}")

    # 代理配置
    proxy = None
    if os.getenv("PLAYWRIGHT_PROXY"):
        proxy = {"server": os.getenv("PLAYWRIGHT_PROXY")}
        print(f"  🌐 使用代理: {os.getenv('PLAYWRIGHT_PROXY')}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, proxy=proxy)

        if auth_file:
            context = browser.new_context(storage_state=auth_file)
            print(f"  使用登录态: {auth_file}")
        else:
            context = browser.new_context()

        page = context.new_page()
        page.goto(url, wait_until="networkidle")
        time.sleep(3)

        # ── 自动登录 ──
        if do_login_flag:
            do_login(page)

        # ── 1. 基础信息 ──
        print(f"\n📋 基础信息")
        print(f"  标题: {page.title()}")
        print(f"  URL: {page.url}")
        print()

        # ── 2. 输入框检测 ──
        print("📝 输入框检测")

        input_selectors = [
            "textarea",
            "input[type='text']",
            "input[type='search']",
            "[role='textbox']",
            "[contenteditable='true']",
            "input:not([type='hidden']):not([type='submit']):not([type='button'])",
        ]

        found_inputs = []
        for sel in input_selectors:
            try:
                elements = page.locator(sel).all()
                for el in elements:
                    if el.is_visible():
                        info = {
                            "tag": el.evaluate("el => el.tagName.toLowerCase()"),
                            "class": el.get_attribute("class") or "",
                            "placeholder": el.get_attribute("placeholder") or "",
                            "role": el.get_attribute("role") or "",
                            "aria_label": el.get_attribute("aria-label") or "",
                            "css_selector_suggest": "",
                        }

                        if info["class"]:
                            info["css_selector_suggest"] = f"{info['tag']}.{info['class'].split()[0]}"
                        elif info["placeholder"]:
                            info["css_selector_suggest"] = f'{info["tag"]}[placeholder*="{info["placeholder"][:20]}"]'
                        else:
                            info["css_selector_suggest"] = sel

                        found_inputs.append(info)
            except Exception:
                pass

        if found_inputs:
            print(f"  找到 {len(found_inputs)} 个候选输入框:")
            for i, inp in enumerate(found_inputs):
                print(f"  [{i+1}] <{inp['tag']}> class='{inp['class'][:50]}'")
                print(f"      placeholder='{inp['placeholder'][:60]}'")
                print(f"      ➜ 推荐: {inp['css_selector_suggest']}")
        else:
            print("  ⚠️ 未找到输入框，可能需要手动分析页面")
        print()

        # ── 3. 消息区域检测 ──
        print("💬 消息/内容区域检测")

        message_selectors = [
            "[class*='message']",
            "[class*='chat']",
            "[class*='conversation']",
            "[class*='bubble']",
            "[class*='agent']",
            "[class*='ai-reply']",
            "[class*='assistant']",
            "[role='log']",
            "[role='list']",
            "[data-testid*='message']",
            "main",
            "article",
        ]

        found_messages = []
        for sel in message_selectors:
            try:
                elements = page.locator(sel).all()
                for el in elements:
                    if el.is_visible():
                        text = (el.text_content() or "")[:100]
                        if len(text) > 10:
                            found_messages.append({
                                "selector": sel,
                                "class": el.get_attribute("class") or "",
                                "text_preview": text,
                            })
                    if len(found_messages) >= 5:
                        break
            except Exception:
                pass
            if len(found_messages) >= 5:
                break

        if found_messages:
            print(f"  找到 {len(found_messages)} 个候选消息元素:")
            for i, msg in enumerate(found_messages):
                print(f"  [{i+1}] selector='{msg['selector']}' class='{msg['class'][:40]}'")
                print(f"      内容: {msg['text_preview']}")
        else:
            print("  ⚠️ 未找到消息元素")
        print()

        # ── 4. 按钮/可点击元素 ──
        print("🔘 可交互元素检测")
        btn_selectors = [
            "button",
            "[role='button']",
            "[class*='btn']",
            "[class*='mode-btn']",
            "[onclick]",
        ]
        buttons_found = []
        for sel in btn_selectors:
            try:
                elements = page.locator(sel).all()
                for el in elements:
                    if el.is_visible():
                        text = (el.text_content() or "").strip()[:60]
                        cls = el.get_attribute("class") or ""
                        if text and len(text) > 1:
                            buttons_found.append({"text": text, "class": cls[:50], "selector": sel})
                if len(buttons_found) >= 10:
                    break
            except Exception:
                pass

        if buttons_found:
            for i, btn in enumerate(buttons_found[:10]):
                print(f"  [{i+1}] '{btn['text']}' (class='{btn['class']}')")
        print()

        # ── 5. 交互测试 ──
        print("🧪 交互测试")
        if found_inputs:
            # 优先选textarea类型的输入框（聊天框通常是textarea）
            chat_inputs = [i for i in found_inputs if "textarea" in i.get("tag", "")]
            test_inputs = chat_inputs + found_inputs
            test_selector = test_inputs[0]["css_selector_suggest"]
            print(f"  尝试输入测试消息 (使用 {test_selector})...")
            try:
                input_el = page.locator(test_selector).first
                if input_el.is_visible():
                    input_el.click()
                    input_el.fill("你好，请介绍一下自己")
                    page.keyboard.press("Enter")
                    print("  ✅ 消息已发送，等待回复...")
                    time.sleep(8)

                    # 再次检查是否有新内容
                    for sel in ["[class*='message']", "[class*='chat']", "[class*='agent']", "main"]:
                        try:
                            msgs = page.locator(sel).all()
                            if msgs:
                                last = (msgs[-1].text_content() or "")[:150]
                                if len(last) > 20:
                                    print(f"  📩 可能回复 (selector={sel}): {last}...")
                                    break
                        except Exception:
                            pass
            except Exception as e:
                print(f"  ⚠️ 交互测试失败: {e}")
        print()

        # ── 6. 页面 HTML 保存 ──
        output_file = f"page_explore_{int(time.time())}"
        html = page.content()
        with open(f"{output_file}.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"📄 页面 HTML 已保存: {output_file}.html")

        # ── 7. 截图 ──
        screenshot_file = f"page_screenshot_{int(time.time())}.png"
        page.screenshot(path=screenshot_file, full_page=True)
        print(f"📸 页面截图已保存: {screenshot_file}")

        # ── 8. 生成配置建议 ──
        print(f"\n{'='*60}")
        print("📋 Agent 配置建议:")
        config = {
            "url": url,
            "login_required": do_login_flag,
            "login_selectors": {
                "name": "input[placeholder*='姓名'], input[placeholder*='账号']",
                "id": "input[placeholder*='学号'], input[placeholder*='工号']",
                "submit": ".lc-submit, button:has-text('进入')",
            },
            "chat_input_selector": found_inputs[0]["css_selector_suggest"] if found_inputs else "textarea",
            "message_selector": found_messages[0]["selector"] if found_messages else "[class*='message']",
        }
        print(json.dumps(config, indent=2, ensure_ascii=False))

        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="探查 Agent 页面结构")
    parser.add_argument("--url", required=True, help="Agent 页面 URL")
    parser.add_argument("--auth", default=None, help="登录态文件路径")
    parser.add_argument("--headless", action="store_true", help="无头模式")
    parser.add_argument("--login", action="store_true", help="自动登录（前端demo）")
    args = parser.parse_args()

    explore(args.url, args.auth, args.headless, args.login)
