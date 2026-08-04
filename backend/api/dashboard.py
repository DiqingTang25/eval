"""Dashboard API 路由"""

import json
import time
from pathlib import Path

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.services.dashboard_service import DashboardService

router = APIRouter()
dashboard_service = DashboardService()


@router.get("/summary")
async def dashboard_summary(db: AsyncSession = Depends(get_db)):
    """首页摘要统计"""
    return await dashboard_service.get_summary(db)


@router.get("/trend")
async def dashboard_trend(db: AsyncSession = Depends(get_db)):
    """得分趋势数据 (独立轻量查询)"""
    trend = await dashboard_service.get_trend(db)
    return {"trend": trend}


@router.get("/distribution")
async def dashboard_distribution(db: AsyncSession = Depends(get_db)):
    """维度分布 (雷达图数据)"""
    return await dashboard_service.get_dimension_distribution(db)


@router.get("/sessions")
async def list_sessions(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """测试会话列表"""
    return await dashboard_service.get_sessions(db, page, page_size)


@router.get("/interaction")
async def interaction_health(quick: bool = True):
    """平台交互健康度。?quick=true 返回缓存/快速探活(毫秒级), ?quick=false 实时运行(分钟级)"""
    return await dashboard_service.get_interaction_health(quick=quick)


@router.post("/interaction/refresh")
async def refresh_interaction_health():
    """手动触发全量健康度刷新 (同步, 2-3分钟)"""
    return await dashboard_service.get_interaction_health(quick=False)


@router.get("/technical-metrics")
async def technical_metrics():
    """技术测评指标: API延迟/QPS/错误率(来自最近一次缓存的健康度数据)"""
    cached = dashboard_service._read_health_cache()
    if cached and not cached.get("probe_mode"):
        features = cached.get("features", {})
        metrics = {
            "cached": True,
            "cache_age_seconds": cached.get("cache_age_seconds", 0),
            "health_score": cached.get("summary", {}).get("health_score", 0),
            "total_features": len(features),
            "by_status": {"working": 0, "degraded": 0, "broken": 0},
            "by_priority": {"P0": [], "P1": [], "P2": []},
            "last_full_check": cached.get("_ts", 0),
        }
        for key, feat in features.items():
            status = feat.get("status", "unknown")
            if status in metrics["by_status"]:
                metrics["by_status"][status] += 1
            pri = feat.get("priority", "P2")
            metrics["by_priority"].setdefault(pri, [])
            metrics["by_priority"][pri].append({
                "key": key, "name": feat.get("name", key),
                "status": status, "detail": feat.get("detail", ""),
            })
        # 排序P0在前
        for pri in metrics["by_priority"]:
            metrics["by_priority"][pri].sort(key=lambda x: {"working": 0, "degraded": 1, "broken": 2}.get(x["status"], 3))
        return metrics
    # 无缓存 → 返回快速探活
    probe = dashboard_service._quick_probe()
    if probe:
        return {"cached": False, "probe": True, "health_score": probe.get("summary", {}).get("health_score", 0)}
    return {"cached": False, "error": "无法连接被测平台"}


@router.get("/metrics-trend")
async def metrics_trend(hours: int = 24):
    """技术指标趋势: 延迟/QPS/错误率/健康度 随时间变化"""
    from backend.services.metrics_history import get_trend
    return {"trend": get_trend(hours=hours)}


@router.post("/metrics-trend/record")
async def record_metrics():
    """手动触发一次指标记录 (通常由后台线程自动调用)"""
    cached = dashboard_service._read_health_cache()
    if cached:
        from backend.services.metrics_history import record_snapshot
        snapshot = record_snapshot(cached)
        return {"ok": True, "snapshot": snapshot}
    return {"ok": False, "error": "无缓存数据"}


@router.get("/heartbeat")
async def heartbeat():
    """最新心跳状态 (5分钟粒度)"""
    from pathlib import Path
    hb_file = Path(__file__).parent.parent.parent / "data" / "heartbeat_log.json"
    if hb_file.exists():
        try:
            return json.loads(hb_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"ts": 0, "status": "no_data"}


@router.get("/quiz-summary")
async def quiz_summary():
    """Quiz各Phase摘要"""
    return await dashboard_service.get_quiz_summary()
