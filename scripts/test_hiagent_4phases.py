"""Test all 4 HiAgent Phases via REST API"""
import sys, os, json, time
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()

phases = [
    ("hi_phase1", "Phase 1 - 国产AI技术基础", os.getenv("HIAGENT_PHASE1_APPID"), os.getenv("HIAGENT_PHASE1_APIKEY")),
    ("hi_phase2", "Phase 2 - 新型硬件设计", os.getenv("HIAGENT_PHASE2_APPID"), os.getenv("HIAGENT_PHASE2_APIKEY")),
    ("hi_phase3_4", "Phase 3&4 - 环境感知与触觉反馈", os.getenv("HIAGENT_PHASE3_4_APPID"), os.getenv("HIAGENT_PHASE3_4_APIKEY")),
    ("hi_phase5", "Phase 5 - 具身智能控制", os.getenv("HIAGENT_PHASE5_APPID"), os.getenv("HIAGENT_PHASE5_APIKEY")),
]

test_question = "请简单介绍一下这门课程的主要内容"

for agent_id, name, app_id, api_key in phases:
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"  app_id: {app_id[:16] if app_id else 'MISSING'}...")
    print(f"  api_key: {'SET' if api_key else 'MISSING'}")

    if not app_id or not api_key:
        print(f"  ❌ SKIP: Missing credentials")
        continue

    # Direct API test
    import urllib.request, urllib.error
    body = json.dumps({
        "app_id": app_id,
        "query": test_question,
        "response_mode": "blocking",
        "user": "agent-eval-test"
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        "https://aiagent.xjtlu.edu.cn/api/proxy/api/v1",
        data=body,
        headers={"Apikey": api_key, "Content-Type": "application/json"}
    )

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
            answer = data.get("answer", "") or data.get("text", "") or str(data)
            elapsed = time.time() - start
            print(f"  ✅ SUCCESS ({elapsed:.1f}s)")
            print(f"  Answer: {answer[:200]}...")
            print(f"  conversation_id: {data.get('conversation_id', 'N/A')}")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:300]
        print(f"  ❌ HTTP {e.code}: {err}")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")

print(f"\n{'='*60}")
print("Done.")
