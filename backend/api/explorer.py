"""Platform Explorer API 路由"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.explorer_service import ExplorerService

router = APIRouter()
explorer_service = ExplorerService()


class ExploreRequest(BaseModel):
    target_url: str
    username: str = ""
    password: str = ""
    headless: bool = True
    max_depth: int = 3
    max_pages: int = 50
    api_threshold: float = 0.50


class ExploreResponse(BaseModel):
    status: str
    session_id: str = ""
    target_url: str = ""
    error: str = ""
    message: str = ""


# ═══════════════════════════════════════════════════════════
# 探索控制
# ═══════════════════════════════════════════════════════════

@router.post("/run")
async def start_explore(body: ExploreRequest) -> dict:
    """
    启动平台探索

    后台运行 PlatformExplorer, 通过 WebSocket 推送进度。
    完成后 schema 写入 output/platform_probe/<session_id>/platform_schema.yaml
    """
    if not body.target_url:
        raise HTTPException(status_code=400, detail="target_url 不能为空")

    # 基本URL验证
    if not body.target_url.startswith(("http://", "https://")):
        body.target_url = "https://" + body.target_url

    return await explorer_service.start_explore(
        target_url=body.target_url,
        username=body.username,
        password=body.password,
        headless=body.headless,
        max_depth=body.max_depth,
        max_pages=body.max_pages,
        api_threshold=body.api_threshold,
    )


@router.get("/status")
async def explore_status() -> dict:
    """当前探索状态"""
    return await explorer_service.get_status()


@router.post("/cancel")
async def cancel_explore() -> dict:
    """取消正在运行的探索"""
    return await explorer_service.cancel_explore()


# ═══════════════════════════════════════════════════════════
# 探索历史
# ═══════════════════════════════════════════════════════════

@router.get("/sessions")
async def list_sessions(page: int = 1, page_size: int = 20) -> dict:
    """探索历史列表"""
    return await explorer_service.get_sessions(page=page, page_size=page_size)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    """单个探索会话详情"""
    session = await explorer_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


# ═══════════════════════════════════════════════════════════
# Schema 管理
# ═══════════════════════════════════════════════════════════

@router.get("/schema/latest")
async def get_latest_schema() -> dict:
    """
    获取最近一次成功探索的 schema 路径
    前端/TestRunner 可据此自动选择 schema 驱动模式
    """
    result = await explorer_service.get_latest_ready_schema()
    if not result:
        return {
            "available": False,
            "message": "暂无可用 schema, 请先运行平台探索",
        }
    return {
        "available": True,
        **result,
    }


@router.get("/schema/{session_id}")
async def get_schema_content(session_id: str):
    """
    获取指定探索会话生成的 schema 内容
    返回 YAML 文本, 前端可用于预览
    """
    from pathlib import Path
    from fastapi.responses import PlainTextResponse

    session = await explorer_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    schema_path = session.get("schema_path")
    if not schema_path or not Path(schema_path).exists():
        raise HTTPException(status_code=404, detail="Schema 文件不存在")

    content = Path(schema_path).read_text(encoding="utf-8")
    return PlainTextResponse(content, media_type="text/yaml")
