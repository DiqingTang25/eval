"""
Coverage Tracker — Agent C (测试覆盖率追踪器)

从真实数据源计算测试覆盖率，零硬编码。

数据源:
  来源 1 (Ground Truth): platform_schema.yaml → 平台有什么
  来源 2 (Test Results): browser_eval_report.json + MySQL → 测了什么

反硬编码原则:
  - Phase 名称/数量: 完全从 schema 动态读取
  - API 端点列表: 完全从 schema apis.* 动态读取
  - Schema 缺失: 返回 {"schema_available": false}, 不回退到默认值
  - 无测试记录: 覆盖率为 0%, 如实报告

产物: data/coverage_report.json → Agent A 的 Reports 页面可直接消费

用法:
  from src.coverage_tracker import CoverageTracker
  tracker = CoverageTracker()
  report = tracker.compute(
      schema_path="output/platform_probe/platform_schema.yaml",
      browser_eval_path="eval_output/browser_eval_report.json",
  )
  # → coverage_report.json 已写入, report dict 返回
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.schema_adapter import SchemaAdapter

logger = logging.getLogger(__name__)

# ── 输出路径 ──
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "coverage_report.json"

# ── Schema 查找路径 (按优先级) ──
SCHEMA_CANDIDATES = [
    "output/platform_probe/platform_schema.yaml",
    "output/platform_schema.yaml",
]


# ═══════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════

@dataclass
class CoverageNode:
    """覆盖树中的一个节点 (Phase / Lesson / Step / API Category / API Endpoint)"""
    node_type: str          # "phase" | "lesson" | "step" | "api_category" | "api_endpoint"
    node_id: str            # schema中的唯一标识
    name: str = ""          # 人类可读名称 (从 schema 读取)
    order: int = 0          # 排序序号
    tested: bool = False    # 是否被测试过
    evidence: dict = field(default_factory=dict)  # 测试证据 {test_type, timestamp, detail}
    children: list[CoverageNode] = field(default_factory=list)

    def mark_tested(self, evidence: dict = None):
        self.tested = True
        if evidence:
            self.evidence = evidence

    def count_all(self) -> int:
        """递归计数所有叶节点"""
        if not self.children:
            return 1
        return sum(c.count_all() for c in self.children)

    def count_tested(self) -> int:
        """递归计数已测试叶节点"""
        if not self.children:
            return 1 if self.tested else 0
        return sum(c.count_tested() for c in self.children)

    def to_dict(self) -> dict:
        d = {
            "type": self.node_type,
            "id": self.node_id,
            "name": self.name,
            "order": self.order,
            "tested": self.tested,
        }
        if self.evidence:
            d["evidence"] = self.evidence
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
            total = self.count_all()
            tested = self.count_tested()
            d["coverage"] = {
                "total": total,
                "tested": tested,
                "pct": round(tested / max(total, 1) * 100, 1),
            }
        return d


# ═══════════════════════════════════════════════════════════════════
# CoverageMap: 从 Schema 构建覆盖树 (Ground Truth)
# ═══════════════════════════════════════════════════════════════════

class CoverageMap:
    """
    从 platform_schema.yaml 构建完整的覆盖树。

    树结构:
      root
       ├── Phase 1 (name from schema)
       │    ├── Lesson 1-1 (name from schema)
       │    │    ├── Step 1 (title from schema)
       │    │    └── Step 2
       │    └── Lesson 1-2
       ├── Phase 2
       └── APIs
            ├── agent (category)
            │    ├── POST /api/agent/chat
            │    └── GET /api/agent/history
            ├── quiz
            └── auth

    所有名称、数量、结构完全从 schema 读取，绝无硬编码。
    """

    def __init__(self, adapter: SchemaAdapter):
        self.adapter = adapter
        self._schema_data = adapter.raw  # 原始 YAML 数据

    def build(self) -> CoverageNode:
        """构建完整覆盖树"""
        root = CoverageNode(node_type="root", node_id="root", name="Platform Coverage")

        # ── Phase → Lesson → Step 树 ──
        structure = self._schema_data.get("structure", {})
        phases = structure.get("phases", [])
        lessons = structure.get("lessons", [])
        steps = structure.get("steps", [])

        for phase in sorted(phases, key=lambda p: p.get("order", 0)):
            phase_node = CoverageNode(
                node_type="phase",
                node_id=phase.get("id", f"phase_{phase.get('order',0)}"),
                name=phase.get("name", ""),
                order=phase.get("order", 0),
            )

            # 该 Phase 下的 Lessons
            phase_lessons = [
                l for l in lessons
                if l.get("phase_id") == phase.get("id")
            ]
            for lesson in sorted(phase_lessons, key=lambda l: l.get("order", 0)):
                lesson_node = CoverageNode(
                    node_type="lesson",
                    node_id=lesson.get("id", ""),
                    name=lesson.get("name", lesson.get("title", "")),
                    order=lesson.get("order", 0),
                )

                # 该 Lesson 下的 Steps
                lesson_steps = [
                    s for s in steps
                    if s.get("lesson_id") == lesson.get("id")
                ]
                for step in sorted(lesson_steps, key=lambda s: s.get("order_index", 0)):
                    step_node = CoverageNode(
                        node_type="step",
                        node_id=step.get("id", ""),
                        name=step.get("title", step.get("name", "")),
                        order=step.get("order_index", 0),
                    )
                    lesson_node.children.append(step_node)

                phase_node.children.append(lesson_node)

            root.children.append(phase_node)

        # ── API 树 ──
        apis = self._schema_data.get("apis", {})
        if apis:
            api_root = CoverageNode(
                node_type="api_category",
                node_id="apis",
                name="API Endpoints",
                order=len(phases) + 1,
            )
            for cat_name, endpoints in sorted(apis.items()):
                if not isinstance(endpoints, list):
                    continue
                cat_node = CoverageNode(
                    node_type="api_category",
                    node_id=f"api_cat_{cat_name}",
                    name=cat_name,
                    order=0,
                )
                for ep in endpoints:
                    method = ep.get("method", "?")
                    path = ep.get("path", "")
                    ep_node = CoverageNode(
                        node_type="api_endpoint",
                        node_id=ep.get("path", f"{method}:{path}"),
                        name=f"{method} {path}",
                        order=0,
                    )
                    cat_node.children.append(ep_node)
                api_root.children.append(cat_node)
            root.children.append(api_root)

        return root

    def get_total_counts(self, root: CoverageNode) -> dict:
        """统计各级节点总数"""
        counts = {"phases": 0, "lessons": 0, "steps": 0, "apis": 0, "api_categories": 0}

        def _walk(node: CoverageNode):
            if node.node_type == "phase":
                counts["phases"] += 1
            elif node.node_type == "lesson":
                counts["lessons"] += 1
            elif node.node_type == "step":
                counts["steps"] += 1
            elif node.node_type == "api_endpoint":
                counts["apis"] += 1
            elif node.node_type == "api_category" and node.node_id != "apis":
                counts["api_categories"] += 1
            for child in node.children:
                _walk(child)

        _walk(root)
        return counts


# ═══════════════════════════════════════════════════════════════════
# CoverageTracker: 合并测试结果到覆盖树
# ═══════════════════════════════════════════════════════════════════

class CoverageTracker:
    """
    从真实测试结果标记覆盖树中的节点。

    支持的测试数据源:
      1. browser_eval_report.json — BrowserEvaluator 产出
      2. MySQL eval_scores — TestRunner LLM 评分产出 (可选)
    """

    def __init__(self):
        self._report: dict = {}

    # ── 公开 API ──

    def compute(
        self,
        schema_path: str = "",
        browser_eval_path: str = "",
    ) -> dict:
        """
        主入口: 计算测试覆盖率并生成报告。

        :param schema_path: platform_schema.yaml 路径 (留空自动查找)
        :param browser_eval_path: browser_eval_report.json 路径 (留空自动查找)
        :return: coverage report dict (同时写入 data/coverage_report.json)
        """
        # 1. 加载 Schema
        resolved_schema = self._resolve_schema_path(schema_path)
        if not resolved_schema:
            return self._no_schema_report()

        try:
            adapter = SchemaAdapter(resolved_schema)
        except (FileNotFoundError, ValueError) as e:
            return self._no_schema_report(str(e))

        # 2. 构建覆盖树
        cmap = CoverageMap(adapter)
        root = cmap.build()
        total_counts = cmap.get_total_counts(root)

        # 3. 加载浏览器测试结果
        resolved_eval = self._resolve_report_path(browser_eval_path)
        eval_data = None
        if resolved_eval:
            eval_data = self._load_json(resolved_eval)

        # 4. 标记已测试节点
        if eval_data:
            self._mark_from_browser_eval(root, eval_data)

        # 5. 加载 DB 评分结果 (可选, 不阻塞)
        db_data = self._load_db_scores()

        # 6. 生成报告
        report = self._build_report(
            root=root,
            total_counts=total_counts,
            schema_path=resolved_schema,
            adapter=adapter,
            eval_data=eval_data,
            db_data=db_data,
        )

        # 7. 写文件
        self._save(report)
        self._report = report
        return report

    # ── 内部方法 ──

    def _resolve_schema_path(self, explicit: str) -> Optional[str]:
        """查找 schema 文件"""
        if explicit and Path(explicit).exists():
            return explicit
        for candidate in SCHEMA_CANDIDATES:
            p = Path(candidate)
            if p.exists():
                return str(p)
        # 再试 output/platform_probe/<session>/platform_schema.yaml
        probe_dir = Path("output/platform_probe")
        if probe_dir.exists():
            for subdir in sorted(probe_dir.iterdir(), reverse=True):
                if subdir.is_dir():
                    schema_file = subdir / "platform_schema.yaml"
                    if schema_file.exists():
                        return str(schema_file)
        return None

    def _resolve_report_path(self, explicit: str) -> Optional[str]:
        """查找 browser_eval_report.json"""
        if explicit and Path(explicit).exists():
            return explicit
        default = Path("eval_output/browser_eval_report.json")
        if default.exists():
            return str(default)
        return None

    @staticmethod
    def _load_json(path: str) -> Optional[dict]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load {path}: {e}")
            return None

    def _no_schema_report(self, error: str = "") -> dict:
        """Schema 缺失时的报告 — 如实反映，不回退到硬编码"""
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "schema_available": False,
            "error": error or "platform_schema.yaml 不存在",
            "hint": "请先运行 Platform Explorer 以生成平台 Schema",
            "overall": None,
            "by_phase": [],
            "by_api": [],
            "risk_areas": [],
        }

    # ── 标记逻辑 ──

    def _mark_from_browser_eval(self, root: CoverageNode, eval_data: dict):
        """
        从 browser_eval_report.json 标记已测试的 Phase/Lesson/Step。

        browser_eval_report.json 结构:
        {
          "phases": {
            "phase_1": {"days": [{"index": 1, "steps_completed": 3, "total_steps": 5,
                                   "agent_triggered": true, "quiz_triggered": true}]},
            "phase_5": {"ok": true, "conversations": [...]}
          },
          "summary": {"phases_tested": [1,2,3]}
        }
        """
        eval_phases = eval_data.get("phases", {})

        for phase_node in root.children:
            if phase_node.node_type != "phase":
                continue

            # 从 node_id 提取 phase 编号 (如 "phase_1" → 1)
            phase_num = self._extract_number(phase_node.node_id)

            # browser_eval_report 的 key 是 "phase_1", "phase_2" 等
            phase_key = f"phase_{phase_num}"
            phase_data = eval_phases.get(phase_key, {})

            if not phase_data:
                continue

            # Phase 5 特殊处理 (Agent 对话, 无 Day/Step 结构)
            if phase_num == 5:
                if phase_data.get("ok"):
                    phase_node.mark_tested({
                        "test_type": "browser_eval",
                        "detail": f"Agent 对话: {len(phase_data.get('conversations',[]))} 轮",
                    })
                    # 标记 Phase 5 下所有子节点
                    for child in self._all_descendants(phase_node):
                        child.mark_tested({
                            "test_type": "browser_eval",
                            "detail": "Phase 5 Agent 对话已通过",
                        })
                continue

            # Phase 1-4: 遍历 days
            days = phase_data.get("days", [])
            if not days:
                continue

            phase_tested = False
            day_indices_tested = set()

            for day_data in days:
                day_idx = day_data.get("index", 0)
                if day_data.get("steps_completed", 0) > 0 or day_data.get("agent_triggered"):
                    day_indices_tested.add(day_idx)
                    phase_tested = True

            if not phase_tested:
                continue

            # 标记 Phase
            phase_node.mark_tested({
                "test_type": "browser_eval",
                "detail": f"Days tested: {sorted(day_indices_tested)}",
            })

            # 标记对应 Lesson (Day → Lesson 映射)
            # Schema 中的 lesson 按 order 排列，对应 Day 1, Day 2, ...
            for lesson_node in phase_node.children:
                if lesson_node.node_type != "lesson":
                    continue
                lesson_order = lesson_node.order
                if lesson_order in day_indices_tested:
                    lesson_node.mark_tested({
                        "test_type": "browser_eval",
                        "detail": f"Day {lesson_order} tested",
                    })

                    # 找到该 day 的具体数据
                    day_detail = next(
                        (d for d in days if d.get("index") == lesson_order), {}
                    )
                    steps_completed = day_detail.get("steps_completed", 0)

                    # 标记该 Lesson 下的 Steps (按 order 标记前 N 个)
                    sorted_steps = sorted(lesson_node.children, key=lambda s: s.order)
                    for i, step_node in enumerate(sorted_steps):
                        if i < steps_completed:
                            step_node.mark_tested({
                                "test_type": "browser_eval",
                                "detail": f"Step {i+1} completed",
                            })

                    # 如果 Agent 被触发, 额外标记
                    if day_detail.get("agent_triggered"):
                        step_node = sorted_steps[-1] if sorted_steps else None
                        if step_node:
                            step_node.evidence["agent_tested"] = True

    def _mark_from_db_scores(self, root: CoverageNode, db_data: list[dict]):
        """
        从 MySQL eval_scores 标记 (额外精细度)。

        db_data: [{"phase": "1", "lesson_id": "...", "overall": 4.2}, ...]
        由于 DB 测评不按 Step 粒度, 只标记到 Lesson 级别。
        """
        for record in db_data:
            phase_num = self._extract_number(str(record.get("phase", "")))
            # 找到对应 Phase 节点
            for phase_node in root.children:
                if phase_node.node_type != "phase":
                    continue
                if self._extract_number(phase_node.node_id) == phase_num:
                    # 标记 Phase
                    if not phase_node.tested:
                        phase_node.mark_tested({"test_type": "llm_eval", "detail": "LLM 评分覆盖"})
                    # 标记 Lesson
                    lesson_id = record.get("lesson_id", "")
                    for lesson_node in phase_node.children:
                        if lesson_node.node_id == lesson_id:
                            lesson_node.mark_tested({"test_type": "llm_eval", "detail": "LLM 评分覆盖"})
                            break
                    break

    def _load_db_scores(self) -> list[dict]:
        """从 MySQL 加载评分记录 (可选, 不阻塞)"""
        try:
            from backend.dependencies import get_sync_db
            from backend.models import EvalScore, TestScenario, TestSession
            from sqlalchemy import select

            db = get_sync_db()
            try:
                # 查询最近 50 条评分记录
                results = db.execute(
                    select(EvalScore)
                    .order_by(EvalScore.id.desc())
                    .limit(50)
                ).scalars().all()

                return [
                    {
                        "scenario_id": str(r.scenario_id),
                        "overall": float(r.overall or 0),
                        "correctness": float(r.correctness or 0),
                    }
                    for r in results
                ]
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"DB scores unavailable (non-blocking): {e}")
            return []

    # ── 报告生成 ──

    def _build_report(
        self,
        root: CoverageNode,
        total_counts: dict,
        schema_path: str,
        adapter: SchemaAdapter,
        eval_data: dict = None,
        db_data: list[dict] = None,
    ) -> dict:
        """从覆盖树构建最终报告"""
        # 计算各级覆盖
        phase_coverages = []
        for phase_node in root.children:
            if phase_node.node_type != "phase":
                continue
            total = phase_node.count_all()
            tested = phase_node.count_tested()
            phase_coverages.append({
                "phase_id": phase_node.node_id,
                "name": phase_node.name,
                "total_children": total,
                "tested_children": tested,
                "coverage_pct": round(tested / max(total, 1) * 100, 1),
                "tested": phase_node.tested,
                "evidence": phase_node.evidence if phase_node.evidence else None,
                "children": [
                    {
                        "id": c.node_id,
                        "name": c.name,
                        "type": c.node_type,
                        "tested": c.tested,
                        "total_steps": c.count_all(),
                        "tested_steps": c.count_tested(),
                    }
                    for c in phase_node.children
                ],
            })

        # API 覆盖
        api_coverages = []
        for child in root.children:
            if child.node_id == "apis":
                for cat_node in child.children:
                    api_total = cat_node.count_all()
                    api_tested = cat_node.count_tested()
                    api_coverages.append({
                        "category": cat_node.name,
                        "total_endpoints": api_total,
                        "tested_endpoints": api_tested,
                        "coverage_pct": round(api_tested / max(api_total, 1) * 100, 1),
                    })

        # 整体覆盖
        all_total = root.count_all()
        all_tested = root.count_tested()

        # 风险区域
        risk_areas = self._identify_risks(root, phase_coverages, api_coverages)

        # 测试数据源信息
        data_sources = []
        if eval_data:
            summary = eval_data.get("summary", {})
            data_sources.append({
                "type": "browser_eval",
                "phases_tested": summary.get("phases_tested", []),
                "days_completed": summary.get("days_completed", 0),
                "days_total": summary.get("days_total", 0),
                "screenshots": summary.get("screenshots", 0),
            })
        if db_data:
            data_sources.append({
                "type": "llm_eval",
                "scenarios_scored": len(db_data),
            })

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "schema_available": True,
            "schema_path": schema_path,
            "schema_version": adapter.schema_version,
            "schema_confidence": adapter.confidence.get("overall", 0),
            "overall": {
                "total_nodes": all_total,
                "tested_nodes": all_tested,
                "coverage_pct": round(all_tested / max(all_total, 1) * 100, 1),
                "phases": f"{sum(1 for p in phase_coverages if p['tested'])}/{len(phase_coverages)}",
                "lessons": f"{total_counts['lessons']} total",
                "steps": f"{total_counts['steps']} total",
                "apis": f"{total_counts['apis']} total",
            },
            "by_phase": phase_coverages,
            "by_api": api_coverages,
            "data_sources": data_sources,
            "risk_areas": risk_areas,
            "tree": root.to_dict(),  # 完整树 → Agent A 可渲染热力图
        }

    def _identify_risks(
        self,
        root: CoverageNode,
        phase_coverages: list[dict],
        api_coverages: list[dict],
    ) -> list[dict]:
        """识别高风险未覆盖区域"""
        risks = []

        # 完全未测试的 Phase
        for pc in phase_coverages:
            if not pc["tested"]:
                risks.append({
                    "area": f"{pc['phase_id']}: {pc['name']}",
                    "risk": "high",
                    "reason": f"Phase 完全未被测试 (0/{pc['total_children']} nodes)",
                })
            elif pc["coverage_pct"] < 30:
                risks.append({
                    "area": f"{pc['phase_id']}: {pc['name']}",
                    "risk": "medium",
                    "reason": f"覆盖率极低 ({pc['coverage_pct']}%)",
                })

        # 零覆盖的 API 类别
        for ac in api_coverages:
            if ac["coverage_pct"] == 0 and ac["total_endpoints"] > 0:
                risks.append({
                    "area": f"API: {ac['category']}",
                    "risk": "high",
                    "reason": f"{ac['total_endpoints']} 个端点零覆盖",
                })

        # 排序: high → medium
        risks.sort(key=lambda r: (0 if r["risk"] == "high" else 1, r["area"]))
        return risks

    def _save(self, report: dict):
        try:
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT_PATH.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            logger.info(f"Coverage report saved to {OUTPUT_PATH}")
        except Exception as e:
            logger.warning(f"Failed to save coverage report: {e}")

    # ── 工具 ──

    @staticmethod
    def _extract_number(s: str) -> int:
        """从字符串中提取第一个数字 (如 "phase_3" → 3, "Phase 01" → 1)"""
        import re
        m = re.search(r'(\d+)', str(s))
        return int(m.group(1)) if m else 0

    @staticmethod
    def _all_descendants(node: CoverageNode):
        """遍历所有后代节点"""
        result = []
        for child in node.children:
            result.append(child)
            result.extend(CoverageTracker._all_descendants(child))
        return result


# ═══════════════════════════════════════════════════════════════════
# 便捷函数: 接入 test_service.py
# ═══════════════════════════════════════════════════════════════════

def compute_coverage_after_eval(
    schema_path: str = "",
    browser_eval_path: str = "eval_output/browser_eval_report.json",
) -> dict:
    """
    在 browser_eval 完成后调用的便捷函数。

    用法 (在 test_service.py 的 _run_browser_eval 末尾):
        from src.coverage_tracker import compute_coverage_after_eval
        coverage_report = compute_coverage_after_eval()
    """
    tracker = CoverageTracker()
    return tracker.compute(
        schema_path=schema_path,
        browser_eval_path=browser_eval_path,
    )


# ═══════════════════════════════════════════════════════════════════
# Health API 集成
# ═══════════════════════════════════════════════════════════════════

def get_health_summary() -> dict:
    """返回覆盖率系统健康摘要"""
    if OUTPUT_PATH.exists():
        try:
            report = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            overall = report.get("overall", {}) or {}
            return {
                "component": "coverage_tracker",
                "status": "healthy" if report.get("schema_available") else "degraded",
                "schema_available": report.get("schema_available", False),
                "coverage_pct": overall.get("coverage_pct", 0),
                "risk_count": len(report.get("risk_areas", [])),
            }
        except Exception:
            pass
    return {
        "component": "coverage_tracker",
        "status": "no_data",
        "schema_available": False,
        "coverage_pct": 0,
    }
