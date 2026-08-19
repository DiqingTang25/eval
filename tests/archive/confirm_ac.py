#!/usr/bin/env python3
"""确认 Agent C 提出的两个待办项"""
import os, yaml, glob, re

base = "/opt/agent_eval"
os.chdir(base)

# 1. Schema Phase 名称 vs 平台实际内容
print("=" * 50)
print("1. Schema Phase 名称")
print("=" * 50)

latest_schemas = sorted(glob.glob("output/platform_probe/*/platform_schema.yaml"), reverse=True)
if latest_schemas:
    sf = latest_schemas[0]
    print(f"  来源: {sf}")
    d = yaml.safe_load(open(sf))
    phases = d.get("structure", {}).get("phases", [])
    print(f"  Phase 数量: {len(phases)}")
    print(f"  前 10 个 Phase 名称:")
    for p in phases[:10]:
        print(f"    {p.get('id', '?')}: {p.get('name', '?')}")

# 2. target_url 传递确认
print()
print("=" * 50)
print("2. target_url 传递链路")
print("=" * 50)
print("  前端 trStart():")
print("    _platformProfile.target_url || _targetUrl || localStorage.getItem('targetUrl')")
print()
print("  前端 trConfirmStart():")
print("    POST {target_url, ...} → /api/tests/run-multi-agent")
print()
print("  后端 trigger_multi_agent():")
print("    body.target_url → start_multi_agent(target_url=...)")
print()
print("  后端 _run_multi_agent():")
print("    target_url → MultiAgentOrchestrator(target_url=...)")
print()
print("  Orchestrator → ExecutorAgent(target_url=...)")
print("  ExecutorAgent → BrowserEvaluator(base_url=...)")
print()

# 3. 检查最新日志中的 target_url
print("=" * 50)
print("3. 最新 MultiAgent 启动日志")
print("=" * 50)
try:
    with open("/var/log/agent_eval.log") as f:
        for line in f:
            if "target_url=" in line and "MultiAgent" in line:
                print(f"  {line.strip()[-120:]}")
except:
    print("  无法读取日志")

# 4. 当前 platform_profile 的 target_url
print()
print("=" * 50)
print("4. 当前 Profile target_url")
print("=" * 50)
try:
    import json
    profile = json.loads(open("output/platform_probe/platform_profile.json").read())
    print(f"  target_url: {profile.get('target_url')}")
    print(f"  phases_found: {profile.get('phases_found')}")
    print(f"  schema_path: {profile.get('schema_path')}")
except Exception as e:
    print(f"  无法读取: {e}")
