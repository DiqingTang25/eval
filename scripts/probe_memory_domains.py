"""
探测记忆库在其他域名/路径上的API
"""

import json, os, sys, urllib.request, urllib.error
from pathlib import Path

env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() not in os.environ:
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")

MEMORY_ID = "mem-d5a321d1"
MEMORY_KEY = "H9THBK9FTPD726PF6GTNQ43W3ANCSNAJTA4R308FJDJWFM90N1N060R30D9R74V38"
HIAGENT_URL = os.getenv("HIAGENT_URL", "https://aiagent.xjtlu.edu.cn")
XJTLU_BASE = os.getenv("XJTLU_BASE_URL", "https://aiagent.xjtlu.edu.cn/api/aigw/v1")

targets = [
    # HiAgent平台本身 (记忆库属于HiAgent)
    ("HiAgent: memory/recall", f"{HIAGENT_URL}/api/memory/recall",
     {"memory_id": MEMORY_ID, "query": "测试", "limit": 3}),
    ("HiAgent: bot/memory/search", f"{HIAGENT_URL}/api/bot/memory/search",
     {"memory_id": MEMORY_ID, "query": "测试"}),
    ("HiAgent: aigw memory", f"{XJTLU_BASE}/memory/search",
     {"memory_id": MEMORY_ID, "query": "测试"}),

    # 火山主API
    ("Volc Main: memory search", "https://open.volcengineapi.com/api/memory/v1/search",
     {"memory_id": MEMORY_ID, "query": "测试", "limit": 3}),

    # 不同路径的知识库域名
    ("KB Domain: v1/memory", "https://api-knowledgebase.mlp.cn-beijing.volces.com/api/v1/memory/search",
     {"resource_id": MEMORY_ID, "query": "测试"}),
    ("KB Domain: bot memory", "https://api-knowledgebase.mlp.cn-beijing.volces.com/api/bot/memory/search",
     {"memory_id": MEMORY_ID, "query": "测试"}),
]

print(f"Memory ID: {MEMORY_ID}")
print(f"Memory Key: {MEMORY_KEY[:20]}...")
print("=" * 60)

for label, url, body in targets:
    print(f"\n[{label}] POST {url}")
    body_bytes = json.dumps(body, ensure_ascii=False).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MEMORY_KEY}",
    }
    try:
        req = urllib.request.Request(url, data=body_bytes, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            code = data.get("code", "?")
            print(f"  HTTP {resp.status} code={code}")
            s = json.dumps(data, ensure_ascii=False, indent=2)
            if len(s) > 500:
                s = s[:500] + "\n..."
            print(f"  {s}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        print(f"  HTTP {e.code}: {body}")
    except Exception as e:
        print(f"  {type(e).__name__}: {e}")

print("\nDone.")
