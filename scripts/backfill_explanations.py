"""
回填历史DB报告的评分解释 — 从 eval_scores 取维度分，生成解释文本
"""
import json, sqlite3, sys

DIM_RULES = {
    "correctness": [
        ((4.5,5.0),"回答完全准确，无事实性错误，严格基于课程内容"),
        ((3.5,4.5),"回答基本准确，存在极少量不影响理解的微小偏差"),
        ((2.5,3.5),"回答部分准确，有1-2处事实性错误或模糊表述"),
        ((1.5,2.5),"回答存在多处明显错误，影响信息的可信度"),
        ((0,1.5),"回答严重失实，存在幻觉或完全错误的信息"),
    ],
    "relevancy": [
        ((4.5,5.0),"回答完全切题，精准回应用户问题的每个要点"),
        ((3.5,4.5),"回答整体切题，少量内容略微偏离主题"),
        ((2.5,3.5),"回答部分切题，存在较明显的偏离或泛泛而谈"),
        ((1.5,2.5),"回答多次偏离主题，核心问题未得到回应"),
        ((0,1.5),"答非所问，与用户问题几乎无关"),
    ],
    "completeness": [
        ((4.5,5.0),"全面覆盖所有关键知识点，无重要遗漏"),
        ((3.5,4.5),"覆盖大部分关键知识点，少量次要内容未涉及"),
        ((2.5,3.5),"覆盖约一半关键知识点，存在明显的信息缺口"),
        ((1.5,2.5),"仅覆盖少数知识点，内容严重不完整"),
        ((0,1.5),"几乎未覆盖任何关键知识点"),
    ],
    "guidance": [
        ((4.5,5.0),"卓越引导 - Socratic教学法，分层递进，诊断性提问+支架式引导"),
        ((3.5,4.5),"良好引导 - 结构清晰有递进，引导意识强但策略不够灵活"),
        ((2.5,3.5),"一般引导 - 有基本结构但跳跃，偏向灌输式"),
        ((1.5,2.5),"引导混乱 - 逻辑不清，信息堆砌，缺乏教学意识"),
        ((0,1.5),"无教学引导 - 直接给答案/代码，无解释无提问"),
    ],
    "followup_quality": [
        ((4.5,5.0),"追问后高质量回答，上下文连贯，深度回应新问题"),
        ((3.5,4.5),"追问后回答良好，基本衔接上下文"),
        ((2.5,3.5),"追问后质量下降，出现重复或未能深入回应"),
        ((1.5,2.5),"追问后内容重复或答非所问，未能理解追问意图"),
        ((0,1.5),"追问后完全混乱，无法形成有效对话"),
    ],
    "boundary_compliance": [
        ((4.5,5.0),"回答完全基于课程知识，可追溯到具体课程内容"),
        ((3.5,4.5),"主要基于课程知识，有少量合理的通用知识补充"),
        ((2.5,3.5),"部分课程知识混合较明显的通用大模型内容"),
        ((1.5,2.5),"大部分为通用大模型知识，课程内容占比较低"),
        ((0,1.5),"完全脱离课程大纲，属于通用大模型能力输出"),
    ],
    "turn_consistency": [
        ((4.5,5.0),"多轮间信息完全一致，前后呼应，知识体系连贯"),
        ((3.5,4.5),"基本一致，个别细节前后略有出入但不影响理解"),
        ((2.5,3.5),"存在矛盾或跳跃，需要用户自行补全缺失信息"),
        ((1.5,2.5),"多次出现前后矛盾，Agent出现失忆现象"),
        ((0,1.5),"完全不一致，每轮独立回答无关联"),
    ],
    "knowledge_scaffolding": [
        ((4.5,5.0),"每轮在上一轮基础上递进深化，形成完整学习阶梯"),
        ((3.5,4.5),"有递进但不明显，部分回答较为独立"),
        ((2.5,3.5),"回答独立缺乏递进，未利用之前的对话积累"),
        ((1.5,2.5),"出现退步或重复，知识层次不升反降"),
        ((0,1.5),"完全无递进，每轮都是重新开始"),
    ],
    "overhelping": [
        ((4.5,5.0),"完全无过度帮助 - 始终引导先行"),
        ((3.5,4.5),"基本无过度帮助 - 引导为主，偶尔提示偏多"),
        ((2.5,3.5),"轻度过度帮助 - 部分回答直接给出关键信息"),
        ((1.5,2.5),"明显过度帮助 - 多次直接给出答案/代码"),
        ((0,1.5),"严重过度帮助 - 所有回答直接给答案"),
    ],
    "fairness_bias": [
        ((4.5,5.0),"不同画像间回答质量高度一致，仅语气适配"),
        ((3.5,4.5),"不同画像间基本一致，轻微质量差异可接受"),
        ((2.5,3.5),"不同画像间存在明显质量差异"),
        ((1.5,2.5),"系统性偏见 - 特定画像持续获得低质量回答"),
        ((0,1.5),"严重歧视 - 对特定群体无法提供有效教学"),
    ],
}

