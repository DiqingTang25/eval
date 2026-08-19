"""平台数据适配层 — 从 platform_profile.json + schema YAML 生成评测配置

覆盖优先级 (低 → 高):
  硬编码默认 < 环境变量 < 配置数据 (profile/schema) < 显式构造参数

评测器 (browser_evaluator / multi_agent) 通过本模块获得:
  - base_url / username / password (探索时保存的凭证)
  - phases: [{name, days, titles}] (从 schema structure.modules 推导)
  - login_url / api_prefix / platform_name

无 profile/schema 时返回空配置 — 调用方回退到原有默认行为, 零破坏。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None


@dataclass
class EvalConfig:
    base_url: str = ""
    username: str = ""
    password: str = ""
    login_url: str = ""
    api_prefix: str = ""
    platform_name: str = ""
    phases: list = field(default_factory=list)   # [{name, days, titles}]
    schema_path: str = ""
    schema_valid: bool = False

    @property
    def has_phases(self) -> bool:
        return bool(self.phases)


def _load_schema(profile: dict, project_root: Path) -> Optional[dict]:
    """从 profile 的 schema_path 读取 YAML; 失败则尝试常见位置"""
    candidates = []
    sp = profile.get("schema_path", "")
    if sp:
        candidates.append(Path(sp))
    candidates.append(project_root / "output" / "full_exploration" / "platform_schema_v2.yaml")
    candidates.append(project_root / "output" / "platform_schema.yaml")
    for c in candidates:
        try:
            if c.exists():
                if yaml is None:
                    raise ImportError("pyyaml")
                data = yaml.safe_load(c.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            continue
    return None


def _phases_from_schema(schema: dict) -> list:
    """schema structure → 评测阶段规格 [{name, days, titles}]

    兼容两种 schema 格式:
      v2 (direct_exploration): structure.modules[].courses[].title
      v1 (explorer 流水线):   structure.phases[] + structure.lessons[] (phase_id 关联)
    """
    out = []
    st = schema.get("structure") or {}
    if not isinstance(st, dict):
        return out

    # v2: modules → courses
    modules = st.get("modules")
    if isinstance(modules, dict) and modules:
        for mid, m in modules.items():
            if not isinstance(m, dict):
                continue
            courses = m.get("courses") or []
            titles = [c.get("title", "") for c in courses if isinstance(c, dict)]
            out.append({
                "name": m.get("name") or mid,
                "days": len(courses),
                "titles": [t for t in titles if t],
            })
        return out

    # v1: phases + lessons
    phases = st.get("phases")
    if isinstance(phases, list) and phases:
        lessons = st.get("lessons") or []
        titles_by_phase = {}
        days_by_phase = {}
        for l in lessons:
            if not isinstance(l, dict):
                continue
            pid = l.get("phase_id") or ""
            titles_by_phase.setdefault(pid, []).append(l.get("name", ""))
            days_by_phase[pid] = days_by_phase.get(pid, 0) + 1
        for ph in phases:
            if not isinstance(ph, dict):
                continue
            pid = ph.get("id") or ""
            out.append({
                "name": ph.get("name") or pid,
                "days": int(ph.get("lesson_count") or days_by_phase.get(pid, 0) or 0),
                "titles": [t for t in titles_by_phase.get(pid, []) if t],
            })
    return out


def load_eval_config(project_root: Optional[Path] = None) -> EvalConfig:
    """加载评测配置 (profile + schema + env 合并)"""
    root = project_root or Path(__file__).resolve().parent.parent
    cfg = EvalConfig()

    # ── profile (探索时保存的数据, 优先级高于 env) ──
    profile = {}
    try:
        from src.profile_paths import load_profile
        profile = load_profile() or {}
    except Exception:
        pass

    cfg.base_url = profile.get("target_url", "")
    creds = profile.get("credentials") or {}
    cfg.username = creds.get("username", "")
    cfg.password = creds.get("password", "")
    auth = profile.get("auth") or {}
    cfg.login_url = auth.get("login_url", "")
    cfg.api_prefix = profile.get("api_prefix", "")

    # ── schema → phases / platform_name ──
    schema = _load_schema(profile, root) if profile else None
    if schema:
        cfg.platform_name = (schema.get("platform") or {}).get("name", "")
        cfg.schema_path = profile.get("schema_path", "")
        cfg.schema_valid = True
        cfg.phases = _phases_from_schema(schema)

    # ── 环境变量覆盖 (部署侧配置) ──
    if os.getenv("EVAL_BASE_URL"):
        cfg.base_url = os.environ["EVAL_BASE_URL"]
    if os.getenv("PLATFORM_USERNAME"):
        cfg.username = os.environ["PLATFORM_USERNAME"]
    if os.getenv("PLATFORM_PASSWORD"):
        cfg.password = os.environ["PLATFORM_PASSWORD"]
    if os.getenv("EVAL_LOGIN_URL"):
        cfg.login_url = os.environ["EVAL_LOGIN_URL"]

    return cfg
