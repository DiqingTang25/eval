"""
MCP Server — 离线单元测试 (Agent C)

重点验证:
  1. Schema 缺失 → 空工具列表 (零硬编码)
  2. Tool 生成: 每个 API 端点 → 一个 MCPTool
  3. Tool name/description/inputSchema 全部来自 schema
  4. tools/list 和 tools/call 接口正确
  5. 未知 tool → 明确报错, 不崩溃
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.mcp_server import (
    MCPServer,
    MCPTool,
    ToolGenerator,
    ToolExecutor,
    MCPToolCallResult,
    get_mcp_server,
    get_health_summary,
    MCP_PROTOCOL_VERSION,
)


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _make_mock_schema() -> dict:
    """最小但合法的 schema (含 API 列表)"""
    return {
        "target_url": "http://test.example.com",
        "schema_version": "1.0",
        "confidence_scores": {"overall": 0.85},
        "auth": {"type": "form", "login_url": "/api/auth/login", "login_method": "POST"},
        "structure": {
            "phases": [
                {"id": "phase_1", "name": "AI基础", "order": 1, "lesson_count": 2},
            ],
            "lessons": [],
            "steps": [],
        },
        "apis": {
            "auth": [
                {"path": "/api/auth/login", "method": "POST", "confidence": 0.95},
            ],
            "agent": [
                {"path": "/api/agent/chat", "method": "POST", "confidence": 0.9,
                 "input_schema": {"message": "string", "lesson_id": "string"}},
                {"path": "/api/agent/history", "method": "GET", "confidence": 0.85},
            ],
            "quiz": [
                {"path": "/api/quiz/start", "method": "POST", "confidence": 0.9},
                {"path": "/api/quiz/submit", "method": "POST", "confidence": 0.9},
            ],
        },
    }


def _write_temp_yaml(data: dict) -> str:
    import yaml
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8")
    yaml.dump(data, tmp, allow_unicode=True)
    tmp.close()
    return tmp.name


# ═══════════════════════════════════════════════════════════════════
# Test: Schema Missing
# ═══════════════════════════════════════════════════════════════════

def test_no_schema_returns_empty_tools():
    """Schema 缺失 → 空工具列表, 不报错崩溃"""
    server = MCPServer(schema_path="/nonexistent/path.yaml")
    result = server.list_tools()

    assert result["schema_available"] is False
    assert result["count"] == 0
    assert result["tools"] == []
    assert "不存在" in result.get("hint", "") or "nonexistent" in result["hint"].lower()


def test_no_schema_call_tool_returns_error():
    """Schema 缺失时 call_tool 返回明确错误"""
    server = MCPServer(schema_path="/nonexistent/path.yaml")
    result = server.call_tool("agent_chat", {"message": "hello"})

    assert result["success"] is False
    assert "Schema" in result.get("error", "")


# ═══════════════════════════════════════════════════════════════════
# Test: ToolGenerator
# ═══════════════════════════════════════════════════════════════════

def test_generate_tools_count():
    """4 个 API 端点 → 4 个 Tool"""
    schema_data = _make_mock_schema()
    schema_path = _write_temp_yaml(schema_data)

    try:
        from src.schema_adapter import SchemaAdapter
        adapter = SchemaAdapter(schema_path)
        tools = ToolGenerator.generate_all(adapter)

        # 4 API endpoints
        assert len(tools) >= 4, f"Expected >=4 tools, got {len(tools)}"
    finally:
        Path(schema_path).unlink(missing_ok=True)


def test_tool_names_from_schema():
    """Tool 名称来自 schema, 不是硬编码"""
    schema_data = _make_mock_schema()
    schema_path = _write_temp_yaml(schema_data)

    try:
        from src.schema_adapter import SchemaAdapter
        adapter = SchemaAdapter(schema_path)
        tools = ToolGenerator.generate_all(adapter)

        names = {t.name for t in tools}
        assert "auth_login" in names, f"Expected auth_login in {names}"
        assert "agent_chat" in names, f"Expected agent_chat in {names}"
        assert "quiz_start" in names, f"Expected quiz_start in {names}"
        assert "quiz_submit" in names, f"Expected quiz_submit in {names}"
    finally:
        Path(schema_path).unlink(missing_ok=True)


def test_tool_input_schema():
    """inputSchema 从 schema 的 input_schema 字段推断"""
    schema_data = _make_mock_schema()
    schema_path = _write_temp_yaml(schema_data)

    try:
        from src.schema_adapter import SchemaAdapter
        adapter = SchemaAdapter(schema_path)
        tools = ToolGenerator.generate_all(adapter)

        chat_tool = next((t for t in tools if t.name == "agent_chat"), None)
        assert chat_tool is not None
        assert "message" in chat_tool.inputSchema.get("properties", {})
    finally:
        Path(schema_path).unlink(missing_ok=True)


def test_tool_description_includes_method():
    """Tool description 包含 HTTP 方法"""
    schema_data = _make_mock_schema()
    schema_path = _write_temp_yaml(schema_data)

    try:
        from src.schema_adapter import SchemaAdapter
        adapter = SchemaAdapter(schema_path)
        tools = ToolGenerator.generate_all(adapter)

        login_tool = next((t for t in tools if t.name == "auth_login"), None)
        assert login_tool is not None
        assert "POST" in login_tool.description
        assert "/api/auth/login" in login_tool.description
    finally:
        Path(schema_path).unlink(missing_ok=True)


def test_get_tools_with_POST_infers_body():
    """POST 端点自动推断 body 字段"""
    schema_data = _make_mock_schema()
    schema_path = _write_temp_yaml(schema_data)

    try:
        from src.schema_adapter import SchemaAdapter
        adapter = SchemaAdapter(schema_path)
        tools = ToolGenerator.generate_all(adapter)

        login_tool = next((t for t in tools if "login" in t.name), None)
        assert login_tool is not None
        props = login_tool.inputSchema.get("properties", {})
        assert "username" in props or "password" in props, \
            f"Login tool should infer body fields, got: {props}"
    finally:
        Path(schema_path).unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════
# Test: MCPServer
# ═══════════════════════════════════════════════════════════════════

def test_list_tools_structure():
    """tools/list 返回正确结构"""
    schema_data = _make_mock_schema()
    schema_path = _write_temp_yaml(schema_data)

    try:
        server = MCPServer(schema_path=schema_path)
        result = server.list_tools()

        assert result["protocolVersion"] == MCP_PROTOCOL_VERSION
        assert result["schema_available"] is True
        assert result["count"] >= 4
        assert isinstance(result["tools"], list)

        # 每个 tool 有 name/description/inputSchema
        for tool in result["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
    finally:
        Path(schema_path).unlink(missing_ok=True)


def test_call_unknown_tool():
    """调用不存在的 tool → 明确报错"""
    schema_data = _make_mock_schema()
    schema_path = _write_temp_yaml(schema_data)

    try:
        server = MCPServer(schema_path=schema_path)
        result = server.call_tool("nonexistent_tool", {})

        assert result["success"] is False
        assert "未知工具" in result.get("error", "") or "nonexistent" in result.get("error", "")
    finally:
        Path(schema_path).unlink(missing_ok=True)


def test_schema_with_no_apis():
    """Schema 存在但没有 API 端点 → 空工具列表"""
    schema_data = _make_mock_schema()
    schema_data["apis"] = {}
    schema_path = _write_temp_yaml(schema_data)

    try:
        server = MCPServer(schema_path=schema_path)
        result = server.list_tools()

        assert result["schema_available"] is True
        assert result["count"] == 0
    finally:
        Path(schema_path).unlink(missing_ok=True)


def test_tool_count_matches_endpoints():
    """Tool 数量 = 唯一 API 端点数量"""
    schema_data = _make_mock_schema()
    schema_path = _write_temp_yaml(schema_data)

    try:
        server = MCPServer(schema_path=schema_path)
        result = server.list_tools()

        # 4 unique endpoints in mock schema
        assert result["count"] >= 4, f"Expected >=4 tools, got {result['count']}"
    finally:
        Path(schema_path).unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════
# Test: MCPToolCallResult
# ═══════════════════════════════════════════════════════════════════

def test_tool_call_result_success():
    result = MCPToolCallResult(
        tool_name="agent_chat",
        success=True,
        content=[{"type": "text", "text": "hello"}],
        duration_ms=150.0,
    )
    d = result.to_dict()
    assert d["success"] is True
    assert d["duration_ms"] == 150.0
    assert d["tool_name"] == "agent_chat"


def test_tool_call_result_error():
    result = MCPToolCallResult(
        tool_name="bad_tool",
        success=False,
        error="Connection refused",
    )
    d = result.to_dict()
    assert d["success"] is False
    assert "Connection refused" in d["error"]


# ═══════════════════════════════════════════════════════════════════
# Test: Hardcoding Detection
# ═══════════════════════════════════════════════════════════════════

def test_no_hardcoded_phase_names():
    """源码中禁止出现弃用的 Phase 名称"""
    src = Path(__file__).parent.parent / "src" / "mcp_server.py"
    code = src.read_text(encoding="utf-8")

    banned = ["国产AI动手派", "人机共创设计与智能制造", "解锁AI五官",
              "全链路实战", "AI机器人创造营", "Embedded Hardware"]

    for phrase in banned:
        assert phrase not in code, (
            f"HARDCODING DETECTED: '{phrase}' in mcp_server.py"
        )


# ═══════════════════════════════════════════════════════════════════
# Test: Health Summary
# ═══════════════════════════════════════════════════════════════════

def test_health_summary():
    summary = get_health_summary()
    assert summary["component"] == "mcp_server"
    assert "schema_available" in summary
    assert "tools_count" in summary
    assert "tool_names" in summary


# ═══════════════════════════════════════════════════════════════════
# Test: _infer_body_fields
# ═══════════════════════════════════════════════════════════════════

def test_infer_body_fields_login():
    from src.mcp_server import _infer_body_fields
    fields = _infer_body_fields({"path": "/api/auth/login", "method": "POST"})
    assert "username" in fields
    assert "password" in fields


def test_infer_body_fields_chat():
    from src.mcp_server import _infer_body_fields
    fields = _infer_body_fields({"path": "/api/agent/chat", "method": "POST"})
    assert "message" in fields


def test_infer_body_fields_quiz_start():
    from src.mcp_server import _infer_body_fields
    fields = _infer_body_fields({"path": "/api/quiz/start", "method": "POST"})
    assert "lesson_id" in fields


# ═══════════════════════════════════════════════════════════════════
# Test: Custom schema → tools adapt
# ═══════════════════════════════════════════════════════════════════

def test_custom_phase_names_in_tools():
    """自定义 Phase 名称应该出现在 tool 相关的 schema 读取中, 不是硬编码"""
    custom = _make_mock_schema()
    custom["structure"]["phases"] = [
        {"id": "p_new", "name": "新型课程模块", "order": 1, "lesson_count": 1},
    ]
    # 加一个自定义 API
    custom["apis"]["custom"] = [
        {"path": "/api/v2/new-feature", "method": "POST", "confidence": 0.85},
    ]

    schema_path = _write_temp_yaml(custom)
    try:
        from src.schema_adapter import SchemaAdapter
        adapter = SchemaAdapter(schema_path)
        tools = ToolGenerator.generate_all(adapter)

        names = {t.name for t in tools}
        # 自定义 API 应该自动生成 tool
        assert "custom_new_feature" in names or "custom_new-feature" in names, \
            f"Custom API should generate tool, got: {names}"
    finally:
        Path(schema_path).unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    passed = 0
    failed = 0
    tests = [
        test_no_schema_returns_empty_tools,
        test_no_schema_call_tool_returns_error,
        test_generate_tools_count,
        test_tool_names_from_schema,
        test_tool_input_schema,
        test_tool_description_includes_method,
        test_get_tools_with_POST_infers_body,
        test_list_tools_structure,
        test_call_unknown_tool,
        test_schema_with_no_apis,
        test_tool_count_matches_endpoints,
        test_tool_call_result_success,
        test_tool_call_result_error,
        test_no_hardcoded_phase_names,
        test_health_summary,
        test_infer_body_fields_login,
        test_infer_body_fields_chat,
        test_infer_body_fields_quiz_start,
        test_custom_phase_names_in_tools,
    ]
    for test in tests:
        try:
            test()
            passed += 1
            print(f"  PASS {test.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL {test.__name__}: {e}")

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    if failed > 0:
        sys.exit(1)
