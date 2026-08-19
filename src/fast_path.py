"""成功路径固化 — Skyvern Route Memorization 简化版

走通一次的导航路径 (点击了什么文字) 保存下来, 下次先重放再 AI 导航:
  data/fast_path.json = {
    "<url指纹>": {
      "1": {"phase_text": "Phase 01", "days": {"1": {"day_text": "Day 1"}}}
    }
  }

写失败静默; 重放失败自动回退原导航流程。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

_lock = threading.Lock()


def fast_path_file(project_root: Optional[Path] = None) -> Path:
    root = project_root or Path(__file__).resolve().parent.parent
    return root / "data" / "fast_path.json"


def _load(project_root: Optional[Path] = None) -> dict:
    p = fast_path_file(project_root)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8") or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict, project_root: Optional[Path] = None) -> None:
    try:
        p = fast_path_file(project_root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def record_navigation(
    target_url: str, phase_num: int, day_num: int,
    phase_text: str, day_text: str,
    project_root: Optional[Path] = None,
) -> None:
    """记录一次成功的导航路径"""
    if not target_url:
        return
    try:
        from src.platform_profile_store import platform_fingerprint
        fp = platform_fingerprint(target_url)
        data = _load(project_root)
        plat = data.setdefault(fp, {})
        ph = plat.setdefault(str(phase_num), {})
        ph["phase_text"] = phase_text
        days = ph.setdefault("days", {})
        days[str(day_num)] = {"day_text": day_text}
        _save(data, project_root)
    except Exception:
        pass


def get_navigation(
    target_url: str, phase_num: int, day_num: int,
    project_root: Optional[Path] = None,
) -> Optional[dict]:
    """取回该平台该阶段的固化路径 (未走过则 None)"""
    try:
        from src.platform_profile_store import platform_fingerprint
        fp = platform_fingerprint(target_url)
        data = _load(project_root)
        ph = data.get(fp, {}).get(str(phase_num), {})
        day = ph.get("days", {}).get(str(day_num))
        if not (ph.get("phase_text") and day and day.get("day_text")):
            return None
        return {
            "phase_text": ph["phase_text"],
            "day_text": day["day_text"],
        }
    except Exception:
        return None
