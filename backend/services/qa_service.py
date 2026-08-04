"""QA 服务 — QA Pair CRUD + 批量操作 + Excel 生成"""

from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import select, func, desc, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import QAPair


class QAService:
    """QA Pair 管理服务"""

    async def list(
        self,
        db: AsyncSession,
        *,
        status: str = "all",
        phase: str = "all",
        qtype: str = "all",
        difficulty: str = "all",
        search: str = "",
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> dict:
        """分页查询 QA 列表"""
        query = select(QAPair)
        count_query = select(func.count(QAPair.id))

        # 筛选
        filters = []
        if status and status != "all":
            filters.append(QAPair.status == status)
        if phase and phase != "all":
            filters.append(QAPair.phase == phase)
        if qtype and qtype != "all":
            filters.append(QAPair.type == qtype)
        if difficulty and difficulty != "all":
            filters.append(QAPair.difficulty == difficulty)
        if search:
            filters.append(
                or_(
                    QAPair.question.ilike(f"%{search}%"),
                    QAPair.golden_answer.ilike(f"%{search}%"),
                )
            )

        for f in filters:
            query = query.where(f)
            count_query = count_query.where(f)

        # 计数
        total_r = await db.execute(count_query)
        total = total_r.scalar() or 0

        # 排序
        sort_col = getattr(QAPair, sort_by, QAPair.created_at)
        if sort_order == "desc":
            query = query.order_by(desc(sort_col))
        else:
            query = query.order_by(sort_col)

        # 分页
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        items = result.scalars().all()

        return {
            "items": [item.to_dict() for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }

    async def get_by_qa_id(self, db: AsyncSession, qa_id: str) -> QAPair | None:
        """根据 qa_id 获取 QA Pair"""
        result = await db.execute(
            select(QAPair).where(QAPair.qa_id == qa_id)
        )
        return result.scalar_one_or_none()

    async def get_stats(self, db: AsyncSession) -> dict:
        """QA 统计"""
        phases = ["PHASE 01", "PHASE 02", "PHASE 03", "PHASE 04", "PHASE 05"]
        by_phase = {}
        for p in phases:
            r = await db.execute(
                select(func.count(QAPair.id)).where(QAPair.phase == p)
            )
            by_phase[p] = r.scalar() or 0

        pending_r = await db.execute(
            select(func.count(QAPair.id)).where(QAPair.status == "pending")
        )
        approved_r = await db.execute(
            select(func.count(QAPair.id)).where(QAPair.status == "approved")
        )
        rejected_r = await db.execute(
            select(func.count(QAPair.id)).where(QAPair.status == "rejected")
        )
        total_r = await db.execute(select(func.count(QAPair.id)))

        return {
            "pending": pending_r.scalar() or 0,
            "approved": approved_r.scalar() or 0,
            "rejected": rejected_r.scalar() or 0,
            "total": total_r.scalar() or 0,
            "by_phase": by_phase,
        }

    async def approve(self, db: AsyncSession, qa_id: str) -> dict:
        """审核通过"""
        qa = await self.get_by_qa_id(db, qa_id)
        if not qa:
            return {"ok": False, "error": "QA not found"}
        qa.status = "approved"
        qa.reviewer_notes = "人工审核通过"
        qa.approved_at = datetime.now(timezone.utc)
        await db.commit()
        return {"ok": True, "qa_id": qa_id, "status": "approved"}

    async def reject(self, db: AsyncSession, qa_id: str, reason: str = "") -> dict:
        """审核拒绝"""
        qa = await self.get_by_qa_id(db, qa_id)
        if not qa:
            return {"ok": False, "error": "QA not found"}
        qa.status = "rejected"
        qa.reviewer_notes = reason or "人工审核拒绝"
        await db.commit()
        return {"ok": True, "qa_id": qa_id, "status": "rejected"}

    async def edit(self, db: AsyncSession, qa_id: str, updates: dict) -> dict:
        """编辑 QA"""
        qa = await self.get_by_qa_id(db, qa_id)
        if not qa:
            return {"ok": False, "error": "QA not found"}
        allowed = ["question", "golden_answer", "knowledge_points", "difficulty", "type", "phase"]
        for key in allowed:
            if key in updates:
                setattr(qa, key, updates[key])
        qa.status = "pending"
        await db.commit()
        return {"ok": True, "qa_id": qa_id}

    async def delete(self, db: AsyncSession, qa_id: str) -> dict:
        """删除 QA"""
        qa = await self.get_by_qa_id(db, qa_id)
        if not qa:
            return {"ok": False, "error": "QA not found"}
        await db.delete(qa)
        await db.commit()
        return {"ok": True, "qa_id": qa_id}

    async def batch_approve(self, db: AsyncSession, qa_ids: list[str]) -> dict:
        """批量通过 — 单次查询"""
        result = await db.execute(
            select(QAPair).where(
                QAPair.qa_id.in_(qa_ids), QAPair.status == "pending"
            )
        )
        qas = result.scalars().all()
        now = datetime.now(timezone.utc)
        for qa in qas:
            qa.status = "approved"
            qa.approved_at = now
        await db.commit()
        return {"ok": True, "approved": len(qas)}

    async def batch_delete(self, db: AsyncSession, qa_ids: list[str]) -> dict:
        """批量删除 — 单次查询"""
        result = await db.execute(
            select(QAPair).where(QAPair.qa_id.in_(qa_ids))
        )
        qas = result.scalars().all()
        for qa in qas:
            await db.delete(qa)
        await db.commit()
        return {"ok": True, "deleted": len(qas)}
