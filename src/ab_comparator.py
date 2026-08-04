"""
A/B 对比框架 v1.0 (P1-2)

功能:
- 两份评测报告的维度级对比
- 效应量计算 (Cohen's d) + 显著性判断
- 回归检测 (任意维度下降 > 阈值则告警)
- 场景级逐题对比
- JSON + Markdown 双格式对比报告

用法:
    comparator = ABComparator()
    result = comparator.compare("reports/report_A.json", "reports/report_B.json")
    comparator.save_comparison(result)  # → reports/ab_comparison_*.json + .md
"""

import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ── 10维度定义 ──

DIMENSIONS = [
    "correctness", "relevancy", "completeness", "guidance",
    "followup_quality", "boundary_compliance",
    "turn_consistency", "knowledge_scaffolding",
    "overhelping", "overall",
]

DIM_LABELS = {
    "correctness": "事实正确性",
    "relevancy": "答案相关性",
    "completeness": "内容完整性",
    "guidance": "教学引导力",
    "followup_quality": "追问响应质量",
    "boundary_compliance": "边界合规性",
    "turn_consistency": "跨轮一致性",
    "knowledge_scaffolding": "知识递进性",
    "overhelping": "过度帮助",
    "overall": "综合得分",
}

# 回归检测阈值
REGRESSION_THRESHOLD = 0.3       # 单维度下降 >= 0.3 分视为显著回归
CRITICAL_REGRESSION = 0.5        # 下降 >= 0.5 分视为严重回归
EFFECT_SIZE_THRESHOLD = 0.5      # Cohen's d >= 0.5 视为中等效应


@dataclass
class DimensionDelta:
    """单维度变化"""
    dimension: str
    label: str
    score_a: float
    score_b: float
    delta: float                   # B - A, 正值 = 提升
    delta_pct: float               # 变化百分比
    effect_size: float             # Cohen's d
    significance: str              # "significant_improvement" | "improvement" | "neutral" | "regression" | "critical_regression"
    verdict: str                   # 人类可读的判定


@dataclass
class ScenarioDelta:
    """单场景变化"""
    scenario_index: int
    qa_id: str
    question: str
    scores_a: dict
    scores_b: dict
    overall_delta: float
    dim_deltas: dict               # {dim: delta}


@dataclass
class ABComparisonResult:
    """A/B 对比完整结果"""
    report_a_path: str
    report_b_path: str
    timestamp_a: str
    timestamp_b: str
    total_a: int
    total_b: int
    dimension_deltas: list[DimensionDelta]
    scenario_deltas: list[ScenarioDelta]
    overall_verdict: str           # "improved" | "regressed" | "mixed" | "neutral"
    regression_count: int          # 回归维度数
    improvement_count: int         # 提升维度数
    critical_regression_count: int # 严重回归维度数
    warnings: list[str]
    generated_at: str


