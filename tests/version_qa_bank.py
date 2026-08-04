"""为黄金QA库添加版本元数据"""
import json, os, subprocess
from datetime import datetime

bank_path = "data/golden_qa_bank.json"
bank = json.load(open(bank_path, "r", encoding="utf-8"))

# 获取git hash
try:
    git_hash = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stderr=subprocess.DEVNULL
    ).decode().strip()
except Exception:
    git_hash = "no-git"

# 检测当前格式
if isinstance(bank, dict) and "items" in bank:
    print("✅ 已有版本元数据")
    bank["updated_at"] = datetime.now().isoformat()
    bank["git_hash"] = git_hash
    bank["item_count"] = len(bank["items"])
else:
    # 纯list → 包装
    print("🔄 添加版本元数据...")
    bank = {
        "version": "3.2",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "git_hash": git_hash,
        "item_count": len(bank),
        "items": bank,
    }

json.dump(bank, open(bank_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# 统计
items = bank if isinstance(bank, list) else bank.get("items", [])
phases = {}; types = {}; diffs = {}; adv = 0; multi = 0
for q in items:
    phases[q.get("phase","?")] = phases.get(q.get("phase","?"),0)+1
    types[q.get("type","?")] = types.get(q.get("type","?"),0)+1
    diffs[q.get("difficulty","?")] = diffs.get(q.get("difficulty","?"),0)+1
    if q.get("adversarial_type"): adv += 1
    if q.get("type") == "多轮对话": multi += 1

print(f"✅ 版本化完成")
print(f"   版本: {bank.get('version','?')}")
print(f"   Git: {bank.get('git_hash','?')}")
print(f"   总计: {len(items)} 条")
print(f"   对抗性: {adv} | 多轮: {multi}")
print(f"   阶段: {dict(sorted(phases.items()))}")
