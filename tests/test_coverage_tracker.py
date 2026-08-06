"""
Coverage Tracker — 单元测试 (Agent C)

重点验证:
  1. Schema 缺失时返回正确的错误报告 (零硬编码)
  2. CoverageMap 从 mock schema 正确构建树
  3. CoverageNode 计数正确
  4. Browser eval 标记逻辑
  5. 风险识别
  6. 报告生成
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.coverage_tracker import (
    CoverageNode,
    CoverageMap,
    CoverageTracker,
    compute_coverage_after_eval,
    get_health_summary,
    OUTPUT_PATH,
)


# ═══════════════════════════════════════════════════════════════════
# Helpers: Mock Data
# ═══════════════════════════════════════════════════════════════════

def _make_mock_schema_yaml() -> str:
    """构建一个最小但合法的 schema (纯 dict, 模拟 YAML 加载结果)"""
    return {
        "target_url": "http://test.example.com",
        "schema_version": "1.0",
        "confidence_scores": {"overall": 0.85},
        "auth": {"type": "form", "login_url": "/api/auth/login", "login_method": "POST"},
        "structure": {
            "hierarchy": ["phase", "lesson", "step"],
            "phases": [
                {"id": "phase_1", "name": "AI基础入门", "order": 1, "lesson_count": 3},
                {"id": "phase_2", "name": "机器人编程", "order": 2, "lesson_count": 5},
            ],
            "lessons": [
                {"id": "lesson_1_1", "phase_id": "phase_1", "name": "Day 1: Python基础", "order": 1},
                {"id": "lesson_1_2", "phase_id": "phase_1", "name": "Day 2: 神经网络", "order": 2},
                {"id": "lesson_1_3", "phase_id": "phase_1", "name": "Day 3: 项目实战", "order": 3},
                {"id": "lesson_2_1", "phase_id": "phase_2", "name": "Day 1: 传感器", "order": 1},
                {"id": "lesson_2_2", "phase_id": "phase_2", "name": "Day 2: 运动控制", "order": 2},
            ],
            "steps": [
                {"id": "step_1_1_1", "lesson_id": "lesson_1_1", "title": "安装环境", "order_index": 1},
                {"id": "step_1_1_2", "lesson_id": "lesson_1_1", "title": "Hello World", "order_index": 2},
                {"id": "step_1_1_3", "lesson_id": "lesson_1_1", "title": "变量类型", "order_index": 3},
                {"id": "step_1_2_1", "lesson_id": "lesson_1_2", "title": "感知机", "order_index": 1},
                {"id": "step_2_1_1", "lesson_id": "lesson_2_1", "title": "接线", "order_index": 1},
            ],
        },
        "apis": {
            "auth": [
                {"path": "/api/auth/login", "method": "POST", "confidence": 0.95},
            ],
            "agent": [
                {"path": "/api/agent/chat", "method": "POST", "confidence": 0.9},
                {"path": "/api/agent/history", "method": "GET", "confidence": 0.85},
            ],
            "quiz": [
                {"path": "/api/quiz/start", "method": "POST", "confidence": 0.9},
                {"path": "/api/quiz/submit", "method": "POST", "confidence": 0.9},
            ],
        },
    }


def _make_mock_browser_eval() -> dict:
    """模拟 BrowserEvaluator 产出"""
    return {
        "meta": {"platform": "http://test.example.com"},
        "phases": {
            "phase_1": {
                "days": [
                    {"index": 1, "steps_completed": 3, "total_steps": 3,
                     "agent_triggered": True, "quiz_triggered": True},
                    {"index": 2, "steps_completed": 1, "total_steps": 1,
                     "agent_triggered": False, "quiz_triggered": False},
                ]
            },
            # phase_2 完全未测试
        },
        "summary": {
            "phases_tested": [1],
            "days_completed": 2,
            "days_total": 5,
            "screenshots": 10,
        },
        "errors": [],
    }


def _write_temp_yaml(data: dict) -> str:
    """将 dict 写入临时 YAML 文件, 返回路径"""
    import yaml
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8")
    yaml.dump(data, tmp, allow_unicode=True)
    tmp.close()
    return tmp.name


def _write_temp_json(data: dict) -> str:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(data, tmp, ensure_ascii=False)
    tmp.close()
    return tmp.name


# ═══════════════════════════════════════════════════════════════════
# Test: Schema Missing → No Hardcoding
# ═══════════════════════════════════════════════════════════════════

def test_missing_schema_returns_error():
    """Schema 缺失: 必须返回错误, 不能回退到硬编码值"""
    tracker = CoverageTracker()
    report = tracker.compute(schema_path="/nonexistent/path.yaml")

    assert report["schema_available"] is False
    assert "不存在" in report.get("error", "") or "nonexistent" in report.get("error", "").lower()
    assert report["overall"] is None
    assert report["by_phase"] == []
    assert "请先运行" in report.get("hint", "")


def test_missing_schema_overall_is_none():
    """Schema 缺失时 overall 必须为 None, 不是 0 (0 意味着'全部未覆盖', 是误导)"""
    tracker = CoverageTracker()
    report = tracker.compute(schema_path="")

    assert report["overall"] is None, (
        f"expected overall=None for missing schema, got {report['overall']}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test: CoverageNode
# ═══════════════════════════════════════════════════════════════════

def test_node_count_all():
    root = CoverageNode("root", "root")
    phase = CoverageNode("phase", "p1", "Phase 1", 1)
    step1 = CoverageNode("step", "s1", "Step 1", 1)
    step2 = CoverageNode("step", "s2", "Step 2", 2)
    phase.children = [step1, step2]
    root.children = [phase]

    assert root.count_all() == 2   # 两个叶节点
    assert phase.count_all() == 2


def test_node_count_tested():
    root = CoverageNode("root", "root")
    phase = CoverageNode("phase", "p1", "Phase 1", 1)
    step1 = CoverageNode("step", "s1", "Step 1", 1, tested=True)
    step2 = CoverageNode("step", "s2", "Step 2", 2, tested=False)
    phase.children = [step1, step2]
    root.children = [phase]

    assert root.count_tested() == 1
    assert phase.count_tested() == 1


def test_node_to_dict():
    node = CoverageNode("phase", "p1", "Test Phase", 1, tested=True,
                        evidence={"test_type": "browser_eval"})
    child = CoverageNode("step", "s1", "Step 1", 1, tested=True)
    node.children = [child]

    d = node.to_dict()
    assert d["type"] == "phase"
    assert d["name"] == "Test Phase"
    assert d["tested"] is True
    assert d["evidence"]["test_type"] == "browser_eval"
    assert "coverage" in d  # 有子节点时自动计算覆盖
    assert d["coverage"]["pct"] == 100.0


# ═══════════════════════════════════════════════════════════════════
# Test: CoverageMap
# ═══════════════════════════════════════════════════════════════════

def test_coverage_map_builds_from_schema():
    """CoverageMap 从 schema 构建树, Phase 名称来自 schema"""
    schema_data = _make_mock_schema_yaml()
    schema_path = _write_temp_yaml(schema_data)

    try:
        from src.schema_adapter import SchemaAdapter
        adapter = SchemaAdapter(schema_path)
        cmap = CoverageMap(adapter)
        root = cmap.build()

        # Phase 名称来自 schema, 不是硬编码
        phase_names = [c.name for c in root.children if c.node_type == "phase"]
        assert "AI基础入门" in phase_names, f"Phase names from schema: {phase_names}"
        assert "机器人编程" in phase_names, f"Phase names from schema: {phase_names}"

        # 总数正确
        counts = cmap.get_total_counts(root)
        assert counts["phases"] == 2
        assert counts["lessons"] == 5
        assert counts["steps"] == 5
        assert counts["apis"] == 5  # 1 auth + 2 agent + 2 quiz
    finally:
        Path(schema_path).unlink(missing_ok=True)


def test_coverage_map_api_tree():
    """API 树从 schema 正确构建"""
    schema_data = _make_mock_schema_yaml()
    schema_path = _write_temp_yaml(schema_data)

    try:
        from src.schema_adapter import SchemaAdapter
        adapter = SchemaAdapter(schema_path)
        cmap = CoverageMap(adapter)
        root = cmap.build()

        # 找 API 子树
        api_root = None
        for child in root.children:
            if child.node_id == "apis":
                api_root = child
                break

        assert api_root is not None, "API root node should exist"
        cat_names = [c.name for c in api_root.children]
        assert "auth" in cat_names
        assert "agent" in cat_names
        assert "quiz" in cat_names
    finally:
        Path(schema_path).unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════
# Test: CoverageTracker
# ═══════════════════════════════════════════════════════════════════

def test_full_compute():
    """端到端: schema + eval report → coverage report"""
    schema_data = _make_mock_schema_yaml()
    eval_data = _make_mock_browser_eval()

    schema_path = _write_temp_yaml(schema_data)
    eval_path = _write_temp_json(eval_data)

    try:
        tracker = CoverageTracker()
        report = tracker.compute(
            schema_path=schema_path,
            browser_eval_path=eval_path,
        )

        # 基本结构
        assert report["schema_available"] is True
        assert report["overall"] is not None

        # Phase 1 被测试了 (2/3 days)
        phase1 = next((p for p in report["by_phase"] if p["phase_id"] == "phase_1"), None)
        assert phase1 is not None
        assert phase1["tested"] is True
        assert phase1["coverage_pct"] > 0

        # Phase 2 完全未测试
        phase2 = next((p for p in report["by_phase"] if p["phase_id"] == "phase_2"), None)
        assert phase2 is not None
        assert phase2["tested"] is False
        assert phase2["coverage_pct"] == 0.0

        # 风险区域: Phase 2 应被标记为高风险
        high_risks = [r for r in report["risk_areas"] if r["risk"] == "high"]
        assert any("phase_2" in r["area"] for r in high_risks), \
            f"Phase 2 should be high risk, got: {high_risks}"

        # 数据源
        assert len(report["data_sources"]) >= 1
        assert report["data_sources"][0]["type"] == "browser_eval"
    finally:
        Path(schema_path).unlink(missing_ok=True)
        Path(eval_path).unlink(missing_ok=True)


def test_eval_without_schema():
    """有 eval 但没有 schema → 必须返回错误"""
    eval_data = _make_mock_browser_eval()
    eval_path = _write_temp_json(eval_data)

    try:
        tracker = CoverageTracker()
        report = tracker.compute(
            schema_path="/nonexistent/schema.yaml",
            browser_eval_path=eval_path,
        )
        assert report["schema_available"] is False
    finally:
        Path(eval_path).unlink(missing_ok=True)


def test_phases_are_not_hardcoded():
    """Phase 名称必须来自 schema, 不来自硬编码"""
    # 构造一个 phase 名称与默认完全不同的 schema
    custom_schema = _make_mock_schema_yaml()
    custom_schema["structure"]["phases"] = [
        {"id": "phase_x", "name": "自定义模块X", "order": 1, "lesson_count": 2},
        {"id": "phase_y", "name": "自定义模块Y", "order": 2, "lesson_count": 1},
    ]
    custom_schema["structure"]["lessons"] = [
        {"id": "lx_1", "phase_id": "phase_x", "name": "课程X-1", "order": 1},
        {"id": "ly_1", "phase_id": "phase_y", "name": "课程Y-1", "order": 1},
    ]
    custom_schema["structure"]["steps"] = []

    schema_path = _write_temp_yaml(custom_schema)

    try:
        tracker = CoverageTracker()
        report = tracker.compute(schema_path=schema_path, browser_eval_path="")

        phase_names = [p["name"] for p in report["by_phase"]]
        assert "自定义模块X" in phase_names, f"Got: {phase_names}"
        assert "自定义模块Y" in phase_names, f"Got: {phase_names}"
        # 关键: 没有出现硬编码名称
        assert "国产AI动手派" not in phase_names, (
            f"HARDCODING DETECTED: found deprecated phase name. Got: {phase_names}"
        )
    finally:
        Path(schema_path).unlink(missing_ok=True)


def test_no_eval_report_all_zero_coverage():
    """没有测试报告 → 所有覆盖率为 0, 但不报错"""
    schema_data = _make_mock_schema_yaml()
    schema_path = _write_temp_yaml(schema_data)

    try:
        tracker = CoverageTracker()
        report = tracker.compute(
            schema_path=schema_path,
            browser_eval_path="",  # 不提供 eval
        )

        assert report["schema_available"] is True
        # 所有 Phase 覆盖率应为 0
        for p in report["by_phase"]:
            assert p["coverage_pct"] == 0.0, \
                f"Phase {p['phase_id']}: expected 0% without eval, got {p['coverage_pct']}%"
    finally:
        Path(schema_path).unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════
# Test: Risk Identification
# ═══════════════════════════════════════════════════════════════════

def test_risks_identified():
    schema_data = _make_mock_schema_yaml()
    eval_data = _make_mock_browser_eval()

    schema_path = _write_temp_yaml(schema_data)
    eval_path = _write_temp_json(eval_data)

    try:
        tracker = CoverageTracker()
        report = tracker.compute(
            schema_path=schema_path,
            browser_eval_path=eval_path,
        )

        risks = report["risk_areas"]
        assert len(risks) > 0, "Should identify untested areas as risks"

        # Phase 2 完全未测试 → high risk
        high_risks = [r for r in risks if r["risk"] == "high"]
        assert len(high_risks) >= 1
    finally:
        Path(schema_path).unlink(missing_ok=True)
        Path(eval_path).unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════
# Test: Health Summary
# ═══════════════════════════════════════════════════════════════════

def test_health_summary_no_data():
    """没有覆盖率报告文件"""
    # 临时删除 output 文件 (如果存在)
    if OUTPUT_PATH.exists():
        backup = OUTPUT_PATH.read_text(encoding="utf-8")
        OUTPUT_PATH.unlink()
        try:
            summary = get_health_summary()
            assert summary["component"] == "coverage_tracker"
            assert summary["status"] == "no_data"
        finally:
            OUTPUT_PATH.write_text(backup, encoding="utf-8")
    else:
        summary = get_health_summary()
        assert summary["status"] == "no_data"


# ═══════════════════════════════════════════════════════════════════
# Test: 硬编码检测 — 负面测试
# ═══════════════════════════════════════════════════════════════════

def test_no_hardcoded_phase_names_in_source():
    """验证 coverage_tracker.py 源码中没有硬编码 Phase 名称"""
    src = Path(__file__).parent.parent / "src" / "coverage_tracker.py"
    code = src.read_text(encoding="utf-8")

    # 这些是已知存在于 browser_evaluator.py 中的硬编码名称
    # coverage_tracker.py 绝不能包含
    banned = ["国产AI动手派", "人机共创设计与智能制造", "解锁AI五官",
              "全链路实战", "AI机器人创造营", "Embedded Hardware"]

    for phrase in banned:
        assert phrase not in code, (
            f"HARDCODING DETECTED: '{phrase}' found in coverage_tracker.py source. "
            f"All phase names must come from schema."
        )


# ═══════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    passed = 0
    failed = 0
    tests = [
        test_missing_schema_returns_error,
        test_missing_schema_overall_is_none,
        test_node_count_all,
        test_node_count_tested,
        test_node_to_dict,
        test_coverage_map_builds_from_schema,
        test_coverage_map_api_tree,
        test_full_compute,
        test_eval_without_schema,
        test_phases_are_not_hardcoded,
        test_no_eval_report_all_zero_coverage,
        test_risks_identified,
        test_health_summary_no_data,
        test_no_hardcoded_phase_names_in_source,
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
