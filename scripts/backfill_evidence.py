"""
历史数据证据回填脚本

对 SQLite/MySQL 中已有的 eval_scores 逐条计算 SHA-256 evidence_hash,
并构建场景哈希链, 嵌入到关联的 reports 中。

用法:
    python scripts/backfill_evidence.py [--db sqlite|mysql] [--dry-run]
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def backfill_sqlite(db_path: str, dry_run: bool = False):
    """回填 SQLite 数据库"""
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ── 1. 找到所有需要回填的 eval_scores ──
    # 检查列是否存在 (兼容迁移前后的 schema)
    cur.execute('PRAGMA table_info(eval_scores)')
    eval_cols = {c[1] for c in cur.fetchall()}
    has_overhelping = 'overhelping' in eval_cols
    has_fairness = 'fairness_bias' in eval_cols

    oh_col = 'es.overhelping' if has_overhelping else '0.0 AS overhelping'
    fb_col = 'es.fairness_bias' if has_fairness else '0.0 AS fairness_bias'

    cur.execute(f"""
        SELECT es.id, es.scenario_id, es.overall, es.correctness, es.relevancy,
               es.completeness, es.guidance, es.followup_quality,
               es.boundary_compliance, es.turn_consistency, es.knowledge_scaffolding,
               {oh_col}, {fb_col}, es.n_judges, es.judge_variance,
               es.flags, es.needs_human_review, es.confidences, es.evidence_hash,
               ts.session_id, ts.scenario_index,
               ts.full_conversation
        FROM eval_scores es
        JOIN test_scenarios ts ON es.scenario_id = ts.id
        WHERE es.evidence_hash IS NULL OR es.evidence_hash = ''
        ORDER BY ts.session_id, ts.scenario_index
    """)
    scores = cur.fetchall()
    print(f"找到 {len(scores)} 条需回填的 eval_score")

    if not scores:
        print("无需回填, 所有 evidence_hash 已存在")
        conn.close()
        return

    # ── 2. 按 session 分组, 构建对话文本 ──
    # conversation_turns 有每轮对话, 拼接起来
    cur.execute("""
        SELECT ct.scenario_id, ct.turn, ct.question, ct.response_text,
               ct.response_duration, ct.response_status
        FROM conversation_turns ct
        ORDER BY ct.scenario_id, ct.turn
    """)
    turns_by_scenario: dict[str, list] = {}
    for r in cur.fetchall():
        sid = r["scenario_id"]
        if sid not in turns_by_scenario:
            turns_by_scenario[sid] = []
        turns_by_scenario[sid].append(dict(r))

    # ── 3. 逐条计算 evidence_hash ──
    updated = 0
    evidence_list_by_session: dict[str, list[str]] = {}

    for s in scores:
        def _g(row, key, default=0):
            """安全取值: sqlite3.Row 用索引, dict 用 .get"""
            try:
                v = row[key]
            except (KeyError, IndexError):
                return default
            return v if v is not None else default

        flags_raw = _g(s, "flags", "")
        try:
            flags_parsed = json.loads(flags_raw) if flags_raw and flags_raw != "[]" else []
        except (json.JSONDecodeError, TypeError):
            flags_parsed = []

        score_dict = {
            "correctness": _g(s, "correctness"),
            "relevancy": _g(s, "relevancy"),
            "completeness": _g(s, "completeness"),
            "guidance": _g(s, "guidance"),
            "followup_quality": _g(s, "followup_quality"),
            "boundary_compliance": _g(s, "boundary_compliance"),
            "turn_consistency": _g(s, "turn_consistency"),
            "knowledge_scaffolding": _g(s, "knowledge_scaffolding"),
            "overhelping": _g(s, "overhelping"),
            "fairness_bias": _g(s, "fairness_bias"),
            "overall": _g(s, "overall"),
            "n_judges": _g(s, "n_judges"),
            "judge_variance": _g(s, "judge_variance"),
            "flags": flags_parsed,
            "needs_human_review": bool(_g(s, "needs_human_review", False)),
        }

        # 对话: 优先用 full_conversation, 否则从 turns 拼接
        full_conv = s["full_conversation"] or ""
        if len(full_conv) < 20:
            # full_conversation 太短, 从 turns 拼接
            turns = turns_by_scenario.get(s["scenario_id"], [])
            conv_parts = []
            for t in turns:
                q = t.get("question", "") or ""
                resp = t.get("response_text", "") or ""
                conv_parts.append(f"[第{t.get('turn', 0)}轮] 问: {q}")
                conv_parts.append(f"[第{t.get('turn', 0)}轮] 答: {resp}")
            full_conv = "\n".join(conv_parts)

        # 计算复合哈希
        composite = json.dumps({
            "conversation": full_conv,
            "score": score_dict,
        }, ensure_ascii=False, sort_keys=True, default=str)
        evidence_hash = hashlib.sha256(composite.encode("utf-8")).hexdigest()

        if dry_run:
            print(f"  [DRY-RUN] {s['id'][:16]}... scenario=#{s['scenario_index']} "
                  f"overall={score_dict['overall']:.2f} conv_len={len(full_conv)} "
                  f"hash={evidence_hash[:16]}...")
        else:
            cur.execute(
                "UPDATE eval_scores SET evidence_hash = ? WHERE id = ?",
                (evidence_hash, s["id"]),
            )

        # 按 session 收集哈希(用于构建链)
        session_id = s["session_id"]
        if session_id not in evidence_list_by_session:
            evidence_list_by_session[session_id] = []
        evidence_list_by_session[session_id].append(evidence_hash)

        updated += 1

    # ── 4. 对每个 session 构建哈希链, 嵌入 reports ──
    if not dry_run:
        conn.commit()
        print(f"  ✅ 已更新 {updated} 条 eval_scores.evidence_hash")

    for session_id, hashes in evidence_list_by_session.items():
        # 构建简单哈希链
        chain = []
        prev = "0" * 64
        for i, h in enumerate(hashes):
            combined = prev + h
            node_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()
            chain.append({
                "index": i + 1,
                "hash": node_hash[:16],
                "hash_full": node_hash,
                "prev_hash": prev[:16],
                "evidence_hash": h[:16],
            })
            prev = node_hash

        chain_root = chain[-1]["hash_full"] if chain else ""

        # 查找关联的 report 并更新 summary_json
        cur.execute("""
            SELECT r.id, r.summary_json FROM reports r
            JOIN test_sessions ts ON r.session_id = ts.id
            WHERE ts.id = ?
            ORDER BY r.created_at DESC LIMIT 1
        """, (session_id,))
        report_r = cur.fetchone()
        if report_r:
            try:
                sj = json.loads(report_r["summary_json"]) if report_r["summary_json"] else {}
            except (json.JSONDecodeError, TypeError):
                sj = {}

            # 注入证据数据
            evidence_block = {
                "evidence_hashes": hashes,
                "scenario_chain": chain,
                "chain_root": chain_root,
                "backfilled_at": datetime.now(timezone.utc).isoformat(),
                "backfill_note": "历史数据回填: conversation从conversation_turns拼接, 评分从eval_scores读取",
            }

            if "extra" not in sj:
                sj["extra"] = {}
            sj["extra"]["evidence"] = evidence_block
            sj["extra"]["evidence_hashes"] = hashes

            if dry_run:
                print(f"  [DRY-RUN] report session={session_id[:20]}... chain_len={len(chain)}")
            else:
                cur.execute(
                    "UPDATE reports SET summary_json = ? WHERE id = ?",
                    (json.dumps(sj, ensure_ascii=False), report_r["id"]),
                )
                conn.commit()
                print(f"  ✅ report session={session_id[:20]}... 已嵌入证据链 ({len(chain)}节点)")

    if dry_run:
        print(f"\n[DRY-RUN 完成] 将更新 {updated} 条 eval_score + {len(evidence_list_by_session)} 个 report")
        print("去掉 --dry-run 参数以实际执行")

    conn.close()


def main():
    dry_run = "--dry-run" in sys.argv

    # 自动检测数据库类型
    db_path = PROJECT_ROOT / "data" / "agent_eval.db"
    if not db_path.exists():
        print(f"错误: 数据库文件不存在: {db_path}")
        sys.exit(1)

    print(f"数据库: {db_path}")
    print(f"模式: {'DRY-RUN (预览不写入)' if dry_run else '实际写入'}")
    print()

    backfill_sqlite(str(db_path), dry_run=dry_run)


if __name__ == "__main__":
    main()
