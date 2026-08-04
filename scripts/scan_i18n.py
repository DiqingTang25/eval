"""scan_i18n.py — 前端i18n覆盖率扫描工具

扫描前端代码中的 i18n 键使用情况和硬编码中文，与字典对比生成报告。

用法:
    python scripts/scan_i18n.py              # 报告模式 — 打印覆盖率报告
    python scripts/scan_i18n.py --check      # CI模式 — 有缺失键时exit 1
    python scripts/scan_i18n.py --fix        # 自动修复 — 将缺失键添加到JSON文件
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
LOCALES_DIR = FRONTEND_DIR / "locales"

# ── 正则模式 ──
# 提取 t('literal_key') 调用 — 只匹配字面量字符串键
RE_T_CALL = re.compile(r"\bt\s*\(\s*['\"]([a-z_][a-z0-9_]*)['\"]")
RE_DATA_I18N = re.compile(r'data-i18n\s*=\s*"([^"]+)"')
RE_DATA_I18N_PH = re.compile(r'data-i18n-ph\s*=\s*"([^"]+)"')
# 过滤掉常见的动态键前缀 (t('dim_' + k), t('intent_' + k) 等)
DYNAMIC_KEY_PREFIXES = {'dim_', 'dim_short_', 'intent_', 'status_'}
# 硬编码中文字符串: 引号内包含至少2个连续中文字符, 且不在注释中
RE_HARDCODED_ZH = re.compile(r"['\"]([^'\"]*[一-鿿]{2,}[^'\"]*?)['\"]")


def scan_frontend():
    """扫描所有前端JS和HTML文件, 提取i18n键和潜在硬编码中文"""
    used_keys = set()
    hardcoded_zh = []

    for pattern in ["**/*.js", "**/*.html"]:
        for f in sorted(FRONTEND_DIR.glob(pattern)):
            try:
                content = f.read_text(encoding="utf-8")
            except Exception:
                continue

            # 提取 t('key') 调用
            used_keys.update(RE_T_CALL.findall(content))

            # 提取 data-i18n 属性
            if f.suffix == ".html":
                used_keys.update(RE_DATA_I18N.findall(content))
                used_keys.update(RE_DATA_I18N_PH.findall(content))

            # 检测硬编码中文 (仅在非注释、非CSS选择器的上下文中)
            for match in RE_HARDCODED_ZH.finditer(content):
                text = match.group(1)
                # 过滤掉明显的非用户可见字符串
                if len(text) < 2:
                    continue
                if text.startswith("--") or text.startswith("var(--"):
                    continue
                if any(kw in text.lower() for kw in ["padding", "margin", "width", "height", "color"]):
                    continue
                # 过滤路径/URL
                if text.startswith("/") or text.startswith("http"):
                    continue
                hardcoded_zh.append({
                    "file": str(f.relative_to(PROJECT_ROOT)),
                    "text": text[:100],
                })

    return used_keys, hardcoded_zh


def load_dict(lang: str) -> dict:
    path = LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_coverage(verbose=True):
    """对比使用的键与字典中的键, 返回报告"""
    zh_dict = load_dict("zh")
    en_dict = load_dict("en")

    used_keys, hardcoded = scan_frontend()

    dict_keys = set(zh_dict.keys())
    # 过滤掉动态键构造产生的前缀 (如 dim_, intent_)
    filtered_used = {k for k in used_keys if k not in DYNAMIC_KEY_PREFIXES}
    missing_in_dict = sorted(filtered_used - dict_keys)
    unused_in_dict = sorted(dict_keys - filtered_used)
    coverage = round((len(filtered_used - set(missing_in_dict)) / max(len(filtered_used), 1)) * 100, 1)
    missing_in_en = sorted(set(zh_dict.keys()) - set(en_dict.keys()))

    report = {
        "used_keys": len(filtered_used),
        "dict_keys": len(dict_keys),
        "missing_in_dict": missing_in_dict,
        "unused_in_dict": unused_in_dict,
        "missing_in_en": missing_in_en,
        "hardcoded_zh_count": len(hardcoded),
        "hardcoded_zh": hardcoded[:30],
        "coverage_pct": coverage,
    }

    if verbose:
        print("=" * 60)
        print("  i18n Coverage Report")
        print("=" * 60)
        print(f"  Keys used in source:     {report['used_keys']:>5}")
        print(f"  Keys in zh.json:         {report['dict_keys']:>5}")
        print(f"  Keys in en.json:         {len(en_dict):>5}")
        print(f"  Dictionary coverage:     {report['coverage_pct']:>5.1f}%")
        print()
        print(f"  Missing from dict ({len(missing_in_dict)}):")
        for k in missing_in_dict[:15]:
            print(f"    - {k}")
        if len(missing_in_dict) > 15:
            print(f"    ... and {len(missing_in_dict) - 15} more")
        print()
        print(f"  Missing EN translations ({len(missing_in_en)}):")
        for k in missing_in_en[:10]:
            print(f"    - {k}")
        if len(missing_in_en) > 10:
            print(f"    ... and {len(missing_in_en) - 10} more")
        print()
        print(f"  Unused dict keys ({len(unused_in_dict)}):")
        for k in unused_in_dict[:10]:
            print(f"    - {k}")
        if len(unused_in_dict) > 10:
            print(f"    ... and {len(unused_in_dict) - 10} more")
        print()
        print(f"  Hardcoded Chinese strings detected: {len(hardcoded)}")
        for h in hardcoded[:10]:
            print(f"    {h['file']}: \"{h['text']}\"")
        if len(hardcoded) > 10:
            print(f"    ... and {len(hardcoded) - 10} more")
        print("=" * 60)

    return report


def auto_fix_missing(missing_keys: list):
    """将缺失的键自动添加到 zh.json 和 en.json (值为占位符)"""
    zh_dict = load_dict("zh")
    en_dict = load_dict("en")

    for key in missing_keys:
        if key not in zh_dict:
            zh_dict[key] = key  # 用key本身作为中文占位符
        if key not in en_dict:
            en_dict[key] = key  # 用key本身作为英文占位符

    for lang, data in [("zh", zh_dict), ("en", en_dict)]:
        path = LOCALES_DIR / f"{lang}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ Added {len(missing_keys)} missing keys to zh.json and en.json")
    print(f"   Keys: {missing_keys}")


def main():
    mode = "report"
    if "--check" in sys.argv:
        mode = "check"
    elif "--fix" in sys.argv:
        mode = "fix"

    report = check_coverage(verbose=(mode == "report"))

    if mode == "fix" and report["missing_in_dict"]:
        auto_fix_missing(report["missing_in_dict"])
    elif mode == "fix":
        print("✅ No missing keys — nothing to fix")

    if mode == "check":
        if report["missing_in_dict"]:
            print(f"❌ {len(report['missing_in_dict'])} keys missing from dictionary!")
            sys.exit(1)
        if report["missing_in_en"]:
            print(f"⚠️  {len(report['missing_in_en'])} EN translations missing!")
            sys.exit(1)
        print(f"✅ i18n coverage: {report['coverage_pct']}% — all keys present")


if __name__ == "__main__":
    main()
