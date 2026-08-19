#!/usr/bin/env python3
"""审查 Agent B/C 产出的脚本"""
import os, sys, json, glob
import yaml

base = "/opt/agent_eval"
os.chdir(base)
sys.path.insert(0, base)

print("=" * 60)
print("Agent B/C 代码与数据审查")
print("=" * 60)

# ── 1. Schema 质量 ──
print("\n--- 1. Schema steps 数据 ---")
probe_dir = os.path.join(base, "output", "platform_probe")
schemas = []
for d in sorted(glob.glob(probe_dir + "/*/")):
    sf = os.path.join(d, "platform_schema.yaml")
    if os.path.exists(sf):
        data = yaml.safe_load(open(sf))
        s = data.get("structure", {})
        schemas.append({
            "name": os.path.basename(d.rstrip("/")),
            "phases": len(s.get("phases", [])),
            "lessons": len(s.get("lessons", [])),
            "steps": len(s.get("steps", [])),
            "apis": len(data.get("apis", [])),
            "confidence": data.get("confidence_scores", {}).get("overall", 0),
        })

schemas.sort(key=lambda x: x["name"], reverse=True)
for sc in schemas[:8]:
    print(f"  {sc['name'][:50]}")
    print(f"    phases={sc['phases']} lessons={sc['lessons']} steps={sc['steps']} apis={sc['apis']} conf={sc['confidence']}")

# ── 2. 新增代码模块 ──
print("\n--- 2. 新增模块检查 ---")
new_modules = [
    ("deep_explorer.py", "Agent B: 深度探索器"),
    ("step_extractor.py", "Agent B: LLM步骤提取"),
    ("dom_step_discovery.py", "Agent B: DOM Step发现"),
    ("api_keys.py", "Agent B: API Key管理"),
    ("multi_agent/__init__.py", "Agent C: Multi-Agent入口"),
    ("mcp_server.py", "Agent C: MCP Server"),
    ("self_healing.py", "Agent C: Self-Healing"),
    ("visual_assertion.py", "Agent C: Visual Assertion"),
    ("coverage_tracker.py", "Agent C: Coverage Tracker"),
    ("llm_client.py", "Agent C: LLM Client"),
]
for fname, desc in new_modules:
    path = os.path.join(base, "src", fname)
    exists = os.path.exists(path)
    if exists:
        if os.path.isdir(path):
            pys = glob.glob(path + "/*.py")
            lines = sum(len(open(p).readlines()) for p in pys)
            status = f"{len(pys)} files, {lines} lines"
        else:
            lines = len(open(path).readlines())
            status = f"{lines} lines"
        print(f"  ✅ {desc}: {status}")
    else:
        print(f"  ❌ {desc}: MISSING")

# ── 3. 误放文件 ──
print("\n--- 3. 误放文件检查 ---")
bad_locations = [
    (os.path.join(base, "src/platform_probe/app.js"), "app.js 应该在 frontend/js/ 不在 platform_probe/"),
    (os.path.join(base, "src/platform_probe/explorer_service.py"), "explorer_service.py 应该在 backend/services/ 不在 platform_probe/"),
]
for path, msg in bad_locations:
    if os.path.exists(path):
        print(f"  ❌ {msg}")
    else:
        print(f"  ✅ {os.path.basename(path)} 位置正确")

# ── 4. 探索流水线接入 ──
print("\n--- 4. Explorer 流水线 ---")
exp_path = os.path.join(base, "src/platform_probe/explorer.py")
exp_code = open(exp_path).read()
checks = {
    "dom_discovery": "dom_step_discovery" in exp_code,
    "step_extract": "step_extractor" in exp_code,
    "deep_explore": "deep_explorer" in exp_code,
    "l2_vision": "l2_vision" in exp_code,
    "l3_fuzzer": "l3_fuzzer" in exp_code,
}
for mod, present in checks.items():
    print(f"  {mod}: {'✅ 已接入' if present else '❌ 未接入'}")

# ── 5. test_service 接入 ──
print("\n--- 5. test_service 接入 ---")
ts_path = os.path.join(base, "backend/services/test_service.py")
ts_code = open(ts_path).read()
ts_checks = {
    "self_healing": "self_healing" in ts_code,
    "coverage": "coverage_tracker" in ts_code,
    "multi_agent": "multi_agent" in ts_code,
}
for mod, present in ts_checks.items():
    print(f"  {mod}: {'✅ 已接入' if present else '❌ 未接入'}")

# ── 6. 总结 ──
print("\n--- 6. 评分 ---")
score = 0
issues = []

# Schema steps
if schemas and schemas[0]["steps"] > 0:
    score += 20
else:
    issues.append("Schema steps=0 — Agent B 的 L1.7/L1.8/L1.9 未产出 step 数据")

# Explorer integration
if checks["dom_discovery"] and checks["step_extract"] and checks["deep_explore"]:
    score += 20
else:
    missing = [k for k, v in checks.items() if not v]
    issues.append(f"Explorer 未接入: {missing}")

# test_service integration
if ts_checks["self_healing"] and ts_checks["coverage"] and ts_checks["multi_agent"]:
    score += 20
else:
    missing = [k for k, v in ts_checks.items() if not v]
    issues.append(f"test_service 未接入: {missing}")

# No misplaced files
if not any(os.path.exists(p) for p, _ in bad_locations):
    score += 20
else:
    issues.append("有文件放在错误位置")

# All modules present
all_modules = all(os.path.exists(os.path.join(base, "src", f[0])) for f in new_modules)
if all_modules:
    score += 20

print(f"  评分: {score}/100")
for i in issues:
    print(f"  ⚠️  {i}")
