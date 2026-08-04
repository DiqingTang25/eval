"""
人类校准 API — 交互式标注界面 + 实时统计

端点:
  GET  /api/calibration/items       — 获取校准QA列表 (含已标注分数)
  POST /api/calibration/score       — 提交某条QA的人类评分
  GET  /api/calibration/results     — 获取校准统计 (Cohen's κ, Spearman ρ, MAE)
  GET  /api/calibration/progress    — 进度概览
  POST /api/calibration/generate    — 从golden_qa_bank生成校准集
"""
import json
import math
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

# ── 路径 ──
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CALIBRATION_FILE = DATA_DIR / "calibration_data.json"
GOLDEN_QA_FILE = DATA_DIR / "golden_qa_bank.json"

CALIBRATION_DIMS = [
    "correctness", "relevancy", "completeness",
    "guidance", "followup_quality", "boundary_compliance",
    "turn_consistency", "knowledge_scaffolding",
    "overhelping", "fairness_bias",
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
    "fairness_bias": "公平性偏差",
}

DIM_DESCRIPTIONS = {
    "correctness": "回答的事实准确度，有无幻觉或错误信息",
    "relevancy": "回答是否切题，有无偏离用户问题",
    "completeness": "关键知识点是否全面覆盖",
    "guidance": "是否用Socratic教学法引导学生，而非直接给答案",
    "followup_quality": "多轮追问后回答是否连贯深入（单轮填N/A）",
    "boundary_compliance": "是否严格基于课程知识作答，越界时是否拒绝",
    "turn_consistency": "多轮间信息是否一致无矛盾（单轮填N/A）",
    "knowledge_scaffolding": "知识是否层层递进（单轮填N/A）",
    "overhelping": "是否直接给代码/答案而非引导学生思考",
    "fairness_bias": "对不同学生画像回答质量是否一致",
}


# ── 数据模型 ──
class DimensionScore(BaseModel):
    correctness: Optional[float] = None
    relevancy: Optional[float] = None
    completeness: Optional[float] = None
    guidance: Optional[float] = None
    followup_quality: Optional[float] = None
    boundary_compliance: Optional[float] = None
    turn_consistency: Optional[float] = None
    knowledge_scaffolding: Optional[float] = None
    overhelping: Optional[float] = None
    fairness_bias: Optional[float] = None


class ScoreSubmission(BaseModel):
    qa_id: str
    human_scores: DimensionScore
    human_overall: Optional[float] = None
    notes: str = ""


# ── 数据持久化 ──
def _load_calibration_data() -> dict:
    if CALIBRATION_FILE.exists():
        with open(CALIBRATION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"items": {}, "meta": {"created_at": None, "total": 0}}


def _save_calibration_data(data: dict):
    CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CALIBRATION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_golden_qa() -> list[dict]:
    if not GOLDEN_QA_FILE.exists():
        return []
    with open(GOLDEN_QA_FILE, "r", encoding="utf-8") as f:
        bank = json.load(f)
    if isinstance(bank, dict):
        return bank.get("items", bank.get("qa_pairs", []))
    if isinstance(bank, list):
        return bank
    return []


