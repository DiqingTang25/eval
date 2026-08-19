"""运行指标 — 退出类型统计 (成功概率的可视化度量)

output/metrics/runs.jsonl 每行一次运行:
  {"ts", "run_type", "exit_type", "session_id", "platform", "had_human", "errors_n", "note"}

退出类型 (行业标准四分类, 来自市场调研):
  completed | completed_with_degradation | needs_human | failed_permanently
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.experience_store import (
    EXIT_COMPLETED,
    EXIT_COMPLETED_DEGRADED,
    EXIT_NEEDS_HUMAN,
    EXIT_FAILED_PERMANENT,
    EXIT_TYPES,
)

_lock = threading.Lock()


def metrics_path(project_root: Optional[Path] = None) -> Path:
    root = project_root or Path(__file__).resolve().parent.parent
    return root / "output" / "metrics" / "runs.jsonl"


def record_run(
    run_type: str,
    exit_type: str,
    session_id: str = "",
    platform: str = "",
    had_human: bool = False,
    errors_n: int = 0,
    note: str = "",
    project_root: Optional[Path] = None,
) -> None:
    """追加一条运行记录 (失败静默)"""
    try:
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_type": (run_type or "unknown")[:40],
            "exit_type": exit_type if exit_type in EXIT_TYPES else EXIT_FAILED_PERMANENT,
            "session_id": session_id or "",
            "platform": (platform or "")[:200],
            "had_human": bool(had_human),
            "errors_n": int(errors_n or 0),
            "note": (note or "")[:300],
        }
        p = metrics_path(project_root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            with open(p, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def summarize_runs(project_root: Optional[Path] = None) -> dict:
    """汇总统计: 总次数 / 各退出类型占比 / 求助率 / 成功率"""
    try:
        p = metrics_path(project_root)
        if not p.exists():
            return {"available": False}
        counts = {k: 0 for k in EXIT_TYPES}
        total = 0
        had_human = 0
        by_type = {}
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                total += 1
                et = r.get("exit_type", "")
                if et in counts:
                    counts[et] += 1
                by_type[r.get("run_type", "unknown")] = by_type.get(r.get("run_type", "unknown"), 0) + 1
                if r.get("had_human"):
                    had_human += 1
        if total == 0:
            return {"available": False}
        success = counts[EXIT_COMPLETED] + counts[EXIT_COMPLETED_DEGRADED]
        return {
            "available": True,
            "total_runs": total,
            "exit_types": counts,
            "success_rate": round(success / total, 3),
            "help_rate": round(had_human / total, 3),   # 求助率: 需要人工介入的运行占比
            "by_run_type": by_type,
        }
    except Exception:
        return {"available": False}
