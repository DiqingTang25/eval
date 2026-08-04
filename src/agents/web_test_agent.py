"""
网站测试 Agent — Playwright 浏览器自动化

通过 Playwright 打开 http://124.174.108.70, 登录 → 进入课时 → 打开AI对话面板 → 发送消息。
不调用 API, 完全模拟真实用户在网站上的操作。

用法:
    agent = WebTestAgent(config={"headless": True})
    agent.start()           # 启动浏览器 → 登录
    resp = agent.send_message("什么是GPIO?")
"""

import os
import time
from .base import BaseAgent, AgentResponse, AgentStatus

PLATFORM_URL = os.getenv("PLATFORM_URL", "http://124.174.108.70")


class WebTestAgent(BaseAgent):
    """网站测试 Agent — Playwright 浏览器自动化"""

    def __init__(self, name: str = "web_test", config: dict = None):
        super().__init__(name, config)
        config = config or {}
        self.base_url = config.get("base_url") or PLATFORM_URL
        self.username = config.get("username") or os.getenv("PLATFORM_USERNAME", "student001")
        self.password = config.get("password") or os.getenv("PLATFORM_PASSWORD", "123456")
        self.headless = config.get("headless", True)
        self.timeout = config.get("timeout", 180)
        self._playwright = None
        self._browser = None
        self._page = None

    def _log(self, msg: str):
        print(f"[WebTest] {msg}")

    def start(self) -> bool:
        from playwright.sync_api import sync_playwright
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self._page = self._browser.new_page()
            self._page.set_default_timeout(30000)

            # 1. 打开平台首页
            self._log(f"打开: {self.base_url}")
            self._page.goto(self.base_url, wait_until="networkidle")
            time.sleep(2)

            # 2. 登录
            self._log("登录中...")
            self._page.fill('input[type="text"], input[placeholder*="用户"], input[name="username"]', self.username)
            self._page.fill('input[type="password"], input[placeholder*="密码"]', self.password)
            self._page.click('button:has-text("登录"), button:has-text("Login"), button[type="submit"]')
            time.sleep(3)
            self._log(f"登录完成: {self._page.title()}")

            # 3. 进入课时4 (电子硬件入门)
            self._page.goto(f"{self.base_url}/lesson/4", wait_until="networkidle")
            time.sleep(3)

            # 4. 找AI对话入口
            chat_btn = self._page.locator('button:has-text("AI"), [class*="chat"], [class*="agent"]').first
            if chat_btn.count() > 0:
                chat_btn.click()
                time.sleep(2)
                self._log("AI对话面板已打开")
            else:
                self._log("未找到AI对话按钮, 尝试直接输入")

            # 5. 找输入框
            self._chat_input = (
                self._page.locator('[contenteditable="true"]').first
                or self._page.locator('textarea').first
                or self._page.locator('input[type="text"]').last
            )
            self._log("Agent 就绪")
            return True
        except Exception as e:
            self._log(f"启动失败: {e}")
            return False

    def send_message(self, text: str, timeout: int = None) -> AgentResponse:
        start = time.time()
        timeout = timeout or self.timeout
        if not self._page:
            return AgentResponse(status=AgentStatus.ERROR, text="", metadata={"error": "浏览器未启动"})

        try:
            # 输入消息
            self._chat_input.click()
            time.sleep(0.5)
            self._chat_input.fill(text)
            time.sleep(0.5)

            # 发送
            before = self._page.locator('[class*="message"], [class*="msg"], [class*="bubble"]').count()
            self._page.keyboard.press("Enter")
            self._log(f"已发送: {text[:50]}...")

            # 等回复
            waited = 0
            while waited < timeout:
                time.sleep(2)
                waited += 2
                current = self._page.locator('[class*="message"], [class*="msg"], [class*="bubble"]').count()
                if current > before:
                    msgs = self._page.locator('[class*="message"], [class*="msg"], [class*="bubble"]').all()
                    txt = (msgs[-1].text_content() or "").strip()
                    if txt and len(txt) > 5:
                        return AgentResponse(
                            status=AgentStatus.SUCCESS, text=txt,
                            duration_seconds=round(time.time() - start, 1),
                            turn=len(self._conversation_history) + 1,
                            metadata={"method": "playwright"},
                        )

            return AgentResponse(status=AgentStatus.TIMEOUT, text="",
                                 metadata={"error": f"等待{timeout}s未回复"})
        except Exception as e:
            return AgentResponse(status=AgentStatus.ERROR, text="", metadata={"error": str(e)})

    def get_history(self) -> list:
        return self._conversation_history

    def close(self):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
