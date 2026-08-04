"""
测试火山引擎知识库 HMAC-SHA256 签名
用法: python scripts/test_volc_sign.py
凭据从 .env 文件读取: VOLC_ACCESS_KEY / VOLC_SECRET_KEY
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

# 加载 .env（项目根目录）
env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                if key.strip() not in os.environ:
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")

# 从环境变量读取凭据 (P1-11: 移除硬编码)
ak = os.getenv("VOLC_ACCESS_KEY", "")
sk = os.getenv("VOLC_SECRET_KEY", "")
host = os.getenv("VOLC_KB_HOST", "api-knowledgebase.mlp.cn-beijing.volces.com")
service_id = os.getenv("VOLC_KB_SERVICE_ID", "kb-service-c5872d5b6644c426")
service = "air"
region = "cn-north-1"

if not ak or not sk:
    print("❌ 错误: 请在 .env 中设置 VOLC_ACCESS_KEY 和 VOLC_SECRET_KEY")
    print("   示例: VOLC_ACCESS_KEY=AKLTxxx...  VOLC_SECRET_KEY=xxx...")
    sys.exit(1)

path = "/api/knowledge/v1/search"
body_dict = {
    "service_id": service_id,
    "query": "hello",
    "top_k": 3,
}
body = json.dumps(body_dict, ensure_ascii=False)

print("=" * 60)
print("火山引擎知识库 HMAC-SHA256 签名测试")
print("=" * 60)

# ── Signature V4 ──
now = datetime.now(timezone.utc)
xdate = now.strftime("%Y%m%dT%H%M%SZ")
datestamp = now.strftime("%Y%m%d")

# Canonical Request
canonical_headers = f"content-type:application/json\nhost:{host}\nx-date:{xdate}\n"
signed_headers = "content-type;host;x-date"
payload_hash = hashlib.sha256(body.encode()).hexdigest()
canonical_request = (
    f"POST\n{path}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
)

# String to Sign
credential_scope = f"{datestamp}/{region}/{service}/request"
cr_hash = hashlib.sha256(canonical_request.encode()).hexdigest()
string_to_sign = (
    f"HMAC-SHA256\n{xdate}\n{credential_scope}\n{cr_hash}"
)

# Signing Key
def hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()

k_date = hmac_sha256(sk.encode(), datestamp)
k_region = hmac_sha256(k_date, region)
k_service = hmac_sha256(k_region, service)
k_signing = hmac_sha256(k_service, "request")

# Signature
signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

auth = (
    f"HMAC-SHA256 "
    f"Credential={ak}/{credential_scope}, "
    f"SignedHeaders={signed_headers}, "
    f"Signature={signature}"
)

print(f"\n[请求信息]:")
print(f"   Host: {host}")
print(f"   Path: {path}")
print(f"   X-Date: {xdate}")
print(f"   Credential Scope: {credential_scope}")
print(f"   Body: {body}")

print(f"\n[签名信息]")
print(f"   CanonicalRequest Hash: {cr_hash}")
print(f"   StringToSign Hash: {hashlib.sha256(canonical_request.encode()).hexdigest()}")
print(f"   Signature: {signature[:40]}...")

# ── 发送请求 ──
print(f"\n[发送请求]...")
req = urllib.request.Request(
    f"http://{host}{path}",
    data=body.encode(),
    headers={
        "Authorization": auth,
        "X-Date": xdate,
        "Host": host,
        "Content-Type": "application/json",
    },
)

try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
        print(f"\n[OK] HTTP {resp.status}")
        print(json.dumps(data, ensure_ascii=False, indent=2))
except urllib.error.HTTPError as e:
    body_resp = e.read().decode()[:500]
    print(f"\n[ERROR] HTTP {e.code}")
    print(body_resp)
except Exception as e:
    print(f"\n[ERROR] 异常: {e}")
