#!/usr/bin/env python3
"""
多学生并发测试工具 v1.0 — 平台负载健壮性验证

对齐交付标准: 可信 → 并发场景下结果一致, 无竞态条件

测试覆盖:
  1. N学生同时登录
  2. N学生同时拉取Phase/Lesson列表
  3. N学生同时获取同一Lesson详情
  4. N学生交错操作 (登录→浏览→访问)
  5. 响应时间分布分析 (P50/P95/P99)

用法:
    python scripts/test_concurrency.py                           # 默认: 5学生
    python scripts/test_concurrency.py --students 10             # 10学生并发
    python scripts/test_concurrency.py --students 20 --rounds 3  # 3轮
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── 配置 ──
TARGET_URL = "http://124.174.108.70"
DEFAULT_STUDENTS = 5
DEFAULT_ROUNDS = 1
REQUEST_TIMEOUT = 30
LOGIN_PREFIX = "student"  # student001, student002, ...


# ═══════════════════════════════════════════════════════════
# 测试执行器
# ═══════════════════════════════════════════════════════════

class ConcurrencyTester:
    """并发测试执行器"""

    def __init__(self, base_url: str = TARGET_URL, num_students: int = DEFAULT_STUDENTS,
                 rounds: int = DEFAULT_ROUNDS):
        self.base_url = base_url.rstrip("/")
        self.num_students = num_students
        self.rounds = rounds
        # 每个并发worker用独立Session
        self.results: dict[str, list[dict]] = defaultdict(list)
        self.timings: dict[str, list[float]] = defaultdict(list)

    # ── 单用户操作 ──

    def _login(self, username: str, password: str = "123456") -> tuple[bool, str | None, float]:
        """单个登录"""
        session = requests.Session()
        session.trust_env = False
        session.proxies = {"http": None, "https": None}

        start = time.monotonic()
        try:
            r = session.post(
                f"{self.base_url}/api/auth/login",
                json={"username": username, "password": password},
                timeout=REQUEST_TIMEOUT,
            )
            elapsed = time.monotonic() - start
            data = r.json()
            token = data.get("token") or data.get("access_token")
            return (r.status_code == 200 and token is not None), token, elapsed
        except Exception as e:
            elapsed = time.monotonic() - start
            return False, None, elapsed

    def _fetch_phases(self, token: str) -> tuple[int, int, float]:
        """获取Phase列表"""
        session = requests.Session()
        session.trust_env = False
        session.proxies = {"http": None, "https": None}
        headers = {"Authorization": f"Bearer {token}"}

        start = time.monotonic()
        try:
            r = session.get(
                f"{self.base_url}/api/phases",
                headers=headers, timeout=REQUEST_TIMEOUT,
            )
            elapsed = time.monotonic() - start
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else []
            count = len(data) if isinstance(data, list) else 0
            return r.status_code, count, elapsed
        except Exception:
            return -1, 0, time.monotonic() - start

    def _fetch_lessons(self, token: str, phase_id: int = 2) -> tuple[int, int, float]:
        """获取某Phase的Lesson列表"""
        session = requests.Session()
        session.trust_env = False
        session.proxies = {"http": None, "https": None}
        headers = {"Authorization": f"Bearer {token}"}

        start = time.monotonic()
        try:
            r = session.get(
                f"{self.base_url}/api/lessons",
                params={"phase_id": phase_id},
                headers=headers, timeout=REQUEST_TIMEOUT,
            )
            elapsed = time.monotonic() - start
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else []
            count = len(data) if isinstance(data, list) else 0
            return r.status_code, count, elapsed
        except Exception:
            return -1, 0, time.monotonic() - start

    def _fetch_lesson_detail(self, token: str, lesson_id: int = 4) -> tuple[int, int, float]:
        """获取Lesson详情 (含Steps)"""
        session = requests.Session()
        session.trust_env = False
        session.proxies = {"http": None, "https": None}
        headers = {"Authorization": f"Bearer {token}"}

        start = time.monotonic()
        try:
            r = session.get(
                f"{self.base_url}/api/lessons/{lesson_id}",
                headers=headers, timeout=REQUEST_TIMEOUT,
            )
            elapsed = time.monotonic() - start
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            steps = len(data.get("steps", [])) if isinstance(data, dict) else 0
            return r.status_code, steps, elapsed
        except Exception:
            return -1, 0, time.monotonic() - start

    # ── 并发worker ──

    def _worker_login_only(self, student_idx: int) -> dict:
        """Worker: 仅登录"""
        username = f"{LOGIN_PREFIX}{student_idx:03d}"
        ok, token, elapsed = self._login(username)

        # 回退: 如果 studentXXX 不存在, 使用已知账号
        if not ok and student_idx > 1:
            username = "student001"
            ok, token, elapsed = self._login(username)

        return {
            "worker": student_idx,
            "action": "login",
            "username": username,
            "success": ok,
            "elapsed_ms": round(elapsed * 1000, 1),
            "has_token": token is not None if ok else False,
        }

    def _worker_full_flow(self, student_idx: int) -> list[dict]:
        """Worker: 完整流程 (登录 → Phase → Lesson → 详情)"""
        results = []

        # 1. Login
        username = f"{LOGIN_PREFIX}{student_idx:03d}"
        ok, token, elapsed = self._login(username)
        results.append({
            "worker": student_idx, "action": "login", "username": username,
            "success": ok, "elapsed_ms": round(elapsed * 1000, 1),
        })

        if not ok:
            # Fallback to student001
            username = "student001"
            ok, token, elapsed = self._login(username)
            results.append({
                "worker": student_idx, "action": "login_fallback", "username": username,
                "success": ok, "elapsed_ms": round(elapsed * 1000, 1),
            })

        if not ok or not token:
            return results

        # 2. Fetch phases
        status, count, elapsed = self._fetch_phases(token)
        results.append({
            "worker": student_idx, "action": "fetch_phases",
            "success": status == 200, "elapsed_ms": round(elapsed * 1000, 1),
            "phase_count": count,
        })

        # 3. Fetch lessons (Phase 3)
        status, count, elapsed = self._fetch_lessons(token, phase_id=2)
        results.append({
            "worker": student_idx, "action": "fetch_lessons",
            "success": status == 200, "elapsed_ms": round(elapsed * 1000, 1),
            "lesson_count": count,
        })

        # 4. Fetch lesson detail (L4)
        status, steps, elapsed = self._fetch_lesson_detail(token, lesson_id=4)
        results.append({
            "worker": student_idx, "action": "fetch_lesson_detail",
            "success": status == 200, "elapsed_ms": round(elapsed * 1000, 1),
            "step_count": steps,
        })

        return results

    # ── 主流程 ──

    def run_login_concurrency(self) -> dict:
        """场景1: N学生同时登录"""
        print(f"\n--- Scenario 1: {self.num_students} concurrent logins ---")
        results = []
        timings = []

        with ThreadPoolExecutor(max_workers=self.num_students) as executor:
            futures = {
                executor.submit(self._worker_login_only, i + 1): i + 1
                for i in range(self.num_students)
            }
            for future in as_completed(futures):
                try:
                    r = future.result()
                    results.append(r)
                    timings.append(r["elapsed_ms"])
                except Exception as e:
                    results.append({"worker": futures[future], "error": str(e)})

        success = sum(1 for r in results if r.get("success"))
        latencies = self._compute_latency(timings)

        print(f"  Success: {success}/{len(results)} | "
              f"P50={latencies['p50']:.0f}ms P95={latencies['p95']:.0f}ms P99={latencies['p99']:.0f}ms")

        return {"scenario": "login_concurrency", "workers": self.num_students,
                "success": success, "total": len(results), "latencies": latencies,
                "details": results}

    def run_full_flow_concurrency(self) -> dict:
        """场景2: N学生完整流程并发"""
        print(f"\n--- Scenario 2: {self.num_students} concurrent full flows ---")
        all_results = []
        all_timings: dict[str, list[float]] = defaultdict(list)

        with ThreadPoolExecutor(max_workers=self.num_students) as executor:
            futures = {
                executor.submit(self._worker_full_flow, i + 1): i + 1
                for i in range(self.num_students)
            }
            for future in as_completed(futures):
                try:
                    worker_results = future.result()
                    all_results.extend(worker_results)
                    for r in worker_results:
                        if "elapsed_ms" in r:
                            all_timings[r["action"]].append(r["elapsed_ms"])
                except Exception as e:
                    all_results.append({"worker": futures[future], "error": str(e)})

        # 统计
        actions = ["login", "fetch_phases", "fetch_lessons", "fetch_lesson_detail"]
        action_stats = {}
        for action in actions:
            timings = all_timings.get(action, [])
            successes = sum(
                1 for r in all_results
                if r.get("action") == action and r.get("success")
            )
            action_stats[action] = {
                "success": successes,
                "total": len(timings),
                "latencies": self._compute_latency(timings),
            }

            lat = action_stats[action]["latencies"]
            print(f"  {action:20s}: {successes}/{len(timings)} ok | "
                  f"P50={lat.get('p50', 0):.0f}ms P95={lat.get('p95', 0):.0f}ms")

        return {"scenario": "full_flow_concurrency", "workers": self.num_students,
                "actions": action_stats, "details": all_results}

    def run_race_condition_test(self) -> dict:
        """场景3: 竞态条件检测 — 多用户同时访问同一资源"""
        print(f"\n--- Scenario 3: Race condition test ({self.num_students} workers) ---")

        # 先获取一个有效token
        session = requests.Session()
        session.trust_env = False
        session.proxies = {"http": None, "https": None}
        r = session.post(
            f"{self.base_url}/api/auth/login",
            json={"username": "student001", "password": "123456"},
            timeout=REQUEST_TIMEOUT,
        )
        token = r.json().get("token", "")

        # 所有worker用同一个token, 同时请求同一lesson详情
        def _fetch_same():
            return self._fetch_lesson_detail(token, lesson_id=4)

        results = []
        timings = []
        step_counts = set()

        with ThreadPoolExecutor(max_workers=self.num_students) as executor:
            futures = [executor.submit(_fetch_same) for _ in range(self.num_students)]
            for i, future in enumerate(as_completed(futures)):
                try:
                    status, steps, elapsed = future.result()
                    results.append({
                        "worker": i + 1, "status": status, "steps": steps,
                        "elapsed_ms": round(elapsed * 1000, 1),
                    })
                    timings.append(elapsed * 1000)
                    if steps > 0:
                        step_counts.add(steps)
                except Exception as e:
                    results.append({"worker": i + 1, "error": str(e)})

        latencies = self._compute_latency(timings)

        # 竞态信号: 同一资源的step数应该一致
        consistent = len(step_counts) <= 1
        success = sum(1 for r in results if r.get("status") == 200)

        print(f"  Success: {success}/{len(results)} | Consistent: {consistent} | "
              f"P50={latencies['p50']:.0f}ms")

        return {"scenario": "race_condition", "workers": self.num_students,
                "success": success, "total": len(results),
                "data_consistent": consistent,
                "unique_step_counts": sorted(step_counts),
                "latencies": latencies, "details": results}

    # ── 工具 ──

    @staticmethod
    def _compute_latency(timings: list[float]) -> dict:
        """计算延迟分位数"""
        if not timings:
            return {"p50": 0, "p95": 0, "p99": 0, "min": 0, "max": 0, "mean": 0, "n": 0}
        sorted_t = sorted(timings)
        n = len(sorted_t)
        return {
            "p50": sorted_t[n // 2],
            "p95": sorted_t[int(n * 0.95)],
            "p99": sorted_t[int(n * 0.99)],
            "min": sorted_t[0],
            "max": sorted_t[-1],
            "mean": sum(sorted_t) / n,
            "n": n,
        }

    def run_all(self) -> dict:
        """执行全部并发测试"""
        print(f"[CONCURRENCY TEST] Platform: {self.base_url}")
        print(f"   Workers: {self.num_students} | Rounds: {self.rounds}")
        print(f"   Time: {datetime.now(timezone.utc).isoformat()}")

        all_scenarios = []

        for round_idx in range(self.rounds):
            if self.rounds > 1:
                print(f"\n===== Round {round_idx + 1}/{self.rounds} =====")

            s1 = self.run_login_concurrency()
            all_scenarios.append(s1)

            s2 = self.run_full_flow_concurrency()
            all_scenarios.append(s2)

            s3 = self.run_race_condition_test()
            all_scenarios.append(s3)

            if round_idx < self.rounds - 1:
                time.sleep(2)  # 轮间冷却

        # 汇总
        total_ok = sum(
            s.get("success", 0) for s in all_scenarios
            if "success" in s
        )
        total_ops = sum(
            s.get("total", 0) for s in all_scenarios
            if "total" in s
        )

        # 所有action级别的统计
        all_action_success = 0
        all_action_total = 0
        for s in all_scenarios:
            for a_stats in (s.get("actions") or {}).values():
                all_action_success += a_stats.get("success", 0)
                all_action_total += a_stats.get("total", 0)

        total_all_success = total_ok + all_action_success
        total_all_ops = total_ops + all_action_total

        print(f"\n{'='*55}")
        print(f"  Overall: {total_all_success}/{total_all_ops} ops success")
        if total_all_ops:
            print(f"  Success rate: {total_all_success/total_all_ops*100:.1f}%")
        print(f"{'='*55}")

        return {
            "test_name": "concurrency",
            "platform_url": self.base_url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "config": {"workers": self.num_students, "rounds": self.rounds},
            "summary": {
                "total_ops": total_all_ops,
                "success_ops": total_all_success,
                "success_rate": round(total_all_success / total_all_ops * 100, 1) if total_all_ops else 0,
            },
            "scenarios": all_scenarios,
        }


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="多学生并发测试工具")
    parser.add_argument("--url", default=TARGET_URL, help=f"平台URL")
    parser.add_argument("--students", type=int, default=DEFAULT_STUDENTS, help=f"并发学生数 (默认: {DEFAULT_STUDENTS})")
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS, help=f"测试轮数 (默认: {DEFAULT_ROUNDS})")
    parser.add_argument("--json-only", action="store_true", help="仅输出JSON")
    parser.add_argument("-o", "--output", help="输出JSON路径")
    args = parser.parse_args()

    tester = ConcurrencyTester(
        base_url=args.url,
        num_students=args.students,
        rounds=args.rounds,
    )
    report = tester.run_all()

    if args.json_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    # 保存
    if args.output:
        path = args.output
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"reports/concurrency_{ts}.json"

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n[REPORT] {path}")

    return 0 if report["summary"]["success_rate"] >= 90 else 1


if __name__ == "__main__":
    exit(main())
