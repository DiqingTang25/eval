"""
MCP Server — Agent C (SOTA Paradigm 3: MCP-driven Test Toolchain)

从 platform_schema.yaml 动态生成 MCP Tool definitions。
让 AI Agent 可以自主发现和调用平台 API。

核心能力:
  - tools/list: 返回所有可用 Tool (从 schema 动态生成)
  - tools/call: 执行指定 Tool (通过 PlatformClient)
  - 零硬编码: Tool 名称/描述/参数全部来自 schema
  - Schema 缺失 → 空工具列表, 不生成假数据

设计约束:
  - 不修改 platform_probe/ 代码
  - 不修改 PlatformClient 代码
  - Schema 中 API 端点格式: {path, method, confidence, [input_schema], [response_sample]}

用法:
  from src.mcp_server import MCPServer
  server = MCPServer()
  tools = server.list_tools()       # → list[dict]  (MCP Tool[])
  result = server.call_tool(        # → dict
      "agent_chat",
      {"message": "hello", "lesson_id": "22"}
  )

对接 Multi-Agent Verifier (未来):
  VerifierAgent
    → tools/list → 发现 quiz_start, quiz_submit, agent_chat
    → tools/call quiz_start {lesson_id: "22"}
    → 拿到正确答案
    → 比对用户提交 → 生成验证报告
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Schema 查找路径 ──
SCHEMA_CANDIDATES = [
    "output/platform_probe/platform_schema.yaml",
    "output/platform_schema.yaml",
]

# ── MCP 协议版本 ──
MCP_PROTOCOL_VERSION = "2024-11-05"


# ═══════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════

@dataclass
class MCPTool:
    """单个 MCP Tool 定义 (对齐 MCP 协议规范)"""
    name: str                          # 唯一工具名 (如 "agent_chat")
    description: str                   # 人类可读描述
    inputSchema: dict = field(default_factory=dict)  # JSON Schema
    category: str = ""                 # 来源类别 (auth/agent/quiz/...)
    source_endpoint: dict = field(default_factory=dict)  # 原始 schema 中的端点数据

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema,
        }


@dataclass
class MCPToolCallResult:
    """tools/call 的返回结果"""
    tool_name: str
    success: bool
    content: list[dict] = field(default_factory=list)  # MCP content blocks
    error: str = ""
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "content": self.content,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }


# ═══════════════════════════════════════════════════════════════════
# Tool 生成器: Schema → MCP Tools
# ═══════════════════════════════════════════════════════════════════

class ToolGenerator:
    """
    从 platform_schema.yaml 的 apis 字段生成 MCP Tool[]。

    每个 API 端点 → 一个 Tool:
      name:        "{category}_{path_last_segment}"  (如 "agent_chat")
      description: "{method} {path} — {category} API"
      inputSchema: 从 endpoint 的 input_schema / params 推断
    """

    @staticmethod
    def generate_all(adapter) -> list[MCPTool]:
        """
        从 SchemaAdapter 生成全部 Tool。

        :param adapter: SchemaAdapter 实例
        :return: MCPTool 列表
        """
        tools: list[MCPTool] = []
        apis = adapter.raw.get("apis", {})

        if not isinstance(apis, dict):
            return tools

        for category, endpoints in apis.items():
            if not isinstance(endpoints, list):
                continue

            for ep in endpoints:
                if not isinstance(ep, dict):
                    continue
                tool = ToolGenerator._endpoint_to_tool(category, ep)
                if tool:
                    tools.append(tool)

        # 如果 schema 有 agent.chat_endpoint 但没有 apis.agent → 补充
        agent = adapter.raw.get("agent", {})
        if agent.get("chat_endpoint"):
            existing_names = {t.name for t in tools}
            if "agent_chat" not in existing_names:
                tools.append(ToolGenerator._agent_to_tool(agent, adapter))

        return tools

    @staticmethod
    def _endpoint_to_tool(category: str, ep: dict) -> Optional[MCPTool]:
        """单个 API 端点 → MCP Tool"""
        path = ep.get("path", "")
        method = ep.get("method", "GET")
        if not path:
            return None

        # 生成唯一名称: category + path 最后一段
        name = ToolGenerator._make_tool_name(category, path)

        # 生成描述
        description = ToolGenerator._make_description(category, method, path, ep)

        # 生成 inputSchema
        input_schema = ToolGenerator._make_input_schema(ep, method)

        return MCPTool(
            name=name,
            description=description,
            inputSchema=input_schema,
            category=category,
            source_endpoint={
                "path": path,
                "method": method,
                "confidence": ep.get("confidence", 0),
            },
        )

    @staticmethod
    def _agent_to_tool(agent: dict, adapter) -> MCPTool:
        """从 agent 字段生成 agent_chat tool"""
        return MCPTool(
            name="agent_chat",
            description="POST /api/agent/chat — 向 AI 教学助手发送消息",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "用户消息"},
                    "lesson_id": {"type": "string", "description": "当前课时 ID"},
                    "phase": {"type": "integer", "description": "Phase 编号"},
                },
                "required": ["message"],
            },
            category="agent",
            source_endpoint={
                "path": agent.get("chat_endpoint", "/api/agent/chat"),
                "method": "POST",
                "confidence": 0.9,
            },
        )

    @staticmethod
    def _make_tool_name(category: str, path: str) -> str:
        """生成语义化的 tool name"""
        # 取 path 最后一段作为名 (去参数)
        clean = path.rstrip("/").split("/")[-1]
        clean = clean.split("?")[0]
        # snake_case
        clean = clean.replace("-", "_").lower()
        return f"{category}_{clean}" if category and clean else clean

    @staticmethod
    def _make_description(category: str, method: str, path: str, ep: dict) -> str:
        """生成工具描述"""
        conf = ep.get("confidence", 0)
        desc_parts = [f"{method} {path}"]
        if category:
            desc_parts.append(f"[{category}]")
        if conf:
            desc_parts.append(f"(confidence: {conf:.0%})")
        if ep.get("response_sample"):
            desc_parts.append("— has response sample")
        return " ".join(desc_parts)

    @staticmethod
    def _make_input_schema(ep: dict, method: str) -> dict:
        """从端点数据推断 inputSchema (JSON Schema 格式)"""
        # 优先使用 schema 中已有的 input_schema
        if ep.get("input_schema") and isinstance(ep["input_schema"], dict):
            schema = {"type": "object", "properties": {}, "required": []}
            for field, ftype in ep["input_schema"].items():
                schema["properties"][field] = {"type": ftype if isinstance(ftype, str) else "string"}
            # 常用必填字段
            for req in ("message", "username", "lesson_id"):
                if req in schema["properties"]:
                    schema.setdefault("required", []).append(req)
            return schema

        # GET 方法无 body
        if method.upper() == "GET":
            return {"type": "object", "properties": {}}

        # POST 方法: 从 response_sample 推断 (通过请求体常见字段)
        body_fields = _infer_body_fields(ep)
        if body_fields:
            return {
                "type": "object",
                "properties": {f: {"type": "string"} for f in body_fields},
            }

        # 最小 schema
        return {"type": "object", "properties": {}}


def _infer_body_fields(ep: dict) -> list[str]:
    """从 response_sample 和 path 推断可能的请求体字段"""
    path = ep.get("path", "").lower()
    fields = []

    # 基于路径推断
    if "login" in path or "auth" in path:
        fields = ["username", "password"]
    elif "chat" in path or "agent" in path:
        fields = ["message", "lesson_id", "step_block_id", "phase", "conversation_id"]
    elif "quiz" in path:
        if "start" in path:
            fields = ["lesson_id"]
        elif "submit" in path:
            fields = ["quiz_id", "answers"]
        else:
            fields = ["lesson_id"]
    elif "search" in path:
        fields = ["query", "lesson_id"]

    return fields


# ═══════════════════════════════════════════════════════════════════
# Tool 执行器: MCP Tool → PlatformClient 调用
# ═══════════════════════════════════════════════════════════════════

class ToolExecutor:
    """
    将 MCP tool call 转发给 PlatformClient 执行。

    Tool name → PlatformClient 方法映射:
      auth_login    → client.login(username, password)
      agent_chat    → client.agent_chat(message, lesson_id=...)
      quiz_start    → client.start_quiz(lesson_id)
      quiz_submit   → client.submit_quiz(quiz_id, answers)
    """

    # Tool name → (PlatformClient method name, kwargs mapping)
    METHOD_MAP: dict[str, tuple[str, list[str]]] = {
        "auth_login":     ("login", ["username", "password"]),
        "agent_chat":     ("agent_chat", ["message", "lesson_id"]),
        "quiz_start":     ("start_quiz", ["lesson_id"]),
        "quiz_submit":    ("submit_quiz", ["quiz_id", "answers"]),
    }

    def __init__(self, client=None):
        """
        :param client: PlatformClient 实例 (可选, 不传则自动创建)
        """
        self._client = client

    @property
    def client(self):
        """懒加载 PlatformClient"""
        if self._client is None:
            from src.platform_client import PlatformClient
            self._client = PlatformClient()
        return self._client

    def execute(self, tool: MCPTool, arguments: dict) -> MCPToolCallResult:
        """
        执行一个 MCP Tool。

        :param tool: MCPTool 定义
        :param arguments: 调用参数 (如 {message: "hello", lesson_id: "1"})
        :return: MCPToolCallResult
        """
        t0 = time.time()
        tool_name = tool.name

        try:
            # 查找映射
            mapped = self.METHOD_MAP.get(tool_name)
            if mapped is None:
                # 未知 tool → 直接 HTTP 调用 (通用回退)
                return self._execute_generic(tool, arguments, t0)

            method_name, param_names = mapped

            # 提取参数
            kwargs = {k: arguments.get(k) for k in param_names if k in arguments}

            # 调 PlatformClient 方法
            platform_method = getattr(self.client, method_name, None)
            if platform_method is None:
                return MCPToolCallResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"PlatformClient 无方法 '{method_name}'",
                    duration_ms=(time.time() - t0) * 1000,
                )

            result = platform_method(**kwargs)

            # 规范化返回值
            content = self._normalize_result(result)
            return MCPToolCallResult(
                tool_name=tool_name,
                success=True,
                content=[{"type": "text", "text": json.dumps(content, ensure_ascii=False)}],
                duration_ms=(time.time() - t0) * 1000,
            )

        except Exception as e:
            logger.warning(f"Tool '{tool_name}' failed: {e}")
            return MCPToolCallResult(
                tool_name=tool_name,
                success=False,
                error=str(e),
                duration_ms=(time.time() - t0) * 1000,
            )

    def _execute_generic(self, tool: MCPTool, arguments: dict, t0: float) -> MCPToolCallResult:
        """
        通用 HTTP 调用回退 — 用于未映射到 PlatformClient 方法的端点。

        直接使用 PlatformClient 的 session 发 HTTP 请求。
        """
        endpoint = tool.source_endpoint
        path = endpoint.get("path", "")
        method = endpoint.get("method", "GET").upper()

        if not path:
            return MCPToolCallResult(
                tool_name=tool.name,
                success=False,
                error=f"无可用路径: {tool.name}",
                duration_ms=(time.time() - t0) * 1000,
            )

        try:
            base = self.client.base_url
            # 如果 path 已经是完整 URL (schema 中存了绝对路径) → 直接用
            if path.startswith("http://") or path.startswith("https://"):
                url = path
            else:
                url = f"{base.rstrip('/')}{path}"
            headers = self.client._auth_headers() if hasattr(self.client, "_auth_headers") else {}

            if method == "GET":
                resp = self.client.session.get(url, headers=headers, timeout=30, proxies={"http": None, "https": None})
            elif method == "POST":
                resp = self.client.session.post(url, json=arguments, headers=headers, timeout=30, proxies={"http": None, "https": None})
            else:
                return MCPToolCallResult(
                    tool_name=tool.name,
                    success=False,
                    error=f"不支持的 HTTP 方法: {method}",
                    duration_ms=(time.time() - t0) * 1000,
                )

            try:
                body = resp.json() if resp.text else {}
            except json.JSONDecodeError:
                body = {"raw": resp.text[:500]}

            return MCPToolCallResult(
                tool_name=tool.name,
                success=resp.status_code < 400,
                content=[{"type": "text", "text": json.dumps(body, ensure_ascii=False)[:2000]}],
                duration_ms=(time.time() - t0) * 1000,
            )

        except Exception as e:
            return MCPToolCallResult(
                tool_name=tool.name,
                success=False,
                error=str(e),
                duration_ms=(time.time() - t0) * 1000,
            )

    @staticmethod
    def _normalize_result(result) -> dict:
        """规范化 PlatformClient 方法的返回值 → JSON-safe dict"""
        if isinstance(result, dict):
            return _sanitize_for_json(result)
        if hasattr(result, "__dataclass_fields__"):
            return _sanitize_for_json({
                k: getattr(result, k)
                for k in result.__dataclass_fields__
            })
        return {"result": str(result)[:2000]}


def _sanitize_for_json(obj: Any) -> Any:
    """递归清理对象使其 JSON-safe"""
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, (int, float, bool, str, type(None))):
        return obj
    return str(obj)[:500]


# ═══════════════════════════════════════════════════════════════════
# MCP Server 主类
# ═══════════════════════════════════════════════════════════════════

class MCPServer:
    """
    MCP Server 主入口。

    用法:
        server = MCPServer()
        server.initialize()             # 读 schema → 生成 tools
        tools = server.list_tools()     # 列出所有工具
        result = server.call_tool(      # 执行工具
            "agent_chat",
            {"message": "hello", "lesson_id": "22"}
        )

    HTTP 端点集成 (backend/api/__init__.py):
        from src.mcp_server import MCPServer
        mcp = MCPServer()
        mcp.initialize()
        router.get("/mcp/tools")(mcp.list_tools)
        router.post("/mcp/call")(mcp.call_tool_endpoint)
    """

    def __init__(self, schema_path: str = ""):
        """
        :param schema_path: 显式指定 schema 路径 (留空自动查找)
        """
        self.schema_path = schema_path
        self._tools: list[MCPTool] = []
        self._executor: Optional[ToolExecutor] = None
        self._initialized = False
        self._schema_available = False
        self._init_error = ""

    # ── 初始化 ──

    def initialize(self) -> bool:
        """
        加载 schema + 生成 tools + 初始化执行器。

        :return: 是否成功初始化 (schema 可用)
        """
        self._initialized = True

        # 读 schema
        resolved = self._resolve_schema()
        if not resolved:
            self._schema_available = False
            self._init_error = "platform_schema.yaml 不存在 — 请先运行 Explorer"
            self._tools = []
            return False

        try:
            from src.schema_adapter import SchemaAdapter
            adapter = SchemaAdapter(resolved)
            self._tools = ToolGenerator.generate_all(adapter)
            self._executor = ToolExecutor()
            self._schema_available = True
            self._init_error = ""
            return True
        except Exception as e:
            self._schema_available = False
            self._init_error = str(e)
            self._tools = []
            return False

    # ── 公开 API ──

    def list_tools(self) -> dict:
        """
        列出所有可用工具 (对齐 MCP tools/list)。

        返回:
          {
            "protocolVersion": "2024-11-05",
            "tools": [{name, description, inputSchema}, ...],
            "count": N,
            "schema_available": true/false,
            "hint": "..."  // schema 缺失时的提示
          }
        """
        if not self._initialized:
            self.initialize()

        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "tools": [t.to_dict() for t in self._tools],
            "count": len(self._tools),
            "schema_available": self._schema_available,
            "hint": self._init_error if not self._schema_available else "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def call_tool(self, name: str, arguments: dict = None) -> dict:
        """
        执行指定工具 (对齐 MCP tools/call)。

        :param name: 工具名 (如 "agent_chat")
        :param arguments: 调用参数
        :return: MCPToolCallResult.to_dict()
        """
        if not self._initialized:
            self.initialize()

        if not self._schema_available:
            return MCPToolCallResult(
                tool_name=name,
                success=False,
                error=f"Schema 不可用: {self._init_error}",
            ).to_dict()

        # 查找工具
        tool = next((t for t in self._tools if t.name == name), None)
        if tool is None:
            return MCPToolCallResult(
                tool_name=name,
                success=False,
                error=f"未知工具: '{name}'. 可用工具: {[t.name for t in self._tools]}",
            ).to_dict()

        # 执行
        if self._executor is None:
            self._executor = ToolExecutor()

        return self._executor.execute(tool, arguments or {}).to_dict()

    # ── 便捷: HTTP 端点 handler ──

    async def call_tool_endpoint(self, body: dict) -> dict:
        """FastAPI 端点: POST /api/mcp/call"""
        name = body.get("name", "")
        args = body.get("arguments", {})
        return self.call_tool(name, args)

    # ── 内部 ──

    def _resolve_schema(self) -> Optional[str]:
        if self.schema_path and Path(self.schema_path).exists():
            return self.schema_path
        for candidate in SCHEMA_CANDIDATES:
            p = Path(candidate)
            if p.exists():
                return str(p)
        probe_dir = Path("output/platform_probe")
        if probe_dir.exists():
            for subdir in sorted(probe_dir.iterdir(), reverse=True):
                if subdir.is_dir():
                    schema_file = subdir / "platform_schema.yaml"
                    if schema_file.exists():
                        return str(schema_file)
        return None

    @property
    def is_available(self) -> bool:
        return self._schema_available

    @property
    def tool_names(self) -> list[str]:
        return [t.name for t in self._tools]


# ═══════════════════════════════════════════════════════════════════
# 全局单例 (供 FastAPI 端点使用)
# ═══════════════════════════════════════════════════════════════════

_mcp_server: Optional[MCPServer] = None


def get_mcp_server() -> MCPServer:
    """获取全局 MCP Server 单例"""
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = MCPServer()
        _mcp_server.initialize()
    return _mcp_server


# ═══════════════════════════════════════════════════════════════════
# Health API 集成
# ═══════════════════════════════════════════════════════════════════

def get_health_summary() -> dict:
    """返回 MCP Server 健康摘要"""
    server = get_mcp_server()
    return {
        "component": "mcp_server",
        "status": "healthy" if server.is_available else ("degraded" if server._initialized else "not_initialized"),
        "schema_available": server.is_available,
        "tools_count": len(server._tools),
        "tool_names": server.tool_names,
    }