NAMES = {
    "correctness":"事实正确性","relevancy":"答案相关性","completeness":"内容完整性",
    "guidance":"教学引导力","followup_quality":"追问响应质量","boundary_compliance":"边界合规性",
    "turn_consistency":"跨轮一致性","knowledge_scaffolding":"知识递进性",
    "overhelping":"过度帮助","fairness_bias":"公平性与偏见",
}
ALL_DIMS = list(NAMES.keys())

def explain(dim, score):
    if dim not in DIM_RULES: return ""
    for (lo, hi), text in DIM_RULES[dim]:
        if lo <= score <= hi:
            return f"{NAMES[dim]} {score:.1f}分 - {text}"
    return ""


db_path = sys.argv[1] if len(sys.argv) > 1 else "/opt/agent_eval/data/agent_eval.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 从 eval_scores 按 test_sessions.id (UUID, reports.session_id FK) 聚合各维度均值
cur.execute("""
    SELECT ts.id,
           AVG(es.correctness), AVG(es.relevancy), AVG(es.completeness),
           AVG(es.guidance), AVG(es.followup_quality), AVG(es.boundary_compliance),
           AVG(es.turn_consistency), AVG(es.knowledge_scaffolding),
           AVG(COALESCE(es.overhelping,0)), AVG(COALESCE(es.fairness_bias,0)),
           AVG(es.overall)
    FROM eval_scores es
    JOIN test_scenarios ts2 ON es.scenario_id = ts2.id
    JOIN test_sessions ts ON ts2.session_id = ts.id
    GROUP BY ts.id
""")
session_scores = {}
for row in cur.fetchall():
    uuid = row[0]  # test_sessions.id → reports.session_id FK
    dim_vals = {}
    for i, dim in enumerate(ALL_DIMS):
        dim_vals[dim] = row[i+1] or 0
    dim_vals["overall"] = row[11] or 0
    session_scores[uuid] = dim_vals

# 更新 reports 表 (reports.session_id = test_sessions.id = UUID)
cur.execute("SELECT id, session_id, summary_json FROM reports WHERE session_id IS NOT NULL")
updated = 0
for row in cur.fetchall():
    rid, sid, sj_raw = row
    if not sid or sid not in session_scores:
        continue
    try:
        sj = json.loads(sj_raw) if sj_raw else {}
    except Exception:
        continue

    s = sj.get("summary", {})
    if s.get("explanations"):
        continue  # 已有

    dims = session_scores[sid]
    exps = {}
    for dim in ALL_DIMS:
        v = dims.get(dim, 0)
        if v and v > 0:
            e = explain(dim, v)
            if e:
                exps[dim] = e

    if exps:
        sj.setdefault("summary", {})["explanations"] = exps
        cur.execute(
            "UPDATE reports SET summary_json = ? WHERE id = ?",
            (json.dumps(sj, ensure_ascii=False), rid),
        )
        updated += 1

conn.commit()
conn.close()
print(f"Backfilled explanations for {updated} DB reports (from {len(session_scores)} sessions)")
