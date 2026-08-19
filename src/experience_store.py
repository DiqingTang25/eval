"""经验库 — 失败反思记忆 (rSSO: 技能库+失败反思组合中最有效的部分)

原则:
  - 只记「失败且经干预/修复」的条目, 不记平淡成功 (防噪声)
  - 下次同类任务先检索历史经验注入 prompt → 用得越多成功率越高
  - 追加式 JSONL, 写失败静默, 绝不阻塞主流程

结构 (data/experience.jsonl, 每行一条):
  {"ts", "task_type", "platform", "trigger", "action", "outcome", "exit_type", "note"}
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_lock = threading.Lock()

TASK_EXPLORATION = "exploration"
TASK_EVALUATION = "evaluation"

EXIT_COMPLETED = "completed"
EXIT_COMPLETED_DEGRADED = "completed_with_degradation"
EXIT_NEEDS_HUMAN = "needs_human"
EXIT_FAILED_PERMANENT = "failed_permanently"

EXIT_TYPES = (EXIT_COMPLETED, EXIT_COMPLETED_DEGRADED, EXIT_NEEDS_HUMAN, EXIT_FAILED_PERMANENT)


def experience_path(project_root: Optional[Path] = None) -> Path:
    root = project_root or Path(__file__).resolve().parent.parent
    return root / "data" / "experience.jsonl"


def record_experience(
    task_type: str,
    trigger: str,
    action: str,
    outcome: str,
    exit_type: str,
    platform: str = "",
    note: str = "",
    project_root: Optional[Path] = None,
) -> None:
    """追加一条经验 (线程安全, 失败静默)"""
    try:
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "task_type": task_type,
            "platform": (platform or "")[:200],
            "trigger": (trigger or "")[:200],
            "action": (action or "")[:200],
            "outcome": (outcome or "")[:200],
            "exit_type": exit_type if exit_type in EXIT_TYPES else EXIT_FAILED_PERMANENT,
            "note": (note or "")[:500],
        }
        p = experience_path(project_root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            with open(p, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def retrieve_experiences(
    task_type: Optional[str] = None,
    platform: Optional[str] = None,
    keywords: Optional[list] = None,
    limit: int = 8,
    project_root: Optional[Path] = None,
) -> list:
    """关键词包含检索 — 最近优先 (简单可靠; embedding 检索为未来可选)

    platform 用指纹前缀匹配 (platform_fingerprint 前8位)。
    """
    try:
        p = experience_path(project_root)
        if not p.exists():
            return []
        rows = []
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        kw = [k.lower() for k in (keywords or []) if k]
        out = []
        for r in reversed(rows):
            if task_type and r.get("task_type") != task_type:
                continue
            if platform and r.get("platform") and platform not in r.get("platform", ""):
                # 指纹前缀匹配: 调用方传 fingerprint[:4] 也可命中
                if platform[:4] != r.get("platform", "")[:4]:
                    continue
            if kw:
                hay = " ".join(str(r.get(k, "")) for k in ("trigger", "action", "note")).lower()
                if not any(k in hay for k in kw):
                    continue
            out.append(r)
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


def experiences_as_prompt_lines(experiences: list) -> str:
    """经验列表 → 注入 prompt 的要点行 (供 planner/explorer 使用)"""
    if not experiences:
        return ""
    lines = []
    for e in experiences[:6]:
        lines.append(
            f"- 曾遇到「{e.get('trigger','')}」, 采用「{e.get('action','')}」, "
            f"结果: {e.get('outcome','')}"
        )
    return "\n".join(lines)
