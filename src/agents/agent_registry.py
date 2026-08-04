"""
Agent 注册表 — v3.4

被测 Agent: 4个 HiAgent Phase + 自主学习平台 + WebTest + Mock
"""
import os
from typing import Optional
from .base import BaseAgent
from .platform_agent import PlatformAgent
from .web_test_agent import WebTestAgent
from .mock_agent import MockAgent

AGENT_CONFIGS = {
    "hi_phase1": {
        "name": "Phase 1 — 国产AI技术基础",
        "type": "api",
        "class": None,  # Lazy import: HiApiAgent
        "config": {
            "phase": "phase1",
            "app_id": os.getenv("HIAGENT_PHASE1_APPID", ""),
            "api_key": os.getenv("HIAGENT_PHASE1_APIKEY", ""),
        },
    },
    "hi_phase2": {
        "name": "Phase 2 — 新型硬件设计",
        "type": "api",
        "class": None,
        "config": {
            "phase": "phase2",
            "app_id": os.getenv("HIAGENT_PHASE2_APPID", ""),
            "api_key": os.getenv("HIAGENT_PHASE2_APIKEY", ""),
        },
    },
    "hi_phase3_4": {
        "name": "Phase 3&4 — 环境感知与触觉反馈",
        "type": "api",
        "class": None,
        "config": {
            "phase": "phase3_4",
            "app_id": os.getenv("HIAGENT_PHASE3_4_APPID", ""),
            "api_key": os.getenv("HIAGENT_PHASE3_4_APIKEY", ""),
        },
    },
    "hi_phase5": {
        "name": "Phase 5 — 具身智能控制",
        "type": "api",
        "class": None,
        "config": {
            "phase": "phase5",
            "app_id": os.getenv("HIAGENT_PHASE5_APPID", "d90b0fd4shh7q1vt7r4g"),
            "api_key": os.getenv("HIAGENT_PHASE5_APIKEY", "d97htrd4shhd3s3p351g"),
        },
    },
    "web_test": {
        "name": "网站测试 (Playwright)",
        "type": "browser",
        "class": WebTestAgent,
        "config": {
            "headless": True,
            "debug": False,
        },
    },
    "platform": {
        "name": "实训教学平台 (http://124.174.108.70)",
        "type": "api",
        "class": PlatformAgent,
        "config": {
            "username": os.getenv("PLATFORM_USERNAME", "student001"),
            "password": os.getenv("PLATFORM_PASSWORD", "123456"),
        },
    },
    "mock": {
        "name": "Mock Agent (管线验证)",
        "type": "mock",
        "class": MockAgent,
        "config": {},
    },
}

DEFAULT_AGENT = "hi_phase5"


class AgentRegistry:
    @staticmethod
    def list_agents() -> dict:
        return {k: {"name": v["name"], "type": v["type"]} for k, v in AGENT_CONFIGS.items()}

    @staticmethod
    def get_agent(agent_id: str = None, **overrides) -> Optional[BaseAgent]:
        agent_id = agent_id or DEFAULT_AGENT
        cfg = AGENT_CONFIGS.get(agent_id)
        if not cfg:
            return None
        agent_config = dict(cfg["config"])
        agent_config.update(overrides)

        # Lazy-load HiApiAgent for phase agents
        agent_cls = cfg["class"]
        if agent_cls is None:
            from .hi_api_agent import HiApiAgent
            agent_cls = HiApiAgent

        return agent_cls(name=agent_id, config=agent_config)
