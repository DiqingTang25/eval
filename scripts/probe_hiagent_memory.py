"""
探测 HiAgent 平台内部记忆库的代理 API

HiAgent Bot 内部调用记忆库，HiAgent平台可能有代理端点。
探测 aiagent.xjtlu.edu.cn 上所有可能的内存相关路径。
"""

import json, os, urllib.request, urllib.error
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

# HiAgent 平台的各种 Base URL
BASES = [
    ("HiAgent AI Gateway", "https://aiagent.xjtlu.edu.cn/api/aigw/v1"),
    ("HiAgent API", "https://aiagent.xjtlu.edu.cn/api"),
    ("HiAgent Root", "https://aiagent.xjtlu.edu.cn"),
]

# 可能的记忆路径
PATHS = [
    "/memory/search",
    "/memory/recall",
    "/memory/remember",
    "/memory/query",
    "/memory/list",
    "/agent/memory/search",
    "/agent/memory/recall",
    "/bot/memory/search",
    "/bot/memory/recall",
    "/aigw/memory/search",
    "/api/memory/search",
    "/hiagent/memory/search",
]

# API Key 传递方式
AUTH_MODES = [
    ("Bearer header", {"Authorization": f"Bearer {MEMORY_KEY}"}),
    ("X-Api-Key header", {"X-Api-Key": MEMORY_KEY}),
    ("api-key header", {"api-key": MEMORY_KEY}),
]

print(f"Memory ID: {MEMORY_ID}")
print("=" * 60)
hits = 0

for base_name, base_url in BASES:
    for path in PATHS:
        for auth_name, auth_headers in AUTH_MODES:
            url = f"{base_url}{path}"
            body = json.dumps({
                "memory_id": MEMORY_ID,
                "resource_id": MEMORY_ID,
                "query": "测试",
                "limit": 3,
            }, ensure_ascii=False).encode()

            headers = {"Content-Type": "application/json"}
            headers.update(auth_headers)

            try:
                req = urllib.request.Request(url, data=body, headers=headers)
                with urllib.request.urlopen(req, timeout=6) as resp:
                    data = json.loads(resp.read().decode())
                    code = data.get("code", "?")
                    # 只打印成功的或有趣的结果
                    if code == 0 or resp.status == 200:
                        hits += 1
                        print(f"\n✅ [{base_name}]{path} | {auth_name}")
                        print(f"   HTTP {resp.status} code={code}")
                        s = json.dumps(data, ensure_ascii=False, indent=2)
                        print(f"   {s[:400]}")
            except urllib.error.HTTPError as e:
                body_str = e.read().decode("utf-8", errors="replace")
                # 过滤掉明显的 HTML 404 页面
                if e.code not in (404, 405) or (
                    e.code == 404 and "Not Found" not in body_str[:50] and "<!DOCTYPE" not in body_str[:50]
                ):
                    # 有趣的错误
                    if any(kw in body_str.lower() for kw in [
                        "api key", "unauthorized", "forbidden", "memory",
                        "invalid", "missing", "parameter"
                    ]):
                        hits += 1
                        print(f"\n🔍 [{base_name}]{path} | {auth_name} → HTTP {e.code}")
                        print(f"   {body_str[:200]}")
            except Exception:
                pass

if hits == 0:
    print("\n所有端点返回 404/HTML — HiAgent 平台无外部记忆库代理API")

# 最后一招: HiAgent 的 Bot 配置API (可能暴露记忆库配置)
print("\n" + "=" * 60)
print("尝试: HiAgent Bot 配置/状态 API")
BOT_URLS = [
    "https://aiagent.xjtlu.edu.cn/api/bot/status",
    "https://aiagent.xjtlu.edu.cn/api/bot/config",
    "https://aiagent.xjtlu.edu.cn/api/agent/status",
    "https://aiagent.xjtlu.edu.cn/api/v1/agent/memory",
    "https://aiagent.xjtlu.edu.cn/api/v1/memory/config",
]
for url in BOT_URLS:
    try:
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {MEMORY_KEY}")
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
            print(f"✅ {url} → {json.dumps(data, ensure_ascii=False)[:300]}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:150]
        print(f"❌ {url} → HTTP {e.code}: {body}")
    except Exception as e:
        print(f"❌ {url} → {e}")

print("\nDone.")
