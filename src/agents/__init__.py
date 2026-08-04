"""
Agent 抽象层 — 支持任意 Agent 接入 (API / Browser)

被测 Agent 通过统一的 BaseAgent 接口接入测评系统。
新增 Agent 只需实现 start/send_message/get_history/close 4个方法。

当前 Agent (v3.4, 被测目标: 自主学习平台 http://124.174.108.70):
  - PlatformAgent: HiAgent API 直连 [默认]
  - WebTestAgent:  Playwright 浏览器网站测试
  - MockAgent:     管线验证
"""

from .base import BaseAgent, AgentResponse, AgentStatus
from .agent_registry import AgentRegistry, AGENT_CONFIGS, DEFAULT_AGENT

__all__ = [
    "BaseAgent",
    "AgentResponse",
    "AgentStatus",
    "AgentRegistry",
    "AGENT_CONFIGS",
    "DEFAULT_AGENT",
]
