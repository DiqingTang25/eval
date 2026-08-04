"""
测评过程入库记录器 (DBRecorder)

把 persona_tester 的一次完整测评过程持久化到数据库, 复用 backend 现有 SQLAlchemy 模型:
  test_sessions → test_scenarios → conversation_turns → eval_scores
  + web_eval_results (网站测评) + reports (完整报告JSON)

设计约束(实测):
  - 火山引擎 RDS 是内网端点, 本地无法直连 → 记录器在服务器(VPC内, DB_TYPE=mysql)才写 MySQL;
    本地默认 sqlite, 逻辑可本地验证。
  - eval_scores 表只有 8 个维度列, 无 overhelping/fairness_bias → 存进 score_explanations(JSON)。
  - 不可达/依赖缺失时优雅跳过, 不影响文件报告生成。
"""
from __future__ import annotations

from datetime import datetime, timezone


class DBRecorder:
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.ok = False
        self._mods = None
        try:
            from backend.dependencies import get_sync_db, _get_sync_session_factory
            from backend.models.base import Base
            from backend.models.test_session import TestSession, TestScenario, ConversationTurn
            from backend.models.eval_score import EvalScore
            from backend.models.web_eval_result import WebEvalResult
            from backend.models.report import Report
            from backend.config import settings
            self._mods = dict(
                get_sync_db=get_sync_db, factory=_get_sync_session_factory, Base=Base,
                TestSession=TestSession, TestScenario=TestScenario, ConversationTurn=ConversationTurn,
                EvalScore=EvalScore, WebEvalResult=WebEvalResult, Report=Report, settings=settings,
            )
            self.ok = True
        except Exception as e:
            self._log(f"⚠️ DB 记录器不可用(依赖缺失): {e}")

    def _log(self, m):
        if self.verbose:
            print(m)

    def available(self) -> bool:
        return self.ok

    def ensure_tables(self):
        """首次/ sqlite 时建表; MySQL 已由 alembic 建好则无副作用"""
        if not isinstance(report_dict, dict):
            report_dict = {}
        m = self._mods
        engine = m["factory"]().kw["bind"]
        m["Base"].metadata.create_all(engine)

    def record(self, *, session_id: str, agent_id: str, profile: str, config: dict,
               results: list, report_dict: dict, web_data: dict = None,
               extra: dict = None, started_at: datetime = None,
               finished_at: datetime = None) -> str | None:
        """写入一次完整测评。返回 test_session.id, 失败返回 None。"""
        if not self.ok:
            return None
        m = self._mods
        try:
            self.ensure_tables()
        except Exception as e:
            self._log(f"⚠️ 建表检查失败(忽略): {e}")

        db = m["get_sync_db"]()
        try:
            ts = m["TestSession"](
                session_id=session_id, agent_id=agent_id, profile=profile,
                status="success", config_snapshot=self._json_safe(config),
                total_scenarios=len(results),
                started_at=started_at or datetime.now(timezone.utc),
                finished_at=finished_at or datetime.now(timezone.utc),
            )
            db.add(ts); db.flush()

            for i, r in enumerate(results):
                qd = r.get("question_data", {})
                scenario = m["TestScenario"](
                    session_id=ts.id, scenario_index=i + 1,
                    status="success" if not r.get("error") else "error",
                    error=r.get("error", "") or "",
                    full_conversation=r.get("full_conversation", "") or "",
                )
                db.add(scenario); db.flush()

                for t in r.get("conversation_turns", []):
                    resp = t.get("response", {})
                    db.add(m["ConversationTurn"](
                        scenario_id=scenario.id, turn=t.get("turn", 0),
                        question=t.get("question", ""),
                        response_status=resp.get("status", ""),
                        response_text=resp.get("response", ""),
                        response_duration=resp.get("duration", 0.0),
                        is_followup=bool(t.get("intent") not in ("concept", None)),
                        turn_index=t.get("turn", 0),
                    ))

                sc = r.get("score") or {}
                if sc:
                    # 10维扩展存进 score_explanations(表无专用列)
                    ext = {
                        "overhelping": sc.get("overhelping"),
                        "fairness_bias": sc.get("fairness_bias"),
                        "overall_legacy": sc.get("overall_legacy"),
                        "importance_weights": sc.get("importance_weights"),
                        "l1_modules": sc.get("l1_modules"),
                        "guidance_sub": sc.get("guidance_sub"),
                        "overhelping_detail": sc.get("overhelping_detail"),
                        "judge_reasons": sc.get("judge_reasons"),
                        "breakdown": sc.get("breakdown"),
                        "persona_id": r.get("persona_id"),
                        "persona_name": qd.get("persona_name"),
                        "lesson_id": r.get("lesson_id"),
                        "lesson_title": qd.get("lesson_title"),
                    }
                    db.add(m["EvalScore"](
                        scenario_id=scenario.id,
                        correctness=sc.get("correctness", 0.0),
                        relevancy=sc.get("relevancy", 0.0),
                        completeness=sc.get("completeness", 0.0),
                        guidance=sc.get("guidance", 0.0),
                        followup_quality=sc.get("followup_quality", 0.0),
                        boundary_compliance=sc.get("boundary_compliance", 0.0),
                        turn_consistency=sc.get("turn_consistency", 0.0),
                        knowledge_scaffolding=sc.get("knowledge_scaffolding", 0.0),
                        overall=sc.get("overall", 0.0),
                        boundary_status=sc.get("boundary_status", "") or "",
                        n_judges=sc.get("n_judges", 1),
                        judge_variance=sc.get("judge_variance", 0.0),
                        flags=self._json_safe(sc.get("flags", [])),
                        needs_human_review=sc.get("needs_human_review", False),
                        confidences=self._json_safe(sc.get("confidences", {})),
                        score_explanations=self._json_safe(ext),
                        # Phase 1: 证据哈希 (在 flush 后由 _stamp_evidence 填充)
                    ))
            db.flush()

            # ── Phase 1: 证据链 → 对每个场景计算 SHA-256 指纹 ──
            evidence_hashes = self._stamp_evidence(db, ts.id, session_id, results, m)

            # 网站测评
            if web_data:
                db.add(m["WebEvalResult"](
                    url=web_data.get("url", "") or "http://124.174.108.70",
                    overall_score=web_data.get("overall_score", 0),
                    performance=self._json_safe(web_data.get("performance")),
                    accessibility=self._json_safe(web_data.get("accessibility")),
                    best_practices=self._json_safe(web_data.get("best_practices")),
                    ai_function=self._json_safe(web_data.get("ai_function")),
                    ui_ux=self._json_safe(web_data.get("ui_ux")),
                    content=self._json_safe(web_data.get("content")),
                    raw_result=self._json_safe(web_data),
                ))

            # 完整报告
            tsp = (report_dict or {}).get("timestamp", datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
            # 将证据哈希注入 extra, 使其进入 Report.summary_json → API → 前端
            enriched_extra = dict(extra or {})
            if evidence_hashes:
                enriched_extra["evidence_hashes"] = evidence_hashes
            db.add(m["Report"](
                session_id=ts.id, timestamp=tsp,
                summary_json=self._json_safe({
                    "summary": (report_dict or {}).get("summary", {}),
                    "extra": enriched_extra,
                }),
                markdown_path=f"reports/report_{tsp}.md",
                json_path=f"reports/report_{tsp}.json",
            ))

            db.commit()
            self._log(f"  🗄️ 已入库: test_session={ts.id[:8]}… ({len(results)}场景, "
                      f"{'含网站' if web_data else '无网站'})")
            return ts.id
        except Exception as e:
            db.rollback()
            self._log(f"  ⚠️ 入库失败(不影响文件报告): {type(e).__name__}: {str(e)[:120]}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return None
        finally:
            db.close()

    # ── Phase 1: 证据指纹 ──

    def _stamp_evidence(self, db, ts_id: str, session_id: str,
                        results: list, mods: dict) -> list[str]:
        """为每个场景计算 SHA-256 指纹 + 写入 evidence_trail (纯 MySQL)。

        写入内容:
          - eval_scores.evidence_hash = 场景级复合指纹
          - evidence_trail: 3条记录 (conversation + scoring + manifest)
        """
        from src.evidence_hasher import EvidenceHasher

        EvalScore = mods["EvalScore"]
        TestScenario = mods["TestScenario"]
        hasher = EvidenceHasher()

        scenarios = (
            db.query(TestScenario)
            .filter(TestScenario.session_id == ts_id)
            .order_by(TestScenario.scenario_index)
            .all()
        )

        stamped = 0
        evidence_list: list[str] = []

        for scenario in scenarios:
            idx = scenario.scenario_index - 1
            if idx >= len(results):
                continue
            r = results[idx]
            conv_json = {"full_conversation": r.get("full_conversation", "") or ""}
            score_json = r.get("score") or {}

            score_row = (
                db.query(EvalScore)
                .filter(EvalScore.scenario_id == scenario.id)
                .first()
            )
            if not score_row:
                continue

            try:
                fingerprint = hasher.store_evidence(
                    db=db,
                    session_id=session_id,
                    eval_score_id=score_row.id,
                    scenario_index=scenario.scenario_index,
                    conversation_json=conv_json,
                    score_json=score_json,
                    metadata={
                        "persona_id": r.get("persona_id"),
                        "lesson_id": r.get("lesson_id"),
                    },
                )
                stamped += 1
                evidence_list.append(fingerprint)
            except Exception as e:
                self._log(f"  ⚠️ 证据写入失败 scenario #{scenario.scenario_index}: {e}")

        if stamped > 0:
            self._log(f"  🔐 证据指纹: {stamped}/{len(scenarios)} 场景 (SHA-256 → MySQL)")
        return evidence_list
        return evidence_list

    @staticmethod
    def _json_safe(obj):
        """截断超大 base64 等, 保证可入库"""
        import json
        if obj is None:
            return None
        try:
            s = json.dumps(obj, ensure_ascii=False, default=str)
            if len(s) > 4_000_000:  # 防超大字段(如内嵌截图) 撑爆
                return {"_truncated": True, "size": len(s)}
            return json.loads(s)
        except Exception:
            return {"_unserializable": str(type(obj))}


if __name__ == "__main__":
    r = DBRecorder()
    print("available:", r.available())
