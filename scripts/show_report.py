"""展示最新测评报告"""
import json, os

reports = sorted([f for f in os.listdir("reports") if f.endswith(".json")], reverse=True)
latest = reports[0]
print(f"=== 最新报告: {latest} ===\n")

with open(f"reports/{latest}") as f:
    r = json.load(f)

s = r["summary"]
print("=" * 55)
print("  测评报告汇总")
print("=" * 55)
print(f"  总场景: {s['total']} | 成功: {s['success']} | 超时: {s['timeout']} | 错误: {s['error']}")
print(f"  综合分: {s['avg_scores']['overall']}")
print()
print("  8维度均分:")
for dim in ["correctness","relevancy","completeness","guidance","followup_quality","boundary_compliance","turn_consistency","knowledge_scaffolding"]:
    val = s['avg_scores'][dim]
    bar = "█" * int(val) + "░" * (5 - int(val))
    print(f"    {dim:25s} {val:.1f} {bar}")
print()
print("  边界检测:")
b = s['boundary']
print(f"    范围内: {b['in_scope']} | 部分: {b['partial_match']} | 超出: {b['out_of_scope']}")
print()
print("=" * 55)
print("  场景详情")
print("=" * 55)

for i, d in enumerate(r["details"]):
    q = d["question_data"]
    sc = d.get("score") or {}
    print(f"\n[{i+1}] {q['qa_id']} | {q['phase']} | {q['type']} | {q['difficulty']}")
    print(f"  问题: {q['question'][:150]}")
    for t in d.get("conversation_turns", []):
        resp = t["response"]["response"][:250].replace("\n", " ")
        print(f"  Turn{t['turn']}: {resp}")
    print(f"  得分: overall={sc.get('overall','N/A')} correct={sc.get('correctness','-')} relev={sc.get('relevancy','-')}")
    print(f"  complete={sc.get('completeness','-')} guidance={sc.get('guidance','-')}")
    print(f"  L1规则分: {sc.get('rule_score','-')} | 跳过LLM: {sc.get('skip_llm_dims',[])}")
    print(f"  flags: {sc.get('flags',[])}")
    if sc.get("rule_evidence"):
        print(f"  L1证据:")
        for e in sc["rule_evidence"][:4]:
            print(f"    {e}")
