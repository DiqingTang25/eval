"""测试HIAGENT聊天 - 发送消息"""
from playwright.sync_api import sync_playwright
import time

p = sync_playwright().start()
b = p.chromium.launch(headless=True)
ctx = b.new_context(storage_state="data/hiagent_auth.json")
page = ctx.new_page()

page.goto("https://aiagent.xjtlu.edu.cn/product/llm/mall/application/d90b0fd4shh7q1vt7r4g/chat")
time.sleep(8)

# 找到 contentEditable 输入框
editable = page.locator("[contenteditable='true']")
print(f"ContentEditable count: {editable.count()}")

if editable.count() > 0:
    el = editable.first
    print(f"Visible: {el.is_visible()}")

    # 点击输入框
    el.click()
    time.sleep(1)

    # 输入消息
    el.fill("你好，请介绍一下课程内容")
    time.sleep(1)

    # 找发送按钮 - 可能是图标按钮或"Send"按钮
    send_btns = page.locator("button").all()
    for btn in send_btns:
        try:
            txt = (btn.text_content() or "").strip()
            aria = btn.get_attribute("aria-label") or ""
            title = btn.get_attribute("title") or ""
            if "send" in txt.lower() or "send" in aria.lower() or "发送" in txt:
                print(f"Send button found: txt='{txt[:30]}' aria='{aria[:30]}'")
                btn.click()
                print("Clicked send!")
                break
        except:
            pass
    else:
        # 没找到发送按钮，按Enter
        print("No send button, pressing Enter")
        page.keyboard.press("Enter")

    # 等待回复
    time.sleep(10)

    # 获取最新消息
    messages = page.locator("[class*='message'], [class*='msg'], [class*='bubble'], [class*='response']").all()
    print(f"Message elements: {len(messages)}")
    for i, m in enumerate(messages[-5:]):
        try:
            txt = (m.text_content() or "").strip()
            if txt and len(txt) > 10:
                print(f"  Message {i}: {txt[:200]}...")
        except:
            pass

page.screenshot(path="data/chat_after_send.png", full_page=True)
print("Done. Screenshot: data/chat_after_send.png")

b.close()
p.stop()
