"""
指标历史存储 — 轻量 JSON 文件，记录平台健康度趋势

存储格式 (data/metrics_history.json):
{
  "snapshots": [
    {"ts": 1234567890.0, "health_score": 0.65, "features_working": 7,
     "features_degraded": 3, "features_broken": 3, "total_features": 13,
     "avg_latency_ms": 450, "error_count": 2}
  ]
}
最多保留 168 条 (7天 × 24小时), 每30分钟一条
"""
import json
import os
import time
from pathlib import Path

HISTORY_FILE = Path(__file__).parent.parent.parent / "data" / "metrics_history.json"
MAX_SNAPSHOTS = 168  # 7天


def record_snapshot(health_data: dict):
    """记录一次健康度快照"""
    snapshot = {
        "ts": time.time(),
        "health_score": round(health_data.get("summary", {}).get("health_score", 0), 3),
    }

    # 按状态统计
    features = health_data.get("features", {})
    statuses = {"working": 0, "degraded": 0, "broken": 0}
    latencies = []
    errors = 0
    for key, feat in features.items():
        s = feat.get("status", "unknown")
        if s in statuses:
            statuses[s] += 1
        lat = feat.get("latency_ms", 0)
        if lat:
            latencies.append(lat)
        if s in ("broken", "degraded"):
            errors += 1

    snapshot["features_working"] = statuses["working"]
    snapshot["features_degraded"] = statuses["degraded"]
    snapshot["features_broken"] = statuses["broken"]
    snapshot["total_features"] = sum(statuses.values())
    snapshot["avg_latency_ms"] = round(sum(latencies) / len(latencies)) if latencies else 0
    snapshot["error_count"] = errors

    # 读写历史文件
    history = _load()
    history["snapshots"].append(snapshot)

    # 裁剪
    if len(history["snapshots"]) > MAX_SNAPSHOTS:
        history["snapshots"] = history["snapshots"][-MAX_SNAPSHOTS:]

    _save(history)
    return snapshot


def get_trend(hours: int = 24, max_points: int = 48) -> list[dict]:
    """获取趋势数据 (最近 N 小时, 最多 M 个点)"""
    history = _load()
    snapshots = history.get("snapshots", [])

    if not snapshots:
        return []

    # 时间过滤
    cutoff = time.time() - hours * 3600
    filtered = [s for s in snapshots if s.get("ts", 0) >= cutoff]

    # 降采样
    if len(filtered) > max_points:
        step = len(filtered) / max_points
        filtered = [filtered[int(i * step)] for i in range(max_points)]

    return filtered


def _load() -> dict:
    try:
        if HISTORY_FILE.exists():
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"snapshots": []}


def _save(data: dict):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        HISTORY_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
