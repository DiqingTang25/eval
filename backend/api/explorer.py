"""Platform Explorer API 路由 — 对话式探索器 + 表单路径 (合并 v4.0 与 chat 端点)"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# Lazy import — 在首次API调用时才加载服务, 避免启动时导入链问题
_explorer_service = None


def _get_service():
    global _explorer_service
    if _explorer_service is None:
        from backend.services.explorer_service import ExplorerService
        _explorer_service = ExplorerService()
    return _explorer_service


# 对话服务 (懒加载, 注入同一个 ExplorerService 单例避免运行状态脱节)
_chat_service = None


def _get_chat_service():
    global _chat_service
    if _chat_service is None:
        from backend.services.explorer_chat import ExplorerChatService
        _chat_service = ExplorerChatService(explorer_service=_get_service())
    return _chat_service


class ExploreRequest(BaseModel):
    target_url: str
    username: str = ""
    password: str = ""
    headless: bool = True
    max_depth: int = 3
    max_pages: int = 50
    api_threshold: float = 0.50
    auth_state_path: str = ""  # 预认证: 已保存的 Playwright storage_state JSON 路径
    llm_api_key: str = ""      # LLM API Key (用于端点枚举)
    vlm_api_key: str = ""      # VLM API Key (用于视觉理解)


class ChatStartRequest(BaseModel):
    """开启对话 — 可预填固定表单值作为默认参数"""
    chat_id: str = ""
    target_url: str = ""
    username: str = ""
    password: str = ""
    headless: bool = True
    max_depth: int = 3
    max_pages: int = 50


class ChatMessageRequest(BaseModel):
    chat_id: str
    message: str


class ExploreResponse(BaseModel):
    status: str
    session_id: str = ""
    target_url: str = ""
    error: str = ""
    message: str = ""


# ═══════════════════════════════════════════════════════════
# 环境检查
# ═══════════════════════════════════════════════════════════

@router.get("/health")
async def explorer_health():
    """检查探索器环境是否就绪 (Playwright, DB, 依赖等)"""
    import asyncio
    issues = []

    # 1. YAML
    try:
        import yaml; yaml_ok = True
    except Exception:
        yaml_ok = False; issues.append("pyyaml not installed")

    # 2. 输出目录
    from pathlib import Path
    out = Path(__file__).parent.parent.parent / "output" / "platform_probe"
    try:
        out.mkdir(parents=True, exist_ok=True); dir_ok = True
    except Exception as e:
        dir_ok = False; issues.append(f"Output dir: {e}")

    # 3. Playwright — 检测 chromium 二进制是否存在 (避免 event loop 冲突)
    try:
        from playwright.sync_api import sync_playwright
        def _check():
            with sync_playwright() as p:
                b = p.chromium.launch(headless=True); b.close()
            return True
        pw_ok = await asyncio.to_thread(_check)
    except Exception as e:
        pw_ok = False; issues.append(f"Playwright: {str(e)[:120]}")

    # 4. 数据库
    try:
        from backend.dependencies import get_sync_db
        from sqlalchemy import text
        db = get_sync_db()
        db.execute(text("SELECT 1"))
        db.close(); db_ok = True
    except Exception as e:
        db_ok = False; issues.append(f"DB: {str(e)[:120]}")

    return {
        "ready": pw_ok and yaml_ok and dir_ok and db_ok,
        "checks": {"playwright": pw_ok, "yaml": yaml_ok, "output_dir": dir_ok, "database": db_ok},
        "issues": issues,
        "fix_hints": ["pip install playwright && python -m playwright install chromium"] if not pw_ok else [],
    }


# ═══════════════════════════════════════════════════════════
# 平台Profile (全链路桥梁)
# ═══════════════════════════════════════════════════════════

@router.get("/profile/latest")
async def get_latest_profile():
    """
    获取最近一次成功探索的平台Profile。
    Health Check / Test Runner / Frontend 通过此端点自动获取平台信息。
    """
    from pathlib import Path
    from src.profile_paths import resolve_profile_path
    profile_path = resolve_profile_path()

    if profile_path is None:
        return {"available": False, "message": "No exploration profile yet. Run an exploration first."}

    try:
        import json
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        # 验证schema文件还存在
        schema_path = profile.get("schema_path", "")
        if schema_path and Path(schema_path).exists():
            profile["schema_valid"] = True
        else:
            profile["schema_valid"] = False
        profile["available"] = True
        return profile
    except Exception as e:
        return {"available": False, "message": f"Failed to read profile: {e}"}


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

    return await _get_service().start_explore(
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
    """当前探索状态 (前端每2秒轮询)"""
    return await _get_service().get_status()


@router.post("/cancel")
async def cancel_explore() -> dict:
    """取消正在运行的探索"""
    return await _get_service().cancel_explore()


# ═══════════════════════════════════════════════════════════
# 探索历史
# ═══════════════════════════════════════════════════════════

@router.get("/sessions")
async def list_sessions(page: int = 1, page_size: int = 20) -> dict:
    """探索历史列表"""
    return await _get_service().get_sessions(page=page, page_size=page_size)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    """单个探索会话详情"""
    session = await _get_service().get_session(session_id)
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
    result = await _get_service().get_latest_ready_schema()
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

    session = await _get_service().get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    schema_path = session.get("schema_path")
    if not schema_path or not Path(schema_path).exists():
        raise HTTPException(status_code=404, detail="Schema 文件不存在")

    content = Path(schema_path).read_text(encoding="utf-8")
    return PlainTextResponse(content, media_type="text/yaml")


# ═══════════════════════════════════════════════════════════
# 对话式探索 (对话为主, 固定表单为辅)
# ═══════════════════════════════════════════════════════════

@router.post("/chat/start")
async def chat_start(body: ChatStartRequest = None):
    """开启新对话 — 固定表单值作为预填默认参数"""
    body = body or ChatStartRequest()
    svc = _get_chat_service()
    return svc.start_chat(defaults={
        "target_url": body.target_url,
        "username": body.username,
        "password": body.password,
        "headless": body.headless,
        "max_depth": body.max_depth,
        "max_pages": body.max_pages,
    })


@router.post("/chat/message")
async def chat_message(body: ChatMessageRequest):
    """发送一条对话消息 — 状态机: 收集参数 → 确认 → 启动探索"""
    if not body.chat_id or not body.message.strip():
        raise HTTPException(status_code=400, detail="chat_id 和 message 不能为空")
    svc = _get_chat_service()
    return await svc.handle_message(body.chat_id, body.message.strip())


@router.get("/chat/history/{chat_id}")
async def chat_history(chat_id: str):
    """获取对话历史"""
    svc = _get_chat_service()
    return svc.get_history(chat_id)
