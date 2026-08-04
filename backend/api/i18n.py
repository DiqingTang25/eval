"""i18n Dictionary API — 自适应双语系统核心

设计原则:
  1. 前端只管写 t('key'), 后端自动补齐字典
  2. 零手工同步 — 启动扫描 + 运行时自动注册 + 文件监控
  3. 字典文件 (frontend/locales/*.json) 是唯一真相源

Endpoints:
  GET  /api/i18n/dict?lang=zh|en    — 返回完整字典
  GET  /api/i18n/version            — 版本检查 (缓存失效)
  POST /api/i18n/auto-register      — 🔥 前端自动上报缺失key, 后端即时补齐
  POST /api/i18n/merge              — 增量合并 (给扫描脚本用)
  GET  /api/i18n/missing            — zh/en 键对齐检查
  POST /api/i18n/rescan             — 手动触发全量扫描
"""

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["i18n"])

PROJECT_ROOT = Path(__file__).parent.parent.parent
LOCALES_DIR = PROJECT_ROOT / "frontend" / "locales"
FRONTEND_DIR = PROJECT_ROOT / "frontend"


class DictMergeRequest(BaseModel):
    lang: str  # "zh" | "en"
    entries: dict  # {key: value, ...}


class AutoRegisterRequest(BaseModel):
    keys: list  # ["key1", "key2", ...]


def _load_dict(lang: str) -> dict:
    path = LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(500, f"Failed to read dict file: {e}")


def _save_dict(lang: str, data: dict):
    path = LOCALES_DIR / f"{lang}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_version() -> str:
    zh_path = LOCALES_DIR / "zh.json"
    if zh_path.exists():
        try:
            stat = zh_path.stat()
            raw = f"{stat.st_mtime:.6f}:{stat.st_size}"
            return hashlib.md5(raw.encode()).hexdigest()[:12]
        except OSError:
            pass
    return "0"


def _key_to_text(key: str) -> str:
    """将 snake_case key 转为可读英文: 'nav_home' → 'Nav Home'"""
    return key.replace("_", " ").strip().title()


# ── 前端代码扫描 ────────────────────────────────

# 提取 t('key'), t("key") 调用
_RE_T_CALL = re.compile(r"\bt\s*\(\s*['\"]([a-z_][a-z0-9_]*)['\"]")
# 提取 data-i18n="key"
_RE_DATA_I18N = re.compile(r'data-i18n\s*=\s*"([^"]+)"')
# 提取 data-i18n-ph="key"
_RE_DATA_I18N_PH = re.compile(r'data-i18n-ph\s*=\s*"([^"]+)"')
# 动态键前缀 (t('dim_' + k) 等), 不当作缺失键
_DYNAMIC_PREFIXES = {"dim_", "dim_short_", "intent_", "status_"}


def scan_frontend_keys() -> set:
    """扫描所有前端文件, 提取所有 i18n 键"""
    keys = set()
    for pattern in ["**/*.js", "**/*.html"]:
        for f in sorted(FRONTEND_DIR.glob(pattern)):
            try:
                content = f.read_text(encoding="utf-8")
            except Exception:
                continue
            keys.update(_RE_T_CALL.findall(content))
            if f.suffix == ".html":
                keys.update(_RE_DATA_I18N.findall(content))
                keys.update(_RE_DATA_I18N_PH.findall(content))
    # 过滤动态键前缀
    return {k for k in keys if k not in _DYNAMIC_PREFIXES}


def auto_register_keys(keys: list) -> dict:
    """将缺失的键自动添加到 zh.json 和 en.json

    策略:
      - zh: 用 key 本身作为占位符 (开发者写的 t('key') 通常 key 本身就描述了内容)
      - en: 用 _key_to_text(key) 生成可读英文占位符
      - 已存在的键不覆盖
    """
    zh = _load_dict("zh")
    en = _load_dict("en")

    added_zh = []
    added_en = []

    for key in keys:
        if not key or key in _DYNAMIC_PREFIXES:
            continue
        if key not in zh:
            zh[key] = key  # 中文占位符: key 名本身就是提示
            added_zh.append(key)
        if key not in en:
            en[key] = _key_to_text(key)  # 英文占位符: 自动生成
            added_en.append(key)

    if added_zh:
        _save_dict("zh", zh)
    if added_en:
        _save_dict("en", en)

    if added_zh:
        logger.info(f"[i18n] Auto-registered {len(added_zh)} new keys: {added_zh[:10]}...")

    return {
        "ok": True,
        "added_zh": added_zh,
        "added_en": added_en,
        "total_zh": len(zh),
        "total_en": len(en),
    }


