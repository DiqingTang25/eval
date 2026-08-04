"""探测 SearchAgentMemory Action 的正确 Service/Version"""
import hashlib, hmac, json, os, urllib.request, urllib.error
from datetime import datetime, timezone
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

AK = os.getenv("VOLC_ACCESS_KEY", "")
SK = os.getenv("VOLC_SECRET_KEY", "")
MEMORY_ID = "mem-d5a321d1"
MEMORY_KEY = os.getenv("VOLC_KB_MEMORY_KEY",
    "H9THBK9FTPD726PF6GTNQ43W3ANCSNAJTA4R308FJDJWFM90N1N060R30D9R74V38")

def hmac_sha256(key, msg):
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()

def signed_headers(host, path, query, body, service, region):
    now = datetime.now(timezone.utc)
    xdate = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    ch = f"content-type:application/json\nhost:{host}\nx-date:{xdate}\n"
    sh = "content-type;host;x-date"
    ph = hashlib.sha256(body.encode()).hexdigest()
    cr = f"POST\n{path}\n{query}\n{ch}\n{sh}\n{ph}"
    cs = f"{datestamp}/{region}/{service}/request"
    sts = f"HMAC-SHA256\n{xdate}\n{cs}\n{hashlib.sha256(cr.encode()).hexdigest()}"
    k_date = hmac_sha256(SK.encode(), datestamp)
    k_region = hmac_sha256(k_date, region)
    k_service = hmac_sha256(k_region, service)
    k_signing = hmac_sha256(k_service, "request")
    sig = hmac.new(k_signing, sts.encode(), hashlib.sha256).hexdigest()
    return {
        "Authorization": f"HMAC-SHA256 Credential={AK}/{cs}, SignedHeaders={sh}, Signature={sig}",
        "X-Date": xdate, "Host": host, "Content-Type": "application/json",
    }

DOMAIN = "open.volcengineapi.com"

tests = [
    # (Action, Version, Service, Region)
    ("SearchAgentMemory", "2023-01-01", "air", "cn-north-1"),
    ("SearchAgentMemory", "2024-07-01", "air", "cn-north-1"),
    ("SearchAgentMemory", "2025-01-01", "air", "cn-north-1"),
    ("SearchAgentMemory", "2024-01-01", "memory", "cn-north-1"),
    ("SearchAgentMemory", "2024-01-01", "ml", "cn-north-1"),
    ("SearchAgentMemory", "2024-01-01", "bot", "cn-north-1"),
    ("SearchAgentMemory", "2024-01-01", "agent", "cn-north-1"),
    ("SearchAgentMemory", "2024-01-01", "hiagent", "cn-north-1"),
    ("RecallAgentMemory", "2024-01-01", "air", "cn-north-1"),
    ("GetAgentMemory", "2024-01-01", "air", "cn-north-1"),
    ("ListAgentMemories", "2024-01-01", "air", "cn-north-1"),
    ("DescribeAgentMemory", "2024-01-01", "air", "cn-north-1"),
]

print(f"Memory ID: {MEMORY_ID}")
print("=" * 60)

for action, version, service, region in tests:
    query = f"Action={action}&Version={version}"
    body = json.dumps({"MemoryId": MEMORY_ID, "Query": "test", "Limit": 3}, ensure_ascii=False)
    headers = signed_headers(DOMAIN, "/", query, body, service, region)
    url = f"https://{DOMAIN}/?{query}"
    try:
        req = urllib.request.Request(url, data=body.encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            err = data.get("ResponseMetadata", {}).get("Error", {})
            code = err.get("Code", "")
            msg = err.get("Message", "")
            if "MissingAction" in code or "InvalidAction" in code:
                continue
            print(f"[{action}] v={version} s={service} r={region}")
            print(f"  code={code} msg={msg}")
            s = json.dumps(data, ensure_ascii=False, indent=2)
            print(f"  {s[:300]}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        if "InvalidAction" not in body and "MissingAction" not in body:
            print(f"[{action}] v={version} s={service} r={region}")
            print(f"  HTTP {e.code}: {body[:200]}")
    except Exception as e:
        pass

# 另外: 尝试直接用Bearer token调用 Knowledge Base API (之前Phase KB用的)
# 确认 mem-d5a321d1 是否可以作为 service_resource_id
print("\n--- 尝试将 mem- ID 作为 Phase KB 的 service_resource_id ---")
KB_URL = "https://api-knowledgebase.mlp.cn-beijing.volces.com/api/knowledge/collection/search_knowledge"
body = json.dumps({
    "service_resource_id": MEMORY_ID,
    "name": "", "query": "测试", "limit": 3,
}, ensure_ascii=False).encode()
try:
    req = urllib.request.Request(KB_URL, data=body, headers={
        "Authorization": f"Bearer {MEMORY_KEY}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        print(f"  HTTP {resp.status} code={data.get('code')}: {data.get('message', '')}")
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", errors="replace")[:200]
    print(f"  HTTP {e.code}: {body}")

print("\nDone.")
