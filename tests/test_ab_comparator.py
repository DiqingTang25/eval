"""P1-2: A/B 对比框架测试"""

import json
import os
import tempfile
import pytest
from src.ab_comparator import (
    ABComparator, ABComparisonResult, DimensionDelta, ScenarioDelta,
    DIMENSIONS, DIM_LABELS, REGRESSION_THRESHOLD, CRITICAL_REGRESSION,
)


@pytest.fixture
def sample_report_a():
    return {
        "timestamp": "20260716_100000",
        "summary": {
            "total": 5, "success": 5,
            "avg_scores": {
                "correctness": 3.5, "relevancy": 4.0, "completeness": 3.2,
                "guidance": 3.0, "followup_quality": 3.5, "boundary_compliance": 4.2,
                "turn_consistency": 3.8, "knowledge_scaffolding": 3.0,
                "overhelping": 4.5, "overall": 3.6,
            }
        },
        "details": [
            {
                "question_data": {"qa_id": "Q001", "question": "What is a breadboard?"},
                "score": {
                    "correctness": 3.5, "relevancy": 4.0, "completeness": 3.2,
                    "guidance": 3.0, "followup_quality": 3.5, "boundary_compliance": 4.2,
                    "turn_consistency": 3.8, "knowledge_scaffolding": 3.0,
                    "overhelping": 4.5, "overall": 3.6,
                }
            },
            {
                "question_data": {"qa_id": "Q002", "question": "Explain Ohm law"},
                "score": {
                    "correctness": 4.0, "relevancy": 3.8, "completeness": 3.5,
                    "guidance": 3.2, "followup_quality": 3.8, "boundary_compliance": 4.0,
                    "turn_consistency": 4.0, "knowledge_scaffolding": 3.5,
                    "overhelping": 4.0, "overall": 3.8,
                }
            },
        ]
    }


@pytest.fixture
def sample_report_b():
    return {
        "timestamp": "20260716_120000",
        "summary": {
            "total": 5, "success": 5,
            "avg_scores": {
                "correctness": 4.0, "relevancy": 4.2, "completeness": 3.0,
                "guidance": 3.8, "followup_quality": 3.2, "boundary_compliance": 4.0,
                "turn_consistency": 4.0, "knowledge_scaffolding": 3.2,
                "overhelping": 4.3, "overall": 3.75,
            }
        },
        "details": [
            {
                "question_data": {"qa_id": "Q001", "question": "What is a breadboard?"},
                "score": {
                    "correctness": 4.0, "relevancy": 4.2, "completeness": 3.0,
                    "guidance": 3.8, "followup_quality": 3.2, "boundary_compliance": 4.0,
                    "turn_consistency": 4.0, "knowledge_scaffolding": 3.2,
                    "overhelping": 4.3, "overall": 3.75,
                }
            },
            {
                "question_data": {"qa_id": "Q002", "question": "Explain Ohm law"},
                "score": {
                    "correctness": 4.2, "relevancy": 4.0, "completeness": 3.8,
                    "guidance": 3.5, "followup_quality": 4.0, "boundary_compliance": 4.2,
                    "turn_consistency": 3.8, "knowledge_scaffolding": 3.8,
                    "overhelping": 4.2, "overall": 4.0,
                }
            },
        ]
    }


class TestABComparator:
    """A/B 对比器核心测试"""

    def test_basic_comparison(self, sample_report_a, sample_report_b):
        comp = ABComparator()
        # Write temp files
        with open("/tmp/_test_a.json", "w") as f:
            json.dump(sample_report_a, f)
        with open("/tmp/_test_b.json", "w") as f:
            json.dump(sample_report_b, f)

        result = comp.compare("/tmp/_test_a.json", "/tmp/_test_b.json")

        assert isinstance(result, ABComparisonResult)
        assert len(result.dimension_deltas) == len(DIMENSIONS)

        # Check correctness improved
        correctness = next(d for d in result.dimension_deltas if d.dimension == "correctness")
        assert correctness.delta > 0
        assert correctness.score_b > correctness.score_a

        # Check overall
        overall = next(d for d in result.dimension_deltas if d.dimension == "overall")
        assert overall.delta > 0

        # Cleanup
        os.remove("/tmp/_test_a.json")
        os.remove("/tmp/_test_b.json")

    def test_dimension_delta_types(self, sample_report_a, sample_report_b):
        comp = ABComparator()
        with open("/tmp/_test_a.json", "w") as f:
            json.dump(sample_report_a, f)
        with open("/tmp/_test_b.json", "w") as f:
            json.dump(sample_report_b, f)

        result = comp.compare("/tmp/_test_a.json", "/tmp/_test_b.json")

        for d in result.dimension_deltas:
            assert isinstance(d.dimension, str)
            assert isinstance(d.score_a, float)
            assert isinstance(d.score_b, float)
            assert isinstance(d.delta, float)
            assert isinstance(d.effect_size, float)
            assert d.significance in (
                "significant_improvement", "improvement", "neutral",
                "regression", "critical_regression",
            )

        os.remove("/tmp/_test_a.json")
        os.remove("/tmp/_test_b.json")

    def test_scenario_deltas(self, sample_report_a, sample_report_b):
        comp = ABComparator()
        with open("/tmp/_test_a.json", "w") as f:
            json.dump(sample_report_a, f)
        with open("/tmp/_test_b.json", "w") as f:
            json.dump(sample_report_b, f)

        result = comp.compare("/tmp/_test_a.json", "/tmp/_test_b.json")

        assert len(result.scenario_deltas) == 2
        for s in result.scenario_deltas:
            assert s.scenario_index in (1, 2)
            assert s.qa_id in ("Q001", "Q002")

        os.remove("/tmp/_test_a.json")
        os.remove("/tmp/_test_b.json")

    def test_save_comparison(self, sample_report_a, sample_report_b):
        comp = ABComparator()
        with open("/tmp/_test_a.json", "w") as f:
            json.dump(sample_report_a, f)
        with open("/tmp/_test_b.json", "w") as f:
            json.dump(sample_report_b, f)

        result = comp.compare("/tmp/_test_a.json", "/tmp/_test_b.json")
        json_path = comp.save_comparison(result, output_dir="/tmp")

        assert os.path.exists(json_path)
        md_path = json_path.replace(".json", ".md")
        assert os.path.exists(md_path)

        # Verify JSON content
        with open(json_path, "r") as f:
            data = json.load(f)
        assert data["overall_verdict"] in ("improved", "regressed", "mixed", "neutral")
        assert len(data["dimension_deltas"]) == len(DIMENSIONS)

        # Cleanup
        os.remove("/tmp/_test_a.json")
        os.remove("/tmp/_test_b.json")
        os.remove(json_path)
        os.remove(md_path)

    def test_file_not_found(self):
        comp = ABComparator()
        with pytest.raises(FileNotFoundError):
            comp.compare("/tmp/nonexistent_a.json", "/tmp/nonexistent_b.json")


