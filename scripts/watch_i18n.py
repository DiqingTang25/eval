"""watch_i18n.py — i18n real-time file watcher + pre-deploy safety check

Core features:
  1. --watch   : Monitor frontend/ directory, auto-scan on file changes
  2. --check   : Pre-deploy gate — blocks deployment if untranslated keys exist
  3. --once    : One-shot scan and auto-fix (for deploy scripts)

Usage:
  python scripts/watch_i18n.py --watch    # Dev mode, runs in background
  python scripts/watch_i18n.py --check    # CI/pre-deploy check
  python scripts/watch_i18n.py --once     # Manual fix all missing keys
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# Force UTF-8 output on Windows
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

PROJECT_ROOT = Path(__file__).parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
LOCALES_DIR = FRONTEND_DIR / "locales"

# ── 扫描引擎 (与 backend/api/i18n.py 保持一致) ──
_RE_T_CALL = re.compile(r"\bt\s*\(\s*['\"]([a-z_][a-z0-9_]*)['\"]")
_RE_DATA_I18N = re.compile(r'data-i18n\s*=\s*"([^"]+)"')
_RE_DATA_I18N_PH = re.compile(r'data-i18n-ph\s*=\s*"([^"]+)"')
_DYNAMIC_PREFIXES = {"dim_", "dim_short_", "intent_", "status_"}


def scan_keys():
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
    return {k for k in keys if k not in _DYNAMIC_PREFIXES}


def load_dict(lang):
    path = LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_dict(lang, data):
    path = LOCALES_DIR / f"{lang}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def key_to_text(key):
    return key.replace("_", " ").strip().title()


def auto_fix():
    """Scan and auto-fix missing keys"""
    code_keys = scan_keys()
    zh = load_dict("zh")
    en = load_dict("en")

    missing = sorted(code_keys - set(zh.keys()))
    if not missing:
        return {"fixed": 0, "keys": []}

    for key in missing:
        zh[key] = key
        en[key] = key_to_text(key)

    save_dict("zh", zh)
    save_dict("en", en)

    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [OK] Auto-fixed {len(missing)} new keys:")
    for k in missing[:15]:
        print(f"    + {k} -> zh:\"{k}\"  en:\"{key_to_text(k)}\"")
    if len(missing) > 15:
        print(f"    ... and {len(missing) - 15} more")

    return {"fixed": len(missing), "keys": missing}


def check_safety():
    """Pre-deploy safety gate: exit 1 if untranslated keys exist"""
    code_keys = scan_keys()
    zh = load_dict("zh")
    en = load_dict("en")

    missing = sorted(code_keys - set(zh.keys()))
    missing_en = sorted(set(zh.keys()) - set(en.keys()))

    errors = []
    if missing:
        errors.append(f"[FAIL] {len(missing)} keys used in code but missing from dict: {missing[:10]}")
    if missing_en:
        errors.append(f"[WARN] {len(missing_en)} keys in zh but missing from en: {missing_en[:10]}")

    coverage = round((len(code_keys - set(missing)) / max(len(code_keys), 1)) * 100, 1)

    if errors:
        print("=" * 55)
        print("  [BLOCKED] i18n safety check FAILED — deployment blocked")
        print("=" * 55)
        for e in errors:
            print(e)
        print()
        print(f"  Coverage: {coverage}%  |  Code keys: {len(code_keys)}  |  Dict keys: {len(zh)}")
        print()
        print("  Run: python scripts/watch_i18n.py --once    to auto-fix")
        print("=" * 55)
        sys.exit(1)

    print(f"[OK] i18n safety check passed — coverage {coverage}% ({len(code_keys)} keys)")
    return True


def watch():
    """Monitor frontend/ directory, auto-scan on file changes"""
    print("[i18n] File watcher started — monitoring frontend/")
    print("       Auto-scan triggers on JS/HTML file changes")
    print("       Ctrl+C to stop\n")

    # Record initial state
    last_scan = time.time()
    auto_fix()  # Initial full scan

    try:
        while True:
            # Check every 3 seconds
            time.sleep(3)

            # Check for file changes under frontend/
            changed = False
            for pattern in ["**/*.js", "**/*.html"]:
                for f in FRONTEND_DIR.glob(pattern):
                    try:
                        mtime = f.stat().st_mtime
                        if mtime > last_scan:
                            changed = True
                            break
                    except Exception:
                        pass
                if changed:
                    break

            last_scan = time.time()

            if changed:
                result = auto_fix()
                if result["fixed"] > 0:
                    ts = time.strftime("%H:%M:%S")
                    print(f"[{ts}] File change detected, auto-processed")

    except KeyboardInterrupt:
        print("\n[i18n] Watcher stopped")


def main():
    parser = argparse.ArgumentParser(description="i18n file watcher & safety check")
    parser.add_argument("--watch", action="store_true", help="Watch mode: auto-fix on file changes")
    parser.add_argument("--check", action="store_true", help="Check mode: pre-deploy safety gate")
    parser.add_argument("--once", action="store_true", help="One-shot: scan and auto-fix")
    args = parser.parse_args()

    if args.watch:
        watch()
    elif args.check:
        check_safety()
    elif args.once:
        auto_fix()
    else:
        # Default: report mode
        code_keys = scan_keys()
        zh = load_dict("zh")
        en = load_dict("en")
        missing = sorted(code_keys - set(zh.keys()))
        missing_en = sorted(set(zh.keys()) - set(en.keys()))

        print("=" * 50)
        print("  i18n Scan Report")
        print("=" * 50)
        print(f"  Keys found in code:   {len(code_keys)}")
        print(f"  Keys in zh.json:      {len(zh)}")
        print(f"  Keys in en.json:      {len(en)}")
        print(f"  Missing from dict:    {len(missing)}")
        print(f"  Missing EN:           {len(missing_en)}")
        if missing:
            print(f"\n  Missing keys: {missing[:20]}")
        print("=" * 50)
        print("\n  Use --once to auto-fix, --watch to monitor, --check for deploy gate")


if __name__ == "__main__":
    main()
