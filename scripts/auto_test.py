"""全自动HIAGENT测试 — 一键运行"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# 从项目根 .env 加载所有密钥 (不再硬编码)
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# ○ HIAGENT 平台 URL (可 .env 覆盖)
os.environ.setdefault('HIAGENT_URL', 'https://aiagent.xjtlu.edu.cn/product/llm/chat/d916d3t4shh21hkk0v6g')
os.environ.setdefault('HIAGENT_APP_ID', 'd90b0fd4shh7q1vt7r4g')
os.environ.setdefault('HIAGENT_API_KEY', 'your-hiagent-api-key-here')

from src.test_runner import TestRunner

r = TestRunner(config_path='config/test_config.yaml')
results = r.run_all()

print(f'\n{"="*50}')
print(f'DONE: {len(results)} scenarios')
for i, res in enumerate(results):
    s = res.get('score') or {}
    b = res.get('boundary') or {}
    print(f'  [{i+1}] overall={s.get("overall","N/A")} boundary={b.get("status","N/A")} flags={s.get("flags",[])}')
    if res.get('error'):
        print(f'       error={res["error"][:120]}')