class TestRegressionDetection:
    """回归检测测试"""

    def test_critical_regression(self):
        """严重回归检测"""
        report_a = {
            "timestamp": "t1",
            "summary": {"total": 3, "avg_scores": {"correctness": 4.5, "overall": 4.0}},
            "details": [
                {"score": {"correctness": 4.5, "overall": 4.0}},
                {"score": {"correctness": 4.5, "overall": 4.0}},
                {"score": {"correctness": 4.5, "overall": 4.0}},
            ]
        }
        report_b = {
            "timestamp": "t2",
            "summary": {"total": 3, "avg_scores": {"correctness": 3.5, "overall": 3.0}},
            "details": [
                {"score": {"correctness": 3.5, "overall": 3.0}},
                {"score": {"correctness": 3.5, "overall": 3.0}},
                {"score": {"correctness": 3.5, "overall": 3.0}},
            ]
        }
        comp = ABComparator()
        with open("/tmp/_reg_a.json", "w") as f: json.dump(report_a, f)
        with open("/tmp/_reg_b.json", "w") as f: json.dump(report_b, f)

        result = comp.compare("/tmp/_reg_a.json", "/tmp/_reg_b.json")

        correctness = next(d for d in result.dimension_deltas if d.dimension == "correctness")
        assert correctness.delta < -CRITICAL_REGRESSION
        assert correctness.significance == "critical_regression"
        assert result.critical_regression_count >= 1
        assert len(result.warnings) >= 1

        os.remove("/tmp/_reg_a.json")
        os.remove("/tmp/_reg_b.json")

    def test_no_regression_when_equal(self):
        """完全相同时无回归"""
        report = {
            "timestamp": "t1",
            "summary": {"total": 2, "avg_scores": {"correctness": 4.0, "overall": 4.0}},
            "details": [
                {"score": {"correctness": 4.0, "overall": 4.0}},
                {"score": {"correctness": 4.0, "overall": 4.0}},
            ]
        }
        comp = ABComparator()
        with open("/tmp/_eq_a.json", "w") as f: json.dump(report, f)
        with open("/tmp/_eq_b.json", "w") as f: json.dump(report, f)

        result = comp.compare("/tmp/_eq_a.json", "/tmp/_eq_b.json")
        assert result.regression_count == 0
        assert result.critical_regression_count == 0
        assert result.overall_verdict == "neutral"

        os.remove("/tmp/_eq_a.json")
        os.remove("/tmp/_eq_b.json")


class TestCohensD:
    """Cohen's d 效应量测试"""

    def test_identical_distributions(self):
        assert ABComparator._cohens_d([4.0, 4.0, 4.0], [4.0, 4.0, 4.0]) == 0.0

    def test_large_effect(self):
        d = ABComparator._cohens_d([3.0, 3.0, 3.0], [5.0, 5.0, 5.0])
        # With zero variance and identical values, pooled SD is 0 → returns 0
        # Test with actual varying data
        d2 = ABComparator._cohens_d([3.0, 3.5, 4.0], [4.5, 5.0, 5.0])
        assert abs(d2) > 0.5  # Should show large effect

    def test_small_effect(self):
        d = ABComparator._cohens_d([3.8, 4.0, 4.2], [4.0, 4.2, 4.4])
        assert abs(d) < 1.0  # Small effect

    def test_single_value(self):
        """单值返回0（无法计算方差）"""
        d = ABComparator._cohens_d([4.0], [4.0])
        assert d == 0.0
