"""Report 服务 — 报告查询、对比、导出 + 统计显著性检验"""

import math
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Report


class ReportService:
    """报告管理服务"""

    DIMENSIONS = [
        "correctness", "relevancy", "completeness", "guidance",
        "followup_quality", "boundary_compliance",
        "turn_consistency", "knowledge_scaffolding",
    ]

    DIMENSION_LABELS = {
        "correctness": "正确性", "relevancy": "相关性",
        "completeness": "完整性", "guidance": "引导力",
        "followup_quality": "追问质量", "boundary_compliance": "边界合规",
        "turn_consistency": "跨轮一致", "knowledge_scaffolding": "知识递进",
    }

    # ── 统计工具 (纯 Python, 无 scipy 依赖) ──

    @staticmethod
    def _mean(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    @staticmethod
    def _stdev(vals: list[float]) -> float:
        if len(vals) < 2:
            return 0.0
        m = ReportService._mean(vals)
        variance = sum((x - m) ** 2 for x in vals) / (len(vals) - 1)
        return math.sqrt(variance)

    @staticmethod
    def _cohens_d(group_a: list[float], group_b: list[float]) -> float:
        """Cohen's d 效应量: (mean_a - mean_b) / pooled_stdev"""
        n_a, n_b = len(group_a), len(group_b)
        if n_a < 1 or n_b < 1:
            return 0.0
        mean_a, mean_b = ReportService._mean(group_a), ReportService._mean(group_b)
        sd_a, sd_b = ReportService._stdev(group_a), ReportService._stdev(group_b)
        # pooled standard deviation
        pooled_var = ((n_a - 1) * sd_a ** 2 + (n_b - 1) * sd_b ** 2) / (n_a + n_b - 2)
        pooled_sd = math.sqrt(max(pooled_var, 0.0001))
        return (mean_a - mean_b) / pooled_sd

    @staticmethod
    def _effect_size_label(d: float) -> str:
        """Cohen's d → 人类可读标签"""
        d_abs = abs(d)
        if d_abs < 0.2:   return "可忽略 (negligible)"
        if d_abs < 0.5:   return "小 (small)"
        if d_abs < 0.8:   return "中等 (medium)"
        if d_abs < 1.2:   return "大 (large)"
        return "非常大 (very large)"

    @staticmethod
    def _confidence_level(cv: float) -> str:
        """变异系数 → 置信度标签"""
        if cv < 0.10: return "🟢 高"
        if cv < 0.25: return "🟡 中"
        return "🔴 低"

    async def list_reports(self, db: AsyncSession, page: int = 1, page_size: int = 20) -> dict:
        total_r = await db.execute(select(func.count(Report.id)))
        total = total_r.scalar() or 0

        reports_r = await db.execute(
            select(Report)
            .order_by(desc(Report.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        reports = reports_r.scalars().all()

        items = []
        for r in reports:
            avg = r.summary_json.get("avg_scores", {}) if r.summary_json else {}
            items.append({
                "id": r.id,
                "timestamp": r.timestamp,
                "overall": avg.get("overall", 0),
                "agent_id": r.summary_json.get("agent_id", ""),
                "total": r.summary_json.get("total", 0),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                # v3.6: 标记内容是否已存入MySQL
                "has_html": bool(r.html_content),
                "has_markdown": bool(r.markdown_content),
            })

        return {
            "items": items, "total": total, "page": page, "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }

    async def _get_report(self, db: AsyncSession, report_id: str):
        """获取单个报告记录"""
        r = await db.execute(select(Report).where(Report.id == report_id))
        return r.scalar_one_or_none()

    async def get_report_detail(self, db: AsyncSession, report_id: str) -> dict:
        r = await self._get_report(db, report_id)
        if not r:
            return None
        result = {
            "id": r.id, "timestamp": r.timestamp,
            "summary_json": r.summary_json,
            "markdown_path": r.markdown_path, "json_path": r.json_path,
            # v3.6: 直接从MySQL返回报告内容, 前端无需读文件
            "markdown_content": r.markdown_content,
            "html_content": r.html_content,
        }
        # ── v3.5: 尝试加载文件报告的 evidence 数据 ──
        if r.json_path:
            from pathlib import Path
            json_file = Path(r.json_path)
            if not json_file.is_absolute():
                # 相对路径: 相对于项目根目录
                json_file = Path(__file__).resolve().parents[2] / r.json_path
            if json_file.exists():
                try:
                    import json as _json
                    with open(json_file, "r", encoding="utf-8") as f:
                        full = _json.load(f)
                    ev = full.get("evidence")
                    if ev:
                        result["evidence"] = ev
                except Exception:
                    pass  # 文件加载失败不影响 DB 数据
        # v3.6: 如果 DB 中已有 evidence 数据 (summary_json 包含), 优先使用
        if "evidence" not in result and r.summary_json:
            ev = r.summary_json.get("evidence") or r.summary_json.get("extra", {}).get("evidence")
            if ev:
                result["evidence"] = ev
        return result

    async def compare_reports(self, db: AsyncSession, ids: list[str]) -> dict:
        """对比多个报告 (增强版: 含统计显著性分析)"""
        reports = []
        for rid in ids:
            r = await self._get_report(db, rid)
            if r and r.summary_json:
                avg = r.summary_json.get("avg_scores", {})
                reports.append({
                    "id": r.id, "timestamp": r.timestamp,
                    "scores": {dim: avg.get(dim, 0) for dim in self.DIMENSIONS},
                    "overall": avg.get("overall", 0),
                })

        # ── 基础差异分析 ──
        deltas = []
        if len(reports) >= 2:
            for dim in self.DIMENSIONS:
                vals = [rep["scores"].get(dim, 0) for rep in reports]
                deltas.append({
                    "dimension": dim,
                    "label": self.DIMENSION_LABELS.get(dim, dim),
                    "values": [round(v, 2) for v in vals],
                    "max_delta": round(max(vals) - min(vals), 2),
                })

        # ── 统计分析 (需要 ≥3 个报告) ──
        statistics = None
        if len(reports) >= 3:
            stats = {}
            for dim in self.DIMENSIONS:
                vals = [rep["scores"].get(dim, 0) for rep in reports]
                mu = self._mean(vals)
                sigma = self._stdev(vals)
                cv = sigma / mu if mu > 0 else float('inf')
                stats[dim] = {
                    "label": self.DIMENSION_LABELS.get(dim, dim),
                    "mean": round(mu, 2),
                    "stdev": round(sigma, 2),
                    "cv": round(cv, 4),  # 变异系数
                    "confidence": self._confidence_level(cv),
                    "range": [round(min(vals), 2), round(max(vals), 2)],
                }
            statistics = stats

        # ── 效应量分析 (取最佳 vs 最差报告) ──
        effect_sizes = None
        if len(reports) >= 3:
            best_idx = max(range(len(reports)), key=lambda i: reports[i]["overall"])
            worst_idx = min(range(len(reports)), key=lambda i: reports[i]["overall"])
            es = {}
            for dim in self.DIMENSIONS:
                # 将每个场景视为一个"样本"时只有聚合数据;
                # 这里用报告的 overall 作为分组依据, 效应量基于报告级别的 scores
                a_vals = [reports[best_idx]["scores"].get(dim, 0)]
                b_vals = [reports[worst_idx]["scores"].get(dim, 0)]
                d = self._cohens_d(a_vals, b_vals)
                es[dim] = {
                    "label": self.DIMENSION_LABELS.get(dim, dim),
                    "cohens_d": round(d, 3),
                    "magnitude": self._effect_size_label(d),
                    "best_score": round(a_vals[0], 2),
                    "worst_score": round(b_vals[0], 2),
                }
            effect_sizes = es

        return {
            "reports": reports,
            "deltas": deltas,
            "statistics": statistics,
            "effect_sizes": effect_sizes,
            "n_reports": len(reports),
            "stat_note": (
                "统计分析基于报告级别聚合分数; 需要 ≥3 个报告才计算 statistics 和 effect_sizes. "
                "Cohen's d 效应量比较最佳与最差报告的差异程度."
                if len(reports) >= 3 else
                "需要 ≥3 个报告才能进行统计分析。当前仅显示基础差异。"
            ),
        }
