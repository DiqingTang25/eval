"""用 CSRF token 访问记忆库"""
import json, urllib.request, urllib.error, http.cookiejar

MEMORY_ID = "mem-d5a321d1"
MEMORY_KEY = "H9THBK9FTPD726PF6GTNQ43W3ANCSNAJTA4R308FJDJWFM90N1N060R30D9R74V38"
CSRF = "e0lpIva-mzAI1SZrWvy2HQTx"

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# Step 1: 获取 session cookie
try:
    resp = opener.open(urllib.request.Request("https://aiagent.xjtlu.edu.cn/"), timeout=8)
    print(f"GET / → HTTP {resp.status}")
    for c in cj:
        print(f"  Cookie: {c.name}={c.value[:30]}...")
except Exception as e:
    print(f"GET / → {e}")

# Step 2: 试不同的 HTTP method / 路径
tests = [
    # GET 方式搜记忆
    ("GET", "https://aiagent.xjtlu.edu.cn/api/memory/search?memory_id=" + MEMORY_ID + "&query=test&limit=3", None),
    # POST body 搜记忆 + CSRF
    ("POST", "https://aiagent.xjtlu.edu.cn/api/memory/search",
     {"memory_id": MEMORY_ID, "query": "test", "limit": 3}),
    # 也许端点不需要 memory_id 而是用 auth 推导
    ("POST", "https://aiagent.xjtlu.edu.cn/api/memory/search",
     {"query": "test", "limit": 3}),
    # recall 端点
    ("POST", "https://aiagent.xjtlu.edu.cn/api/memory/recall",
     {"memory_id": MEMORY_ID, "query": "test", "limit": 3}),
    # v1 端点
    ("POST", "https://aiagent.xjtlu.edu.cn/api/v1/memory/search",
     {"memory_id": MEMORY_ID, "query": "test", "limit": 3}),
    # GraphQL
    ("POST", "https://aiagent.xjtlu.edu.cn/api/graphql",
     {"query": "query { memoryInfo(id: \"" + MEMORY_ID + "\") { id name } }"}),
]

for method, url, body in tests:
    body_bytes = json.dumps(body).encode() if body else None
    if method == "GET":
        req = urllib.request.Request(url)
    else:
        req = urllib.request.Request(url, data=body_bytes)
        req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {MEMORY_KEY}")
    req.add_header("x-csrf-token", CSRF)
    req.add_header("csrf-token", CSRF)

    try:
        resp = opener.open(req, timeout=8)
        data = json.loads(resp.read().decode())
        code = data.get("code", "?")
        print(f"\n{method} {url[:70]} → HTTP {resp.status} code={code}")
        if code and code != "EBADCSRFTOKEN":
            s = json.dumps(data, ensure_ascii=False, indent=2)
            print(s[:600])
            break  # 找到了!
    except urllib.error.HTTPError as e:
        b = e.read().decode("utf-8", errors="replace")
        if "csrf" not in b.lower() and e.code not in (404, 405):
            print(f"\n{method} {url[:70]} → HTTP {e.code}: {b[:250]}")
    except Exception as e:
        print(f"{method} {url[:50]} → {type(e).__name__}: {str(e)[:80]}")

print("\nDone.")
