"""
火山引擎记忆库 API 探测脚本 (只读, 不修改任何数据)

测试目标: mem-d5a321d1
目的: 确定记忆库的正确API端点、认证方式、返回格式

安全: 所有请求都是 GET/POST search/query (只读), 不会修改现有数据
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
print("火山引擎记忆库 API 探测")
print(f"  Resource ID: {MEMORY_ID}")
print(f"  API Key:     {MEMORY_KEY[:20]}...")
print(f"  Domain:      {DOMAIN}")
print("=" * 70)


def try_endpoint(
    label: str,
    url: str,
    body: dict,
    headers: dict = None,
    method: str = "POST",
):
    """尝试一个API端点, 打印结果"""
    print(f"\n── [{label}] ──")
    print(f"   {method} {url}")

    _headers = {"Content-Type": "application/json"}
    if headers:
        _headers.update(headers)

    body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
    print(f"   Body: {json.dumps(body, ensure_ascii=False)[:200]}")

    try:
        req = urllib.request.Request(url, data=body_bytes, headers=_headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            code = data.get("code", "N/A")
            msg = data.get("message", "")
            print(f"   ✅ HTTP {resp.status} | code={code} | msg={msg}")

            # 截断打印返回数据
            result_str = json.dumps(data, ensure_ascii=False, indent=2)
            if len(result_str) > 800:
                result_str = result_str[:800] + "\n... (truncated)"
            print(f"   Response:\n{result_str}")
            return data
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        print(f"   ❌ HTTP {e.code}: {body}")
        return None
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None


# ═══════════════════════════════════════════════════════════
# 测试1: 知识库 collection/search_knowledge (Phase KB 模式)
# ═══════════════════════════════════════════════════════════
try_endpoint(
    "知识库API: collection/search_knowledge",
    f"https://{DOMAIN}/api/knowledge/collection/search_knowledge",
    body={
        "service_resource_id": MEMORY_ID,  # mem- 格式的ID
        "name": "",                         # 记忆库可能不需要 collection name
        "query": "测试",
        "limit": 3,
    },
    headers={"Authorization": f"Bearer {MEMORY_KEY}"},
)

# ═══════════════════════════════════════════════════════════
# 测试2: 知识库 v1/search (HMAC 模式, 但这里用 Bearer)
# ═══════════════════════════════════════════════════════════
try_endpoint(
    "知识库API: v1/search (Bearer认证)",
    f"https://{DOMAIN}/api/knowledge/v1/search",
    body={
        "service_id": MEMORY_ID,
        "query": "测试",
        "top_k": 3,
    },
    headers={"Authorization": f"Bearer {MEMORY_KEY}"},
)

# ═══════════════════════════════════════════════════════════
# 测试3: 记忆库专用API (mem- 产品推断端点)
# ═══════════════════════════════════════════════════════════
try_endpoint(
    "记忆库: /api/memory/v1/search",
    f"https://{DOMAIN}/api/memory/v1/search",
    body={
        "memory_id": MEMORY_ID,
        "query": "测试",
        "top_k": 3,
    },
    headers={"Authorization": f"Bearer {MEMORY_KEY}"},
)

# ═══════════════════════════════════════════════════════════
# 测试4: 记忆库 recall API
# ═══════════════════════════════════════════════════════════
try_endpoint(
    "记忆库: /api/memory/v1/recall",
    f"https://{DOMAIN}/api/memory/v1/recall",
    body={
        "memory_id": MEMORY_ID,
        "query": "测试",
        "limit": 3,
    },
    headers={"Authorization": f"Bearer {MEMORY_KEY}"},
)

# ═══════════════════════════════════════════════════════════
# 测试5: 记忆库 query API
# ═══════════════════════════════════════════════════════════
try_endpoint(
    "记忆库: /api/memory/v1/query",
    f"https://{DOMAIN}/api/memory/v1/query",
    body={
        "resource_id": MEMORY_ID,
        "query": "测试",
    },
    headers={"Authorization": f"Bearer {MEMORY_KEY}"},
)

# ═══════════════════════════════════════════════════════════
# 测试6: 通用Bot记忆 API (Agent Memory)
# ═══════════════════════════════════════════════════════════
try_endpoint(
    "Agent记忆: /api/bot/memory/search",
    f"https://{DOMAIN}/api/bot/memory/search",
    body={
        "resource_id": MEMORY_ID,
        "query": "测试",
        "limit": 3,
    },
    headers={"Authorization": f"Bearer {MEMORY_KEY}"},
)

# ═══════════════════════════════════════════════════════════
# 测试7: 不用 name 参数的 collection/search_knowledge
# ═══════════════════════════════════════════════════════════
try_endpoint(
    "知识库API: collection/search_knowledge (无name)",
    f"https://{DOMAIN}/api/knowledge/collection/search_knowledge",
    body={
        "service_resource_id": MEMORY_ID,
        "query": "测试",
        "limit": 3,
    },
    headers={"Authorization": f"Bearer {MEMORY_KEY}"},
)

# ═══════════════════════════════════════════════════════════
# 测试8: 记忆库 list personas (尝试读取已有数据验证连通性)
# ═══════════════════════════════════════════════════════════
try_endpoint(
    "记忆库: /api/memory/v1/list",
    f"https://{DOMAIN}/api/memory/v1/list",
    body={
        "memory_id": MEMORY_ID,
    },
    headers={"Authorization": f"Bearer {MEMORY_KEY}"},
)

print("\n" + "=" * 70)
print("探测完成。根据上面返回结果:")
print("  - code=0 / HTTP 200 → 端点可用")
print("  - HTTP 404 → 端点不存在, 产品不同")
print("  - HTTP 401/403 → 认证方式不对")
print("  - HTTP 400 + 'service_resource_id not found' → ID不对应此产品")
print("=" * 70)
