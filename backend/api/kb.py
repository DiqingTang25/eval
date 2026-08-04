"""Knowledge Base API 路由"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.services.kb_service import KBService

router = APIRouter()
kb_service = KBService()


@router.get("/status")
async def kb_status(db: AsyncSession = Depends(get_db)):
    """知识库连接状态"""
    return await kb_service.get_status()


@router.get("/bases")
async def list_bases(db: AsyncSession = Depends(get_db)):
    """已同步的知识库列表"""
    return await kb_service.list_bases(db)


@router.post("/bases/sync")
async def sync_bases(db: AsyncSession = Depends(get_db)):
    """从火山引擎同步知识库"""
    result = await kb_service.sync_from_volcengine(db)
    if not result.get("ok"):
        raise HTTPException(500, result.get("error", "Sync failed"))
    return result


@router.get("/bases/{base_id}/documents")
async def list_documents(base_id: str, db: AsyncSession = Depends(get_db)):
    """获取知识库下的文档列表"""
    return await kb_service.list_documents(db, base_id)


@router.get("/search")
async def search_kb(q: str = "", top_k: int = 5):
    """跨知识库搜索"""
    if not q:
        raise HTTPException(400, "Query parameter 'q' is required")
    return await kb_service.search(q, top_k=top_k)
