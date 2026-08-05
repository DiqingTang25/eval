"""
SchemaAdapter — 探索器与现有测评系统的薄适配层

读取 platform_schema.yaml → 提供与现有 PlatformClient/BrowserEvaluator
兼容的数据接口。

设计原则:
  - 只读 schema, 不修改
  - 返回的字典结构与现有硬编码数据格式对齐
  - 如果 schema 缺失字段, 返回 None (调用方 fallback 到硬编码)

用法:
  from src.schema_adapter import SchemaAdapter
  adapter = SchemaAdapter("output/platform_probe/platform_schema.yaml")

  # PlatformClient 使用
  client = PlatformClient(
      base_url=adapter.base_url,
      api_prefix=adapter.get_api_prefix("interactive"),
      content_api_prefix=adapter.get_api_prefix("content"),
  )

  # BrowserEvaluator 使用
  phases = adapter.get_phases()  # → {1: {"name": "...", "days": 4}, ...}
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml


class SchemaAdapter:
    """读取 platform_schema.yaml, 提供便捷访问方法"""

    def __init__(self, schema_path: str):
        self.schema_path = Path(schema_path)
        if not self.schema_path.exists():
            raise FileNotFoundError(f"Schema 文件不存在: {schema_path}")

        with open(self.schema_path, "r", encoding="utf-8") as f:
            self._data = yaml.safe_load(f)

        self._validate()

    def _validate(self):
        """基本格式验证"""
        required = ["target_url", "auth", "structure", "apis"]
        for key in required:
            if key not in self._data:
                raise ValueError(f"Schema 缺少必要字段: {key}")

    # ── 基本信息 ──

    @property
    def base_url(self) -> str:
        """平台 URL"""
        return self._data.get("target_url", "")

    @property
    def schema_version(self) -> str:
        return self._data.get("schema_version", "1.0")

    @property
    def confidence(self) -> dict:
        return self._data.get("confidence_scores", {})

    # ── 认证 ──

    def get_auth(self) -> dict:
        """获取认证配置"""
        auth = self._data.get("auth", {})
        return {
            "type": auth.get("type", "form"),
            "login_url": auth.get("login_url", ""),
            "login_method": auth.get("login_method", "POST"),
            "fields": auth.get("fields", []),
            "token_location": auth.get("token_location", "header"),
            "token_key": auth.get("token_key", "Authorization"),
            "token_prefix": auth.get("token_prefix", "Bearer "),
        }

    def get_login_endpoint(self) -> Optional[dict]:
        """获取登录 API 端点"""
        auth_apis = self._data.get("apis", {}).get("auth", [])
        for api in auth_apis:
            if "login" in api.get("path", "").lower():
                return api
        # 回退: 从 auth 信息构造
        auth = self._data.get("auth", {})
        if auth.get("login_url"):
            return {
                "path": auth["login_url"],
                "method": auth.get("login_method", "POST"),
                "confidence": 0.9,
            }
        return None

    # ── API 端点 ──

    def get_api_prefix(self, category: str = "interactive") -> str:
        """
        获取 API 前缀
        :param category: "interactive" (Agent/Quiz/Profile) 或 "content" (Phase/Lesson)
        :returns: 第一个匹配的前缀, 如 "/phase3-api"
        """
        prefixes = self._data.get("platform", {}).get("api_prefixes", [])
        if not prefixes:
            return ""

        if category == "content":
            # 内容类API通常使用更短的prefix
            for p in prefixes:
                if "/api" in p and "phase" not in p.lower():
                    return p
            return prefixes[0] if prefixes else ""
        else:
            # 交互类API
            for p in prefixes:
                if "phase" in p.lower() or "v1" in p or "v2" in p:
                    return p
            return prefixes[0] if prefixes else ""

    def get_endpoints_by_category(self, category: str) -> list[dict]:
        """获取特定类别的所有端点"""
        apis = self._data.get("apis", {})
        return apis.get(category, [])

    def get_agent_chat_endpoint(self) -> Optional[dict]:
        """获取 AI Agent 对话端点"""
        agent = self._data.get("agent", {})
        if agent.get("chat_endpoint"):
            return {
                "path": agent["chat_endpoint"],
                "method": agent.get("method", "POST"),
                "input_schema": agent.get("input_schema", {}),
                "output_schema": agent.get("output_schema", {}),
                "context_fields": agent.get("context_fields", []),
            }

        # 回退: 从 apis.agent 中查找
        agent_apis = self.get_endpoints_by_category("agent")
        if agent_apis:
            best = max(agent_apis, key=lambda a: a.get("confidence", 0))
            return best

        return None

    def get_quiz_endpoints(self) -> list[dict]:
        """获取测验相关端点"""
        return self.get_endpoints_by_category("quiz")

    def get_progress_endpoints(self) -> list[dict]:
        """获取进度追踪端点"""
        return self.get_endpoints_by_category("progress")

    # ── 教学结构 (对接现有接口) ──

    def get_structure(self) -> dict[str, Any]:
        """
        获取完整教学结构, 兼容现有 BrowserEvaluator 的 PHASES 格式

        :returns: {
            "hierarchy": ["phase", "lesson", "step"],
            "phases": {1: {"name": "...", "lessons": [...]}, ...},
            "lessons": [...],
            "steps": [...],
        }
        """
        structure = self._data.get("structure", {})

        # 转换为现有 PHASES 字典格式 {id: {name, days/lessons}}
        phases = {}
        for p in structure.get("phases", []):
            pid = p.get("id", "")
            # 提取数字ID
            order = p.get("order", 0)
            phases[order] = {
                "name": p.get("name", ""),
                "lessons": [
                    l for l in structure.get("lessons", [])
                    if l.get("phase_id") == pid
                ],
            }

        return {
            "hierarchy": structure.get("hierarchy", []),
            "phases": phases,
            "lessons": structure.get("lessons", []),
            "steps": structure.get("steps", []),
        }

    def get_phases(self) -> dict[int, dict]:
        """
        获取 Phase 列表 (兼容现有 PHASES 字典格式)
        :returns: {1: {"name": "...", "days": 4}, 2: {...}}
        """
        result = {}
        for p in self._data.get("structure", {}).get("phases", []):
            order = p.get("order", len(result) + 1)
            result[order] = {
                "name": p.get("name", ""),
                "lesson_count": p.get("lesson_count", 0),
            }
        return result

    def get_lessons(self, phase_id: str = "") -> list[dict]:
        """获取课时列表"""
        lessons = self._data.get("structure", {}).get("lessons", [])
        if phase_id:
            lessons = [l for l in lessons if l.get("phase_id") == phase_id]
        return lessons

    def get_steps(self, lesson_id: str = "") -> list[dict]:
        """获取Step列表"""
        steps = self._data.get("structure", {}).get("steps", [])
        if lesson_id:
            steps = [s for s in steps if s.get("lesson_id") == lesson_id]
        return sorted(steps, key=lambda s: s.get("order_index", 0))

    def get_lesson_topics(self, lesson_id: str = "") -> list[str]:
        """获取课时的知识点/主题列表"""
        for l in self._data.get("structure", {}).get("lessons", []):
            if l.get("id") == lesson_id:
                return l.get("topics", [])
        return []

    # ── 导航 ──

    def get_navigation_patterns(self) -> list[dict]:
        """获取导航模式"""
        nav = self._data.get("navigation", {})
        return nav.get("patterns", [])

    # ── Agent 交互模式 ──

    def get_agent_triggers(self) -> list[dict]:
        """获取 Agent 触发方式"""
        agent = self._data.get("agent", {})
        return agent.get("triggers", [])

    # ── 整体状态 ──

    def is_ready(self) -> bool:
        """Schema 是否足够完整以驱动测评"""
        conf = self.confidence
        return conf.get("overall", 0) >= 0.5

    def needs_human_review(self) -> list[str]:
        """需要人工复核的字段"""
        return self.confidence.get("fields_needing_human_review", [])

    # ── 原始数据访问 ──

    @property
    def raw(self) -> dict:
        """直接访问原始 schema 数据"""
        return self._data

    def __repr__(self) -> str:
        return (f"SchemaAdapter({self.base_url}, "
                f"v{self.schema_version}, "
                f"confidence={self.confidence.get('overall', 0):.0%})")