def startup_scan():
    """启动时全量扫描 — 确保所有代码中的 t() 键都在字典中"""
    try:
        code_keys = scan_frontend_keys()
        zh = _load_dict("zh")
        missing = sorted(code_keys - set(zh.keys()))
        if missing:
            result = auto_register_keys(missing)
            logger.info(
                f"[i18n] Startup scan: found {len(code_keys)} keys in code, "
                f"auto-registered {len(result['added_zh'])} missing keys"
            )
        else:
            logger.info(f"[i18n] Startup scan: all {len(code_keys)} keys present in dictionary")
    except Exception as e:
        logger.warning(f"[i18n] Startup scan failed (non-fatal): {e}")


# ═══════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════


@router.get("/dict")
async def get_dict(lang: str = "zh"):
    """返回指定语言的完整字典"""
    if lang not in ("zh", "en"):
        raise HTTPException(400, "lang must be zh or en")
    return {
        "lang": lang,
        "version": _get_version(),
        "dict": _load_dict(lang),
    }


@router.get("/version")
async def get_version():
    """快速版本检查 — 用于前端 localStorage 缓存失效"""
    return {"version": _get_version()}


@router.post("/auto-register")
async def auto_register(body: AutoRegisterRequest):
    """🔥 前端自动上报缺失键 — 后端即时补齐到 JSON 文件

    前端 t() 函数检测到字典中没有的 key 时,
    自动调用此端点。后端立即写入 JSON 文件,
    下次 /api/i18n/dict 请求即包含新键。

    这是实现「写活」的核心机制:
      开发者写 t('new_key') → 前端检测缺失 → POST 到此端点
      → 后端写入 JSON → 下次请求即生效
    """
    return auto_register_keys(body.keys)


@router.post("/rescan")
async def rescan():
    """手动触发全量扫描 — 扫描所有前端代码, 补齐缺失键"""
    code_keys = scan_frontend_keys()
    zh = _load_dict("zh")
    missing = sorted(code_keys - set(zh.keys()))
    result = auto_register_keys(missing)
    return {
        **result,
        "scanned_keys": len(code_keys),
        "missing_before": len(missing),
    }


@router.post("/merge")
async def merge_dict(body: DictMergeRequest):
    """增量合并字典条目"""
    if body.lang not in ("zh", "en"):
        raise HTTPException(400, "lang must be zh or en")

    current = _load_dict(body.lang)
    added = 0
    for k, v in body.entries.items():
        if k not in current or current[k] != v:
            current[k] = v
            added += 1

    _save_dict(body.lang, current)
    return {"ok": True, "merged": added, "total": len(current)}


@router.get("/missing")
async def get_missing_keys():
    """对比 zh 和 en 字典，返回英文缺失的键"""
    zh = _load_dict("zh")
    en = _load_dict("en")
    missing = sorted(k for k in zh if k not in en)
    return {"missing": missing, "count": len(missing)}


@router.get("/status")
async def get_status():
    """返回 i18n 系统状态"""
    zh = _load_dict("zh")
    en = _load_dict("en")
    code_keys = scan_frontend_keys()
    missing_in_dict = sorted(code_keys - set(zh.keys()))
    missing_in_en = sorted(set(zh.keys()) - set(en.keys()))
    return {
        "version": _get_version(),
        "zh_keys": len(zh),
        "en_keys": len(en),
        "code_keys_found": len(code_keys),
        "missing_from_dict": len(missing_in_dict),
        "missing_en_translations": len(missing_in_en),
        "coverage_pct": round(
            (len(code_keys - set(missing_in_dict)) / max(len(code_keys), 1)) * 100, 1
        ),
    }
