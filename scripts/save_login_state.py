"""重新保存 HIAGENT 登录态 — 直达聊天页"""
from playwright.sync_api import sync_playwright

p = sync_playwright().start()
b = p.chromium.launch(headless=False)
page = b.new_page()

# 直接到聊天页
page.goto('https://aiagent.xjtlu.edu.cn/product/llm/mall/application/d90b0fd4shh7q1vt7r4g/chat')
print('>>> 请在浏览器中完成 SSO 登录 <<<')
print('>>> 看到聊天输入框后，回终端按 Enter <<<')
input()

page.context.storage_state(path='data/hiagent_auth.json')
print('✅ 登录态已保存到 data/hiagent_auth.json')

b.close()
p.stop()
