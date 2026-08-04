"""生成 HMAC 签名并输出 curl 命令 (凭据从 .env 读取)"""
import hashlib, hmac, json, os, sys
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

# P1-11: 从环境变量读取, 移除硬编码凭据
ak = os.getenv("VOLC_ACCESS_KEY")
sk = os.getenv("VOLC_SECRET_KEY")
host = os.getenv("VOLC_KB_HOST", "api-knowledgebase.mlp.cn-beijing.volces.com")
service_id = os.getenv("VOLC_KB_SERVICE_ID", "kb-service-c5872d5b6644c426")
service = "air"
region = "cn-north-1"

if not ak or not sk:
    print("❌ 错误: 请在 .env 中设置 VOLC_ACCESS_KEY 和 VOLC_SECRET_KEY")
    sys.exit(1)
path = "/api/knowledge/v1/search"
body_dict = {"service_id": service_id, "query": "hello", "top_k": 3}
body = json.dumps(body_dict, ensure_ascii=False)

now = datetime.now(timezone.utc)
xdate = now.strftime("%Y%m%dT%H%M%SZ")
datestamp = now.strftime("%Y%m%d")

canonical_headers = f"content-type:application/json\nhost:{host}\nx-date:{xdate}\n"
signed_headers = "content-type;host;x-date"
payload_hash = hashlib.sha256(body.encode()).hexdigest()
canonical_request = f"POST\n{path}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

credential_scope = f"{datestamp}/{region}/{service}/request"
cr_hash = hashlib.sha256(canonical_request.encode()).hexdigest()
string_to_sign = f"HMAC-SHA256\n{xdate}\n{credential_scope}\n{cr_hash}"

def hmac_sha256(key, msg):
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()

k_date = hmac_sha256(sk.encode(), datestamp)
k_region = hmac_sha256(k_date, region)
k_service = hmac_sha256(k_region, service)
k_signing = hmac_sha256(k_service, "request")
signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

auth = f"HMAC-SHA256 Credential={ak}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"

# Output curl command (JSON body on one line)
body_oneline = json.dumps(body_dict, ensure_ascii=False)
print(f'curl -v -X POST "http://{host}{path}" -H "Content-Type: application/json" -H "X-Date: {xdate}" -H "Authorization: {auth}" -H "Host: {host}" -d \'{body_oneline}\'')
