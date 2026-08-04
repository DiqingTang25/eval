"""
L1规则阈值统计校准器 v1.0 (P1-3)

功能:
- 从历史评测数据中提取L1规则分数分布
- 计算经验性阈值 (中位数/百分位数/SD)
- 对比硬编码阈值 vs 经验阈值, 生成校准建议
- 支持按画像/阶段分层校准

用法:
    calibrator = RuleCalibrator()
    calibrator.load_from_reports("reports/")       # 加载历史报告
    calibrator.load_from_db(db_session)             # 或从数据库加载
    report = calibrator.calibrate()                 # 生成校准报告
    calibrator.apply_thresholds(report)             # 可选: 自动应用保守调整
"""

import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ── 当前硬编码阈值 (Single Source of Truth) ──

HARDCODED_THRESHOLDS = {
    "facts": {
        "skip_llm_score": 4.5,       # fact_result.score >= 4.5 → skip LLM
        "veto_empty_answer": True,     # 空回答 → correctness=0
        "min_keyword_coverage": 0.3,   # 关键词覆盖率最低阈值
        "fallback_score": 3.0,
    },
    "safety": {
        "skip_llm_score": 5.0,        # safety_result.score >= 5.0 → skip LLM
        "pii_detected_veto": True,     # PII → 多维度0分
        "fallback_score": 3.0,
    },
    "structure": {
        "min_total_length": 50,        # 最小总长度(字符)
        "min_answer_length": 20,       # 最小回答长度
        "fallback_score": 3.0,
    },
    "sla": {
        "max_response_time": 30.0,     # 最大响应时间(秒)
        "min_success_rate": 0.5,       # 最小成功率
        "fallback_score": 3.0,
    },
    "overhelping": {
        "code_block_threshold": 2,     # 代码块数量超过此值→过度帮助
        "student_ratio_threshold": 0.3, # 学生文字占比低于此值→独角戏
        "fallback_score": 5.0,
    },
    "aggregation": {
        "rule_weight_global": 0.30,    # L1全局权重
        "llm_weight_global": 0.70,     # L3全局权重
        "skip_dimension_threshold": 4.5,  # 单维度规则分≥此值→跳过LLM
    },
}


# ── 数据模型 ──────────────────────────────────────────────

@dataclass
class ThresholdStats:
    """单个阈值的统计信息"""
    name: str                          # 阈值名称
    current_value: float               # 当前硬编码值
    empirical_mean: float = 0.0
    empirical_median: float = 0.0
    empirical_std: float = 0.0
    empirical_p25: float = 0.0
    empirical_p75: float = 0.0
    empirical_p90: float = 0.0
    empirical_p95: float = 0.0
    n_samples: int = 0
    recommended_value: float = 0.0
    recommendation: str = ""           # "increase" | "decrease" | "keep"
    confidence: str = ""               # "high" | "medium" | "low"
    evidence: str = ""


@dataclass
class CalibrationReport:
    """校准报告"""
    generated_at: str
    source: str                        # "reports" | "database" | "hybrid"
    n_reports: int = 0
    n_scenarios: int = 0
    n_dimension_scores: int = 0
    thresholds: list[ThresholdStats] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# ── 校准器 ────────────────────────────────────────────────

