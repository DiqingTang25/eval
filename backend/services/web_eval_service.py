"""Web Eval 服务"""

import asyncio
import os

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import WebEvalResult


class WebEvalService:
    """网页评测服务"""

    async def run_evaluation(self, db: AsyncSession, url: str, test_questions: list = None) -> dict:
        api_key = os.getenv("OPENAI_API_KEY", "")
        try:
            from src.web_evaluator import WebEvaluator
            evaluator = WebEvaluator(api_key=api_key)
            # Run sync Playwright evaluate in thread pool to avoid event loop conflict
            result = await asyncio.to_thread(evaluator.evaluate, url, test_questions or [])

            db_result = WebEvalResult(
                url=url,
                overall_score=result.overall_score,
                performance=vars(result.performance) if hasattr(result.performance, '__dict__') else None,
                accessibility=vars(result.accessibility) if hasattr(result.accessibility, '__dict__') else None,
                best_practices=vars(result.best_practices) if hasattr(result.best_practices, '__dict__') else None,
                ai_function=vars(result.ai_function) if hasattr(result.ai_function, '__dict__') else None,
                ui_ux=vars(result.ui_ux) if hasattr(result.ui_ux, '__dict__') else None,
                content=vars(result.content) if hasattr(result.content, '__dict__') else None,
                raw_result=result.to_dict(),
            )
            db.add(db_result)
            await db.commit()
            return {"ok": True, "overall_score": result.overall_score, "detail": result.to_dict()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def list_results(self, db: AsyncSession, page: int = 1, page_size: int = 20) -> dict:
        total_r = await db.execute(select(func.count(WebEvalResult.id)))
        total = total_r.scalar() or 0

        results_r = await db.execute(
            select(WebEvalResult)
            .order_by(desc(WebEvalResult.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        results = results_r.scalars().all()
        return {
            "items": [
                {"id": r.id, "url": r.url, "overall_score": r.overall_score,
                 "created_at": r.created_at.isoformat() if r.created_at else None}
                for r in results
            ],
            "total": total, "page": page, "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }

    async def get_result(self, db: AsyncSession, result_id: str) -> dict:
        r = await db.execute(select(WebEvalResult).where(WebEvalResult.id == result_id))
        result = r.scalar_one_or_none()
        if not result:
            return None
        return {
            "id": result.id, "url": result.url, "overall_score": result.overall_score,
            "performance": result.performance, "accessibility": result.accessibility,
            "best_practices": result.best_practices, "ai_function": result.ai_function,
            "ui_ux": result.ui_ux, "content": result.content, "raw_result": result.raw_result,
        }

    async def delete_result(self, db: AsyncSession, result_id: str) -> bool:
        r = await db.execute(select(WebEvalResult).where(WebEvalResult.id == result_id))
        result = r.scalar_one_or_none()
        if result:
            await db.delete(result)
            await db.commit()
            return True
        return False
