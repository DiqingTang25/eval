#!/usr/bin/env python3
"""
PRD API 就绪监听器 v1.0

监控 PRD v10.0 (2026-07-09) 定义的7个API端点是否已上线。
当检测到 404→200 状态变化时, 记录上线时间并触发验收测试。

用法:
    python src/prd_api_monitor.py --check          # 检查所有PRD API状态
    python src/prd_api_monitor.py --watch          # 持续监听 (每5分钟)
    python src/prd_api_monitor.py --baseline       # 建立基线快照
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.platform_client import PlatformClient

BASELINE_FILE = Path(__file__).parent.parent / "data" / "prd_api_baseline.json"

# PRD v10.0 定义的API端点
PRD_APIS = [
    {
        "path": "/api/quiz/payload",
        "method": "POST",
        "prd_section": "8.2 Agent出题 → 接口保存",
        "priority": "P0",
        "acceptance_criteria": ["AC-Q04: 题目结构统一", "AC-Q05: 知识点绑定"],
        "test_body": {"question_id": "test", "lesson_id": "p1_l01", "question_type": "single_choice"},
    },
    {
        "path": "/api/quiz/session",
        "method": "GET",
        "prd_section": "8.1 Quiz触发 → 获取当前Lesson Quiz",
        "priority": "P0",
        "acceptance_criteria": ["AC-Q01: Quiz按Lesson触发", "AC-Q02: 每Lesson一次"],
    },
    {
        "path": "/api/quiz/submit",
        "method": "POST",
        "prd_section": "8.1 Quiz提交 → 画像更新",
        "priority": "P0",
        "acceptance_criteria": ["AC-04: Quiz提交", "AC-Q08: 隐藏答案"],
        "test_body": {"attempt_id": "test", "answers": []},
    },
    {
        "path": "/api/recommendations/1",
        "method": "GET",
        "prd_section": "11. Step渲染配置 → GET recommendations",
        "priority": "P0",
        "acceptance_criteria": ["AC-S01: Step最小渲染", "AC-S02: 配置读取"],
    },
    {
        "path": "/api/events",
        "method": "POST",
        "prd_section": "12.3 事件上报",
        "priority": "P1",
        "acceptance_criteria": ["AC-03: 学习行为记录"],
        "test_body": {"event_type": "lesson_entered", "lesson_id": 1},
    },
    {
        "path": "/api/agent/events",
        "method": "POST",
        "prd_section": "12.3 Agent事件上报",
        "priority": "P1",
        "acceptance_criteria": [],
        "test_body": {"event_type": "agent_opened", "lesson_id": 1},
    },
    {
        "path": "/api/profile/me",
        "method": "GET",
        "prd_section": "10. 学生知识点画像",
        "priority": "P1",
        "acceptance_criteria": ["AC-S05: 自然语言推荐原因"],
    },
]


class PRDAPIMonitor:
    """PRD API 就绪状态监听器"""

    def __init__(self, base_url: str = None):
        self.base_url = base_url or "http://124.174.108.70"
        self.client = PlatformClient(base_url=self.base_url, verbose=False)
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.proxies = {"http": None, "https": None}

    def check_all(self) -> dict:
        """检查所有PRD API的当前状态"""
        self.client.login()
        token = self.client.token
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        results = []
        for api in PRD_APIS:
            result = self._check_api(api, headers)
            results.append(result)

        online = sum(1 for r in results if r["status"] == "online")
        offline = sum(1 for r in results if r["status"] == "offline")
        error = sum(1 for r in results if r["status"] == "error")

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform_url": self.base_url,
            "summary": {
                "total": len(results),
                "online": online,
                "offline": offline,
                "error": error,
                "ready_pct": round(online / len(results) * 100) if results else 0,
                "all_ready": online == len(results),
            },
            "apis": results,
        }

    def _check_api(self, api_def: dict, headers: dict) -> dict:
        """检查单个API"""
        path = api_def["path"]
        method = api_def["method"]
        url = f"{self.base_url}{path}"

        try:
            if method == "GET":
                r = self.session.get(url, headers=headers, timeout=10)
            else:
                body = api_def.get("test_body", {})
                r = self.session.post(url, headers=headers, json=body, timeout=10)

            status_code = r.status_code
            if status_code == 404:
                api_status = "offline"
                detail = "API未部署 (404)"
            elif status_code == 422:
                api_status = "partial"
                detail = f"API存在但参数校验失败 (422): {r.text[:100]}"
            elif status_code < 400:
                api_status = "online"
                detail = f"API已上线 (HTTP {status_code})"
            else:
                api_status = "error"
                detail = f"HTTP {status_code}: {r.text[:100]}"
        except Exception as e:
            api_status = "error"
            status_code = 0
            detail = str(e)[:100]

        return {
            "path": path,
            "method": method,
            "priority": api_def["priority"],
            "prd_section": api_def["prd_section"],
            "acceptance_criteria": api_def["acceptance_criteria"],
            "status": api_status,
            "http_code": status_code,
            "detail": detail,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def save_baseline(self) -> Path:
        """保存当前API状态为基线快照"""
        report = self.check_all()
        with open(BASELINE_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return BASELINE_FILE

    def compare_with_baseline(self) -> dict:
        """与基线对比, 检测API状态变化"""
        if not BASELINE_FILE.exists():
            return {"error": "基线文件不存在, 请先运行 --baseline"}

        with open(BASELINE_FILE, "r", encoding="utf-8") as f:
            baseline = json.load(f)

        current = self.check_all()
        changes = []

        baseline_apis = {a["path"]: a["status"] for a in baseline.get("apis", [])}
        for api in current["apis"]:
            path = api["path"]
            old_status = baseline_apis.get(path, "unknown")
            new_status = api["status"]
            if old_status != new_status:
                changes.append({
                    "path": path,
                    "old_status": old_status,
                    "new_status": new_status,
                    "detail": api["detail"],
                    "significance": "NEW_FEATURE_ONLINE" if new_status == "online" and old_status == "offline"
                    else "REGRESSION" if new_status == "offline" and old_status == "online"
                    else "CHANGE",
                })

        return {
            "baseline_time": baseline.get("timestamp"),
            "current_time": current["timestamp"],
            "changes": changes,
            "has_changes": len(changes) > 0,
            "current": current["summary"],
        }


def main():
    ap = argparse.ArgumentParser(description="PRD API 就绪监听器")
    ap.add_argument("--check", action="store_true", help="检查所有PRD API状态")
    ap.add_argument("--baseline", action="store_true", help="建立基线快照")
    ap.add_argument("--compare", action="store_true", help="与基线对比")
    ap.add_argument("--watch", action="store_true", help="持续监听 (每5分钟)")
    ap.add_argument("--url", type=str, default="http://124.174.108.70")
    ap.add_argument("--output", type=str, help="JSON报告输出路径")
    args = ap.parse_args()

    monitor = PRDAPIMonitor(base_url=args.url)

    if args.baseline:
        path = monitor.save_baseline()
        print(f"[PRD Monitor] 基线已保存: {path}")
        report = monitor.check_all()
        s = report["summary"]
        print(f"  状态: {s['online']}在线 / {s['offline']}离线 / {s['error']}错误 (共{s['total']})")
        return

    if args.compare:
        result = monitor.compare_with_baseline()
        if "error" in result:
            print(f"[ERROR] {result['error']}")
            return
        print(f"[PRD Monitor] 基线对比: {result['baseline_time'][:19]} → {result['current_time'][:19]}")
        if result["changes"]:
            print(f"  检测到 {len(result['changes'])} 个变化:")
            for c in result["changes"]:
                print(f"    [{c['significance']}] {c['path']}: {c['old_status']} → {c['new_status']}")
        else:
            print(f"  无变化")
        return

    # Default: --check
    report = monitor.check_all()
    s = report["summary"]
    print(f"[PRD Monitor] 平台: {report['platform_url']}")
    print(f"[PRD Monitor] 时间: {report['timestamp'][:19]}")
    print(f"[PRD Monitor] API状态: {s['online']}在线 / {s['offline']}离线 / {s['error']}错误 (共{s['total']})")
    print(f"[PRD Monitor] 就绪率: {s['ready_pct']}%")
    print()

    for api in report["apis"]:
        icon = {"online": "[ON]", "offline": "[OFF]", "partial": "[~]", "error": "[ERR]"}.get(api["status"], "[?]")
        print(f"  {icon} {api['method']:4s} {api['path']:35s} [{api['priority']}] {api['detail'][:80]}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n报告已保存: {args.output}")

    sys.exit(0 if s["all_ready"] else 1)


if __name__ == "__main__":
    main()