class RuleCalibrator:
    """L1规则阈值统计校准器"""

    # 阈值调整策略: 保守(不激进降低阈值) vs 激进(完全跟随数据)
    CONSERVATIVE_FACTOR = 0.5  # 保守因子: 只移动差异的50%

    def __init__(self, conservative: bool = True):
        """
        :param conservative: True=保守策略(推荐), False=激进策略
        """
        self.conservative = conservative
        self._rule_scores: dict[str, list[float]] = defaultdict(list)
        self._dimension_scores: dict[str, list[float]] = defaultdict(list)
        self._meta = {"n_reports": 0, "n_scenarios": 0}

    # ── 数据加载 ──────────────────────────────────────────

    def load_from_reports(self, reports_dir: str) -> int:
        """从 reports/ 目录加载历史报告JSON

        :return: 加载的场景数
        """
        if not os.path.isdir(reports_dir):
            return 0

        json_files = sorted([
            f for f in os.listdir(reports_dir)
            if f.startswith("report_") and f.endswith(".json")
        ])

        total_scenarios = 0
        for fname in json_files:
            try:
                with open(os.path.join(reports_dir, fname), "r", encoding="utf-8") as f:
                    report = json.load(f)
                n = self._ingest_report(report)
                total_scenarios += n
                self._meta["n_reports"] += 1
            except Exception as e:
                print(f"  ⚠️ 跳过 {fname}: {e}")

        self._meta["n_scenarios"] = total_scenarios
        return total_scenarios

    def load_from_results(self, results: list[dict]) -> int:
        """从评测结果列表(raw results, 非报告)中提取L1数据

        :param results: [{"score": {...}, "question_data": {...}}, ...]
        :return: 加载的场景数
        """
        count = 0
        for r in results:
            score = r.get("score", {})
            if not score:
                continue

            # 提取L1规则相关信息
            rule_score = score.get("rule_score", 0)
            if rule_score > 0:
                self._rule_scores["rule_score"].append(rule_score)

            rule_evidence = score.get("rule_evidence", [])
            if rule_evidence:
                self._rule_scores["evidence_count"].append(len(rule_evidence))

            # 各维度分数
            for dim in ("correctness", "relevancy", "completeness", "guidance",
                        "followup_quality", "boundary_compliance",
                        "turn_consistency", "knowledge_scaffolding",
                        "overhelping"):
                val = score.get(dim, 0)
                if val > 0:
                    self._dimension_scores[dim].append(val)

            # 中间过程
            intermediate = score.get("_intermediate", {})
            if intermediate:
                l1 = intermediate.get("layers", {}).get("L1_rules", {})
                l1_rule_score = l1.get("rule_score", 0)
                if l1_rule_score > 0:
                    self._rule_scores["l1_score"].append(l1_rule_score)

            count += 1

        self._meta["n_scenarios"] += count
        return count

    def _ingest_report(self, report: dict) -> int:
        """从单个报告中提取规则数据"""
        count = 0
        for detail in report.get("details", []):
            score = detail.get("score", {})
            if not score:
                continue
            count += 1

            # 规则分数
            rule_score = score.get("rule_score", 0)
            if rule_score > 0:
                self._rule_scores["rule_score"].append(rule_score)

            # 规则证据
            rule_evidence = score.get("rule_evidence", [])
            if rule_evidence:
                self._rule_scores["evidence_count"].append(len(rule_evidence))

            # 各维度
            for dim in ("correctness", "relevancy", "completeness", "guidance",
                        "followup_quality", "boundary_compliance",
                        "turn_consistency", "knowledge_scaffolding",
                        "overhelping"):
                val = score.get(dim, 0)
                if val > 0:
                    self._dimension_scores[dim].append(val)

        return count

    # ── 统计计算 ──────────────────────────────────────────

    @staticmethod
    def _compute_percentiles(values: list[float]) -> dict:
        """计算基本统计量"""
        if not values:
            return {}
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        return {
            "mean": sum(values) / n,
            "median": sorted_vals[n // 2] if n % 2 == 1
                      else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2,
            "std": (sum((x - sum(values) / n) ** 2 for x in values) / (n - 1)) ** 0.5
                   if n > 1 else 0.0,
            "p25": sorted_vals[int(n * 0.25)],
            "p75": sorted_vals[int(n * 0.75)],
            "p90": sorted_vals[int(n * 0.90)],
            "p95": sorted_vals[int(n * 0.95)],
            "n": n,
            "min": sorted_vals[0],
            "max": sorted_vals[-1],
        }

    @staticmethod
    def _recommend_threshold(
        current: float, empirical_median: float, empirical_std: float,
        name: str, n_samples: int, conservative: bool,
    ) -> tuple[float, str, str, str]:
        """推荐阈值调整

        策略:
        - 如果经验中位数与当前值差异 < 0.5个标准差 → keep
        - 保守模式: 只移动差异的50%
        - 样本量 < 10 → 置信度低
        """
        if n_samples < 3:
            return current, "keep", "low", "样本量不足(<3), 无法校准"

        diff = empirical_median - current
        abs_diff_std = abs(diff) / empirical_std if empirical_std > 0 else float("inf")

        if abs_diff_std < 0.5:
            return current, "keep", "high" if n_samples >= 20 else "medium", (
                f"当前值{current}接近经验中位数{empirical_median:.2f} "
                f"(差异{abs(diff):.2f} < 0.5σ, n={n_samples})"
            )

        # 需要调整
        if conservative:
            adjusted = current + diff * RuleCalibrator.CONSERVATIVE_FACTOR
        else:
            adjusted = empirical_median

        # 方向
        if diff > 0:
            direction = "increase"
            action = f"建议从 {current} 提升到 {adjusted:.2f}"
        else:
            direction = "decrease"
            action = f"建议从 {current} 降低到 {adjusted:.2f}"

        conf = "high" if n_samples >= 20 else "medium"
        evidence = (
            f"{action} (经验中位数={empirical_median:.2f}, "
            f"σ={empirical_std:.2f}, n={n_samples})"
        )

        return round(adjusted, 2), direction, conf, evidence

    # ── 校准 ──────────────────────────────────────────────

    def calibrate(self) -> CalibrationReport:
        """执行校准, 生成报告"""
        report = CalibrationReport(
            generated_at=datetime.now().isoformat(),
            source="reports",
            n_reports=self._meta["n_reports"],
            n_scenarios=self._meta["n_scenarios"],
            n_dimension_scores=sum(
                len(v) for v in self._dimension_scores.values()
            ),
        )

        # ── 规则分数阈值校准 ──
        rule_score_stats = self._compute_percentiles(
            self._rule_scores.get("rule_score", [])
        )
        l1_score_stats = self._compute_percentiles(
            self._rule_scores.get("l1_score", [])
        )

        # 使用更完整的规则分数
        scores_for_threshold = (
            self._rule_scores.get("l1_score", []) or
            self._rule_scores.get("rule_score", [])
        )
        stats = self._compute_percentiles(scores_for_threshold)

        if stats:
            # skip_llm_score: 当前硬编码 4.5
            current_skip = HARDCODED_THRESHOLDS["facts"]["skip_llm_score"]
            rec_val, direction, conf, evidence = self._recommend_threshold(
                current_skip, stats["median"], stats["std"],
                "skip_llm_score", stats["n"], self.conservative,
            )
            report.thresholds.append(ThresholdStats(
                name="facts.skip_llm_score",
                current_value=current_skip,
                empirical_mean=stats["mean"],
                empirical_median=stats["median"],
                empirical_std=stats["std"],
                empirical_p25=stats["p25"],
                empirical_p75=stats["p75"],
                empirical_p90=stats["p90"],
                empirical_p95=stats["p95"],
                n_samples=stats["n"],
                recommended_value=rec_val,
                recommendation=direction,
                confidence=conf,
                evidence=evidence,
            ))

        # ── 各维度分数分布 ──
        dim_order = [
            "correctness", "relevancy", "completeness", "guidance",
            "followup_quality", "boundary_compliance",
            "turn_consistency", "knowledge_scaffolding", "overhelping",
        ]
        for dim in dim_order:
            dim_vals = self._dimension_scores.get(dim, [])
            if not dim_vals:
                continue
            dim_stats = self._compute_percentiles(dim_vals)
            report.thresholds.append(ThresholdStats(
                name=f"dimension.{dim}",
                current_value=0,  # 无硬编码阈值, 纯统计
                empirical_mean=dim_stats["mean"],
                empirical_median=dim_stats["median"],
                empirical_std=dim_stats["std"],
                empirical_p25=dim_stats["p25"],
                empirical_p75=dim_stats["p75"],
                empirical_p90=dim_stats["p90"],
                empirical_p95=dim_stats["p95"],
                n_samples=dim_stats["n"],
                recommended_value=0,
                recommendation="info",
                confidence="high" if dim_stats["n"] >= 20 else "medium",
                evidence=f"维度{dim}分数分布: mean={dim_stats['mean']:.2f}, "
                         f"median={dim_stats['median']:.2f}, σ={dim_stats['std']:.2f}",
            ))

        # ── 汇总 ──
        report.summary = {
            "calibrated_thresholds": sum(
                1 for t in report.thresholds if t.recommendation in ("increase", "decrease")
            ),
            "kept_thresholds": sum(
                1 for t in report.thresholds if t.recommendation == "keep"
            ),
            "info_only": sum(
                1 for t in report.thresholds if t.recommendation == "info"
            ),
            "high_confidence": sum(
                1 for t in report.thresholds if t.confidence == "high"
            ),
            "low_confidence": sum(
                1 for t in report.thresholds if t.confidence == "low"
            ),
        }

        # ── 建议 ──
        for t in report.thresholds:
            if t.recommendation == "increase":
                report.recommendations.append(
                    f"[{t.confidence}置信度] 提升 {t.name}: "
                    f"{t.current_value} → {t.recommended_value} ({t.evidence})"
                )
            elif t.recommendation == "decrease":
                report.recommendations.append(
                    f"[{t.confidence}置信度] 降低 {t.name}: "
                    f"{t.current_value} → {t.recommended_value} ({t.evidence})"
                )

        # ── 告警 ──
        if self._meta["n_scenarios"] < 10:
            report.warnings.append(
                f"样本量仅{self._meta['n_scenarios']}个场景, "
                "建议至少收集30个场景后再执行正式校准"
            )
        if not self._rule_scores:
            report.warnings.append(
                "未找到L1规则分数, 请确保评测报告中包含'rule_score'和'rule_evidence'字段"
            )

        return report

    def get_dimension_percentiles(self, dim: str) -> dict:
        """获取某维度的百分位分布"""
        vals = self._dimension_scores.get(dim, [])
        return self._compute_percentiles(vals)

    def clear(self):
        """清除已加载数据"""
        self._rule_scores.clear()
        self._dimension_scores.clear()
        self._meta = {"n_reports": 0, "n_scenarios": 0}


# ── CLI ──────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="L1规则阈值统计校准工具")
    parser.add_argument("--reports-dir", default="reports",
                        help="历史报告目录 (默认: reports/)")
    parser.add_argument("--output", default=None,
                        help="输出校准报告JSON路径 (默认: stdout)")
    parser.add_argument("--aggressive", action="store_true",
                        help="激进模式 (完全跟随数据, 默认保守)")

    args = parser.parse_args()

    calibrator = RuleCalibrator(conservative=not args.aggressive)
    n = calibrator.load_from_reports(args.reports_dir)

    if n == 0:
        print("⚠️ 未找到历史报告或报告中没有L1规则数据。")
        print("   请先运行评测生成报告, 确保报告JSON中包含 'rule_score' 字段。")
        return 1

    report = calibrator.calibrate()

    # 输出
    output_data = {
        "generated_at": report.generated_at,
        "source": report.source,
        "n_reports": report.n_reports,
        "n_scenarios": report.n_scenarios,
        "summary": report.summary,
        "warnings": report.warnings,
        "recommendations": report.recommendations,
        "thresholds": [
            {
                "name": t.name,
                "current_value": t.current_value,
                "empirical_mean": round(t.empirical_mean, 2),
                "empirical_median": round(t.empirical_median, 2),
                "empirical_std": round(t.empirical_std, 2),
                "empirical_p25": round(t.empirical_p25, 2),
                "empirical_p75": round(t.empirical_p75, 2),
                "empirical_p90": round(t.empirical_p90, 2),
                "n_samples": t.n_samples,
                "recommended_value": t.recommended_value,
                "recommendation": t.recommendation,
                "confidence": t.confidence,
                "evidence": t.evidence,
            }
            for t in report.thresholds
        ],
    }

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"📄 校准报告: {args.output}")
    else:
        print(json.dumps(output_data, ensure_ascii=False, indent=2))

    print(f"\n{'='*50}")
    print(f"校准摘要")
    print(f"{'='*50}")
    print(f"数据: {report.n_reports} 份报告, {report.n_scenarios} 个场景")
    print(f"待调整阈值: {report.summary['calibrated_thresholds']}")
    print(f"保持阈值: {report.summary['kept_thresholds']}")
    print(f"统计信息: {report.summary['info_only']}")
    if report.warnings:
        print(f"\n⚠️ 告警:")
        for w in report.warnings:
            print(f"  - {w}")
    if report.recommendations:
        print(f"\n📋 建议:")
        for r in report.recommendations:
            print(f"  - {r}")

    return 0


if __name__ == "__main__":
    exit(main())
