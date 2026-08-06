#!/usr/bin/env python3
"""
CI/CD 自主巡检脚本 — Agent C

云端定时运行 (systemd timer 或 cron):
  */30 * * * * /opt/agent_eval/venv/bin/python /opt/agent_eval/scripts/ci_quick_check.py

检查项:
  1. Schema 可用性
  2. MCP Server 健康
  3. Coverage 报告生成
  4. Multi-Agent 模式可用性 (端点可达)
  5. 自愈事件统计
  6. 视觉断言统计

输出: data/ci_status.json (最新巡检状态)
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).parent.parent
os.chdir(str(project_root))
sys.path.insert(0, str(project_root))

OUTPUT = project_root / "data" / "ci_status.json"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)


def check(label: str) -> dict:
    """单个检查项包装器"""
    try:
        return {"status": "ok", "label": label}
    except Exception as e:
        return {"status": "error", "label": label, "error": str(e)[:200]}


def main():
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {},
    }

    # ── 1. Schema 可用性 ──
    try:
        from src.schema_adapter import SchemaAdapter
        candidates = [
            "output/platform_probe/platform_schema.yaml",
            "output/platform_schema.yaml",
        ]
        found = False
        for c in candidates:
            if Path(c).exists():
                adapter = SchemaAdapter(c)
                results["checks"]["schema"] = {
                    "status": "ok",
                    "available": True,
                    "confidence": adapter.confidence.get("overall", 0),
                    "phases": len(adapter.raw.get("structure", {}).get("phases", [])),
                }
                found = True
                break
        if not found:
            results["checks"]["schema"] = {"status": "degraded", "available": False, "hint": "Run Explorer"}
    except Exception as e:
        results["checks"]["schema"] = {"status": "error", "error": str(e)[:200]}

    # ── 2. MCP Server 健康 ──
    try:
        from src.mcp_server import get_health_summary
        results["checks"]["mcp"] = get_health_summary()
    except Exception as e:
        results["checks"]["mcp"] = {"status": "error", "error": str(e)[:200]}

    # ── 3. Coverage Report ──
    try:
        from src.coverage_tracker import CoverageTracker
        tracker = CoverageTracker()
        report = tracker.compute()
        results["checks"]["coverage"] = {
            "status": "ok" if report.get("schema_available") else "degraded",
            "schema_available": report.get("schema_available", False),
            "overall": report.get("overall"),
        }
    except Exception as e:
        results["checks"]["coverage"] = {"status": "error", "error": str(e)[:200]}

    # ── 4. Self-Healing 统计 ──
    try:
        from src.self_healing import get_healing_log
        summary = get_healing_log().summary()
        results["checks"]["self_healing"] = {
            "status": "ok",
            "total_events": summary["total"],
            "success_rate": summary["success_rate"],
        }
    except Exception as e:
        results["checks"]["self_healing"] = {"status": "error", "error": str(e)[:200]}

    # ── 5. Visual Assertion 统计 ──
    try:
        from src.visual_assertion import get_va_log
        summary = get_va_log().summary()
        results["checks"]["visual_assertion"] = {
            "status": "ok",
            "total": summary["total"],
            "pass_rate": summary["pass_rate"],
        }
    except Exception as e:
        results["checks"]["visual_assertion"] = {"status": "error", "error": str(e)[:200]}

    # ── 6. LLM 可用性 ──
    try:
        from src.llm_client import is_available
        results["checks"]["llm"] = {
            "status": "ok" if is_available() else "degraded",
            "text_available": is_available(require_vision=False),
            "vision_available": is_available(require_vision=True),
        }
    except Exception as e:
        results["checks"]["llm"] = {"status": "error", "error": str(e)[:200]}

    # ── 汇总 ──
    statuses = [c.get("status", "error") for c in results["checks"].values()]
    errors = statuses.count("error")
    degraded = statuses.count("degraded")
    results["summary"] = {
        "total_checks": len(statuses),
        "ok": statuses.count("ok"),
        "degraded": degraded,
        "error": errors,
        "healthy": errors == 0,
    }

    # 写文件
    OUTPUT.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"CI Quick Check: {results['summary']['ok']}/{results['summary']['total_checks']} ok, "
          f"{degraded} degraded, {errors} errors → {OUTPUT}")
    return 0 if results["summary"]["healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
