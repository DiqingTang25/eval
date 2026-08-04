"""
系统探测火山引擎记忆库的 OpenAPI

火山引擎 OpenAPI:
  POST https://open.volcengineapi.com/?Action=XXX&Version=YYY
  Service 名需要在签名中指定

记忆库 (mem-d5a321d1) 是火山引擎云产品, API在 open.volcengineapi.com
"""
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
REGION = "cn-north-1"

def hmac_sha256(key, msg):
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()

def try_action(action, version, service, body_dict, region="cn-north-1"):
    """尝试 OpenAPI 调用, 返回 (error_code, error_msg) 或 (None, data)"""
    DOMAIN = "open.volcengineapi.com"
    query = f"Action={action}&Version={version}"
    body = json.dumps(body_dict, ensure_ascii=False)

    now = datetime.now(timezone.utc)
    xdate = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    ch = f"content-type:application/json\nhost:{DOMAIN}\nx-date:{xdate}\n"
    sh_headers = "content-type;host;x-date"
    ph = hashlib.sha256(body.encode()).hexdigest()
    cr = f"POST\n/\n{query}\n{ch}\n{sh_headers}\n{ph}"
    cs = f"{datestamp}/{region}/{service}/request"
    sts = f"HMAC-SHA256\n{xdate}\n{cs}\n{hashlib.sha256(cr.encode()).hexdigest()}"
    k_date = hmac_sha256(SK.encode(), datestamp)
    k_region = hmac_sha256(k_date, region)
    k_service = hmac_sha256(k_region, service)
    k_signing = hmac_sha256(k_service, "request")
    sig = hmac.new(k_signing, sts.encode(), hashlib.sha256).hexdigest()
    auth = f"HMAC-SHA256 Credential={AK}/{cs}, SignedHeaders={sh_headers}, Signature={sig}"

    url = f"https://{DOMAIN}/?{query}"
    headers = {"Authorization": auth, "X-Date": xdate, "Host": DOMAIN, "Content-Type": "application/json"}
    try:
        req = urllib.request.Request(url, data=body.encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            err = data.get("ResponseMetadata", {}).get("Error", {})
            if err:
                return err.get("Code", ""), err.get("Message", "")
            return None, data
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        try:
            err_data = json.loads(err_body)
            err = err_data.get("ResponseMetadata", {}).get("Error", {})
            if err:
                return err.get("Code", ""), err.get("Message", "")
        except:
            pass
        return f"HTTP{e.code}", err_body[:100]
    except Exception as e:
        return type(e).__name__, str(e)[:100]


print(f"Memory ID: {MEMORY_ID}")
print(f"AK: {AK[:8]}...")
print("=" * 60)

# Phase 1: 找到正确的 Service 名
# 记忆库可能属于这些产品
SERVICES = [
    "ark",       # ARK (AI 应用平台, 最可能)
    "ai",        # AI 平台
    "bot",       # Bot 平台
    "agent",     # Agent 平台
    "air",       # ML 平台
    "memory",    # 直接叫 memory
    "ml",        # ML
    "aim",       # AI Memory?
    "iam",       # 不可能, 但测试
]

# Phase 2: 搜索正确的 Action 名
ACTIONS = [
    "SearchMemory",
    "SearchAgentMemory",
    "RecallMemory",
    "RecallAgentMemory",
    "QueryMemory",
    "ListMemories",
    "GetMemory",
    "DescribeMemory",
    "DescribeMemories",
    "SearchRecords",
    "SearchEvents",
    "SearchPersonae",
]

VERSIONS = ["2024-01-01", "2025-01-01", "2023-12-01", "2024-06-01"]

found = []
for action in ACTIONS:
    for version in VERSIONS:
        for service in SERVICES:
            code, msg = try_action(action, version, service,
                                   {"MemoryId": MEMORY_ID, "Query": "test", "Limit": 3})
            key = (service, code)
            if key not in found:
                found.append(key)
                # 只打印有趣的 (不是 MissingAction/InvalidAction)
                if "Invalid" not in code and "Missing" not in code:
                    print(f"Action={action} v={version} s={service}")
                    print(f"  → {code}: {msg[:120]}")
                    if code == "ServiceNotExist" and service == "ark":
                        # ARK 可能是对的, 只是版本不对
                        pass

# 第二轮: 如果是 ARK 服务, 试不同 Version
print("\n--- ARK service, all versions ---")
for action in ["SearchMemory", "RecallMemory", "ListMemories", "GetMemory"]:
    for version in ["2022-01-01", "2023-01-01", "2023-06-01", "2024-01-01",
                    "2024-06-01", "2024-10-01", "2025-01-01", "2025-04-01"]:
        code, msg = try_action(action, version, "ark",
                               {"MemoryId": MEMORY_ID, "Query": "test", "Limit": 3})
        if "Invalid" not in code and "Missing" not in code:
            print(f"  {action} v={version} → {code}: {msg[:120]}")

print("\nDone.")
