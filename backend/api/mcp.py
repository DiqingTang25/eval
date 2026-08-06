"""
MCP API 路由 — Agent C

GET  /api/mcp/tools  — 列出所有可用 MCP Tool
POST /api/mcp/call   — 执行指定 Tool
GET  /api/mcp/health — MCP Server 健康状态
"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["MCP"])


class ToolCallRequest(BaseModel):
    name: str = ""
    arguments: dict = {}


@router.get("/tools")
async def list_tools():
    """列出所有可用 MCP Tool (从 platform_schema.yaml 动态生成)"""
    from src.mcp_server import get_mcp_server
    server = get_mcp_server()
    return server.list_tools()


@router.post("/call")
async def call_tool(body: ToolCallRequest):
    """执行指定 MCP Tool"""
    from src.mcp_server import get_mcp_server
    server = get_mcp_server()
    return server.call_tool(body.name, body.arguments)


@router.get("/health")
async def mcp_health():
    """MCP Server 健康状态"""
    from src.mcp_server import get_health_summary
    return get_health_summary()
