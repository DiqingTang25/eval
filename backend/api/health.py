"""
Health API — Agent C 模块健康端点 (4.4 P2)

Agent A 红线: 不修改 dashboard.py
→ 独立路由文件, 在 __init__.py 中注册
"""
import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(tags=["Health"])

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _read_json(path: Path) -> dict:
    """安全读取 JSON 文件, 不存在则返回 available=false"""
    if not path.exists():
        return {"available": False}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"available": False, "error": "parse failed"}


@router.get("/self-healing")
async def health_self_healing():
    """Self-Healing 统计 — 读取 data/healing_log.json"""
    data = _read_json(DATA_DIR / "healing_log.json")
    if not data.get("available", True):
        return {"available": False}
    summary = data.get("summary", {})
    events = data.get("events", [])
    return {
        "available": True,
        "total": summary.get("total", 0),
        "success_rate": summary.get("success_rate", 0),
        "by_strategy": summary.get("by_strategy", {}),
        "last_run": events[-1]["timestamp"] if events else None,
        "recent": events[-5:] if events else [],
    }


@router.get("/visual-assertion")
async def health_visual_assertion():
    """Visual Assertion 统计 — 读取 data/visual_assertion_log.json"""
    data = _read_json(DATA_DIR / "visual_assertion_log.json")
    if not data.get("available", True):
        return {"available": False}
    summary = data.get("summary", {})
    return {
        "available": True,
        "total": summary.get("total", 0),
        "passed": summary.get("passed", 0),
        "failed": summary.get("failed", 0),
        "skipped": summary.get("skipped", 0),
        "pass_rate": summary.get("pass_rate", 0),
        "models_used": summary.get("models_used", []),
    }


@router.get("/coverage")
async def health_coverage():
    """Coverage Tracker 统计 — 读取 data/coverage_report.json"""
    data = _read_json(DATA_DIR / "coverage_report.json")
    if not data.get("available", True) and not data.get("schema_available"):
        return {"available": False, "hint": "Run Explorer first"}
    overall = data.get("overall") or {}
    return {
        "available": data.get("schema_available", False),
        "coverage_pct": overall.get("coverage_pct", 0),
        "phases": overall.get("phases", "0/0"),
        "lessons": overall.get("lessons", "0 total"),
        "steps": overall.get("steps", "0 total"),
        "apis": overall.get("apis", "0 total"),
    }


@router.get("/anomaly")
async def health_anomaly():
    """Anomaly Detector 统计 — 读取 data/anomaly_report.json"""
    data = _read_json(DATA_DIR / "anomaly_report.json")
    if not data.get("available", True):
        return {"available": False}
    summary = data.get("summary", {})
    return {
        "available": True,
        "baseline_exists": data.get("baseline_exists", False),
        "changes": {
            "added": summary.get("added", 0),
            "removed": summary.get("removed", 0),
            "modified": summary.get("modified", 0),
        },
        "needs_attention": data.get("needs_attention", False),
        "recommendation": data.get("recommendation", ""),
    }
