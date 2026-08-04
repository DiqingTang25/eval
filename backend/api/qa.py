"""QA API 路由"""

import os

from fastapi import APIRouter, Depends, Query, Body, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.services.qa_service import QAService

router = APIRouter()
qa_service = QAService()


@router.get("")
async def list_qa(
    status: str = "all",
    phase: str = "all",
    type: str = "all",
    difficulty: str = "all",
    search: str = "",
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    db: AsyncSession = Depends(get_db),
):
    """QA 列表 (分页+筛选)"""
    return await qa_service.list(
        db,
        status=status,
        phase=phase,
        qtype=type,
        difficulty=difficulty,
        search=search,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/stats")
async def qa_stats(db: AsyncSession = Depends(get_db)):
    """QA 统计"""
    return await qa_service.get_stats(db)


@router.get("/{qa_id}")
async def get_qa(qa_id: str, db: AsyncSession = Depends(get_db)):
    """获取单个 QA"""
    qa = await qa_service.get_by_qa_id(db, qa_id)
    if not qa:
        raise HTTPException(404, "QA not found")
    return qa.to_dict()


@router.post("/{qa_id}/approve")
async def approve_qa(qa_id: str, db: AsyncSession = Depends(get_db)):
    """通过审核"""
    return await qa_service.approve(db, qa_id)


@router.post("/{qa_id}/reject")
async def reject_qa(
    qa_id: str,
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
):
    """拒绝审核"""
    reason = body.get("reason", "") if body else ""
    return await qa_service.reject(db, qa_id, reason)


@router.put("/{qa_id}")
async def edit_qa(qa_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    """编辑 QA"""
    return await qa_service.edit(db, qa_id, body)


@router.delete("/{qa_id}")
async def delete_qa(qa_id: str, db: AsyncSession = Depends(get_db)):
    """删除 QA"""
    return await qa_service.delete(db, qa_id)


@router.post("/batch/approve")
async def batch_approve(body: dict, db: AsyncSession = Depends(get_db)):
    """批量通过"""
    qa_ids = body.get("qa_ids", [])
    return await qa_service.batch_approve(db, qa_ids)


@router.post("/batch/delete")
async def batch_delete(body: dict, db: AsyncSession = Depends(get_db)):
    """批量删除"""
    qa_ids = body.get("qa_ids", [])
    return await qa_service.batch_delete(db, qa_ids)


@router.post("/generate")
async def generate_qa():
    """从 Excel 批量生成 QA"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(400, "OPENAI_API_KEY not configured")

    try:
        from src.qa_generator import QAGenerator
        gen = QAGenerator(api_key)
        qa_pairs = gen.generate_from_excel()
        gen.save_pending(qa_pairs)
        return {"ok": True, "total": len(qa_pairs)}
    except Exception as e:
        raise HTTPException(500, f"QA generation failed: {e}")
