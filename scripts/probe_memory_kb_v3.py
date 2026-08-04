"""
火山引擎记忆库 API 探测 v3 — HMAC-SHA256 签名方式

关键发现: /api/memory/v1/search 端点存在, 需要 V4 签名认证
           (与 /api/knowledge/v1/search 相同的认证机制)
"""

import hashlib
import hmac
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# 加载 .env
env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                if key.strip() not in os.environ:
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")

# 从 .env 读取 HMAC 签名凭据 (与 boundary_detector.py 相同)
AK = os.getenv("VOLC_ACCESS_KEY", "")
SK = os.getenv("VOLC_SECRET_KEY", "")

MEMORY_ID = "mem-d5a321d1"
API_KEY = "H9THBK9FTPD726PF6GTNQ43W3ANCSNAJTA4R308FJDJWFM90N1N060R30D9R74V38"  # 备用
DOMAIN = "api-knowledgebase.mlp.cn-beijing.volces.com"
SERVICE = os.getenv("VOLC_SERVICE", "air")
REGION = os.getenv("VOLC_REGION", "cn-north-1")

print("=" * 70)
print("火山引擎记忆库 API 探测 v3 — HMAC-SHA256 签名")
print(f"  AK: {AK[:8]}...")
print(f"  Memory ID: {MEMORY_ID}")
print("=" * 70)


def hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def sign_request(method: str, host: str, path: str, body: str, query: str = "") -> dict:
    """HMAC-SHA256 V4 签名 (与 volcengine_auth.py 相同逻辑)"""
    now = datetime.now(timezone.utc)
    xdate = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")

    canonical_headers = f"content-type:application/json\nhost:{host}\nx-date:{xdate}\n"
    signed_headers = "content-type;host;x-date"
    payload_hash = hashlib.sha256(body.encode()).hexdigest()

    canonical_request = (
        f"{method.upper()}\n{path}\n{query}\n"
        f"{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )

    credential_scope = f"{datestamp}/{REGION}/{SERVICE}/request"
    cr_hash = hashlib.sha256(canonical_request.encode()).hexdigest()
    string_to_sign = f"HMAC-SHA256\n{xdate}\n{credential_scope}\n{cr_hash}"

    k_date = hmac_sha256(SK.encode(), datestamp)
    k_region = hmac_sha256(k_date, REGION)
    k_service = hmac_sha256(k_region, SERVICE)
    k_signing = hmac_sha256(k_service, "request")
    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

    authorization = (
        f"HMAC-SHA256 Credential={AK}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    return {
        "Authorization": authorization,
        "X-Date": xdate,
        "Host": host,
        "Content-Type": "application/json",
    }


def try_memory_endpoint(label: str, path: str, body: dict, extra_headers: dict = None):
    print(f"\n── [{label}] ──")
    url = f"https://{DOMAIN}{path}"
    body_str = json.dumps(body, ensure_ascii=False)
    headers = sign_request("POST", DOMAIN, path, body_str)
    if extra_headers:
        headers.update(extra_headers)
    print(f"   POST {path}")
    print(f"   Body: {body_str[:200]}")

    try:
        req = urllib.request.Request(url, data=body_str.encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            code = data.get("code", "N/A")
            msg = data.get("message", "")
            result_str = json.dumps(data, ensure_ascii=False, indent=2)
            if len(result_str) > 800:
                result_str = result_str[:800] + "\n... (truncated)"
            print(f"   ✅ HTTP {resp.status} | code={code} | {msg}")
            print(f"   {result_str}")
            return data
    except urllib.error.HTTPError as e:
        body_resp = e.read().decode("utf-8", errors="replace")[:400]
        print(f"   ❌ HTTP {e.code}: {body_resp}")
        return None
    except Exception as e:
        print(f"   ❌ {e}")
        return None


# ═══════════════════════════════════════════════════════════
# 测试 memory/v1/search (HMAC签名)
# ═══════════════════════════════════════════════════════════
try_memory_endpoint(
    "memory/v1/search (HMAC签名, memory_id)",
    "/api/memory/v1/search",
    body={
        "memory_id": MEMORY_ID,
        "query": "测试",
        "limit": 3,
    },
)

# memory_id 改成 resource_id?
try_memory_endpoint(
    "memory/v1/search (resource_id)",
    "/api/memory/v1/search",
    body={
        "resource_id": MEMORY_ID,
        "query": "测试",
        "limit": 3,
    },
)

# 用 service_id?
try_memory_endpoint(
    "memory/v1/search (service_id)",
    "/api/memory/v1/search",
    body={
        "service_id": MEMORY_ID,
        "query": "测试",
        "top_k": 3,
    },
)

# ═══════════════════════════════════════════════════════════
# 测试 memory/v1/list (获取已有数据, 只读验证)
# ═══════════════════════════════════════════════════════════
try_memory_endpoint(
    "memory/v1/list (HMAC签名)",
    "/api/memory/v1/list",
    body={"memory_id": MEMORY_ID},
)

# ═══════════════════════════════════════════════════════════
# 测试 v1/search 是否支持 mem- 格式 (知识库API)
# ═══════════════════════════════════════════════════════════
try_memory_endpoint(
    "knowledge/v1/search (HMAC, mem- ID)",
    "/api/knowledge/v1/search",
    body={
        "service_id": MEMORY_ID,  # 用 mem- ID 试知识库API
        "query": "测试",
        "top_k": 3,
    },
)

# ═══════════════════════════════════════════════════════════
# 测试 memory/v1/event/search
# ═══════════════════════════════════════════════════════════
try_memory_endpoint(
    "memory/v1/event/search",
    "/api/memory/v1/event/search",
    body={
        "memory_id": MEMORY_ID,
        "query": "测试",
        "limit": 3,
    },
)

# ═══════════════════════════════════════════════════════════
# 测试: 用 Bearer token 作为 api_key 参数 + HMAC签名
# ═══════════════════════════════════════════════════════════
try_memory_endpoint(
    "memory/v1/search (HMAC + api_key in body)",
    "/api/memory/v1/search",
    body={
        "memory_id": MEMORY_ID,
        "api_key": API_KEY,
        "query": "测试",
        "limit": 3,
    },
)

print("\n" + "=" * 70)
print("探测完成。记忆库产品名/API路径推测:")
print("  产品: 火山引擎「Agent记忆」或「Bot记忆」")
print("  API: 需要 HMAC-SHA256 签名 (和知识库v1 API相同)")
print("=" * 70)
