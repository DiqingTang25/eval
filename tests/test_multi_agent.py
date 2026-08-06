"""
Multi-Agent 系统 — 单元测试 (Agent C)

重点验证:
  1. Planner: Schema → TestPlan (零硬编码)
  2. Models: TestPlan/DiagnosticReport 数据结构
  3. Verifier: 三通道降级逻辑
  4. Reporter: 诊断报告生成
  5. 降级策略: Schema 缺失/MCP 不可用/Visual 不可用
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.multi_agent.models import (
    TestPlan, PhaseTarget, LessonTarget, StepTarget,
    StepResult, VerificationResult, Diagnosis, DiagnosticReport,
)
from src.multi_agent.planner import PlannerAgent
from src.multi_agent.reporter import ReporterAgent


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _make_mock_schema() -> dict:
    return {
        "target_url": "http://test.example.com",
        "schema_version": "1.0",
        "confidence_scores": {"overall": 0.80},
        "auth": {"type": "form"},
        "apis": {"agent": [], "auth": []},     # SchemaAdapter 要求此字段
        "structure": {
            "phases": [
                {"id": "phase_1", "name": "AI基础", "order": 1, "lesson_count": 2},
                {"id": "phase_2", "name": "机器人", "order": 2, "lesson_count": 3},
            ],
            "lessons": [
                {"id": "l1_1", "phase_id": "phase_1", "name": "Python基础", "order": 1},
                {"id": "l1_2", "phase_id": "phase_1", "name": "神经网络", "order": 2},
                {"id": "l2_1", "phase_id": "phase_2", "name": "传感器", "order": 1},
                {"id": "l2_2", "phase_id": "phase_2", "name": "控制", "order": 2},
            ],
            "steps": [
                {"id": "s1", "lesson_id": "l1_1", "title": "安装环境", "order_index": 1},
                {"id": "s2", "lesson_id": "l1_1", "title": "Hello World", "order_index": 2},
                {"id": "s3", "lesson_id": "l2_1", "title": "接线", "order_index": 1},
            ],
        },
    }


def _write_temp_yaml(data: dict) -> str:
    import yaml
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8")
    yaml.dump(data, tmp, allow_unicode=True)
    tmp.close()
    return tmp.name


# ═══════════════════════════════════════════════════════════════════
# Test: TestPlan / Models
# ═══════════════════════════════════════════════════════════════════

def test_testplan_total_steps():
    plan = TestPlan(
        phases=[
            PhaseTarget("p1", "Phase 1", 1, lessons=[
                LessonTarget("l1", "L1", 1, 1, steps=[
                    StepTarget("s1", "S1", 1), StepTarget("s2", "S2", 2),
                ]),
            ]),
        ],
    )
    assert plan.total_steps == 2
    assert plan.total_lessons == 1


def test_testplan_total_steps_no_steps():
    """无 step 数据时按 lesson 计数"""
    plan = TestPlan(
        phases=[
            PhaseTarget("p1", "P1", 1, lessons=[
                LessonTarget("l1", "L1", 1, 1),
                LessonTarget("l2", "L2", 2, 2),
            ]),
        ],
    )
    assert plan.total_steps == 2  # 2 lessons


def test_testplan_to_ws_dict():
    plan = TestPlan(
        phases=[PhaseTarget("p1", "P1", 1, lessons=[LessonTarget("l1", "L1", 1, 1)])],
        strategy="spot_check",
        estimated_minutes=5,
        risk_areas=["Phase 3"],
    )
    d = plan.to_ws_dict()
    assert d["strategy"] == "spot_check"
    assert d["estimated_minutes"] == 5
    assert d["phases"][0]["name"] == "P1"
    assert d["risk_areas"] == ["Phase 3"]


# ═══════════════════════════════════════════════════════════════════
# Test: PlannerAgent
# ═══════════════════════════════════════════════════════════════════

def test_planner_missing_schema():
    planner = PlannerAgent(schema_path="/nonexistent.yaml")
    plan = planner.generate()
    assert plan.plan_available is False
    assert "不存在" in plan.error


def test_planner_generates_from_schema():
    schema_path = _write_temp_yaml(_make_mock_schema())
    try:
        planner = PlannerAgent(schema_path=schema_path)
        plan = planner.generate(strategy="full")

        assert plan.plan_available is True
        assert plan.strategy == "full"
        assert len(plan.phases) == 2
        # Phase names from schema
        assert plan.phases[0].phase_name == "AI基础"
        assert plan.phases[1].phase_name == "机器人"
    finally:
        Path(schema_path).unlink(missing_ok=True)


def test_planner_spot_check():
    schema_path = _write_temp_yaml(_make_mock_schema())
    try:
        planner = PlannerAgent(schema_path=schema_path)
        plan = planner.generate(strategy="spot_check")

        # spot_check: 每条最多 2 Day
        for p in plan.phases:
            assert len(p.lessons) <= 2, f"Phase {p.phase_name} has {len(p.lessons)} lessons"
    finally:
        Path(schema_path).unlink(missing_ok=True)


def test_planner_no_hardcoded_phases():
    """Phase 名称绝对不来自硬编码"""
    custom_schema = _make_mock_schema()
    custom_schema["structure"]["phases"] = [
        {"id": "p_x", "name": "自定义训练模块", "order": 1, "lesson_count": 1},
    ]
    custom_schema["structure"]["lessons"] = [
        {"id": "lx1", "phase_id": "p_x", "name": "课程X", "order": 1},
    ]
    custom_schema["structure"]["steps"] = []
    schema_path = _write_temp_yaml(custom_schema)

    try:
        planner = PlannerAgent(schema_path=schema_path)
        plan = planner.generate()

        assert plan.phases[0].phase_name == "自定义训练模块"
        # Critical: must NOT contain hardcoded names
        banned = ["国产AI动手派", "人机共创", "嵌入式硬件", "AI机器人创造营"]
        for p in plan.phases:
            for b in banned:
                assert b not in p.phase_name, f"HARDCODING: '{b}' in phase name"
    finally:
        Path(schema_path).unlink(missing_ok=True)


def test_planner_phases_filter():
    schema_path = _write_temp_yaml(_make_mock_schema())
    try:
        planner = PlannerAgent(schema_path=schema_path)
        plan = planner.generate(phases_filter=["phase_1"])
        assert len(plan.phases) == 1
        assert plan.phases[0].phase_id == "phase_1"
    finally:
        Path(schema_path).unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════
# Test: VerificationResult
# ═══════════════════════════════════════════════════════════════════

def test_verification_result_pass():
    v = VerificationResult(
        phase_name="P1", lesson_name="L1", step_name="S1",
        text_pass=True, visual_pass=True, api_pass=False,
        verdict="pass",
    )
    assert v.verdict == "pass"


def test_verification_result_degraded():
    """Visual 跳过时不影响结果"""
    v = VerificationResult(
        phase_name="P1", lesson_name="L1", step_name="S1",
        text_pass=True, visual_pass=True, visual_skipped=True,
        api_pass=True, api_skipped=True,
        verdict="pass",
    )
    assert v.visual_skipped is True
    assert v.verdict == "pass"


# ═══════════════════════════════════════════════════════════════════
# Test: ReporterAgent
# ═══════════════════════════════════════════════════════════════════

def test_reporter_generates_report():
    plan = TestPlan(phases=[], strategy="spot_check")
    verifications = [
        VerificationResult("P1", "L1", "S1", text_pass=True, visual_pass=True, api_pass=True, verdict="pass"),
        VerificationResult("P1", "L1", "S2", text_pass=False, visual_pass=False, api_pass=True, verdict="fail",
                          text_score=1.5, diagnosis="文本评分低"),
    ]
    reporter = ReporterAgent()
    report = reporter.generate("test_session", plan, verifications)

    assert report.total_steps == 2
    assert report.failures == 1
    assert report.pass_rate == 0.5
    assert len(report.findings) >= 1


def test_reporter_critical_failures():
    plan = TestPlan(phases=[], strategy="full")
    verifications = [
        VerificationResult("P1", "L1", "S1", text_pass=False, visual_pass=False, api_pass=True, verdict="fail"),
    ]
    reporter = ReporterAgent()
    report = reporter.generate("s", plan, verifications)

    assert report.critical_failures == 1  # text+visual both fail


def test_reporter_to_dict_format():
    """to_dict 必须对齐 Agent A 要求的 diagnosis 格式"""
    plan = TestPlan(phases=[], strategy="full")
    verifications = [VerificationResult("P1", "L1", "S1", text_pass=True, visual_pass=True, api_pass=True, verdict="pass")]
    reporter = ReporterAgent()
    report = reporter.generate("test", plan, verifications)
    d = report.to_dict()

    assert "diagnosis" in d
    assert "pass_rate" in d["diagnosis"]
    assert "findings" in d["diagnosis"]
    assert "verification_details" in d


def test_reporter_save():
    plan = TestPlan(phases=[], strategy="spot_check")
    verifications = [VerificationResult("P1", "L1", "S1", verdict="pass", text_pass=True)]
    reporter = ReporterAgent()
    report = reporter.generate("test_save", plan, verifications)
    path = reporter.save(report)

    assert path.endswith(".json")
    assert Path(path).exists()
    # Clean up
    Path(path).unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════
# Test: Diagnosis model
# ═══════════════════════════════════════════════════════════════════

def test_diagnosis():
    d = Diagnosis(
        finding="API正常但页面空白 — SPA渲染bug",
        severity="high",
        step="Phase 2 Day 3 Step 2",
        evidence={"text_score": 4.2},
    )
    assert d.severity == "high"
    assert "API正常" in d.finding


# ═══════════════════════════════════════════════════════════════════
# Test: No hardcoded phase names in source
# ═══════════════════════════════════════════════════════════════════

def test_no_hardcoded_phases_in_multi_agent():
    """Multi-Agent 源码中禁止硬编码弃用 Phase 名称"""
    import glob
    src_files = glob.glob("src/multi_agent/*.py")
    banned = ["国产AI动手派", "人机共创设计与智能制造", "解锁AI五官",
              "全链路实战", "AI机器人创造营", "Embedded Hardware"]

    for filepath in src_files:
        code = Path(filepath).read_text(encoding="utf-8")
        for phrase in banned:
            assert phrase not in code, (
                f"HARDCODING: '{phrase}' in {filepath}"
            )


# ═══════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    passed = 0
    failed = 0
    tests = [
        test_testplan_total_steps,
        test_testplan_total_steps_no_steps,
        test_testplan_to_ws_dict,
        test_planner_missing_schema,
        test_planner_generates_from_schema,
        test_planner_spot_check,
        test_planner_no_hardcoded_phases,
        test_planner_phases_filter,
        test_verification_result_pass,
        test_verification_result_degraded,
        test_reporter_generates_report,
        test_reporter_critical_failures,
        test_reporter_to_dict_format,
        test_reporter_save,
        test_diagnosis,
        test_no_hardcoded_phases_in_multi_agent,
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