class ABComparator:
    """A/B 对比器"""

    def __init__(self, regression_threshold: float = REGRESSION_THRESHOLD,
                 critical_threshold: float = CRITICAL_REGRESSION):
        self.regression_threshold = regression_threshold
        self.critical_threshold = critical_threshold

    # ── 公共API ──────────────────────────────────────────

    def compare(self, report_a_path: str, report_b_path: str) -> ABComparisonResult:
        """对比两份评测报告

        :param report_a_path: 基线报告路径 (A)
        :param report_b_path: 对比报告路径 (B)
        :return: ABComparisonResult
        """
        report_a = self._load_report(report_a_path)
        report_b = self._load_report(report_b_path)

        dim_deltas = self._compare_dimensions(report_a, report_b)
        scenario_deltas = self._compare_scenarios(report_a, report_b)

        # 汇总
        warnings = []
        regression_count = 0
        improvement_count = 0
        critical_regression_count = 0

        for d in dim_deltas:
            if d.significance == "critical_regression":
                critical_regression_count += 1
                warnings.append(
                    f"[严重回归] {d.label}: {d.score_a:.2f} → {d.score_b:.2f} "
                    f"({d.delta:+.2f}, d={d.effect_size:.2f})"
                )
            elif d.significance == "regression":
                regression_count += 1
                warnings.append(
                    f"[回归] {d.label}: {d.score_a:.2f} → {d.score_b:.2f} "
                    f"({d.delta:+.2f})"
                )
            elif d.significance in ("significant_improvement", "improvement"):
                improvement_count += 1

        # 整体判定
        overall_verdict = self._determine_overall_verdict(
            dim_deltas, critical_regression_count, regression_count, improvement_count
        )

        return ABComparisonResult(
            report_a_path=report_a_path,
            report_b_path=report_b_path,
            timestamp_a=report_a.get("timestamp", "unknown"),
            timestamp_b=report_b.get("timestamp", "unknown"),
            total_a=report_a.get("summary", {}).get("total", 0),
            total_b=report_b.get("summary", {}).get("total", 0),
            dimension_deltas=dim_deltas,
            scenario_deltas=scenario_deltas,
            overall_verdict=overall_verdict,
            regression_count=regression_count,
            improvement_count=improvement_count,
            critical_regression_count=critical_regression_count,
            warnings=warnings,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def save_comparison(self, result: ABComparisonResult,
                        output_dir: str = "reports") -> str:
        """保存对比报告 (JSON + Markdown)

        :return: JSON 文件路径
        """
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # JSON
        json_path = os.path.join(output_dir, f"ab_comparison_{ts}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self._result_to_dict(result), f, ensure_ascii=False, indent=2)

        # Markdown
        md_path = os.path.join(output_dir, f"ab_comparison_{ts}.md")
        self._write_markdown(result, md_path)

        return json_path

    # ── 维度对比 ─────────────────────────────────────────

    def _compare_dimensions(self, report_a: dict, report_b: dict) -> list[DimensionDelta]:
        """逐维度对比两份报告的平均分数"""
        avg_a = report_a.get("summary", {}).get("avg_scores", {})
        avg_b = report_b.get("summary", {}).get("avg_scores", {})

        # 提取每份报告的维度分数列表(用于效应量计算)
        scores_by_dim_a = self._extract_dim_scores(report_a)
        scores_by_dim_b = self._extract_dim_scores(report_b)

        deltas = []
        for dim in DIMENSIONS:
            sa = avg_a.get(dim, 0)
            sb = avg_b.get(dim, 0)
            delta = sb - sa
            delta_pct = (delta / sa * 100) if sa > 0 else 0

            # Cohen's d
            vals_a = scores_by_dim_a.get(dim, [])
            vals_b = scores_by_dim_b.get(dim, [])
            d = self._cohens_d(vals_a, vals_b)

            # 显著性判定
            if delta >= 0.5:
                sig = "significant_improvement"
            elif delta >= 0.2:
                sig = "improvement"
            elif delta > -self.regression_threshold:
                sig = "neutral"
            elif delta > -self.critical_threshold:
                sig = "regression"
            else:
                sig = "critical_regression"

            # 人类可读判定
            if d >= EFFECT_SIZE_THRESHOLD and delta > 0:
                verdict = f"显著提升 (d={d:.2f})"
            elif delta > 0.1:
                verdict = f"小幅提升 (+{delta:.2f})"
            elif delta < -self.critical_threshold:
                verdict = f"⚠️ 严重回归 ({delta:+.2f}, d={d:.2f})"
            elif delta < -self.regression_threshold:
                verdict = f"⚠️ 回归 ({delta:+.2f})"
            elif abs(delta) <= 0.1:
                verdict = "基本持平"
            else:
                verdict = f"小幅下降 ({delta:+.2f})"

            deltas.append(DimensionDelta(
                dimension=dim,
                label=DIM_LABELS.get(dim, dim),
                score_a=sa,
                score_b=sb,
                delta=round(delta, 2),
                delta_pct=round(delta_pct, 1),
                effect_size=round(d, 3),
                significance=sig,
                verdict=verdict,
            ))

        return deltas

    def _compare_scenarios(self, report_a: dict, report_b: dict) -> list[ScenarioDelta]:
        """逐场景对比"""
        details_a = report_a.get("details", [])
        details_b = report_b.get("details", [])

        deltas = []
        max_len = max(len(details_a), len(details_b))

        for i in range(max_len):
            ra = details_a[i] if i < len(details_a) else {}
            rb = details_b[i] if i < len(details_b) else {}

            qd = ra.get("question_data", {}) or rb.get("question_data", {})
            sc_a = ra.get("score", {}) or {}
            sc_b = rb.get("score", {}) or {}

            overall_delta = sc_b.get("overall", 0) - sc_a.get("overall", 0)

            dim_deltas = {}
            for dim in DIMENSIONS:
                if dim == "overall":
                    continue
                da = sc_a.get(dim, 0)
                db_val = sc_b.get(dim, 0)
                if da > 0 or db_val > 0:
                    dim_deltas[dim] = round(db_val - da, 2)

            deltas.append(ScenarioDelta(
                scenario_index=i + 1,
                qa_id=qd.get("qa_id", f"scenario_{i+1}"),
                question=qd.get("question", "N/A")[:100],
                scores_a=sc_a,
                scores_b=sc_b,
                overall_delta=round(overall_delta, 2),
                dim_deltas=dim_deltas,
            ))

        return deltas

    # ── 统计方法 ─────────────────────────────────────────

    @staticmethod
    def _cohens_d(values_a: list, values_b: list) -> float:
        """计算 Cohen's d 效应量 (pooled SD)"""
        if not values_a or not values_b:
            return 0.0

        mean_a = sum(values_a) / len(values_a)
        mean_b = sum(values_b) / len(values_b)

        # Pooled standard deviation
        var_a = sum((x - mean_a) ** 2 for x in values_a) / (len(values_a) - 1) if len(values_a) > 1 else 0
        var_b = sum((x - mean_b) ** 2 for x in values_b) / (len(values_b) - 1) if len(values_b) > 1 else 0

        n_a, n_b = len(values_a), len(values_b)
        pooled_var = ((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2) if (n_a + n_b) > 2 else 0

        if pooled_var <= 0:
            return 0.0

        pooled_sd = math.sqrt(pooled_var)
        if pooled_sd == 0:
            return 0.0

        return (mean_b - mean_a) / pooled_sd

    @staticmethod
    def _extract_dim_scores(report: dict) -> dict[str, list[float]]:
        """从报告的 details 中提取每个维度的分数列表"""
        dim_scores: dict[str, list[float]] = {dim: [] for dim in DIMENSIONS}
        for r in report.get("details", []):
            sc = r.get("score", {})
            if sc:
                for dim in DIMENSIONS:
                    val = sc.get(dim, 0)
                    if val > 0:
                        dim_scores[dim].append(val)
        return dim_scores

    @staticmethod
    def _determine_overall_verdict(
        dim_deltas: list[DimensionDelta],
        critical_count: int,
        regression_count: int,
        improvement_count: int,
    ) -> str:
        """综合判定"""
        total_dims = len(dim_deltas)
        if total_dims == 0:
            return "neutral"

        # 只看非overall维度
        core_deltas = [d for d in dim_deltas if d.dimension != "overall"]
        if not core_deltas:
            return "neutral"

        if critical_count > 0:
            return "regressed"       # 存在严重回归 → 总体判定为退步
        if regression_count > 0 and improvement_count == 0:
            return "regressed"
        if improvement_count > regression_count and improvement_count >= len(core_deltas) * 0.5:
            return "improved"        # 一半以上维度提升 → 总体判定为进步
        if regression_count > 0 and improvement_count > 0:
            return "mixed"           # 有升有降
        if improvement_count > 0:
            return "improved"

        return "neutral"

    # ── I/O ──────────────────────────────────────────────

    @staticmethod
    def _load_report(path: str) -> dict:
        """加载报告JSON文件"""
        if not os.path.exists(path):
            raise FileNotFoundError(f"报告文件不存在: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _result_to_dict(result: ABComparisonResult) -> dict:
        """序列化为字典"""
        return {
            "report_a": result.report_a_path,
            "report_b": result.report_b_path,
            "timestamp_a": result.timestamp_a,
            "timestamp_b": result.timestamp_b,
            "total_a": result.total_a,
            "total_b": result.total_b,
            "overall_verdict": result.overall_verdict,
            "regression_count": result.regression_count,
            "improvement_count": result.improvement_count,
            "critical_regression_count": result.critical_regression_count,
            "warnings": result.warnings,
            "dimension_deltas": [
                {
                    "dimension": d.dimension,
                    "label": d.label,
                    "score_a": d.score_a,
                    "score_b": d.score_b,
                    "delta": d.delta,
                    "delta_pct": d.delta_pct,
                    "effect_size": d.effect_size,
                    "significance": d.significance,
                    "verdict": d.verdict,
                }
                for d in result.dimension_deltas
            ],
            "scenario_deltas": [
                {
                    "scenario_index": s.scenario_index,
                    "qa_id": s.qa_id,
                    "question": s.question,
                    "overall_delta": s.overall_delta,
                    "dim_deltas": s.dim_deltas,
                }
                for s in result.scenario_deltas
            ],
            "generated_at": result.generated_at,
        }

    # ── Markdown 输出 ────────────────────────────────────

    def _write_markdown(self, result: ABComparisonResult, path: str) -> None:
        """生成 Markdown 对比报告"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# A/B 评测对比报告\n\n")
            f.write(f"**生成时间**: {result.generated_at}\n\n")

            # 基本信息
            f.write(f"## 基本信息\n\n")
            f.write(f"| 项目 | 基线 (A) | 对比 (B) |\n")
            f.write(f"|------|----------|----------|\n")
            f.write(f"| 报告时间 | {result.timestamp_a} | {result.timestamp_b} |\n")
            f.write(f"| 场景数 | {result.total_a} | {result.total_b} |\n")
            f.write(f"| 文件 | {os.path.basename(result.report_a_path)} | {os.path.basename(result.report_b_path)} |\n\n")

            # 综合判定
            verdict_emoji = {
                "improved": "📈 提升",
                "regressed": "📉 退步",
                "mixed": "🔄 混合",
                "neutral": "➡️ 持平",
            }
            f.write(f"## 综合判定: {verdict_emoji.get(result.overall_verdict, result.overall_verdict)}\n\n")

            if result.warnings:
                f.write(f"### ⚠️ 告警\n\n")
                for w in result.warnings:
                    f.write(f"- {w}\n")
                f.write("\n")

            # 维度级对比表
            f.write(f"## 维度级对比\n\n")
            f.write(f"| 维度 | A | B | Δ | Δ% | Cohen's d | 判定 |\n")
            f.write(f"|------|---|---|----|-----|----------|------|\n")
            for d in result.dimension_deltas:
                delta_str = f"+{d.delta:.2f}" if d.delta > 0 else f"{d.delta:.2f}"
                pct_str = f"+{d.delta_pct:.1f}%" if d.delta_pct > 0 else f"{d.delta_pct:.1f}%"
                d_str = f"{d.effect_size:.3f}" if d.effect_size != 0 else "N/A"
                f.write(
                    f"| {d.label} | {d.score_a:.2f} | {d.score_b:.2f} | "
                    f"{delta_str} | {pct_str} | {d_str} | {d.verdict} |\n"
                )

            # 场景级对比
            if result.scenario_deltas:
                f.write(f"\n## 场景级对比\n\n")
                f.write(f"| # | QA ID | 问题 | Δ Overall | 回归维度 |\n")
                f.write(f"|---|-------|------|-----------|----------|\n")
                for s in result.scenario_deltas:
                    delta_str = f"+{s.overall_delta:.2f}" if s.overall_delta > 0 else f"{s.overall_delta:.2f}"
                    regressed = [
                        f"{DIM_LABELS.get(dim, dim)}({v:+.2f})"
                        for dim, v in s.dim_deltas.items()
                        if v < -self.regression_threshold
                    ]
                    reg_str = ", ".join(regressed) if regressed else "—"
                    f.write(
                        f"| {s.scenario_index} | {s.qa_id} | {s.question[:50]}... | "
                        f"{delta_str} | {reg_str} |\n"
                    )

            # 建议
            f.write(f"\n## 分析建议\n\n")
            if result.critical_regression_count > 0:
                f.write(f"- 🔴 **{result.critical_regression_count}** 个维度出现严重回归，建议立即排查Agent变更点。\n")
            if result.regression_count > 0:
                f.write(f"- 🟡 **{result.regression_count}** 个维度出现回归，建议Review相关配置变更。\n")
            if result.improvement_count > 0:
                f.write(f"- 🟢 **{result.improvement_count}** 个维度有提升，变更可能有效。\n")
            if result.overall_verdict == "neutral":
                f.write(f"- 整体无显著变化，变更影响有限。\n")

            f.write(f"\n> 回归阈值: {self.regression_threshold} 分 | 严重回归阈值: {self.critical_threshold} 分\n")
            f.write(f"> 效应量: Cohen's d ≥ {EFFECT_SIZE_THRESHOLD} 视为中等效应\n")


# ── CLI ──────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="A/B 评测对比工具")
    parser.add_argument("report_a", help="基线报告 JSON 路径 (A)")
    parser.add_argument("report_b", help="对比报告 JSON 路径 (B)")
    parser.add_argument("-o", "--output", default="reports", help="输出目录")
    parser.add_argument("--regression-threshold", type=float, default=REGRESSION_THRESHOLD,
                        help=f"回归阈值 (默认 {REGRESSION_THRESHOLD})")
    parser.add_argument("--critical-threshold", type=float, default=CRITICAL_REGRESSION,
                        help=f"严重回归阈值 (默认 {CRITICAL_REGRESSION})")
    parser.add_argument("--json-only", action="store_true", help="仅输出JSON到stdout")

    args = parser.parse_args()

    comparator = ABComparator(
        regression_threshold=args.regression_threshold,
        critical_threshold=args.critical_threshold,
    )

    try:
        result = comparator.compare(args.report_a, args.report_b)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1

    if args.json_only:
        import json as _json
        print(_json.dumps(comparator._result_to_dict(result), ensure_ascii=False, indent=2))
        return 0

    # 保存完整报告
    json_path = comparator.save_comparison(result, args.output)
    md_path = json_path.replace(".json", ".md")

    print(f"\n{'='*60}")
    print(f"A/B 对比报告")
    print(f"{'='*60}")
    print(f"基线 (A): {os.path.basename(args.report_a)} ({result.total_a} 场景)")
    print(f"对比 (B): {os.path.basename(args.report_b)} ({result.total_b} 场景)")
    print(f"\n综合判定: {result.overall_verdict}")
    print(f"提升维度: {result.improvement_count} | 回归维度: {result.regression_count} | 严重回归: {result.critical_regression_count}")

    if result.warnings:
        print(f"\n⚠️ 告警:")
        for w in result.warnings:
            print(f"  {w}")

    print(f"\n维度对比:")
    for d in result.dimension_deltas:
        delta_str = f"+{d.delta:.2f}" if d.delta > 0 else f"{d.delta:.2f}"
        print(f"  {d.label:12s}: {d.score_a:.2f} → {d.score_b:.2f} ({delta_str}) | {d.verdict}")

    print(f"\n📄 JSON: {json_path}")
    print(f"📄 Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    exit(main())
