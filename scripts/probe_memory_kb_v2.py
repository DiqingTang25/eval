"""
火山引擎记忆库 API 探测 v2 — 测试不同的认证方式

关键发现: /api/memory/v1/search 端点存在(HTTP 400, 不是404)
            错误 "api key miss parameter" → API Key传递方式需要调整
"""

import json
import os
import sys
import urllib.request
import urllib.error
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

MEMORY_ID = "mem-d5a321d1"
MEMORY_KEY = "H9THBK9FTPD726PF6GTNQ43W3ANCSNAJTA4R308FJDJWFM90N1N060R30D9R74V38"
DOMAIN = os.getenv("VOLC_KB_DOMAIN", "api-knowledgebase.mlp.cn-beijing.volces.com")

print("=" * 70)
print("火山引擎记忆库 API 探测 v2 — 认证方式测试")
print("=" * 70)


def try_request(label: str, url: str, body: dict, headers: dict):
    print(f"\n── [{label}] ──")
    print(f"   URL: {url}")
    body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=body_bytes, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            code = data.get("code", "N/A")
            msg = data.get("message", "")
            result_str = json.dumps(data, ensure_ascii=False, indent=2)
            if len(result_str) > 600:
                result_str = result_str[:600] + "\n... (truncated)"
            print(f"   ✅ HTTP {resp.status} code={code}")
            print(f"   {result_str}")
            return data
    except urllib.error.HTTPError as e:
        body_resp = e.read().decode("utf-8", errors="replace")[:300]
        print(f"   ❌ HTTP {e.code}: {body_resp}")
        return None
    except Exception as e:
        print(f"   ❌ {e}")
        return None


# ── 测试 memory/v1/search 的不同认证方式 ──

# 1. api_key 在 body 中
try_request(
    "Body中传 api_key",
    f"https://{DOMAIN}/api/memory/v1/search",
    body={"memory_id": MEMORY_ID, "api_key": MEMORY_KEY, "query": "测试", "limit": 3},
    headers={"Content-Type": "application/json"},
)

# 2. api_key 在 query string
try_request(
    "Query string 传 api_key",
    f"https://{DOMAIN}/api/memory/v1/search?api_key={MEMORY_KEY}",
    body={"memory_id": MEMORY_ID, "query": "测试", "limit": 3},
    headers={"Content-Type": "application/json"},
)

# 3. X-Api-Key header
try_request(
    "X-Api-Key header",
    f"https://{DOMAIN}/api/memory/v1/search",
    body={"memory_id": MEMORY_ID, "query": "测试", "limit": 3},
    headers={"Content-Type": "application/json", "X-Api-Key": MEMORY_KEY},
)

# 4. Authorization: HMAC-SHA256 格式但没有签名
try_request(
    "Authorization: HMAC-SHA256 (api key as credential)",
    f"https://{DOMAIN}/api/memory/v1/search",
    body={"memory_id": MEMORY_ID, "query": "测试", "limit": 3},
    headers={
        "Content-Type": "application/json",
        "Authorization": f"HMAC-SHA256 Credential={MEMORY_KEY}",
    },
)

# 5. 记忆库可能用不同的 Host
ALT_DOMAIN = "api-memory.mlp.cn-beijing.volces.com"
try_request(
    "备用域名: api-memory",
    f"https://{ALT_DOMAIN}/api/memory/v1/search",
    body={"memory_id": MEMORY_ID, "api_key": MEMORY_KEY, "query": "测试", "limit": 3},
    headers={"Content-Type": "application/json"},
)

# 6. Bearer 但 api_key 在 body
try_request(
    "Bearer + Body api_key",
    f"https://{DOMAIN}/api/memory/v1/search",
    body={"memory_id": MEMORY_ID, "api_key": MEMORY_KEY, "query": "测试", "limit": 3},
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MEMORY_KEY}",
    },
)

# ── recaill 端点的同样测试 ──

# 7. recall: Body传api_key
try_request(
    "Recall: Body api_key",
    f"https://{DOMAIN}/api/memory/v1/recall",
    body={"memory_id": MEMORY_ID, "api_key": MEMORY_KEY, "query": "测试", "limit": 3},
    headers={"Content-Type": "application/json"},
)

# 8. recall: X-Api-Key
try_request(
    "Recall: X-Api-Key",
    f"https://{DOMAIN}/api/memory/v1/recall",
    body={"memory_id": MEMORY_ID, "query": "测试", "limit": 3},
    headers={"Content-Type": "application/json", "X-Api-Key": MEMORY_KEY},
)

# ── 记忆库 list 端点 ──

# 9. list: 尝试获取已有的 personas (只读)
try_request(
    "List: Body api_key",
    f"https://{DOMAIN}/api/memory/v1/list",
    body={"memory_id": MEMORY_ID, "api_key": MEMORY_KEY},
    headers={"Content-Type": "application/json"},
)

# 10. personae 端点
try_request(
    "Personae list",
    f"https://{DOMAIN}/api/memory/v1/personae",
    body={"memory_id": MEMORY_ID, "api_key": MEMORY_KEY},
    headers={"Content-Type": "application/json"},
)

print("\n" + "=" * 70)
print("如果以上仍然全部失败, 说明记忆库API可能与知识库共用同一域名")
print("但端口/路径前缀可能不同。请检查火山引擎控制台中记忆库的API文档。")
print("=" * 70)
