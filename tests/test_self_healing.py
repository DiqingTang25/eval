"""
Self-Healing 定位器恢复 — 离线单元测试
Agent C: 测试四层级联回退逻辑 (不依赖 Playwright, 纯逻辑验证)
"""
import json
import sys
from pathlib import Path

# 确保 src/ 在路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.self_healing import (
    _text_similarity,
    _generate_selector_variants,
    _fuzzy_find_button,
    _structural_find_button,
    HealingEvent,
    HealingLog,
    get_healing_log,
)


# ═══════════════════════════════════════════════════════════════════
# Test: _text_similarity
# ═══════════════════════════════════════════════════════════════════

def test_text_similarity_exact():
    assert _text_similarity("Phase 01", "Phase 01") == 1.0

def test_text_similarity_whitespace():
    """空格和大小写差异应该被容忍"""
    sim = _text_similarity("Phase 01", "phase01")
    assert sim >= 0.7, f"Expected >=0.7, got {sim}"

def test_text_similarity_partial():
    """部分匹配"""
    sim = _text_similarity("Phase 01 国产AI动手派", "Phase 01")
    assert sim >= 0.5, f"Expected >=0.5, got {sim}"

def test_text_similarity_different():
    """完全不相关的文本"""
    sim = _text_similarity("Phase 01", "退出登录")
    assert sim < 0.4, f"Expected <0.4, got {sim}"

def test_text_similarity_chinese():
    """中文文本匹配"""
    sim = _text_similarity("本步已完成", "本步已完成")
    assert sim == 1.0, f"Expected 1.0, got {sim}"
    sim2 = _text_similarity("本步已完成", "已完成")
    assert sim2 >= 0.6, f"Expected >=0.6, got {sim2}"


# ═══════════════════════════════════════════════════════════════════
# Test: _generate_selector_variants
# ═══════════════════════════════════════════════════════════════════

def test_selector_variants_has_text():
    variants = _generate_selector_variants("button:has-text('Phase 01')")
    assert len(variants) >= 2, f"Expected >=2 variants, got {len(variants)}: {variants}"
    assert any('"Phase 01"' in v for v in variants), f"No double-quote variant: {variants}"

def test_selector_variants_class_attr():
    variants = _generate_selector_variants("[class*=step-title]")
    assert len(variants) >= 1, f"Expected >=1 variants, got {len(variants)}"
    assert any(".step-title" in v for v in variants), f"No dot-class variant: {variants}"

def test_selector_variants_empty():
    variants = _generate_selector_variants("div.something")
    assert variants == [], f"Expected empty, got {variants}"


# ═══════════════════════════════════════════════════════════════════
# Test: _fuzzy_find_button (offline — no Playwright page)
# ═══════════════════════════════════════════════════════════════════

def test_fuzzy_find_exact():
    """精确匹配应该返回最高置信度"""
    buttons = [
        {"text": "Phase 01 国产AI动手派", "class": "phase-btn active", "disabled": False},
        {"text": "Phase 02 人机共创", "class": "phase-btn", "disabled": False},
        {"text": "退出登录", "class": "logout-btn", "disabled": False},
    ]
    # 不传 page → _fuzzy_find_button 返回候选但不做可见性验证
    text, selector, conf = _fuzzy_find_button(None, "Phase 01", buttons)
    # 由于没有 page 验证, 会遍历候选但是验证会失败 → 这里只测试不崩溃
    # (有 page 的集成测试在浏览器环境跑)

def test_fuzzy_find_no_match():
    buttons = [
        {"text": "退出登录", "class": "logout-btn", "disabled": False},
    ]
    text, selector, conf = _fuzzy_find_button(None, "Phase 01", buttons)
    assert text is None, f"Expected None, got {text}"


# ═══════════════════════════════════════════════════════════════════
# Test: _structural_find_button (offline)
# ═══════════════════════════════════════════════════════════════════

def test_structural_find():
    dom = {
        "url": "http://test/phase",
        "buttons": [
            {"text": "Phase 1 - 国产AI动手派", "class": "lesson-card", "disabled": False},
            {"text": "Phase 2 - 人机共创", "class": "lesson-card", "disabled": False},
            {"text": "退出登录", "class": "logout-btn", "disabled": False},
        ],
        "visibleText": "Phase 1 - 国产AI动手派 Phase 2 ...",
    }
    text, selector, conf = _structural_find_button(None, "Phase 01", dom)
    # 没有 page 验证时, 候选会被找到但验证失败 → 返回 None
    # 集成测试在有 page 的环境跑


# ═══════════════════════════════════════════════════════════════════
# Test: HealingEvent
# ═══════════════════════════════════════════════════════════════════

def test_healing_event_basic():
    event = HealingEvent(
        original_text="Phase 01",
        strategy="L1_fuzzy",
        found_text="Phase 1 - 国产AI动手派",
        found_selector="button:has-text('Phase 1')",
        confidence=0.95,
        page_url="http://test/phase",
    )
    d = event.to_dict()
    assert d["strategy"] == "L1_fuzzy"
    assert d["confidence"] == 0.95
    assert "Phase 1" in d["found_text"]


def test_healing_event_failed():
    event = HealingEvent(
        original_text="不存在的按钮",
        strategy="failed",
        page_url="http://test/phase",
    )
    d = event.to_dict()
    assert d["strategy"] == "failed"
    assert d["found_text"] == ""


# ═══════════════════════════════════════════════════════════════════
# Test: HealingLog
# ═══════════════════════════════════════════════════════════════════

def test_healing_log_summary():
    log = HealingLog()
    # 添加一些测试事件
    log.events = [
        HealingEvent("btn1", "L1_fuzzy", "btn1_alt", "sel1", 0.9),
        HealingEvent("btn2", "L1_fuzzy", "btn2_alt", "sel2", 0.8),
        HealingEvent("btn3", "L2_dom", "btn3_alt", "sel3", 0.6),
        HealingEvent("btn4", "failed", "", "", 0.0),
    ]
    summary = log.summary()
    assert summary["total"] == 4
    assert summary["by_strategy"]["L1_fuzzy"] == 2
    assert summary["by_strategy"]["L2_dom"] == 1
    assert summary["by_strategy"]["failed"] == 1
    assert summary["success_rate"] == 0.75


def test_healing_log_empty():
    log = HealingLog()
    log.events = []
    summary = log.summary()
    assert summary["total"] == 0
    assert summary["success_rate"] == 0.0


# ═══════════════════════════════════════════════════════════════════
# Test: get_health_summary
# ═══════════════════════════════════════════════════════════════════

def test_get_health_summary():
    from src.self_healing import get_health_summary
    summary = get_health_summary()
    assert "component" in summary
    assert summary["component"] == "self_healing"
    assert "success_rate" in summary
    assert "strategies_used" in summary


# ═══════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    passed = 0
    failed = 0
    tests = [
        test_text_similarity_exact,
        test_text_similarity_whitespace,
        test_text_similarity_partial,
        test_text_similarity_different,
        test_text_similarity_chinese,
        test_selector_variants_has_text,
        test_selector_variants_class_attr,
        test_selector_variants_empty,
        test_fuzzy_find_exact,
        test_fuzzy_find_no_match,
        test_structural_find,
        test_healing_event_basic,
        test_healing_event_failed,
        test_healing_log_summary,
        test_healing_log_empty,
        test_get_health_summary,
    ]
    for test in tests:
        try:
            test()
            passed += 1
            print(f"  PASS {test.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL {test.__name__}: {e}")

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    if failed > 0:
        sys.exit(1)
