#!/usr/bin/env python3
"""最终审查脚本 — 检查 Agent B/C + 全链路"""
import os, yaml, glob
base = "/opt/agent_eval"

print("=" * 50)
print("最终审查")
print("=" * 50)

# 1. Explorer 集成
print("\n--- Explorer 流水线接入 ---")
exp = open(f"{base}/src/platform_probe/explorer.py").read()
for mod in ["dom_step_discovery", "deep_explorer", "step_extractor", "l3_fuzzer", "l2_vision"]:
    status = "✅" if mod in exp else "❌"
    print(f"  {status} {mod}")

# 2. 误放文件
print("\n--- 误放文件 ---")
checks = [
    ("src/platform_probe/app.js", "app.js"),
    ("src/platform_probe/explorer_service.py", "explorer_service.py"),
]
for path, name in checks:
    full = f"{base}/{path}"
    if os.path.exists(full):
        print(f"  ❌ {name} 仍在 platform_probe/")
    else:
        print(f"  ✅ {name} 已清理")

# 3. 最新 Schema
print("\n--- Schema 数据 ---")
for d in sorted(glob.glob(f"{base}/output/platform_probe/*/"), reverse=True)[:5]:
    sf = os.path.join(d, "platform_schema.yaml")
    if os.path.exists(sf):
        data = yaml.safe_load(open(sf))
        s = data.get("structure", {})
        print(f"  {os.path.basename(d.rstrip('/'))[:50]}")
        print(f"    phases={len(s.get('phases',[]))} lessons={len(s.get('lessons',[]))} steps={len(s.get('steps',[]))}")

# 4. API 连通
print("\n--- API 连通 ---")
import urllib.request, json
try:
    body = json.dumps({"strategy":"spot_check","target_url":"http://124.174.108.70/personalized-secure"}).encode()
    req = urllib.request.Request("http://127.0.0.1:8000/api/tests/run-multi-agent",
        data=body, headers={"Content-Type":"application/json"}, method="POST")
    r = urllib.request.urlopen(req, timeout=10)
    data = json.loads(r.read())
    print(f"  ✅ API: {data.get('status')} ({data.get('session_id','?')[:30]})")
except Exception as e:
    print(f"  ❌ API: {e}")

# 5. Planner
print("\n--- Planner ---")
import sys
sys.path.insert(0, base)
os.chdir(base)
from src.multi_agent.planner import PlannerAgent
p = PlannerAgent()
plan = p.generate(strategy="spot_check")
print(f"  phases={len(plan.phases)} lessons={sum(len(ph.lessons) for ph in plan.phases)} available={plan.plan_available}")

# 6. 总结
print("\n--- 总结 ---")
issues = []
if "dom_step_discovery" not in exp:
    issues.append("l1_7 未接入 explorer.py")
if not any(os.path.exists(f"{base}/{p}") for p, _ in checks):
    pass  # clean
else:
    issues.append("仍有误放文件")

# 检查最新 schema steps
latest = sorted(glob.glob(f"{base}/output/platform_probe/*/platform_schema.yaml"), reverse=True)
if latest:
    data = yaml.safe_load(open(latest[0]))
    steps = len(data.get("structure", {}).get("steps", []))
    if steps == 0:
        issues.append(f"最新 schema steps=0 (Agent B L1.7/L1.9 未产出)")

if plan.plan_available and len(plan.phases) > 20:
    pass
else:
    issues.append("Planner 产出不足")

if issues:
    print(f"  ⚠️  {len(issues)} 个待解决问题:")
    for i in issues:
        print(f"     - {i}")
else:
    print("  ✅ 全部通过")
