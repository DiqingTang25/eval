"""
Anomaly Detector — Agent C (平台结构变更自动检测)

对比当前 platform_schema.yaml 与基线 → 检测 API/结构变更 → 生成告警报告。

用途:
  - CI 定时巡检: 平台悄悄更新了 API → 自动发现
  - Explorer 重新运行后: 对比新旧 Schema → 展示变更清单
  - 测试前: 检查 Schema 是否过期 → 建议重新探索

产物: data/anomaly_report.json
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

BASELINE_PATH = Path("data/anomaly_baseline.json")
REPORT_PATH = Path("data/anomaly_report.json")


# ═══════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════

class ChangeRecord:
    """单条变更记录"""
    def __init__(self, change_type: str, path: str, before: Any, after: Any):
        self.change_type = change_type  # added | removed | modified
        self.path = path                 # 如 "apis.auth.0.path"
        self.before = before
        self.after = after

    def to_dict(self) -> dict:
        return {
            "type": self.change_type,
            "path": self.path,
            "before": str(self.before)[:200] if self.before else None,
            "after": str(self.after)[:200] if self.after else None,
        }

    @property
    def severity(self) -> str:
        if self.change_type == "removed":
            return "high"
        if self.change_type == "added":
            return "medium"
        return "low"


class AnomalyReport:
    """变更检测报告"""
    def __init__(self):
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.baseline_exists = False
        self.schema_available = False
        self.changes: list[ChangeRecord] = []
        self.summary = {
            "added": 0, "removed": 0, "modified": 0,
            "high": 0, "medium": 0, "low": 0,
        }

    def add(self, change: ChangeRecord):
        self.changes.append(change)
        self.summary[change.change_type] += 1
        self.summary[change.severity] += 1

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "baseline_exists": self.baseline_exists,
            "schema_available": self.schema_available,
            "summary": self.summary,
            "changes": [c.to_dict() for c in self.changes],
            "needs_attention": self.summary["high"] > 0 or self.summary["removed"] > 0,
            "recommendation": self._recommend(),
        }

    def _recommend(self) -> str:
        if self.summary["removed"] > 0:
            return f"检测到 {self.summary['removed']} 项移除 — 建议重新运行 Explorer 并更新 MCP Tools"
        if self.summary["added"] > 0:
            return f"检测到 {self.summary['added']} 项新增 — 新 API/结构可被 Planner 自动纳入测试计划"
        if self.summary["modified"] > 0:
            return "检测到结构变更 — 确认变更是有意的, 更新基线"
        return "无变更 — 平台结构稳定"


# ═══════════════════════════════════════════════════════════════════
# 核心: Schema Diff 引擎
# ═══════════════════════════════════════════════════════════════════

class AnomalyDetector:
    """
    对比当前 Schema 与基线, 检测变更。

    用法:
        detector = AnomalyDetector()
        report = detector.detect()
        # → data/anomaly_report.json 已写入

        # 手动对比
        report = detector.compare(current_schema, baseline_schema)
    """

    def __init__(self):
        self._baseline: Optional[dict] = None
        self._report: Optional[AnomalyReport] = None

    # ── 公开 API ──

    def detect(self) -> AnomalyReport:
        """
        主入口: 读当前 Schema → 对比基线 → 生成报告。
        """
        report = AnomalyReport()

        # 1. 加载基线
        baseline = self._load_baseline()
        if baseline is None:
            report.baseline_exists = False
            report.schema_available = False
            self._save_report(report)
            self._report = report
            return report
        report.baseline_exists = True

        # 2. 加载当前 Schema
        current = self._load_current_schema()
        if current is None:
            report.schema_available = False
            self._save_report(report)
            self._report = report
            return report
        report.schema_available = True

        # 3. Diff
        self._diff_schemas(baseline, current, report)

        # 4. 保存
        self._save_report(report)
        self._report = report
        return report

    def save_baseline(self, schema_path: str = ""):
        """
        将当前 Schema 保存为基线。
        在 Explorer 完成后调用, 建立"已知良好"的快照。
        """
        current = self._load_current_schema(schema_path)
        if current is None:
            logger.warning("Cannot save baseline: no schema available")
            return False

        # 只保留可比较的结构部分 (去时间戳等易变字段)
        snapshot = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "schema_path": schema_path or "auto-detected",
            "structure": {
                "phase_count": len(current.get("structure", {}).get("phases", [])),
                "lesson_count": len(current.get("structure", {}).get("lessons", [])),
                "step_count": len(current.get("structure", {}).get("steps", [])),
            },
            "apis": current.get("apis", {}),
            "auth": {
                "type": current.get("auth", {}).get("type", ""),
                "login_url": current.get("auth", {}).get("login_url", ""),
            },
            "target_url": current.get("target_url", ""),
        }

        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._baseline = snapshot
        logger.info(f"Baseline saved: {snapshot['structure']}")
        return True

    # ── Diff 逻辑 ──

    def _diff_schemas(self, baseline: dict, current: dict, report: AnomalyReport):
        """递归对比两个 Schema"""

        # ── API 端点对比 ──
        baseline_apis = self._flatten_apis(baseline.get("apis", {}))
        current_apis = self._flatten_apis(current.get("apis", {}))

        baseline_keys = set(baseline_apis.keys())
        current_keys = set(current_apis.keys())

        # 移除的 API
        for key in baseline_keys - current_keys:
            report.add(ChangeRecord("removed", f"apis.{key}",
                baseline_apis[key], None))

        # 新增的 API
        for key in current_keys - baseline_keys:
            report.add(ChangeRecord("added", f"apis.{key}",
                None, current_apis[key]))

        # 修改的 API
        for key in baseline_keys & current_keys:
            b_api = baseline_apis[key]
            c_api = current_apis[key]
            if b_api.get("method") != c_api.get("method"):
                report.add(ChangeRecord("modified", f"apis.{key}.method",
                    b_api.get("method"), c_api.get("method")))
            if b_api.get("path") != c_api.get("path"):
                report.add(ChangeRecord("modified", f"apis.{key}.path",
                    b_api.get("path"), c_api.get("path")))

        # ── 结构对比 ──
        b_struct = baseline.get("structure", {})
        c_struct = current.get("structure", {})

        b_phases = b_struct.get("phase_count", len(baseline.get("structure", {}).get("phases", [])))
        c_phases = len(current.get("structure", {}).get("phases", []))

        if b_phases != c_phases:
            report.add(ChangeRecord("modified", "structure.phases",
                f"{b_phases} phases", f"{c_phases} phases"))

        b_lessons = b_struct.get("lesson_count", len(baseline.get("structure", {}).get("lessons", [])))
        c_lessons = len(current.get("structure", {}).get("lessons", []))

        if b_lessons != c_lessons:
            report.add(ChangeRecord("modified", "structure.lessons",
                f"{b_lessons} lessons", f"{c_lessons} lessons"))

        b_steps = b_struct.get("step_count", len(baseline.get("structure", {}).get("steps", [])))
        c_steps = len(current.get("structure", {}).get("steps", []))

        if b_steps != c_steps:
            report.add(ChangeRecord("modified", "structure.steps",
                f"{b_steps} steps", f"{c_steps} steps"))

        # ── Auth 变更 ──
        b_auth_type = baseline.get("auth", {}).get("type", "")
        c_auth_type = current.get("auth", {}).get("type", "")
        if b_auth_type != c_auth_type:
            report.add(ChangeRecord("modified", "auth.type",
                b_auth_type, c_auth_type))

        b_login = baseline.get("auth", {}).get("login_url", "")
        c_login = current.get("auth", {}).get("login_url", "")
        if b_login != c_login:
            report.add(ChangeRecord("modified", "auth.login_url",
                b_login, c_login))

        # ── URL 变更 ──
        b_url = baseline.get("target_url", "")
        c_url = current.get("target_url", "")
        if b_url and c_url and b_url != c_url:
            report.add(ChangeRecord("modified", "target_url",
                b_url, c_url))

    # ── 内部工具 ──

    @staticmethod
    def _flatten_apis(apis: dict) -> dict:
        """展平 API 结构: {category: [endpoints]} → {"category.0": endpoint_dict}"""
        flat = {}
        for cat, endpoints in apis.items():
            if not isinstance(endpoints, list):
                continue
            for i, ep in enumerate(endpoints):
                if isinstance(ep, dict):
                    flat[f"{cat}.{i}"] = {
                        "path": ep.get("path", ""),
                        "method": ep.get("method", ""),
                        "confidence": ep.get("confidence", 0),
                    }
        return flat

    def _load_current_schema(self, path: str = "") -> Optional[dict]:
        """加载当前 Schema"""
        import yaml
        candidates = [
            path,
            "output/platform_probe/platform_schema.yaml",
            "output/platform_schema.yaml",
        ]
        for c in candidates:
            p = Path(c)
            if c and p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        return yaml.safe_load(f)
                except Exception as e:
                    logger.warning(f"Schema load failed: {e}")

        # 尝试 session 子目录
        probe_dir = Path("output/platform_probe")
        if probe_dir.exists():
            for subdir in sorted(probe_dir.iterdir(), reverse=True):
                if subdir.is_dir():
                    sf = subdir / "platform_schema.yaml"
                    if sf.exists():
                        try:
                            import yaml
                            with open(sf, "r", encoding="utf-8") as f:
                                return yaml.safe_load(f)
                        except Exception:
                            continue
        return None

    def _load_baseline(self) -> Optional[dict]:
        if self._baseline:
            return self._baseline
        if BASELINE_PATH.exists():
            try:
                self._baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
                return self._baseline
            except Exception as e:
                logger.warning(f"Baseline load failed: {e}")
        return None

    def _save_report(self, report: AnomalyReport):
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @property
    def last_report(self) -> Optional[AnomalyReport]:
        return self._report


# ═══════════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════════

def save_baseline_now(schema_path: str = "") -> bool:
    """便捷: 保存当前 Schema 为基线"""
    detector = AnomalyDetector()
    return detector.save_baseline(schema_path)


def detect_anomalies() -> AnomalyReport:
    """便捷: 运行一次检测"""
    detector = AnomalyDetector()
    return detector.detect()


# ═══════════════════════════════════════════════════════════════════
# Health API 集成
# ═══════════════════════════════════════════════════════════════════

def get_health_summary() -> dict:
    """返回异常检测系统健康摘要"""
    report_exists = REPORT_PATH.exists()
    if report_exists:
        try:
            data = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
            return {
                "component": "anomaly_detector",
                "status": "attention" if data.get("needs_attention") else "healthy",
                "baseline_exists": data.get("baseline_exists", False),
                "changes_total": sum(data.get("summary", {}).values()),
                "high_severity": data.get("summary", {}).get("high", 0),
            }
        except Exception:
            pass
    return {
        "component": "anomaly_detector",
        "status": "no_data",
        "baseline_exists": BASELINE_PATH.exists(),
        "changes_total": 0,
    }
