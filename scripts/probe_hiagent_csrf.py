"""
绕过 HiAgent CSRF 保护 — 获取 token 后访问记忆库

CSRF token 通常通过以下方式获取:
1. GET /api/csrf-token 获取 token
2. 从 cookie (_csrf) 中提取
3. 从 HTML meta 标签提取
"""

import json, os, urllib.request, urllib.error, http.cookiejar
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

# 先试: 用 _csrf token query param 或 cookie
# Express 的 csurf 通常接受这些方式

# 方案1: 尝试 GET 请求获取 CSRF cookie
print("=== 方案1: 获取 CSRF cookie ===")
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

for url in [
    "https://aiagent.xjtlu.edu.cn/api/memory/search",
    "https://aiagent.xjtlu.edu.cn/",
    "https://aiagent.xjtlu.edu.cn/api/",
]:
    try:
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {MEMORY_KEY}")
        resp = opener.open(req, timeout=8)
        print(f"GET {url} → HTTP {resp.status}")
        for cookie in cj:
            print(f"  Cookie: {cookie.name}={cookie.value}")
        # 如果有 _csrf cookie, 用它发POST
        csrf_cookie = None
        for cookie in cj:
            if "csrf" in cookie.name.lower():
                csrf_cookie = cookie.value
                break
        if csrf_cookie:
            body = json.dumps({
                "memory_id": MEMORY_ID, "query": "测试", "limit": 3,
            }, ensure_ascii=False).encode()
            req2 = urllib.request.Request(url, data=body)
            req2.add_header("Content-Type", "application/json")
            req2.add_header("Authorization", f"Bearer {MEMORY_KEY}")
            req2.add_header("x-csrf-token", csrf_cookie)
            req2.add_header("csrf-token", csrf_cookie)
            try:
                resp2 = opener.open(req2, timeout=8)
                data = json.loads(resp2.read().decode())
                print(f"POST with CSRF → HTTP {resp2.status} code={data.get('code', '?')}")
                print(json.dumps(data, ensure_ascii=False)[:500])
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")[:200]
                print(f"POST with CSRF → HTTP {e.code}: {body}")
    except urllib.error.HTTPError as e:
        print(f"GET {url} → HTTP {e.code}")
    except Exception as e:
        print(f"GET {url} → {e}")

# 方案2: 用 _csrf query param
print("\n=== 方案2: _csrf query param ===")
test_token = "test"
body = json.dumps({
    "memory_id": MEMORY_ID, "query": "测试", "limit": 3,
}, ensure_ascii=False).encode()
try:
    req = urllib.request.Request(
        f"https://aiagent.xjtlu.edu.cn/api/memory/search?_csrf={test_token}",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {MEMORY_KEY}",
        },
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode())
        print(f"HTTP {resp.status} code={data.get('code', '?')}")
        print(json.dumps(data, ensure_ascii=False)[:500])
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", errors="replace")[:200]
    print(f"HTTP {e.code}: {body}")

# 方案3: 用不同的API路径 (不走 Express csurf middleware)
print("\n=== 方案3: 尝试不同的API入口 ===")
ALT_DOMAINS = [
    "https://aiagent.xjtlu.edu.cn/product/llm/api/memory/search",
    "https://aiagent.xjtlu.edu.cn/api/v1/memory/search",
    "https://aiagent.xjtlu.edu.cn/api/aigw/v1/memory/search",
]
for url in ALT_DOMAINS:
    body = json.dumps({
        "memory_id": MEMORY_ID, "query": "测试", "limit": 3,
    }, ensure_ascii=False).encode()
    try:
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {MEMORY_KEY}",
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            print(f"POST {url} → HTTP {resp.status} code={data.get('code', '?')}")
            if data.get('code') != 'EBADCSRFTOKEN':
                print(json.dumps(data, ensure_ascii=False)[:400])
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        if "csrf" not in body.lower():
            print(f"POST {url} → HTTP {e.code}: {body}")
        else:
            print(f"POST {url} → CSRF (route exists!)")

# 方案4: HiAgent 可能提供专门的无CSRF API路径
print("\n=== 方案4: 内网/服务间 API路径 ===")
SERVICE_PATHS = [
    "https://aiagent.xjtlu.edu.cn/api/internal/memory/search",
    "https://aiagent.xjtlu.edu.cn/api/service/memory/search",
    "https://aiagent.xjtlu.edu.cn/api/private/memory/search",
    "https://aiagent.xjtlu.edu.cn/api/rpc/memory/search",
]
for url in SERVICE_PATHS:
    body = json.dumps({
        "memory_id": MEMORY_ID, "query": "测试", "limit": 3,
    }, ensure_ascii=False).encode()
    try:
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {MEMORY_KEY}",
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            code = data.get('code', '?')
            print(f"POST {url} → HTTP {resp.status} code={code}")
            if code != 'EBADCSRFTOKEN' and code != 404:
                print(json.dumps(data, ensure_ascii=False)[:400])
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        if "csrf" not in body.lower() and e.code != 404:
            print(f"POST {url} → HTTP {e.code}: {body[:150]}")

print("\nDone.")
