"""
Visual Assertion 引擎 — 离线单元测试
Agent C: 测试 VLM 响应解析、结果对象、日志系统 (不调真实 VLM API)
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.visual_assertion import (
    VisualAssertion,
    VisualAssertionResult,
    VisualAssertionLog,
    _parse_vision_response,
    _encode_image,
    _build_vision_prompt,
    get_va_log,
    get_health_summary,
)


# ═══════════════════════════════════════════════════════════════════
# Test: _parse_vision_response
# ═══════════════════════════════════════════════════════════════════

def test_parse_valid_json():
    passed, conf, reason = _parse_vision_response(
        '{"passed": true, "confidence": 0.95, "reasoning": "截图显示得分4/5"}'
    )
    assert passed is True
    assert conf == 0.95
    assert "得分" in reason


def test_parse_false():
    passed, conf, reason = _parse_vision_response(
        '{"passed": false, "confidence": 0.9, "reasoning": "页面空白"}'
    )
    assert passed is False


def test_parse_markdown_wrapped():
    """VLM 可能输出 ```json ... ``` 包裹"""
    passed, conf, reason = _parse_vision_response(
        '```json\n{"passed": true, "confidence": 0.85, "reasoning": "OK"}\n```'
    )
    assert passed is True
    assert conf == 0.85


def test_parse_extra_text():
    """VLM 可能在 JSON 前后加文字"""
    passed, conf, reason = _parse_vision_response(
        '分析结果: {"passed": true, "confidence": 0.7, "reasoning": "显示正常"} 以上是分析。'
    )
    assert passed is True


def test_parse_keyword_fallback():
    """完全无法解析时, 关键词推断"""
    passed, conf, reason = _parse_vision_response(
        "The screenshot shows the quiz result is visible and passed"
    )
    assert passed is True


def test_parse_garbage():
    passed, conf, reason = _parse_vision_response("asdfghjkl")
    assert passed is False
    assert conf <= 0.5


# ═══════════════════════════════════════════════════════════════════
# Test: _build_vision_prompt
# ═══════════════════════════════════════════════════════════════════

def test_build_prompt_basic():
    prompt = _build_vision_prompt("登录成功?", "")
    assert "登录成功?" in prompt
    assert "passed" in prompt.lower()
    assert "confidence" in prompt.lower()


def test_build_prompt_with_context():
    prompt = _build_vision_prompt("分数显示?", "Phase 2 Day 1 Quiz")
    assert "Phase 2 Day 1 Quiz" in prompt
    assert "分数显示?" in prompt


# ═══════════════════════════════════════════════════════════════════
# Test: _encode_image
# ═══════════════════════════════════════════════════════════════════

def test_encode_image():
    """创建一个小 PNG 并编码"""
    # 最小合法 PNG (1x1 pixel red)
    min_png = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
        b'\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(min_png)
        tmp_path = f.name

    try:
        encoded = _encode_image(tmp_path)
        assert len(encoded) > 0
        # 验证是可解码的 base64
        import base64
        decoded = base64.b64decode(encoded)
        assert decoded[:4] == b'\x89PNG'
    finally:
        Path(tmp_path).unlink()


# ═══════════════════════════════════════════════════════════════════
# Test: VisualAssertionResult
# ═══════════════════════════════════════════════════════════════════

def test_result_passed():
    r = VisualAssertionResult(
        intent="登录成功提示是否可见?",
        screenshot="path/to/ss.png",
        passed=True,
        confidence=0.92,
        reasoning="截图显示用户名'student001'",
        model="gpt-4o",
    )
    assert r.passed is True
    assert r.model == "gpt-4o"
    assert r.skipped is False


def test_result_skipped():
    r = VisualAssertionResult(
        intent="测验分数?",
        screenshot="path/to/ss.png",
        error="无可用VLM",
        skipped=True,
    )
    assert r.skipped is True
    assert r.passed is False


# ═══════════════════════════════════════════════════════════════════
# Test: VisualAssertion without VLM (graceful degradation)
# ═══════════════════════════════════════════════════════════════════

def test_assert_without_vlm():
    """没有 VLM API key 时, 应该优雅跳过而非报错"""
    va = VisualAssertion()
    # 使用不存在的截图路径 → 会先触发"截图不存在"跳过
    result = va.assert_that("/nonexistent/path.png", "测试意图")
    assert result.skipped is True
    assert "不存在" in result.error


def test_assert_batch_empty():
    va = VisualAssertion()
    results = va.assert_batch("/nonexistent/path.png", [])
    assert results == []


# ═══════════════════════════════════════════════════════════════════
# Test: VisualAssertionLog
# ═══════════════════════════════════════════════════════════════════

def test_log_summary():
    log = VisualAssertionLog()
    log.results = [
        VisualAssertionResult("i1", "s1", passed=True, confidence=0.9, model="gpt-4o"),
        VisualAssertionResult("i2", "s2", passed=True, confidence=0.8, model="gpt-4o"),
        VisualAssertionResult("i3", "s3", passed=False, confidence=0.3, model="gpt-4o"),
        VisualAssertionResult("i4", "s4", skipped=True, error="no VLM"),
    ]
    s = log.summary()
    assert s["total"] == 4
    assert s["passed"] == 2
    assert s["failed"] == 1
    assert s["skipped"] == 1
    assert s["pass_rate"] == round(2/3, 3)  # 2 passed / (4 total - 1 skipped)


def test_log_empty():
    log = VisualAssertionLog()
    log.results = []
    s = log.summary()
    assert s["total"] == 0


# ═══════════════════════════════════════════════════════════════════
# Test: get_health_summary
# ═══════════════════════════════════════════════════════════════════

def test_health_summary():
    summary = get_health_summary()
    assert summary["component"] == "visual_assertion"
    assert "vlm_available" in summary
    assert "pass_rate" in summary


# ═══════════════════════════════════════════════════════════════════
# Test: assert_step
# ═══════════════════════════════════════════════════════════════════

def test_assert_step():
    va = VisualAssertion()
    result = va.assert_step(
        screenshot_path="/nonexistent/step.png",
        step_description="Step 3: 学习传感器连接",
        expected_visual_state="显示本步已完成",
    )
    assert result.skipped is True  # 截图不存在
    assert "Step 3" in result.intent


# ═══════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    passed = 0
    failed = 0
    tests = [
        test_parse_valid_json,
        test_parse_false,
        test_parse_markdown_wrapped,
        test_parse_extra_text,
        test_parse_keyword_fallback,
        test_parse_garbage,
        test_build_prompt_basic,
        test_build_prompt_with_context,
        test_encode_image,
        test_result_passed,
        test_result_skipped,
        test_assert_without_vlm,
        test_assert_batch_empty,
        test_log_summary,
        test_log_empty,
        test_health_summary,
        test_assert_step,
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
