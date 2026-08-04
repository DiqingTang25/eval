"""诊断当前评分系统Judge配置"""
import os
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY", "")
claude_key = os.getenv("CLAUDE_API_KEY", "")
gpt_key = os.getenv("GPT_API_KEY", "")
glm_key = os.getenv("XJTLU_JUDGE_GLM52_API_KEY", "")
glm_model = os.getenv("XJTLU_JUDGE_GLM52_MODEL_ID", "")
doubao_key = os.getenv("XJTLU_JUDGE_DOUBAO_API_KEY", "")
doubao_model = os.getenv("XJTLU_JUDGE_DOUBAO_MODEL_ID", "")
xjtl_base = os.getenv("XJTLU_BASE_URL", "")

print(f"DeepSeek: {'YES' if api_key else 'NO'}")
print(f"Claude: {'YES' if claude_key else 'NO (CLAUDE_API_KEY not set)'}")
print(f"GPT: {'YES' if gpt_key else 'NO (GPT_API_KEY not set)'}")
print(f"XJTLU GLM-5.2: {'YES' if glm_key else 'NO'}")
print(f"XJTLU Doubao: {'YES' if doubao_key else 'NO'}")
print(f"Total model families: {sum(1 for v in [api_key, claude_key, gpt_key, glm_key, doubao_key] if v)}")
print()

# Test XJTLU connectivity
if glm_key and glm_model:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=glm_key, base_url=xjtl_base, timeout=10)
        resp = client.chat.completions.create(
            model=glm_model,
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=5
        )
        print(f"GLM-5.2 test: {resp.choices[0].message.content}")
    except Exception as e:
        print(f"GLM-5.2 test FAILED: {e}")

if doubao_key and doubao_model:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=doubao_key, base_url=xjtl_base, timeout=10)
        resp = client.chat.completions.create(
            model=doubao_model,
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=5
        )
        print(f"Doubao test: {resp.choices[0].message.content}")
    except Exception as e:
        print(f"Doubao test FAILED: {e}")
