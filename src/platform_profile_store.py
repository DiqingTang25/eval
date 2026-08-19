"""多平台 profile 库 — 按 URL 指纹归档探索结果, 不再单文件覆盖丢历史

结构:
  output/platforms/<sha1(host+path)[:8]>/
    profile.json        ← 该平台最新画像 (与全局 platform_profile.json 同步)
    schema.yaml         ← 最近一次 schema 副本 (可选)
    history.json        ← 每次探索记录 [{explored_at, phases, steps, apis, confidence, session_id}]

「用上次的平台」改为从库中读取 → 换平台探索不丢上一个平台的数据。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def platform_fingerprint(target_url: str) -> str:
    """URL 指纹: host+path 的 sha1 前 8 位 (仅用于目录名, 非安全用途)"""
    from urllib.parse import urlparse
    try:
        p = urlparse(target_url)
        key = f"{p.netloc}{p.path or '/'}"
    except Exception:
        key = target_url or "unknown"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]


def store_root(project_root: Optional[Path] = None) -> Path:
    root = project_root or Path(__file__).resolve().parent.parent
    return root / "output" / "platforms"


def platform_dir(target_url: str, project_root: Optional[Path] = None) -> Path:
    return store_root(project_root) / platform_fingerprint(target_url)


def archive_profile(profile: dict, project_root: Optional[Path] = None) -> Optional[Path]:
    """归档一次探索结果到平台库 (探索完成后调用; 失败静默, 不影响主流程)

    返回归档目录; profile 缺 target_url 时返回 None。
    """
    try:
        url = profile.get("target_url")
        if not url:
            return None
        d = platform_dir(url, project_root)
        d.mkdir(parents=True, exist_ok=True)
        # 最新画像
        (d / "profile.json").write_text(
            json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        # schema 副本 (若存在且可读)
        sp = profile.get("schema_path", "")
        if sp:
            try:
                src = Path(sp)
                if src.exists():
                    (d / "schema.yaml").write_bytes(src.read_bytes())
            except Exception:
                pass
        # 历史追加
        entry = {
            "explored_at": profile.get("explored_at") or datetime.now(timezone.utc).isoformat(),
            "session_id": profile.get("session_id", ""),
            "phases_found": profile.get("phases_found"),
            "steps_found": profile.get("steps_found"),
            "api_endpoints_found": profile.get("api_endpoints_found"),
            "overall_confidence": profile.get("overall_confidence"),
        }
        hist_path = d / "history.json"
        hist = []
        if hist_path.exists():
            try:
                hist = json.loads(hist_path.read_text(encoding="utf-8") or "[]")
                if not isinstance(hist, list):
                    hist = []
            except Exception:
                hist = []
        hist.append(entry)
        hist = hist[-20:]  # 每平台保留最近 20 次
        hist_path.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")
        return d
    except Exception:
        return None


def latest_platform_profile(project_root: Optional[Path] = None) -> Optional[dict]:
    """库中最近一次探索的平台画像 (按 explored_at 排序); 无则 None"""
    try:
        root = store_root(project_root)
        if not root.exists():
            return None
        best = None
        for prof in root.glob("*/profile.json"):
            try:
                data = json.loads(prof.read_text(encoding="utf-8"))
                if data.get("target_url"):
                    ts = data.get("explored_at", "")
                    if best is None or ts > best.get("explored_at", ""):
                        best = data
            except Exception:
                continue
        return best
    except Exception:
        return None


def list_platforms(project_root: Optional[Path] = None) -> list:
    """平台列表摘要 [{fingerprint, target_url, explored_at, phases_found, overall_confidence, history_n}]"""
    out = []
    try:
        root = store_root(project_root)
        if not root.exists():
            return out
        for d in sorted(root.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            try:
                data = json.loads((d / "profile.json").read_text(encoding="utf-8"))
                hist = []
                hp = d / "history.json"
                if hp.exists():
                    hist = json.loads(hp.read_text(encoding="utf-8") or "[]")
                out.append({
                    "fingerprint": d.name,
                    "target_url": data.get("target_url", ""),
                    "explored_at": data.get("explored_at", ""),
                    "phases_found": data.get("phases_found"),
                    "overall_confidence": data.get("overall_confidence"),
                    "history_n": len(hist) if isinstance(hist, list) else 0,
                })
            except Exception:
                continue
    except Exception:
        pass
    return out
