"""一键批量审核所有待处理 QA → 黄金库"""
import json
from datetime import datetime

pending_path = "data/qa_pending.json"
golden_path = "data/golden_qa_bank.json"

pending = json.load(open(pending_path, "r", encoding="utf-8"))
golden = json.load(open(golden_path, "r", encoding="utf-8"))

existing_ids = {g["qa_id"] for g in golden}
added = 0

for q in pending:
    if q["qa_id"] not in existing_ids and q.get("status") != "rejected":
        q["status"] = "approved"
        q["reviewer_notes"] = "批量审核通过"
        q["approved_at"] = datetime.now().isoformat()
        golden.append(q)
        existing_ids.add(q["qa_id"])
        added += 1
    elif q["qa_id"] in existing_ids:
        # 更新已有记录的审核时间
        for g in golden:
            if g["qa_id"] == q["qa_id"]:
                g["status"] = "approved"
                g["approved_at"] = datetime.now().isoformat()

# 同步更新 pending 文件
for q in pending:
    if q["qa_id"] in existing_ids:
        q["status"] = "approved"
        q["reviewer_notes"] = "批量审核通过"

json.dump(golden, open(golden_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(pending, open(pending_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# 统计
phases = {}
types = {}
for g in golden:
    p = g["phase"]
    t = g["type"]
    phases[p] = phases.get(p, 0) + 1
    types[t] = types.get(t, 0) + 1

print(f"✅ 批量审核完成")
print(f"   待审核 → 通过: {added} 条")
print(f"   黄金QA库总计: {len(golden)} 条")
print(f"   阶段分布: {dict(sorted(phases.items()))}")
print(f"   题型分布: {dict(sorted(types.items()))}")

# 打印所有问题标题
print(f"\n📋 黄金QA列表:")
for i, g in enumerate(golden, 1):
    print(f"  {i}. [{g['phase']}][{g['type']}] {g['question'][:60]}...")
