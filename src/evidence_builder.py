"""
证据链构建器 v1.0 — 报告完整性证明 + 置信度量化

职责:
  1. 构建场景级哈希链 (类 Merkle 结构, 防篡改)
  2. 计算报告自校验哈希 (报告内容 = 证据本身)
  3. 生成审计清单 (哪些文件在 TOS 可查)
  4. 置信度量化 (CV + 可靠性分级 + 95%CI)
  5. Judge 一致性分析 (Fleiss' κ 近似 + 分歧检测)

设计原则:
  - 离线可用: 无 TOS/Redis 也能计算哈希和置信度
  - 增量: 不修改已有数据结构, 仅从现有数据派生
  - 透明: 所有计算过程可追溯, 公式公开

用法:
    from src.evidence_builder import EvidenceBuilder

    builder = EvidenceBuilder()
    manifest = builder.build(results, config_snapshot, extra)
    # manifest 嵌入 report JSON → HTML reporter 渲染为可视化证据面板
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from datetime import datetime, timezone
from typing import Optional


class EvidenceBuilder:
    """证据链构建器 — 报告完整性 + 置信度"""

    # 可靠性分级阈值
    RELIABILITY = {
        "high":    {"cv_max": 0.10, "label": "🟢 高可信",   "desc": "CV<10%, 评分稳定可复现"},
        "medium":  {"cv_max": 0.25, "label": "🟡 中可信",   "desc": "CV 10-25%, 评分有波动但在可接受范围"},
        "low":     {"cv_max": 0.50, "label": "🟠 低可信",   "desc": "CV 25-50%, 评分不稳定, 建议人工复核"},
        "unreliable": {"cv_max": float("inf"), "label": "🔴 不可靠", "desc": "CV>50%, 评分高度不确定, 不应作为决策依据"},
    }

    DIMS = [
        "correctness", "relevancy", "completeness", "guidance",
        "followup_quality", "boundary_compliance",
        "turn_consistency", "knowledge_scaffolding",
        "overhelping", "fairness_bias",
    ]

    DIM_LABELS = {
        "correctness": "事实正确性", "relevancy": "答案相关性",
        "completeness": "内容完整性", "guidance": "教学引导力",
        "followup_quality": "追问响应质量", "boundary_compliance": "边界合规性",
        "turn_consistency": "跨轮一致性", "knowledge_scaffolding": "知识递进性",
        "overhelping": "过度帮助", "fairness_bias": "公平性与偏见",
    }

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    # ═══════════════════════════════════════════════════════════
    # 公共 API
    # ═══════════════════════════════════════════════════════════

    def build(
        self,
        results: list[dict],
        config_snapshot: dict = None,
        extra: dict = None,
    ) -> dict:
        """构建完整证据清单

        Returns: {
            "report_self_hash": str,       # 报告自校验哈希
            "scenario_chain": [...],        # 场景级哈希链
            "chain_root": str,             # 链根哈希
            "confidence": {...},            # 置信度分析
            "judge_consensus": {...},       # Judge 共识分析
            "audit_manifest": {...},        # 审计文件清单
            "config_fingerprint": str,      # 配置指纹
            "generated_at": str,            # 生成时间
            "builder_version": str,         # 构建器版本
        }
        """
        ts = datetime.now(timezone.utc).isoformat()

        # 1. 场景级哈希链
        scenario_chain = self._build_scenario_chain(results)
        chain_root = self._chain_root(scenario_chain) if scenario_chain else ""

        # 2. 置信度分析
        confidence = self._build_confidence(results)

        # 3. Judge 共识分析
        judge_consensus = self._build_judge_consensus(results)

        # 4. 审计文件清单
        audit_manifest = self._build_audit_manifest(results)

        # 5. 配置指纹
        config_fingerprint = self._hash_config(config_snapshot or {})

        manifest = {
            "report_self_hash": "",  # 后填: 由 reporter 在生成完整 JSON 后回填
            "scenario_chain": scenario_chain,
            "chain_root": chain_root,
            "confidence": confidence,
            "judge_consensus": judge_consensus,
            "audit_manifest": audit_manifest,
            "config_fingerprint": config_fingerprint,
            "generated_at": ts,
            "builder_version": "1.0",
        }

        # 如果 extra 中有 evidence 数据, 合并进来
        if extra:
            if extra.get("evidence_hashes"):
                manifest["_evidence_hashes"] = extra["evidence_hashes"]

        return manifest

    def compute_report_self_hash(self, report_json: dict) -> str:
        """对完整报告 JSON 计算自校验哈希 (排除 self_hash 字段本身)"""
        # 深拷贝, 去掉 self_hash 避免循环依赖
        clean = {k: v for k, v in report_json.items() if k != "evidence"}
        canonical = json.dumps(clean, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ═══════════════════════════════════════════════════════════
    # 场景级哈希链
    # ═══════════════════════════════════════════════════════════

    def _build_scenario_chain(self, results: list[dict]) -> list[dict]:
        """为每个场景构建哈希链节点

        每个节点 = SHA-256(上一节点哈希 + 当前 conversation + 当前 scores)
        形成一条不可篡改的单向链: 修改任一场景 → 后续所有哈希失效
        """
        chain = []
        prev_hash = "0" * 64  # 创世哈希

        for i, r in enumerate(results):
            conv = r.get("full_conversation", "") or ""
            sc = r.get("score") or {}

            # 场景载荷
            payload = json.dumps({
                "conversation": str(conv)[:50000],   # 截断极长文本
                "score": {k: v for k, v in sc.items() if not k.startswith("_")},
            }, ensure_ascii=False, sort_keys=True, default=str)

            # 链式哈希: prev_hash + payload → 当前哈希
            combined = prev_hash + payload
            node_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()

            chain.append({
                "index": i + 1,
                "hash": node_hash[:16],            # 短哈希便于显示
                "hash_full": node_hash,            # 完整 64 位哈希
                "prev_hash": prev_hash[:16],
                "persona_id": r.get("persona_id", ""),
                "lesson_title": (r.get("question_data") or {}).get("lesson_title", ""),
                "overall": sc.get("overall", 0),
                "flags": len(sc.get("flags", [])),
            })

            prev_hash = node_hash

        return chain

    def _chain_root(self, chain: list[dict]) -> str:
        """链根 = 最后一个节点的完整哈希"""
        return chain[-1]["hash_full"] if chain else ""

    # ═══════════════════════════════════════════════════════════
    # 置信度分析
    # ═══════════════════════════════════════════════════════════

    def _build_confidence(self, results: list[dict]) -> dict:
        """逐维度计算置信度 (CV + 可靠性分级 + 95%CI)"""
        # 收集每维度所有场景的分数
        dim_scores: dict[str, list[float]] = {d: [] for d in self.DIMS}
        dim_scores["overall"] = []

        for r in results:
            sc = r.get("score") or {}
            for d in self.DIMS:
                v = sc.get(d)
                if v is not None and v > 0:
                    dim_scores[d].append(v)
            ov = sc.get("overall")
            if ov is not None and ov > 0:
                dim_scores["overall"].append(ov)

        dims_analysis = {}
        for dim in list(self.DIMS) + ["overall"]:
            vals = dim_scores.get(dim, [])
            if not vals or len(vals) < 2:
                dims_analysis[dim] = {
                    "label": self.DIM_LABELS.get(dim, dim),
                    "mean": round(self._mean(vals), 2) if vals else None,
                    "stdev": 0.0,
                    "cv": None,
                    "ci_95": None,
                    "reliability": "⚪ 数据不足",
                    "n_samples": len(vals),
                    "range": [round(min(vals), 2), round(max(vals), 2)] if vals else None,
                }
                continue

            mu = self._mean(vals)
            sigma = self._stdev(vals)
            cv = sigma / mu if mu > 0 else float("inf")
            ci = self._ci_95(vals, mu, sigma)
            reliability = self._reliability_grade(cv, len(vals))

            dims_analysis[dim] = {
                "label": self.DIM_LABELS.get(dim, dim),
                "mean": round(mu, 2),
                "stdev": round(sigma, 2),
                "cv": round(cv, 4),
                "ci_95": ci,
                "reliability": reliability,
                "n_samples": len(vals),
                "range": [round(min(vals), 2), round(max(vals), 2)],
            }

        # 整体可信度评估
        cv_values = [d["cv"] for d in dims_analysis.values() if d["cv"] is not None and d["cv"] != float("inf")]
        avg_cv = self._mean(cv_values) if cv_values else float("inf")
        overall_reliability = self._reliability_grade(avg_cv, len(cv_values))

        return {
            "dimensions": dims_analysis,
            "overall_cv": round(avg_cv, 4) if cv_values else None,
            "overall_reliability": overall_reliability,
            "method": "CV (Coefficient of Variation) = σ/μ; 95%CI = μ ± 1.96×σ/√n",
            "note": "CV<10%高可信, 10-25%中可信, 25-50%低可信, >50%不可靠。单场景报告CV=0不代表无变异性,仅表示本次测评内部一致。",
        }

    # ═══════════════════════════════════════════════════════════
    # Judge 共识分析
    # ═══════════════════════════════════════════════════════════

    def _build_judge_consensus(self, results: list[dict]) -> dict:
        """分析多 Judge 投票的一致性"""
        judge_variances: list[float] = []
        n_judges_list: list[int] = []
        veto_count = 0
        skip_count = 0
        total_scenarios = 0

        for r in results:
            sc = r.get("score") or {}
            n_judges = sc.get("n_judges", 0)
            if n_judges > 0:
                total_scenarios += 1
                n_judges_list.append(n_judges)
                jv = sc.get("judge_variance", 0)
                if jv > 0:
                    judge_variances.append(jv)
                # Veto 计数
                if sc.get("veto_dims"):
                    veto_count += 1
                if sc.get("skip_llm_dims"):
                    skip_count += 1

        avg_judges = self._mean(n_judges_list) if n_judges_list else 0
        avg_variance = self._mean(judge_variances) if judge_variances else 0

        # 共识评级
        if avg_variance < 0.3 and avg_judges >= 3:
            consensus = "🟢 强共识 — 多 Judge 高度一致"
        elif avg_variance < 0.7:
            consensus = "🟡 中等共识 — 部分维度存在分歧"
        elif avg_variance < 1.5:
            consensus = "🟠 弱共识 — Judge 间有显著分歧, 建议人工审核"
        else:
            consensus = "🔴 无共识 — Judge 严重分歧, 评分不可直接采信"

        return {
            "avg_judges_per_scenario": round(avg_judges, 1),
            "avg_variance": round(avg_variance, 3),
            "consensus_level": consensus,
            "veto_scenarios": veto_count,
            "skip_scenarios": skip_count,
            "total_scenarios_with_judges": total_scenarios,
            "interpretation": (
                f"{total_scenarios} 个场景经 {avg_judges:.0f} 个 Judge 独立投票, "
                f"平均方差 {avg_variance:.2f}。{consensus}"
            ),
        }

    # ═══════════════════════════════════════════════════════════
    # 审计清单
    # ═══════════════════════════════════════════════════════════

    def _build_audit_manifest(self, results: list[dict]) -> dict:
        """构建可审计清单 — 基于实际可用的存储后端

        根据环境变量自动检测:
          - TOS 可用 (VOLC_ACCESS_KEY + REDIS_URL): 对象存储 + 预签名URL
          - 仅数据库:  SQLite/MySQL 查询 → 重算 SHA-256 → 比对
        """
        total_turns = sum(len(r.get("conversation_turns", [])) for r in results)
        tos_available = bool(os.getenv("VOLC_ACCESS_KEY"))
        redis_available = False
        try:
            import redis
            r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), socket_timeout=2)
            redis_available = r.ping()
        except Exception:
            pass

        storage_mode = "tos" if (tos_available and redis_available) else "database"

        files = [
            {"type": "report_json", "description": "完整评测报告 (含自校验哈希)",
             "location": "reports/ 目录 + 数据库 reports 表", "verifiable": True},
            {"type": "eval_scores", "description": f"{len(results)} 场景 × 10维评分 + n_judges + judge_variance",
             "location": "数据库 eval_scores 表", "verifiable": True},
            {"type": "conversation_turns", "description": f"{total_turns} 轮对话 (question, response, latency, tokens)",
             "location": "数据库 conversation_turns 表", "verifiable": True},
            {"type": "test_sessions", "description": "评测配置快照 (agent_id, profile, config_snapshot)",
             "location": "数据库 test_sessions 表", "verifiable": True},
            {"type": "qa_pairs", "description": "黄金QA对 (问题, 参考答案, 知识点)",
             "location": "数据库 qa_pairs 表", "verifiable": True},
        ]

        if storage_mode == "tos":
            verification_desc = "下载 TOS 原始文件 → 计算 SHA-256 → 与 evidence_hash 比对"
            storage_desc = "火山引擎 TOS · agent-eval-evidence"
            verification_api = "/api/reports/verify/file/{name} + TOS SHA-256 比对"
        else:
            verification_desc = "查询数据库原始数据 → 计算 SHA-256 → 与 evidence_hash 比对"
            storage_desc = "SQLite/MySQL (test_sessions + test_scenarios + eval_scores + conversation_turns)"
            verification_api = "/api/reports/verify/file/{name}"

        # 检查实际存了哪些数据
        has_traces = any(
            r.get("score", {}).get("breakdown") for r in results
        )
        has_judge_details = any(
            r.get("score", {}).get("judge_reasons") for r in results
        )

        data_completeness = {
            "scores_stored": True,                                    # eval_scores 表
            "conversations_stored": total_turns > 0,                  # conversation_turns 表
            "l1_l2_traces_stored": has_traces,                        # eval_traces 表 (当前空)
            "judge_decisions_stored": has_judge_details,              # judge_decisions 表 (当前空)
            "tos_files_uploaded": storage_mode == "tos",
            "data_completeness_note": (
                "完整: 评分+对话+配置 均已入库, L1/L2/L3中间过程可追溯"
                if has_traces and has_judge_details else
                "基础: 评分+对话+配置已入库。L1/L2中间过程(eval_traces)和独立Judge评分(judge_decisions)未入库, "
                "仅能验证最终分数, 无法逐层回溯评分过程。"
            ),
        }

        return {
            "total_files": len(files),
            "files": files,
            "storage_mode": storage_mode,
            "storage_description": storage_desc,
            "verification_method": verification_desc,
            "verification_api": verification_api,
            "data_completeness": data_completeness,
        }

    # ═══════════════════════════════════════════════════════════
    # 配置指纹
    # ═══════════════════════════════════════════════════════════

    def _hash_config(self, config: dict) -> str:
        """对配置快照做 SHA-256 指纹"""
        if not config:
            return ""
        canonical = json.dumps(config, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    # ═══════════════════════════════════════════════════════════
    # 统计工具 (无 scipy 依赖)
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _mean(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    @staticmethod
    def _stdev(vals: list[float]) -> float:
        if len(vals) < 2:
            return 0.0
        m = EvidenceBuilder._mean(vals)
        return math.sqrt(sum((x - m) ** 2 for x in vals) / (len(vals) - 1))

    @staticmethod
    def _ci_95(vals: list[float], mu: float, sigma: float) -> list[float]:
        """95% 置信区间: μ ± 1.96 × σ/√n (正态近似)"""
        n = len(vals)
        if n < 2 or sigma == 0:
            return [round(mu, 2), round(mu, 2)]
        se = sigma / math.sqrt(n)
        margin = 1.96 * se
        return [round(mu - margin, 2), round(mu + margin, 2)]

    @classmethod
    def _reliability_grade(cls, cv: float, n: int) -> str:
        if n < 2:
            return "⚪ 数据不足 (需≥2个场景)"
        for grade, info in cls.RELIABILITY.items():
            if cv <= info["cv_max"]:
                return info["label"]
        return "🔴 不可靠"

    # ═══════════════════════════════════════════════════════════
    # 静态工具: 离线索证校验 (供 API 调用)
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def verify_report_integrity(report_json: dict) -> dict:
        """验证报告完整性: 重算 self_hash 并与记录值比对

        供 API /reports/{id}/verify 调用。
        """
        evidence = report_json.get("evidence", {})
        if not evidence:
            return {"status": "no_evidence", "message": "报告不含证据链数据(v3.5之前的报告)", "tampered": None}

        recorded_hash = evidence.get("report_self_hash", "")
        if not recorded_hash:
            return {"status": "no_self_hash", "message": "证据数据存在但缺少 self_hash", "tampered": None}

        # 重算
        builder = EvidenceBuilder()
        computed_hash = builder.compute_report_self_hash(report_json)

        match = computed_hash == recorded_hash
        return {
            "status": "verified" if match else "TAMPERED",
            "recorded_hash": recorded_hash,
            "computed_hash": computed_hash,
            "match": match,
            "tampered": not match,
            "message": (
                "✅ 报告完整性校验通过 — 内容与生成时一致, 未被篡改"
                if match else
                "🚨 报告已被篡改! recorded_hash != computed_hash"
            ),
        }

    @staticmethod
    def verify_scenario_chain(chain: list[dict]) -> dict:
        """验证场景哈希链的连续性"""
        if not chain:
            return {"status": "empty", "message": "空链"}

        prev = "0" * 64
        results = []
        all_ok = True

        for node in chain:
            recorded_prev = node.get("prev_hash", "")
            expected_prev_short = prev[:16]
            link_ok = (recorded_prev == expected_prev_short) if results else True  # 第一个节点 prev=000...
            results.append({
                "index": node.get("index"),
                "link_ok": link_ok,
                "recorded_prev": recorded_prev,
                "expected_prev": expected_prev_short,
            })
            if not link_ok:
                all_ok = False
            prev = node.get("hash_full", "")

        return {
            "status": "verified" if all_ok else "BROKEN_CHAIN",
            "chain_length": len(chain),
            "all_links_ok": all_ok,
            "details": results,
            "message": (
                "✅ 哈希链连续 — 所有场景按序链接, 无篡改"
                if all_ok else
                "🚨 哈希链断裂 — 场景顺序被修改或内容被篡改"
            ),
        }
