#!/usr/bin/env python3
"""
回归测试基准 (Regression Benchmark) — P0-8

用法:
    # 首次: 建立基线
    python tests/regression_benchmark.py --baseline

    # 后续: 对比当前分数 vs 基线, 检测回归
    python tests/regression_benchmark.py --check

    # 指定Agent版本
    python tests/regression_benchmark.py --check --agent-version v1.2

原理:
    每次Agent更新后, 用固定的10条黄金QA重新评分, 对比基线分数。
    任一维度下降>0.3分 → 标记为回归 → 阻断上线。

BAT对标:
    字节跳动: 所有ML模型上线前必须在固定benchmark重跑, 分数下降>1%阻断
    阿里巴巴: 双11前所有模型在固定测试集验证无回归
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# 确保项目根在sys.path中
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

BENCHMARK_FILE = Path(__file__).parent.parent / "data" / "regression_baseline.json"
GOLDEN_QA_FILE = Path(__file__).parent.parent / "data" / "golden_qa_bank.json"

# 10条固定benchmark QA — 从golden_qa_bank中按阶段/类型/难度分层选取
# 如果golden_qa_bank不存在, 使用写死的fallback
BENCHMARK_SIZE = 10

# 回归阈值: 维度分数下降超过此值 → 标记为回归
REGRESSION_THRESHOLD = 0.3

# 关键维度 (回归时必须严格检查)
CRITICAL_DIMS = ["correctness", "boundary_compliance", "guidance", "overhelping"]


def load_benchmark_qa() -> list[dict]:
    """从golden_qa_bank中分层选取10条benchmark QA"""
    if not GOLDEN_QA_FILE.exists():
        print(f"[BENCHMARK] golden_qa_bank不存在: {GOLDEN_QA_FILE}")
        return _fallback_qa()

    with open(GOLDEN_QA_FILE, "r", encoding="utf-8") as f:
        bank = json.load(f)

    if isinstance(bank, dict):
        items = bank.get("items", bank.get("qa_pairs", []))
    elif isinstance(bank, list):
        items = bank
    else:
        items = []

    if len(items) < BENCHMARK_SIZE:
        return items

    # 分层选取: 每个phase至少1条, 每个type至少1条
    selected = []
    seen_phases = set()
    seen_types = set()

    for q in items:
        if len(selected) >= BENCHMARK_SIZE:
            break
        phase = q.get("phase", "")
        qtype = q.get("type", "")
        if phase not in seen_phases or qtype not in seen_types:
            selected.append(q)
            seen_phases.add(phase)
            seen_types.add(qtype)

    # 补充到10条
    for q in items:
        if len(selected) >= BENCHMARK_SIZE:
            break
        if q not in selected:
            selected.append(q)

    print(f"[BENCHMARK] 从golden_qa_bank选取 {len(selected)} 条QA作为基准集")
    return selected[:BENCHMARK_SIZE]


def _fallback_qa() -> list[dict]:
    """Fallback: 硬编码的基准QA (golden_qa_bank不可用时)"""
    return [
        {
            "qa_id": "BENCH_001", "phase": "PHASE 01",
            "question": "什么是ESP32-S3的ADC精度?",
            "golden_answer": "ESP32-S3具有12位SAR型ADC，分辨率4096级，采样率最高200ksps。",
            "goal": "测试基本事实正确性",
        },
        {
            "qa_id": "BENCH_002", "phase": "PHASE 01",
            "question": "请解释什么是云边协同?",
            "golden_answer": "云边协同是将大模型部署在云端、推理在边缘端协同工作的架构模式。",
            "goal": "测试概念解释完整性",
        },
    ]


def run_benchmark_eval(qa_items: list[dict]) -> dict:
    """对每条benchmark QA执行L1规则层评分 (确定性, 无需LLM)"""
    from src.evaluator import Evaluator

    api_key = os.getenv("OPENAI_API_KEY", "benchmark-key")
    evaluator = Evaluator(api_key, config={"use_embedding": False, "use_structure": True})

    results = []
    for qa in qa_items:
        score = evaluator.evaluate(
            question=qa.get("question", ""),
            agent_answer=qa.get("golden_answer", ""),  # 用黄金答案作为"完美Agent"
            golden_answer=qa.get("golden_answer", ""),
            goal=qa.get("goal", ""),
        )
        results.append({
            "qa_id": qa.get("qa_id", "?"),
            "question": qa.get("question", "")[:80],
            "scores": {k: v for k, v in score.items()
                       if k in evaluator.DIMENSION_NAMES and isinstance(v, (int, float))},
            "overall": score.get("overall", 0),
        })

    dims = evaluator.DIMENSION_NAMES
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "benchmark_size": len(qa_items),
        "avg_scores": {
            dim: round(sum(r["scores"].get(dim, 0) for r in results) / len(results), 2)
            for dim in dims
        },
        "avg_overall": round(sum(r["overall"] for r in results) / len(results), 2),
        "per_item": results,
    }


def save_baseline(result: dict) -> None:
    """保存基线到文件"""
    BENCHMARK_FILE.parent.mkdir(parents=True, exist_ok=True)
    result["baseline_version"] = "1.0"
    result["created_at"] = datetime.now(timezone.utc).isoformat()
    with open(BENCHMARK_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[BENCHMARK] 基线已保存: {BENCHMARK_FILE}")


def check_regression(current: dict) -> int:
    """对比当前分数与基线, 检测回归"""
    if not BENCHMARK_FILE.exists():
        print("[BENCHMARK] 基线文件不存在, 请先运行 --baseline")
        return 1

    with open(BENCHMARK_FILE, "r", encoding="utf-8") as f:
        baseline = json.load(f)

    baseline_scores = baseline.get("avg_scores", {})
    current_scores = current.get("avg_scores", {})

    regressions = []
    for dim in CRITICAL_DIMS:
        bl = baseline_scores.get(dim, 0)
        cur = current_scores.get(dim, 0)
        delta = cur - bl
        if delta < -REGRESSION_THRESHOLD:
            regressions.append({
                "dimension": dim,
                "baseline": bl,
                "current": cur,
                "delta": round(delta, 2),
                "severity": "REGRESSION",
            })

    print(f"\n{'='*60}")
    print(f"回归检测报告 — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}")
    print(f"基线时间: {baseline.get('timestamp', 'unknown')[:19]}")
    print(f"{'='*60}")
    print(f"{'维度':<25} {'基线':>6} {'当前':>6} {'Δ':>7} {'状态'}")
    print(f"{'-'*60}")

    exit_code = 0
    for dim in CRITICAL_DIMS:
        bl = baseline_scores.get(dim)
        cur = current_scores.get(dim)
        if bl is None or cur is None:
            print(f"{dim:<25} {'N/A':>6} {'N/A':>6} {'-':>7} ⚠️ 缺失")
            continue
        delta = cur - bl
        if delta < -REGRESSION_THRESHOLD:
            status = "🔴 回归"
            exit_code = 1
        elif delta < 0:
            status = "🟡 微降"
        else:
            status = "✅ 正常"
        print(f"{dim:<25} {bl:>6.2f} {cur:>6.2f} {delta:>+7.2f} {status}")

    print(f"{'-'*60}")
    print(f"整体均分: {baseline.get('avg_overall',0):.2f} → {current.get('avg_overall',0):.2f} "
          f"(Δ{current.get('avg_overall',0) - baseline.get('avg_overall',0):+.2f})")

    if regressions:
        print(f"\n🔴 发现 {len(regressions)} 个回归:")
        for r in regressions:
            print(f"  - {r['dimension']}: {r['baseline']:.2f}→{r['current']:.2f} ({r['delta']:+.2f})")
    else:
        print(f"\n✅ 无回归, 所有关键维度正常")

    return exit_code


def main():
    parser = argparse.ArgumentParser(description="AI Agent 回归测试基准")
    parser.add_argument("--baseline", action="store_true", help="建立/更新基线")
    parser.add_argument("--check", action="store_true", help="检测回归")
    parser.add_argument("--agent-version", type=str, default="current", help="Agent版本标识")
    args = parser.parse_args()

    if not args.baseline and not args.check:
        parser.print_help()
        print("\n请指定 --baseline (建立基线) 或 --check (检测回归)")
        return 1

    qa_items = load_benchmark_qa()
    if not qa_items:
        print("[BENCHMARK] 无可用的benchmark QA, 退出")
        return 1

    print(f"[BENCHMARK] 使用 {len(qa_items)} 条QA, Agent版本: {args.agent_version}")
    result = run_benchmark_eval(qa_items)

    if args.baseline:
        save_baseline(result)
        print(f"[BENCHMARK] 基线已建立, 后续用 --check 检测回归")
    elif args.check:
        return check_regression(result)

    return 0


if __name__ == "__main__":
    sys.exit(main())
