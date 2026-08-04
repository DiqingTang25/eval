"""
Knowledge Base 服务 — 火山引擎知识库 (Bearer API Key)

正确 API: POST /api/knowledge/collection/search_knowledge
  请求头: Authorization: Bearer {api_key}
  请求体: {"service_resource_id": "kb-xxx", "name": "phase_N", "query": "...", "limit": 5}

4个Phase KB:
  Phase 1: kb-1cf46d36aaa68622 / phase_1
  Phase 2: kb-453f9a68d45f983c / phase_2
  Phase 3&4: kb-service-c9c4a9287f094dc6 / phase_4
  Phase 5: kb-service-9116de458fb8d1cf / domestic_ai_makers_pbl_platform
"""

import json
import os
from datetime import datetime, timezone
import httpx
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import KnowledgeBase, KBDocument

KB_DOMAIN = "api-knowledgebase.mlp.cn-beijing.volces.com"
KB_SEARCH_URL = f"https://{KB_DOMAIN}/api/knowledge/collection/search_knowledge"

KB_PHASES = {
    "phase1": {
        "name": "Phase 1 — 国产AI技术基础",
        "resource_id": os.getenv("VOLC_KB_PHASE1_ID", "kb-1cf46d36aaa68622"),
        "collection": "phase_1",
        "api_key": os.getenv("VOLC_KB_PHASE1_KEY", ""),
    },
    "phase2": {
        "name": "Phase 2 — 新型硬件设计",
        "resource_id": os.getenv("VOLC_KB_PHASE2_ID", "kb-453f9a68d45f983c"),
        "collection": "phase_2",
        "api_key": os.getenv("VOLC_KB_PHASE2_KEY", ""),
    },
    "phase3_4": {
        "name": "Phase 3&4 — 环境感知与触觉反馈",
        "resource_id": os.getenv("VOLC_KB_PHASE3_4_ID", "kb-service-c9c4a9287f094dc6"),
        "collection": "phase_4",
        "api_key": os.getenv("VOLC_KB_PHASE3_4_KEY", ""),
    },
    "phase5": {
        "name": "Phase 5 — 具身智能控制",
        "resource_id": os.getenv("VOLC_KB_PHASE5_ID", "kb-service-9116de458fb8d1cf"),
        "collection": "domestic_ai_makers_pbl_platform",
        "api_key": os.getenv("VOLC_KB_PHASE5_KEY", ""),
    },
}


class KBService:
    def __init__(self):
        self.configured = any(kb["api_key"] for kb in KB_PHASES.values())

    async def get_status(self) -> dict:
        configured_phases = [p for p, kb in KB_PHASES.items() if kb["api_key"]]
        return {
            "configured": self.configured,
            "total_phases": len(KB_PHASES),
            "configured_phases": configured_phases,
            "kb_domain": KB_DOMAIN,
            "provider": "火山引擎 (Volcengine)",
        }

    async def list_bases(self, db: AsyncSession) -> dict:
        """返回已配置的Phase KB列表"""
        items = []
        for phase_id, kb in KB_PHASES.items():
            items.append({
                "id": phase_id,
                "name": kb["name"],
                "resource_id": kb["resource_id"],
                "collection": kb["collection"],
                "configured": bool(kb["api_key"]),
            })
        return {"items": items, "count": len(items)}

    async def list_documents(self, db: AsyncSession, base_id: str) -> dict:
        return {"items": [], "message": "文档列表需要通过火山引擎控制台查看"}

    async def sync_from_volcengine(self, db: AsyncSession) -> dict:
        if not self.configured:
            return {"ok": False, "error": "未配置火山引擎知识库"}
        # 同步到MySQL
        try:
            for phase_id, kb in KB_PHASES.items():
                if not kb["api_key"]:
                    continue
                existing_r = await db.execute(
                    select(KnowledgeBase).where(KnowledgeBase.dify_dataset_id == kb["resource_id"])
                )
                existing = existing_r.scalar_one_or_none()
                if not existing:
                    entry = KnowledgeBase(
                        dify_dataset_id=kb["resource_id"],
                        name=kb["name"],
                        description=f"火山引擎知识库 / {kb['collection']}",
                        document_count=1,
                        last_synced_at=datetime.now(timezone.utc),
                        sync_status="synced",
                    )
                    db.add(entry)
            await db.commit()
            configured = sum(1 for kb in KB_PHASES.values() if kb["api_key"])
            return {"ok": True, "synced": configured, "total": len(KB_PHASES)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def search(self, query: str, top_k: int = 5) -> dict:
        """搜索所有已配置的Phase KB"""
        if not self.configured:
            return {"ok": False, "error": "未配置火山引擎知识库"}

        all_results = []
        errors = []
        limit_per_phase = max(3, top_k)
        async with httpx.AsyncClient(timeout=15) as client:
            for phase_id, kb in KB_PHASES.items():
                if not kb["api_key"]:
                    continue
                try:
                    body = {
                        "service_resource_id": kb["resource_id"],
                        "name": kb["collection"],
                        "query": query,
                        "limit": limit_per_phase,
                    }
                    resp = await client.post(KB_SEARCH_URL, headers={
                        "Authorization": f"Bearer {kb['api_key']}",
                        "Content-Type": "application/json",
                    }, json=body)
                    if resp.status_code == 200:
                        data = resp.json()
                        result_list = data.get("data", {}).get("result_list", [])
                        for r in result_list:
                            all_results.append({
                                "phase": phase_id,
                                "phase_name": kb["name"],
                                "content": r.get("content", ""),
                                "score": r.get("score", 0),
                                "source": r.get("source_doc", "") or r.get("chunk_title", ""),
                            })
                    else:
                        errors.append(f"{phase_id}: HTTP {resp.status_code}")
                except Exception as e:
                    errors.append(f"{phase_id}: {str(e)[:80]}")

        return {
            "ok": True,
            "results": sorted(all_results, key=lambda x: x["score"], reverse=True),
            "total": len(all_results),
            "errors": errors if errors else None,
        }
