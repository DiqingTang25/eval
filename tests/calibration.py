#!/usr/bin/env python3
"""
人类校准基线框架 (Human Calibration Baseline) — P0-4

BAT标准对标:
  字节跳动: Cohen's κ ≥ 0.7 或 Spearman ρ ≥ 0.8
  阿里巴巴: ≥200条人类专家标注验证集, 计算MAE和Pearson r
  腾讯: 每个维度独立校准, 不允许仅校准overall (overall可能正负抵消)

用法:
    # 1) 从 golden_qa_bank 创建校准模板 (添加 human_scores 字段)
    python tests/calibration.py --create-template --size 50

    # 2) 人工填写 human_scores 后, 运行评估+校准
    python tests/calibration.py --calibrate calibration_set.json

    # 3) 快速健康检查 (用模拟数据验证统计计算)
    python tests/calibration.py --self-test
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

CALIBRATION_DIR = Path(__file__).parent.parent / "data"
GOLDEN_QA_FILE = CALIBRATION_DIR / "golden_qa_bank.json"
DEFAULT_CALIBRATION_SET = CALIBRATION_DIR / "calibration_set.json"

# 10个评分维度 (对齐 evaluator.DIMENSION_NAMES)
CALIBRATION_DIMS = [
    "correctness", "relevancy", "completeness",
    "guidance", "followup_quality", "boundary_compliance",
    "turn_consistency", "knowledge_scaffolding",
    "overhelping", "fairness_bias",
]

# ── BAT 标准阈值 ──
COHENS_KAPPA_MIN = 0.70    # 字节跳动标准
SPEARMAN_RHO_MIN = 0.80    # 字节跳动标准
MAE_MAX = 0.50             # 平均绝对误差上限 (5分制)
PEARSON_R_MIN = 0.75       # 皮尔逊相关系数下限


# ═══════════════════════════════════════════════════════════════
# 统计工具函数
# ═══════════════════════════════════════════════════════════════

def mean(values: list[float]) -> float:
    """算术平均"""
    return sum(values) / len(values) if values else 0.0


def _rank(values: list[float]) -> list[float]:
    """计算秩次 (处理平局: 使用平均秩)"""
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j < len(indexed) and indexed[j][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j - 1) / 2.0 + 1
        for k in range(i, j):
            ranks[indexed[k][0]] = avg_rank
        i = j
    return ranks


def pearson_r(x: list[float], y: list[float]) -> float:
    """皮尔逊相关系数"""
    n = len(x)
    if n < 3:
        return 0.0
    mx, my = mean(x), mean(y)
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    sx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    sy = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if sx < 1e-10 or sy < 1e-10:
        return 0.0
    return cov / (sx * sy)


def spearman_rho(x: list[float], y: list[float]) -> float:
    """斯皮尔曼等级相关系数"""
    if len(x) < 3:
        return 0.0
    rx = _rank(x)
    ry = _rank(y)
    return pearson_r(rx, ry)


def cohens_kappa_weighted(
    human_scores: list[float],
    llm_scores: list[float],
    n_categories: int = 5,
) -> float:
    """
    加权 Cohen's κ (二次权重 / Quadratic Weighted Kappa).

    用于有序分类评分 (1-5分制), 对高偏差给予更高惩罚。
    QWK = 1 - (Σ w_ij * O_ij) / (Σ w_ij * E_ij)
    其中 w_ij = ((i - j) / (k - 1))²
    """
    k = n_categories
    n = len(human_scores)
    if n < 2:
        return 0.0

    # 离散化到 1..k
    def discretize(v: float) -> int:
        return max(1, min(k, round(v)))

    h = [discretize(s) for s in human_scores]
    m = [discretize(s) for s in llm_scores]

    # 混淆矩阵 O (observed)
    O = [[0] * k for _ in range(k)]
    for hi, mi in zip(h, m):
        O[hi - 1][mi - 1] += 1

    # 权重矩阵 (quadratic)
    W = [[((i - j) / (k - 1)) ** 2 for j in range(k)] for i in range(k)]

    # 期望矩阵 E (chance agreement)
    h_marg = [sum(O[i][j] for j in range(k)) for i in range(k)]
    m_marg = [sum(O[i][j] for i in range(k)) for j in range(k)]
    E = [[h_marg[i] * m_marg[j] / n for j in range(k)] for i in range(k)]

    # QWK
    num = sum(W[i][j] * O[i][j] for i in range(k) for j in range(k))
    den = sum(W[i][j] * E[i][j] for i in range(k) for j in range(k))

    if den < 1e-10:
        return 1.0 if num < 1e-10 else 0.0
    return 1.0 - num / den


def mae(x: list[float], y: list[float]) -> float:
    """平均绝对误差"""
    if not x:
        return 0.0
    return sum(abs(xi - yi) for xi, yi in zip(x, y)) / len(x)


# ═══════════════════════════════════════════════════════════════
# 校准执行
# ═══════════════════════════════════════════════════════════════

def run_calibration(calibration_file: Path) -> dict:
    """
    对校准集执行全维度校准, 计算所有 BAT 标准指标。

    返回:
      {
        "overall": {metrics...},
        "per_dimension": {dim: {metrics...}, ...},
        "passed": bool,
        "failures": [...],
        "summary": str,
      }
    """
    if not calibration_file.exists():
        return {"error": f"校准文件不存在: {calibration_file}"}

    with open(calibration_file, "r", encoding="utf-8") as f:
        cal_data = json.load(f)

    if isinstance(cal_data, dict):
        items = cal_data.get("items", [])
    elif isinstance(cal_data, list):
        items = cal_data
    else:
        return {"error": "校准文件格式错误"}

    # 筛选有效条目 (必须同时有 human_scores 和 evaluated_scores)
    valid = []
    for it in items:
        hs = it.get("human_scores") or {}
        es = it.get("evaluated_scores") or {}
        if hs and es:
            valid.append((hs, es, it.get("qa_id", "?")))

    n = len(valid)
    if n < 10:
        return {
            "error": f"有效校准样本不足 (n={n}, 需要 ≥10)",
            "n_samples": n,
        }

    # ── 每维度计算 ──
    per_dim: dict[str, dict] = {}
    all_h_overall = []
    all_e_overall = []

    for dim in CALIBRATION_DIMS + ["overall"]:
        h_vals = []
        e_vals = []
        for hs, es, _ in valid:
            hv = hs.get(dim)
            ev = es.get(dim)
            if hv is not None and ev is not None:
                h_vals.append(float(hv))
                e_vals.append(float(ev))

        if len(h_vals) < 5:
            per_dim[dim] = {
                "n_samples": len(h_vals),
                "warning": "样本不足, 指标仅供参考",
                "mae": mae(h_vals, e_vals) if h_vals else None,
                "pearson_r": None,
                "spearman_rho": None,
                "cohens_kappa": None,
                "cv_human": None,
                "cv_llm": None,
            }
            continue

        sd_h = float(__import__("statistics").stdev(h_vals)) if len(h_vals) >= 2 else 0.0
        sd_e = float(__import__("statistics").stdev(e_vals)) if len(e_vals) >= 2 else 0.0

        per_dim[dim] = {
            "n_samples": len(h_vals),
            "mae": round(mae(h_vals, e_vals), 3),
            "pearson_r": round(pearson_r(h_vals, e_vals), 3),
            "spearman_rho": round(spearman_rho(h_vals, e_vals), 3),
            "cohens_kappa": round(cohens_kappa_weighted(h_vals, e_vals), 3),
            "human_mean": round(mean(h_vals), 2),
            "llm_mean": round(mean(e_vals), 2),
            "human_stdev": round(sd_h, 3),
            "llm_stdev": round(sd_e, 3),
            "cv_human": round(sd_h / abs(mean(h_vals)), 3) if abs(mean(h_vals)) > 0.001 else None,
            "cv_llm": round(sd_e / abs(mean(e_vals)), 3) if abs(mean(e_vals)) > 0.001 else None,
        }

        if dim == "overall":
            all_h_overall = h_vals
            all_e_overall = e_vals

    # ── 通过/失败判定 ──
    failures = []
    overall_k = per_dim.get("overall", {}).get("cohens_kappa", 0) or 0
    overall_rho = per_dim.get("overall", {}).get("spearman_rho", 0) or 0
    overall_mae = per_dim.get("overall", {}).get("mae", 999) or 999
    overall_r = per_dim.get("overall", {}).get("pearson_r", 0) or 0

    if overall_k < COHENS_KAPPA_MIN:
        failures.append(f"Cohen's κ={overall_k:.3f} < {COHENS_KAPPA_MIN} (overall)")
    if overall_rho < SPEARMAN_RHO_MIN:
        failures.append(f"Spearman ρ={overall_rho:.3f} < {SPEARMAN_RHO_MIN} (overall)")
    if overall_mae > MAE_MAX:
        failures.append(f"MAE={overall_mae:.3f} > {MAE_MAX} (overall)")
    if overall_r < PEARSON_R_MIN:
        failures.append(f"Pearson r={overall_r:.3f} < {PEARSON_R_MIN} (overall)")

    # 每维度检查
    for dim in CALIBRATION_DIMS:
        pdim = per_dim.get(dim, {})
        k = pdim.get("cohens_kappa") or 0
        rho = pdim.get("spearman_rho") or 0
        dim_mae = pdim.get("mae") or 999
        if k < COHENS_KAPPA_MIN:
            failures.append(f"[{dim}] Cohen's κ={k:.3f} < {COHENS_KAPPA_MIN}")
        if rho < SPEARMAN_RHO_MIN:
            failures.append(f"[{dim}] Spearman ρ={rho:.3f} < {SPEARMAN_RHO_MIN}")
        if dim_mae > MAE_MAX:
            failures.append(f"[{dim}] MAE={dim_mae:.3f} > {MAE_MAX}")

    passed = len(failures) == 0

    summary_lines = [
        f"Result: {'[PASS]' if passed else '[FAIL]'}",
        f"样本数: {n}",
        f"",
        f"Overall 指标:",
        f"  Cohen's κ = {overall_k:.3f}  (要求 ≥{COHENS_KAPPA_MIN})",
        f"  Spearman ρ = {overall_rho:.3f}  (要求 ≥{SPEARMAN_RHO_MIN})",
        f"  Pearson r  = {overall_r:.3f}  (要求 ≥{PEARSON_R_MIN})",
        f"  MAE        = {overall_mae:.3f}  (要求 ≤{MAE_MAX})",
        f"",
        f"每维度 κ / ρ / MAE:",
    ]
    for dim in CALIBRATION_DIMS:
        pdim = per_dim.get(dim, {})
        k = pdim.get("cohens_kappa", "?")
        rho = pdim.get("spearman_rho", "?")
        m = pdim.get("mae", "?")
        status = "[PASS]" if (
            isinstance(k, (int, float)) and isinstance(rho, (int, float))
            and k >= COHENS_KAPPA_MIN and rho >= SPEARMAN_RHO_MIN
        ) else "[FAIL]"
        summary_lines.append(
            f"  {status} {dim:30s} κ={str(k):>6s}  ρ={str(rho):>6s}  MAE={str(m):>6s}"
        )

    if failures:
        summary_lines.append(f"\n失败明细:")
        for f in failures:
            summary_lines.append(f"  [FAIL] {f}")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "n_samples": n,
        "thresholds": {
            "cohens_kappa_min": COHENS_KAPPA_MIN,
            "spearman_rho_min": SPEARMAN_RHO_MIN,
            "mae_max": MAE_MAX,
            "pearson_r_min": PEARSON_R_MIN,
        },
        "overall": per_dim.get("overall", {}),
        "per_dimension": {d: per_dim.get(d, {}) for d in CALIBRATION_DIMS},
        "passed": passed,
        "failures": failures,
        "summary": "\n".join(summary_lines),
    }


# ═══════════════════════════════════════════════════════════════
# 校准集创建
# ═══════════════════════════════════════════════════════════════

def create_calibration_template(size: int = 50, output_file: Path = None) -> Path:
    """
    从 golden_qa_bank 分层采样, 创建带 human_scores 占位字段的校准模板。

    输出格式:
      {
        "calibration_meta": {
          "version": "1.0",
          "created_at": "...",
          "n_items": 50,
          "instructions": "人工专家需为每条QA在10个维度上打分(1-5分)"
        },
        "items": [
          {
            "qa_id": "...",
            "question": "...",
            "golden_answer": "...",
            "human_scores": {dim: null, ...},
            "evaluated_scores": null
          },
          ...
        ]
      }
    """
    output_file = output_file or DEFAULT_CALIBRATION_SET

    # 加载 golden_qa_bank
    if not GOLDEN_QA_FILE.exists():
        print(f"[CALIBRATION] golden_qa_bank 不存在, 用内置模板")
        items = _fallback_calibration_items(size)
    else:
        with open(GOLDEN_QA_FILE, "r", encoding="utf-8") as f:
            bank = json.load(f)
        if isinstance(bank, dict):
            items = bank.get("items", bank.get("qa_pairs", []))
        elif isinstance(bank, list):
            items = bank
        else:
            items = []

        # 分层采样: 按 phase + type 均匀分布
        items = _stratified_sample(items, size)

    # 构建校准模板
    template = {
        "calibration_meta": {
            "version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "n_items": len(items),
            "scoring_scale": "1-5 (1=最差, 5=最优)",
            "dimensions": [
                {"key": "correctness", "label": "事实正确性", "description": "回答的事实准确度"},
                {"key": "relevancy", "label": "答案相关性", "description": "回答是否切题"},
                {"key": "completeness", "label": "内容完整性", "description": "关键知识点覆盖度"},
                {"key": "guidance", "label": "教学引导力", "description": "Socratic教学/支架引导"},
                {"key": "followup_quality", "label": "追问响应质量", "description": "多轮追问后的回答质量"},
                {"key": "boundary_compliance", "label": "边界合规性", "description": "是否基于课程知识作答"},
                {"key": "turn_consistency", "label": "跨轮一致性", "description": "多轮间信息一致性"},
                {"key": "knowledge_scaffolding", "label": "知识递进性", "description": "知识层级递进"},
                {"key": "overhelping", "label": "过度帮助", "description": "是否直接给代码/答案"},
                {"key": "fairness_bias", "label": "公平性偏差", "description": "跨学生画像的一致性"},
            ],
            "instructions": (
                "请人类专家为每条 QA 在以上 10 个维度上独立打分(1-5分)。\n"
                "打分后填入 items[].human_scores 字段, null值表示该维度不适用。\n"
                "然后运行: python tests/calibration.py --calibrate <本文件>\n"
                "BAT标准: Cohen's κ ≥ 0.70, Spearman ρ ≥ 0.80, MAE ≤ 0.50"
            ),
        },
        "items": [
            {
                "qa_id": qa.get("qa_id", f"CAL_{i:04d}"),
                "phase": qa.get("phase", ""),
                "type": qa.get("type", ""),
                "difficulty": qa.get("difficulty", ""),
                "question": qa.get("question", ""),
                "golden_answer": qa.get("golden_answer", ""),
                "human_scores": {d: None for d in CALIBRATION_DIMS},
                "human_overall": None,
                "evaluated_scores": None,
            }
            for i, qa in enumerate(items)
        ],
    }

    # 修复重复 key
    for item in template["items"]:
        pass  # 上面有重复的 human_scores, 但 Python dict 最后 key 胜出, 没问题

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)

    print(f"[CALIBRATION] Template created: {output_file}")
    print(f"  样本数: {len(items)}")
    print(f"  下一步: 人类专家填写 human_scores → python tests/calibration.py --calibrate {output_file.name}")
    return output_file


def _stratified_sample(items: list[dict], size: int) -> list[dict]:
    """分层采样: 按 phase 均匀分布"""
    if len(items) <= size:
        return items

    # 按 phase 分组
    by_phase: dict[str, list] = defaultdict(list)
    for q in items:
        phase = q.get("phase", "Unknown")
        by_phase[phase].append(q)

    phases = sorted(by_phase.keys())
    per_phase = max(1, size // len(phases))

    selected = []
    for phase in phases:
        pool = by_phase[phase]
        step = max(1, len(pool) // per_phase) if per_phase < len(pool) else 1
        taken = pool[::step][:per_phase]
        selected.extend(taken)

    # 补充或裁剪
    if len(selected) < size:
        remaining = [q for q in items if q not in selected]
        selected.extend(remaining[:size - len(selected)])
    return selected[:size]


def _fallback_calibration_items(size: int) -> list[dict]:
    """golden_qa_bank 不可用时的内置最小校准集"""
    return [
        {
            "qa_id": f"CAL_FALLBACK_{i:03d}",
            "phase": "PHASE 01",
            "type": "概念解释",
            "difficulty": "中等",
            "question": f"请解释课程中的核心概念 #{i}",
            "golden_answer": f"概念 #{i} 的详细解释...",
        }
        for i in range(min(size, 20))
    ]


# ═══════════════════════════════════════════════════════════════
# 自测 (验证统计方法正确性)
# ═══════════════════════════════════════════════════════════════

def self_test() -> bool:
    """用模拟数据验证所有统计指标的计算正确性"""
    print("=" * 60)
    print("校准框架自测 (Self-Test)")
    print("=" * 60)

    # Test 1: 完全一致 → κ ≈ 1, ρ ≈ 1, MAE ≈ 0
    perfect_h = [5.0, 4.0, 3.0, 2.0, 1.0, 5.0, 4.0, 3.0, 2.0, 1.0]
    perfect_e = [5.0, 4.0, 3.0, 2.0, 1.0, 5.0, 4.0, 3.0, 2.0, 1.0]
    k = cohens_kappa_weighted(perfect_h, perfect_e)
    rho = spearman_rho(perfect_h, perfect_e)
    r = pearson_r(perfect_h, perfect_e)
    m = mae(perfect_h, perfect_e)
    print(f"\n[Test 1] 完全一致:")
    print(f"  Cohen's κ = {k:.3f} (期望 ~1.0)")
    print(f"  Spearman ρ = {rho:.3f} (期望 1.0)")
    print(f"  Pearson r  = {r:.3f} (期望 1.0)")
    print(f"  MAE        = {m:.3f} (期望 0.0)")
    assert k > 0.99, f"完全一致时κ应≈1, 实际{k:.3f}"
    assert rho > 0.99, f"完全一致时ρ应≈1, 实际{rho:.3f}"
    assert r > 0.99, f"完全一致时r应≈1, 实际{r:.3f}"
    assert m < 0.01, f"完全一致时MAE应≈0, 实际{m:.3f}"

    # Test 2: 完全相反 → κ ≈ 0
    opposite_h = [1.0, 2.0, 3.0, 4.0, 5.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    opposite_e = [5.0, 4.0, 3.0, 2.0, 1.0, 5.0, 4.0, 3.0, 2.0, 1.0]
    k2 = cohens_kappa_weighted(opposite_h, opposite_e)
    rho2 = spearman_rho(opposite_h, opposite_e)
    m2 = mae(opposite_h, opposite_e)
    print(f"\n[Test 2] 反向打分:")
    print(f"  Cohen's κ = {k2:.3f} (期望 <0)")
    print(f"  Spearman ρ = {rho2:.3f} (期望 <0)")
    print(f"  MAE        = {m2:.3f} (期望 >2)")
    assert k2 < 0, f"反向时κ应<0, 实际{k2:.3f}"
    assert rho2 < 0, f"反向时ρ应<0, 实际{rho2:.3f}"

    # Test 3: 随机偏差 → 中等指标
    noisy_h = [4.0, 3.0, 5.0, 2.0, 4.0, 3.0, 5.0, 2.0, 4.0, 3.0]
    noisy_e = [4.5, 2.5, 4.5, 2.5, 3.5, 3.5, 4.5, 2.5, 3.5, 3.5]
    k3 = cohens_kappa_weighted(noisy_h, noisy_e)
    rho3 = spearman_rho(noisy_h, noisy_e)
    r3 = pearson_r(noisy_h, noisy_e)
    m3 = mae(noisy_h, noisy_e)
    print(f"\n[Test 3] 有噪声:")
    print(f"  Cohen's κ = {k3:.3f}")
    print(f"  Spearman ρ = {rho3:.3f}")
    print(f"  Pearson r  = {r3:.3f}")
    print(f"  MAE        = {m3:.3f}")
    # 不做断言, 仅验证计算不崩溃

    # Test 4: 单值输入
    k4 = cohens_kappa_weighted([3.0], [4.0])
    assert k4 == 0.0, "单值κ应为0"

    # Test 5: 空输入
    k5 = cohens_kappa_weighted([], [])
    assert k5 == 0.0, "空输入κ应为0"

    print(f"\n{'=' * 60}")
    print("[PASS] All self-tests passed")
    print(f"{'=' * 60}")
    return True


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="人类校准基线框架 — 对齐BAT标准 (Cohen's κ / Spearman ρ / MAE / Pearson r)"
    )
    ap.add_argument(
        "--create-template", action="store_true",
        help="从 golden_qa_bank 创建校准模板 (含 human_scores 占位)",
    )
    ap.add_argument(
        "--size", type=int, default=50,
        help="校准集大小 (默认50, 阿里标准≥200)",
    )
    ap.add_argument(
        "--calibrate", type=str, metavar="FILE",
        help="对已标注的校准集执行校准评估",
    )
    ap.add_argument(
        "--output", type=str, default=None,
        help="校准报告输出路径 (默认打印到控制台)",
    )
    ap.add_argument(
        "--self-test", action="store_true",
        help="自测统计方法正确性",
    )

    args = ap.parse_args()

    if args.self_test:
        ok = self_test()
        sys.exit(0 if ok else 1)

    if args.create_template:
        output = Path(args.output) if args.output else None
        create_calibration_template(size=args.size, output_file=output)
        return

    if args.calibrate:
        cal_file = Path(args.calibrate)
        result = run_calibration(cal_file)

        if "error" in result:
            print(f"[ERROR] {result['error']}")
            sys.exit(1)

        print(result["summary"])

        if args.output:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n校准报告已保存: {out_path}")

        sys.exit(0 if result.get("passed") else 1)

    ap.print_help()


if __name__ == "__main__":
    main()
