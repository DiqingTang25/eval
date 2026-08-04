"""Web Eval API 路由"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.services.web_eval_service import WebEvalService

router = APIRouter()
web_eval_service = WebEvalService()


@router.post("/run")
async def run_web_eval(
    url: str = "http://124.174.108.70",
    db: AsyncSession = Depends(get_db),
):
    """执行网页评测"""
    result = await web_eval_service.run_evaluation(db, url)
    if not result.get("ok"):
        raise HTTPException(500, result.get("error", "Evaluation failed"))
    return result


@router.get("/results")
async def list_results(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """网页评测结果列表"""
    return await web_eval_service.list_results(db, page, page_size)


@router.get("/results/{result_id}")
async def get_result(result_id: str, db: AsyncSession = Depends(get_db)):
    """获取单个网页评测结果"""
    result = await web_eval_service.get_result(db, result_id)
    if not result:
        raise HTTPException(404, "Result not found")
    return result


@router.delete("/results/{result_id}")
async def delete_result(result_id: str, db: AsyncSession = Depends(get_db)):
    """删除网页评测结果"""
    ok = await web_eval_service.delete_result(db, result_id)
    if not ok:
        raise HTTPException(404, "Result not found")
    return {"ok": True}