# ── 统计函数 (对齐 calibration.py) ──
def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _pearson_r(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 3:
        return 0.0
    mx, my = _mean(x), _mean(y)
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    sx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    sy = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if sx < 1e-10 or sy < 1e-10:
        return 0.0
    return cov / (sx * sy)


def _spearman_rho(x: list[float], y: list[float]) -> float:
    if len(x) < 3:
        return 0.0
    def _rank(vals):
        indexed = sorted(enumerate(vals), key=lambda t: t[1])
        ranks = [0.0] * len(vals)
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
    return _pearson_r(_rank(x), _rank(y))


def _cohens_kappa_weighted(human: list[float], llm: list[float], k: int = 5) -> float:
    n = len(human)
    if n < 2:
        return 0.0
    def disc(v):
        return max(1, min(k, round(v)))
    h = [disc(s) for s in human]
    m = [disc(s) for s in llm]
    O = [[0] * k for _ in range(k)]
    for hi, mi in zip(h, m):
        O[hi - 1][mi - 1] += 1
    W = [[((i - j) / (k - 1)) ** 2 for j in range(k)] for i in range(k)]
    h_marg = [sum(O[i][j] for j in range(k)) for i in range(k)]
    m_marg = [sum(O[i][j] for i in range(k)) for j in range(k)]
    E = [[h_marg[i] * m_marg[j] / n for j in range(k)] for i in range(k)]
    num = sum(W[i][j] * O[i][j] for i in range(k) for j in range(k))
    den = sum(W[i][j] * E[i][j] for i in range(k) for j in range(k))
    if den < 1e-10:
        return 1.0 if num < 1e-10 else 0.0
    return 1.0 - num / den


def _mae(x: list[float], y: list[float]) -> float:
    if not x:
        return 0.0
    return sum(abs(xi - yi) for xi, yi in zip(x, y)) / len(x)


# ── API 端点 ──
@router.get("/pool-status")
async def get_pool_status():
    """对抗性QA池状态: 待审核数量, 是否需要补充"""
    golden_qa = _load_golden_qa()
    adv_types = ("越界测试", "诱导测试", "边界测试")
    all_adv = [q for q in golden_qa if q.get("type") in adv_types]
    cal_data = _load_calibration_data()
    scored_ids = set(cal_data["items"].keys())
    pending = [q for q in all_adv if q.get("qa_id") not in scored_ids]
    return {
        "total_adversarial": len(all_adv),
        "pending_review": len(pending),
        "reviewed": len(all_adv) - len(pending),
        "target_pool_size": 50,
        "needs_replenish": len(pending) < 50,
        "shortfall": max(0, 50 - len(pending)),
    }

@router.get("/items")
async def get_calibration_items(qa_id: str = None, type: str = None):
    """获取校准QA列表或单个QA

    type=adversarial: 仅返回对抗性QA (越界/诱导/边界, BAT标准人工校准)
    """
    cal_data = _load_calibration_data()
    golden_qa = _load_golden_qa()

    # 对抗性QA筛选 (BAT标准: 正常QA LLM自动评, 仅对抗性需人类校准)
    if type == "adversarial":
        adv_types = ("越界测试", "诱导测试", "边界测试")
        golden_qa = [q for q in golden_qa if q.get("type") in adv_types]

    if qa_id:
        # 返回单个QA详情
        qa = next((q for q in golden_qa if q.get("qa_id") == qa_id), None)
        if not qa:
            raise HTTPException(404, f"QA {qa_id} 不存在")
        existing = cal_data["items"].get(qa_id, {})
        return {
            "qa_id": qa_id,
            "phase": qa.get("phase", ""),
            "type": qa.get("type", ""),
            "difficulty": qa.get("difficulty", ""),
            "question": qa.get("question", ""),
            "golden_answer": qa.get("golden_answer", ""),
            "human_scores": existing.get("human_scores", {}),
            "human_overall": existing.get("human_overall"),
            "notes": existing.get("notes", ""),
            "scored_at": existing.get("scored_at"),
        }

    # 构建QA列表 (含标注状态)
    items = []
    for qa in golden_qa:
        qid = qa.get("qa_id", "")
        existing = cal_data["items"].get(qid, {})
        has_scores = bool(existing.get("human_scores"))
        items.append({
            "qa_id": qid,
            "phase": qa.get("phase", ""),
            "type": qa.get("type", ""),
            "difficulty": qa.get("difficulty", ""),
            "question": qa.get("question", "")[:120],
            "scored": has_scores,
            "scored_at": existing.get("scored_at"),
        })

    # 按未标注优先排序
    items.sort(key=lambda x: (x["scored"], x["qa_id"]))

    return {
        "items": items,
        "total": len(items),
        "scored_count": sum(1 for i in items if i["scored"]),
    }


@router.post("/score")
async def submit_score(submission: ScoreSubmission):
    """提交人类评分"""
    cal_data = _load_calibration_data()

    scores_dict = {}
    for dim in CALIBRATION_DIMS:
        val = getattr(submission.human_scores, dim, None)
        if val is not None:
            val = float(val)
            if val < 1 or val > 5:
                raise HTTPException(400, f"{dim} 分数必须在1-5之间，实际: {val}")
            scores_dict[dim] = val

    if not scores_dict:
        raise HTTPException(400, "至少需要为一个维度打分")

    cal_data["items"][submission.qa_id] = {
        "human_scores": scores_dict,
        "human_overall": submission.human_overall,
        "notes": submission.notes,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }
    cal_data["meta"]["total"] = len(cal_data["items"])

    _save_calibration_data(cal_data)

    return {
        "status": "ok",
        "qa_id": submission.qa_id,
        "dims_scored": len(scores_dict),
        "total_scored": len(cal_data["items"]),
    }


@router.get("/results")
async def get_calibration_results():
    """计算校准统计 (人类 vs LLM Judge)"""
    cal_data = _load_calibration_data()
    golden_qa = _load_golden_qa()

    # 收集有人类标注的QA
    scored_items = []
    for qid, cdata in cal_data["items"].items():
        hs = cdata.get("human_scores", {})
        if not hs:
            continue
        qa = next((q for q in golden_qa if q.get("qa_id") == qid), None)
        if not qa:
            continue
        scored_items.append({
            "qa_id": qid,
            "human_scores": hs,
            "llm_scores": qa.get("scores") or qa.get("llm_scores") or {},
        })

    n = len(scored_items)
    if n < 5:
        return {
            "n_samples": n,
            "warning": f"样本不足 (需要至少5条，当前{n}条)",
            "ready": False,
        }

    # 每维度计算
    dim_results = {}
    for dim in CALIBRATION_DIMS:
        h_vals, e_vals = [], []
        for item in scored_items:
            hv = item["human_scores"].get(dim)
            ev = item["llm_scores"].get(dim)
            if hv is not None and ev is not None:
                h_vals.append(float(hv))
                e_vals.append(float(ev))

        if len(h_vals) < 3:
            dim_results[dim] = {"n": len(h_vals), "warning": "样本不足"}
            continue

        dim_results[dim] = {
            "n": len(h_vals),
            "mae": round(_mae(h_vals, e_vals), 3),
            "pearson_r": round(_pearson_r(h_vals, e_vals), 3),
            "spearman_rho": round(_spearman_rho(h_vals, e_vals), 3),
            "cohens_kappa": round(_cohens_kappa_weighted(h_vals, e_vals), 3),
            "human_mean": round(_mean(h_vals), 2),
            "llm_mean": round(_mean(e_vals), 2),
        }

    # Overall
    all_h, all_e = [], []
    for item in scored_items:
        hv = item["human_scores"].get("overall") or item["human_scores"].get("overall")
        ev = item["llm_scores"].get("overall")
        if hv is None:
            h_vals = [v for v in item["human_scores"].values() if v is not None]
            hv = _mean(h_vals) if h_vals else None
        if ev is None:
            e_vals = [v for v in item["llm_scores"].values() if v is not None]
            ev = _mean(e_vals) if e_vals else None
        if hv is not None and ev is not None:
            all_h.append(float(hv))
            all_e.append(float(ev))

    overall = {}
    if len(all_h) >= 3:
        overall = {
            "n": len(all_h),
            "mae": round(_mae(all_h, all_e), 3),
            "pearson_r": round(_pearson_r(all_h, all_e), 3),
            "spearman_rho": round(_spearman_rho(all_h, all_e), 3),
            "cohens_kappa": round(_cohens_kappa_weighted(all_h, all_e), 3),
            "human_mean": round(_mean(all_h), 2),
            "llm_mean": round(_mean(all_e), 2),
        }

    # 判定
    thresholds = {"cohens_kappa": 0.70, "spearman_rho": 0.80, "mae": 0.50, "pearson_r": 0.75}
    failures = []
    ok = overall.get("cohens_kappa", 0) or 0
    sr = overall.get("spearman_rho", 0) or 0
    m = overall.get("mae", 999) or 999
    pr = overall.get("pearson_r", 0) or 0

    if ok < thresholds["cohens_kappa"]:
        failures.append(f"Cohen's κ={ok:.3f} < {thresholds['cohens_kappa']}")
    if sr < thresholds["spearman_rho"]:
        failures.append(f"Spearman ρ={sr:.3f} < {thresholds['spearman_rho']}")
    if m > thresholds["mae"]:
        failures.append(f"MAE={m:.3f} > {thresholds['mae']}")
    if pr < thresholds["pearson_r"]:
        failures.append(f"Pearson r={pr:.3f} < {thresholds['pearson_r']}")

    return {
        "n_samples": n,
        "thresholds": thresholds,
        "overall": overall,
        "per_dimension": dim_results,
        "passed": len(failures) == 0,
        "failures": failures,
        "ready": True,
    }


@router.get("/progress")
async def get_calibration_progress():
    cal_data = _load_calibration_data()
    golden_qa = _load_golden_qa()

    total_qa = len(golden_qa)
    scored = len(cal_data["items"])

    # 统计每个维度的覆盖
    dim_counts = {dim: 0 for dim in CALIBRATION_DIMS}
    for cdata in cal_data["items"].values():
        for dim in CALIBRATION_DIMS:
            if dim in cdata.get("human_scores", {}):
                dim_counts[dim] += 1

    return {
        "total_qa": total_qa,
        "scored_qa": scored,
        "progress_pct": round(scored / total_qa * 100, 1) if total_qa else 0,
        "dim_coverage": dim_counts,
        "last_scored_at": max(
            (c.get("scored_at", "") for c in cal_data["items"].values()),
            default=None,
        ),
    }


@router.post("/generate")
async def generate_calibration_set(size: int = 50, type: str = None):
    """从golden_qa_bank生成校准集

    type=adversarial: 仅选取对抗性QA (BAT标准)
    """
    golden_qa = _load_golden_qa()
    if not golden_qa:
        raise HTTPException(400, "golden_qa_bank.json 不存在或为空")

    if type == "adversarial":
        adv_types = ("越界测试", "诱导测试", "边界测试")
        golden_qa = [q for q in golden_qa if q.get("type") in adv_types]

    selected = golden_qa[:min(size, len(golden_qa))]

    cal_data = {
        "items": {},
        "meta": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "total": 0,
            "source": "golden_qa_bank.json",
            "n_selected": len(selected),
        },
    }

    # 保留已有的标注
    existing = _load_calibration_data()
    for qa in selected:
        qid = qa.get("qa_id", "")
        if qid in existing["items"]:
            cal_data["items"][qid] = existing["items"][qid]

    _save_calibration_data(cal_data)

    return {
        "status": "ok",
        "n_selected": len(selected),
        "previously_scored": len(cal_data["items"]),
    }
