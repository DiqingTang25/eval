"""
最简测试 — 验证 Playwright 能否弹出浏览器
运行: .venv_wsl/bin/python tests/manual_test_browser.py
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

print("1. 导入 Playwright...")
from playwright.sync_api import sync_playwright
print("   ✅ 导入成功")

print("2. 启动浏览器 (headless=False)...")
with sync_playwright() as p:
    proxy = None
    if os.getenv("PLAYWRIGHT_PROXY"):
        proxy = {"server": os.getenv("PLAYWRIGHT_PROXY")}
    browser = p.chromium.launch(headless=False, proxy=proxy)
    print("   ✅ 浏览器已启动，你应该能看到 Chromium 窗口")

    page = browser.new_page()
    print("3. 打开百度...")
    page.goto("https://www.baidu.com", wait_until="networkidle")
    print(f"   ✅ 页面标题: {page.title()}")

    print("4. 5秒后自动关闭...")
    time.sleep(5)
    browser.close()
    print("✅ 测试完成！浏览器弹出了吗？")
