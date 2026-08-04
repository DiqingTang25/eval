"""Agents API 路由"""

from fastapi import APIRouter

from src.agents.agent_registry import AgentRegistry

router = APIRouter()


@router.get("")
async def list_agents():
    """获取所有已注册 Agent 列表"""
    return AgentRegistry.list_agents()
