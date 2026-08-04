"""
Platform Agent 适配器 — 桥接 platform_client.py → BaseAgent 接口

被测平台: http://124.174.108.70 (AI+硬件实训平台)
实际后端: PlatformClient → POST /api/agent/chat (火山知识库驱动)

用法:
    from src.agents.platform_agent import PlatformAgent
    agent = PlatformAgent(config={"username": "student001", "password": "123456"})
    agent.start()           # → login + JWT
    resp = agent.send_message("什么是GPIO?")   # → ChatResult
    agent.close()
"""

import os
import time
from typing import Optional
from .base import BaseAgent, AgentResponse, AgentStatus


class PlatformAgent(BaseAgent):
    """自主学习平台 Agent — 桥接 PlatformClient"""

    def __init__(self, name: str = "platform", config: dict = None):
        super().__init__(name, config)
        config = config or {}
        self._client = None
        self._lesson_id = config.get("lesson_id", 4)
        self._username = config.get("username") or os.getenv("PLATFORM_USERNAME", "student001")
        self._password = config.get("password") or os.getenv("PLATFORM_PASSWORD", "123456")
        self._timeout = config.get("timeout", 120)

    def start(self) -> bool:
        from src.platform_client import PlatformClient
        base_url = os.getenv("PLATFORM_URL", "http://124.174.108.70")
        self._client = PlatformClient(
            base_url=base_url,
            username=self._username,
            password=self._password,
            min_interval=4.0,
            timeout=45,
            max_retries=4,
            verbose=True,
        )
        try:
            self._client.login()
            return True
        except Exception as e:
            print(f"[PlatformAgent] Login failed: {e}")
            return False

    def send_message(self, text: str, timeout: int = None) -> AgentResponse:
        start = time.time()
        if not self._client:
            return AgentResponse(status=AgentStatus.ERROR, text="", metadata={"error": "未登录"})

        result = self._client.chat(self._lesson_id, text)
        if result.is_usable:
            response = AgentResponse(
                status=AgentStatus.SUCCESS,
                text=result.answer,
                duration_seconds=round(time.time() - start, 1),
                turn=len(self._conversation_history) + 1,
                metadata={"method": "rest_api", "sources": result.sources},
            )
            self._conversation_history.append(response)
            return response

        return AgentResponse(
            status=AgentStatus.ERROR, text="",
            duration_seconds=round(time.time() - start, 1),
            metadata={"error": result.error or "QPS 限流", "rate_limited": result.rate_limited},
        )

    def get_history(self) -> list:
        return self._conversation_history

    def close(self):
        if self._client:
            self._client.session.close()
        self._client = None
