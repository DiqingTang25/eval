"""
HIAGENT 适配器 v3.3 — 西交利物浦教学AI助手

被测页面: https://aiagent.xjtlu.edu.cn/product/llm/mall/application/d90b0fd4shh7q1vt7r4g/chat
模式: Playwright 浏览器自动化 + XJTLU SSO 登录态复用
"""

import os
import time
from playwright.sync_api import sync_playwright
from .base import BaseAgent, AgentResponse, AgentStatus


class HiAgent(BaseAgent):
    """HIAGENT 教学助手 — 浏览器自动化模式"""

    def __init__(self, name: str = "hiagent", config: dict = None):
        super().__init__(name, config)
        self.page_url = (
            config.get("page_url")
            or os.getenv("HIAGENT_URL")
            or "https://aiagent.xjtlu.edu.cn/product/llm/mall/application/d90b0fd4shh7q1vt7r4g/chat"
        )
        self.app_id = config.get("app_id") or os.getenv("HIAGENT_APP_ID", "")
        self.api_key = config.get("api_key") or os.getenv("HIAGENT_API_KEY", "")
        self.headless = config.get("headless", True)
        self.debug = config.get("debug", True)

        self._playwright = None
        self._browser = None
        self._page = None

    def _log(self, msg: str):
        if self.debug:
            print(f"[HiAgent] {msg}")

    def start(self) -> bool:
        """启动浏览器 → 加载登录态 → 进入聊天页"""
        self._log("启动浏览器...")
        try:
            proxy = None
            if os.getenv("PLAYWRIGHT_PROXY"):
                proxy = {"server": os.getenv("PLAYWRIGHT_PROXY")}

            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.headless, proxy=proxy
            )

            auth_path = "data/hiagent_auth.json"
            if os.path.exists(auth_path):
                self._log("加载已保存登录态...")
                ctx = self._browser.new_context(storage_state=auth_path)
            else:
                ctx = self._browser.new_context()

            self._page = ctx.new_page()
            self._page.goto(self.page_url, wait_until="networkidle", timeout=30000)
            time.sleep(8)  # 等React渲染
            self._log(f"页面: {self._page.title()}")

            # 确认聊天输入框存在
            editable = self._page.locator("[contenteditable='true']")
            if editable.count() == 0:
                self._log("❌ 未找到聊天输入框 (contentEditable)")
                return False

            self._log("✅ Agent 就绪")
            return True

        except Exception as e:
            self._log(f"启动失败: {e}")
            return False

    def send_message(self, text: str, timeout: int = 180) -> AgentResponse:
        """发送消息并等待AI回复"""
        start = time.time()
        self._log(f"发送: {text[:60]}...")

        if not self._page:
            return AgentResponse(status=AgentStatus.ERROR, text="",
                                 metadata={"error": "浏览器未启动"})

        try:
            # 找输入框 (contentEditable div)
            editable = self._page.locator("[contenteditable='true']").first
            editable.click()
            time.sleep(0.5)
            editable.fill(text)
            time.sleep(0.5)

            # 记录发送前的消息数
            before_msgs = self._page.locator("[class*='message'], [class*='msg'], [class*='bubble']").count()

            # 发送 (Enter)
            self._page.keyboard.press("Enter")
            self._log("已发送, 等待回复...")

            # 等待新消息出现
            waited = 0
            while waited < timeout:
                time.sleep(2)
                waited += 2

                # 检查是否有新消息
                current_msgs = self._page.locator("[class*='message'], [class*='msg'], [class*='bubble']").all()
                if len(current_msgs) > before_msgs:
                    # 取最后一条消息
                    last = current_msgs[-1]
                    txt = (last.text_content() or "").strip()
                    # 排除 loading/empty 信号
                    if txt and "flow output is empty" not in txt.lower() and len(txt) > 5:
                        response = AgentResponse(
                            status=AgentStatus.SUCCESS,
                            text=txt,
                            duration_seconds=round(time.time() - start, 1),
                            turn=len(self._conversation_history) + 1,
                            metadata={"method": "playwright"},
                        )
                        self._conversation_history.append(response)
                        return response

                # 也用body文本对比检测
                body = (self._page.locator("body").first.text_content() or "")
                if "flow output is empty" in body.lower():
                    self._log("⚠️ Chatflow 返回空 (后端未配置)")

            return AgentResponse(
                status=AgentStatus.TIMEOUT, text="",
                duration_seconds=waited,
                metadata={"error": f"等待{timeout}s未收到回复"},
            )

        except Exception as e:
            return AgentResponse(
                status=AgentStatus.ERROR, text="",
                duration_seconds=time.time() - start,
                metadata={"error": str(e)},
            )

    def get_history(self) -> list[AgentResponse]:
        return self._conversation_history

    def close(self):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._page = None
