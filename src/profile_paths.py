"""platform_profile.json 全局路径解析 — 统一所有读取方

历史遗留两处写入位置:
  1. output/platform_probe/platform_profile.json  (流水线 explorer.py 写入, 最新)
  2. output/platform_profile.json                 (早期直接探索流程写入)

所有读取方统一走 resolve_profile_path(), 优先流水线位置、回退旧位置。
(Phase D 的多平台 profile 库会取代本模块的候选链)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def project_root() -> Path:
    """项目根目录 — src/ 的父目录 (本地 ~/agent_eval 与云端 /opt/agent_eval 布局一致)"""
    return Path(__file__).resolve().parent.parent


def profile_candidates() -> list[Path]:
    root = project_root()
    return [
        root / "output" / "platform_probe" / "platform_profile.json",  # 流水线写入 (最新)
        root / "output" / "platform_profile.json",                     # 历史/直接探索写入
    ]


def resolve_profile_path() -> Optional[Path]:
    """返回第一个存在的全局 platform_profile.json 路径; 都没有则 None"""
    for cand in profile_candidates():
        if cand.exists():
            return cand
    return None


def load_profile() -> Optional[dict]:
    """读取全局 platform_profile.json 内容; 无文件或解析失败返回 None"""
    import json

    p = resolve_profile_path()
    if p is None:
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
