"""
课程知识库检索器 v3.3 — 火山引擎 KB API (Bearer token)

正确API (来源: 火山引擎控制台 → 知识库 → API调用):
  POST https://api-knowledgebase.mlp.cn-beijing.volces.com/api/knowledge/collection/search_knowledge
  Authorization: Bearer {api_key}
  Body: {"service_resource_id": "kb-xxx", "name": "phase_N", "query": "...", "limit": 5}

Phase KB 映射:
  Phase 1: kb-1cf46d36aaa68622 / name=phase_1
  Phase 2: kb-453f9a68d45f983c / name=phase_2
  Phase 3&4: kb-service-c9c4a9287f094dc6 / name=phase_4 (含phase_3+phase_4)
  Phase 5: kb-b8dc39b8662e5b9c / name=phase_5 (待确认)
"""

import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

# 加载 .env (云服务器和本地都能工作)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

KB_API_URL = "https://api-knowledgebase.mlp.cn-beijing.volces.com/api/knowledge/collection/search_knowledge"

KB_CONFIGS = {
    "phase1": {
        "label": "Phase 1 — 国产AI技术基础",
        "resource_id": os.getenv("VOLC_KB_PHASE1_ID", "kb-1cf46d36aaa68622"),
        "name": "phase_1",
        "api_key": os.getenv("VOLC_KB_PHASE1_KEY", ""),
    },
    "phase2": {
        "label": "Phase 2 — 新型硬件设计",
        "resource_id": os.getenv("VOLC_KB_PHASE2_ID", "kb-453f9a68d45f983c"),
        "name": "phase_2",
        "api_key": os.getenv("VOLC_KB_PHASE2_KEY", ""),
    },
    "phase3_4": {
        "label": "Phase 3&4 — 环境感知与触觉反馈",
        "resource_id": os.getenv("VOLC_KB_PHASE3_4_ID", "kb-service-c9c4a9287f094dc6"),
        "name": "phase_4",
        "api_key": os.getenv("VOLC_KB_PHASE3_4_KEY", ""),
    },
    "phase5": {
        "label": "Phase 5 — 具身智能控制 (domestic_ai_makers_pbl_platform)",
        "resource_id": os.getenv("VOLC_KB_PHASE5_ID", "kb-service-9116de458fb8d1cf"),
        "name": "domestic_ai_makers_pbl_platform",
        "api_key": os.getenv("VOLC_KB_PHASE5_KEY", ""),
    },
}


@dataclass
class KBChunk:
    content: str = ""
    score: float = 0.0
    source: str = ""
    chunk_id: str = ""


@dataclass
class KBSearchResult:
    phase: str = ""
    phase_name: str = ""
    resource_id: str = ""
    query: str = ""
    chunks: list = field(default_factory=list)
    top_score: float = 0.0
    avg_score: float = 0.0
    hit_count: int = 0
    error: str = ""


def _call_kb_api(
    resource_id: str,
    name: str,
    api_key: str,
    query: str,
    limit: int = 5,
    timeout: int = 15,
) -> tuple[list[KBChunk], Optional[str]]:
    """调用火山引擎知识库 collection/search_knowledge API"""
    body = json.dumps({
        "service_resource_id": resource_id,
        "name": name,
        "query": query,
        "limit": limit,
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(KB_API_URL, data=body, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return [], f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"
    except Exception as e:
        return [], str(e)

    if data.get("code") != 0:
        return [], data.get("message", f"API error code={data.get('code')}")

    result_list = data.get("data", {}).get("result_list", [])
    chunks = []
    for r in result_list:
        content = r.get("content", "")
        score = r.get("score", 0.0)
        source = r.get("source_doc", "") or r.get("chunk_title", "")
        chunk_id = r.get("chunk_id", "")
        chunks.append(KBChunk(content=content, score=score, source=source, chunk_id=chunk_id))

    return chunks, None


def query_phase_kb(
    query: str,
    phase: str = "phase1",
    limit: int = 5,
    timeout: int = 15,
) -> KBSearchResult:
    """查询指定 Phase 的知识库"""
    cfg = KB_CONFIGS.get(phase)
    if not cfg:
        return KBSearchResult(phase=phase, error=f"未知Phase: {phase}")

    if not cfg["api_key"]:
        return KBSearchResult(
            phase=phase, phase_name=cfg["label"], resource_id=cfg["resource_id"],
            query=query, error=f"未配置 VOLC_KB_{phase.upper()}_KEY",
        )

    chunks, error = _call_kb_api(cfg["resource_id"], cfg["name"], cfg["api_key"], query, limit, timeout)

    if error:
        return KBSearchResult(
            phase=phase, phase_name=cfg["label"], resource_id=cfg["resource_id"],
            query=query, error=error,
        )

    scores = [c.score for c in chunks]
    return KBSearchResult(
        phase=phase, phase_name=cfg["label"], resource_id=cfg["resource_id"],
        query=query, chunks=chunks,
        top_score=max(scores) if scores else 0.0,
        avg_score=sum(scores) / len(scores) if scores else 0.0,
        hit_count=len(chunks),
    )


def query_all_phase_kbs(
    query: str,
    phases: list[str] = None,
    limit: int = 5,
    timeout: int = 15,
) -> dict[str, KBSearchResult]:
    """查询所有 Phase 知识库"""
    if phases is None:
        phases = ["phase1", "phase2", "phase3_4", "phase5"]
    return {p: query_phase_kb(query, phase=p, limit=limit, timeout=timeout) for p in phases}


def get_best_kb_match(query: str, answer: str = "") -> KBSearchResult:
    """在所有KB中查询，返回最佳匹配 Phase"""
    combined = f"{query} {answer[:300]}" if answer else query
    all_results = query_all_phase_kbs(combined, limit=3)
    best, best_score = None, 0.0
    for phase, r in all_results.items():
        if not r.error and r.top_score > best_score:
            best_score, best = r.top_score, r
    return best or KBSearchResult(query=query, error="所有KB查询失败")


def get_aggregated_scores(query: str, answer: str = "") -> dict:
    """获取所有KB的聚合分数"""
    combined = f"{query} {answer[:300]}" if answer else query
    all_results = query_all_phase_kbs(combined, limit=3)

    scores = {}
    best_phase, best_score = "", 0.0
    tops, avgs = [], []

    for phase, r in all_results.items():
        scores[f"{phase}_top"] = r.top_score
        scores[f"{phase}_avg"] = r.avg_score
        tops.append(r.top_score)
        avgs.append(r.avg_score)
        if r.top_score > best_score:
            best_score, best_phase = r.top_score, phase

    scores["best_phase"] = best_phase
    scores["best_score"] = best_score
    scores["overall_top"] = max(tops) if tops else 0.0
    scores["overall_avg"] = sum(avgs) / len(avgs) if avgs else 0.0
    return scores
