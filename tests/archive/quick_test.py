#!/usr/bin/env python3
"""环1-3 快速测试 (不需要浏览器)"""
import urllib.request, json, os, sys

def test1():
    r = urllib.request.urlopen("http://124.174.108.70/personalized-secure", timeout=10)
    size = len(r.read())
    print(f"环1 平台可达: HTTP {r.status}, {size}B")
    return size > 100

def test2():
    body = json.dumps({"strategy":"spot_check","target_url":"http://124.174.108.70/personalized-secure"}).encode()
    req = urllib.request.Request("http://127.0.0.1:8000/api/tests/run-multi-agent",
        data=body, headers={"Content-Type":"application/json"}, method="POST")
    r = urllib.request.urlopen(req, timeout=10)
    data = json.loads(r.read())
    print(f"环2 API: {data}")
    return data.get("status") == "started"

def test3():
    os.chdir("/opt/agent_eval")
    sys.path.insert(0, "/opt/agent_eval")
    from src.multi_agent.planner import PlannerAgent
    p = PlannerAgent()
    plan = p.generate(strategy="spot_check")
    ok = plan.plan_available and len(plan.phases) > 0
    print(f"环3 Planner: available={plan.plan_available} phases={len(plan.phases)}")
    for ph in plan.phases[:5]:
        print(f"  {ph.phase_id}: {ph.phase_name} ({len(ph.lessons)} lessons)")
    return ok

for name, fn in [("环1", test1), ("环2", test2), ("环3", test3)]:
    try:
        ok = fn()
        print(f"✅ {name} PASSED" if ok else f"❌ {name} FAILED")
    except Exception as e:
        print(f"❌ {name} ERROR: {e}")
