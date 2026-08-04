"""Cloud platform API test via PlatformClient"""
import sys
sys.path.insert(0, '.')
from src.platform_client import PlatformClient
import requests

c = PlatformClient(verbose=True, min_interval=1)
print("Login:", c.login())
print()

# Agent Chat
print("Agent Chat:")
chat = c.chat("你好")
print(f"  ok={chat.ok}, usable={chat.is_usable}")
print(f"  answer={chat.answer[:100] if chat.answer else '(empty)'}")
print(f"  error={chat.error[:100] if chat.error else 'none'}")
print()

# Quiz Start
print("Quiz Start:")
try:
    q = c.quiz_start(26)
    print(f"  ok={q.get('ok')}, status={q.get('status_code')}")
    if not q.get("ok"):
        print(f"  error={q.get('error','')[:200]}")
except Exception as e:
    print(f"  Error: {e}")
print()

# Profile
print("Profile:")
h = {"Authorization": f"Bearer {c._token}"}
r = requests.get(f"{c.base_url}/phase3-api/profile/me", headers=h, timeout=10)
print(f"  status={r.status_code}")
print(f"  body={r.text[:200]}")
