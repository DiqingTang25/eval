"""
探测火山引擎记忆库的 OpenAPI Action 名称

火山引擎 OpenAPI 格式:
  POST https://open.volcengineapi.com/?Action=XXX&Version=YYYY-MM-DD
  Body: JSON
  Auth: HMAC-SHA256 或 AK/SK
"""

import hashlib, hmac, json, os, sys, urllib.request, urllib.error
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
MEMORY_KEY = "H9THBK9FTPD726PF6GTNQ43W3ANCSNAJTA4R308FJDJWFM90N1N060R30D9R74V38"

SERVICE = "air"
REGION = "cn-north-1"
DOMAIN = "open.volcengineapi.com"

print(f"Memory ID: {MEMORY_ID}")
print(f"AK: {AK[:8]}...")
print("=" * 60)

def hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()

def signed_request(method, host, path, query, body):
    now = datetime.now(timezone.utc)
    xdate = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    canonical_headers = f"content-type:application/json\nhost:{host}\nx-date:{xdate}\n"
    signed_headers = "content-type;host;x-date"
    payload_hash = hashlib.sha256(body.encode()).hexdigest()
    canonical_request = f"{method}\n{path}\n{query}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    credential_scope = f"{datestamp}/{REGION}/{SERVICE}/request"
    cr_hash = hashlib.sha256(canonical_request.encode()).hexdigest()
    string_to_sign = f"HMAC-SHA256\n{xdate}\n{credential_scope}\n{cr_hash}"
    k_date = hmac_sha256(SK.encode(), datestamp)
    k_region = hmac_sha256(k_date, REGION)
    k_service = hmac_sha256(k_region, SERVICE)
    k_signing = hmac_sha256(k_service, "request")
    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
    auth = f"HMAC-SHA256 Credential={AK}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"
    return {
        "Authorization": auth, "X-Date": xdate,
        "Host": host, "Content-Type": "application/json",
    }

# 常见的记忆API Action名
actions = [
    ("SearchMemory", "2024-01-01"),
    ("SearchMemory", "2025-01-01"),
    ("RecallMemory", "2024-01-01"),
    ("RecallMemory", "2025-01-01"),
    ("QueryMemory", "2024-01-01"),
    ("SearchRecord", "2024-01-01"),
    ("RecallRecord", "2024-01-01"),
    ("ListMemories", "2024-01-01"),
    ("GetMemory", "2024-01-01"),
    ("SearchAgentMemory", "2024-01-01"),
    ("MemorySearch", "2024-01-01"),
]

for action, version in actions:
    query = f"Action={action}&Version={version}"
    body_dict = {"MemoryId": MEMORY_ID, "Query": "测试", "Limit": 3}
    body_str = json.dumps(body_dict, ensure_ascii=False)
    headers = signed_request("POST", DOMAIN, "/", query, body_str)
    url = f"https://{DOMAIN}/?{query}"

    try:
        req = urllib.request.Request(url, data=body_str.encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            err = data.get("ResponseMetadata", {}).get("Error", {})
            if err:
                code = err.get("Code", "")
                msg = err.get("Message", "")
                if code == "MissingAction":
                    continue  # 静默跳过
                if "InvalidAction" in code or "not found" in msg.lower():
                    continue
                print(f"[{action}] HTTP {resp.status} | {code}: {msg[:120]}")
            else:
                print(f"[{action}] ✅ SUCCESS!")
                s = json.dumps(data, ensure_ascii=False, indent=2)
                print(s[:600])
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        if "MissingAction" not in body and "InvalidAction" not in body:
            print(f"[{action}] HTTP {e.code}: {body[:150]}")
    except Exception as e:
        if "MissingAction" not in str(e) and "InvalidAction" not in str(e):
            print(f"[{action}] {e}")

print("\nDone — 如果有任何 Action 返回了 code!=MissingAction/InvalidAction, 则可能是正确端点")
