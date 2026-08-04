"""
Test XJTLU AI Gateway GLM-5.2 vs DeepSeek speed comparison
凭据从环境变量读取: XJTLU_API_KEY / OPENAI_API_KEY
"""
import os
import sys
import time
import json
from pathlib import Path
from openai import OpenAI

sys.stdout.reconfigure(encoding='utf-8')

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

# ── XJTLU AI Gateway GLM-5.2 ──
XJTLU_API_KEY = os.getenv("XJTLU_API_KEY", "")
XJTLU_BASE_URL = os.getenv("XJTLU_BASE_URL", "https://aiagent.xjtlu.edu.cn/api/aigw/v1")
XJTLU_MODEL_ID = os.getenv("XJTLU_MODEL_ID", "d9699737u3anoctava6g")

# ── DeepSeek ──
DS_API_KEY = os.getenv("OPENAI_API_KEY", "")
DS_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")

if not XJTLU_API_KEY and not DS_API_KEY:
    print("[WARN] 未设置 XJTLU_API_KEY 或 OPENAI_API_KEY, 请在 .env 中配置")
    sys.exit(1)

TEST_PROMPT = """你是一个AI评分专家。对以下AI助手回答打分(1-5整数)。

【用户问题】
什么是机器学习中的过拟合？

【参考答案】
过拟合是指模型在训练数据上表现很好，但在测试数据上表现差的现象，通常因为模型过于复杂或训练数据太少。

【AI助手回答】
过拟合就是模型把训练数据学得太死板了，把噪声都记住了，导致在没见过的新数据上表现不好。就好比你死记硬背了10道题的答案，但考试换了个问法就不会了。

只输出JSON，不要其他内容：
{"correctness": int, "relevancy": int, "completeness": int, "guidance": int, "overall": float, "one_line_reason": "string"}"""


def test(name, api_key, base_url, model, use_json_format=True):
    client = OpenAI(api_key=api_key, base_url=base_url)
    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": TEST_PROMPT}],
        "temperature": 0.1,
        "timeout": 60,
    }
    if use_json_format:
        kwargs["response_format"] = {"type": "json_object"}

    start = time.time()
    try:
        response = client.chat.completions.create(**kwargs)
        elapsed = time.time() - start
        content = response.choices[0].message.content.strip()
        usage = response.usage

        # Try to parse JSON
        try:
            parsed = json.loads(content)
            return {
                "success": True,
                "elapsed": round(elapsed, 2),
                "content": content,
                "parsed": parsed,
                "tokens": {
                    "prompt": usage.prompt_tokens,
                    "completion": usage.completion_tokens,
                    "total": usage.total_tokens,
                } if usage else {},
                "tps": round(usage.completion_tokens / elapsed, 1) if usage and elapsed > 0 else None,
            }
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                    return {
                        "success": True,
                        "elapsed": round(elapsed, 2),
                        "content": content,
                        "parsed": parsed,
                        "tokens": {
                            "prompt": usage.prompt_tokens,
                            "completion": usage.completion_tokens,
                            "total": usage.total_tokens,
                        } if usage else {},
                        "tps": round(usage.completion_tokens / elapsed, 1) if usage and elapsed > 0 else None,
                    }
                except:
                    pass
            return {
                "success": True,
                "elapsed": round(elapsed, 2),
                "content": content,
                "parsed": None,
                "json_error": "Could not parse JSON from response",
                "tokens": {
                    "prompt": usage.prompt_tokens,
                    "completion": usage.completion_tokens,
                    "total": usage.total_tokens,
                } if usage else {},
                "tps": round(usage.completion_tokens / elapsed, 1) if usage and elapsed > 0 else None,
            }
    except Exception as e:
        elapsed = time.time() - start
        return {"success": False, "elapsed": round(elapsed, 2), "error": str(e)}


def main():
    print("=" * 60)
    print("XJTLU GLM-5.2 vs DeepSeek Speed Test")
    print("=" * 60)

    # ── 1. GLM-5.2 (no json_object format) ──
    print("\n>>> [1/2] Testing XJTLU GLM-5.2...")
    r_glm = test("GLM-5.2", XJTLU_API_KEY, XJTLU_BASE_URL, XJTLU_MODEL_ID, use_json_format=False)

    # ── 2. DeepSeek ──
    print("\n>>> [2/2] Testing DeepSeek-chat...")
    r_ds = test("DeepSeek", DS_API_KEY, DS_BASE_URL, "deepseek-chat", use_json_format=True)

    # ── Report ──
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    print(f"\n[GLM-5.2 via XJTLU Gateway]")
    if r_glm["success"]:
        t = r_glm.get('tokens', {})
        print(f"  Latency: {r_glm['elapsed']}s | Speed: {r_glm.get('tps')} tok/s")
        print(f"  Tokens: prompt={t.get('prompt')}, completion={t.get('completion')}, total={t.get('total')}")
        if r_glm.get('parsed'):
            print(f"  JSON OK: {json.dumps(r_glm['parsed'], ensure_ascii=False)}")
        else:
            print(f"  Raw Output: {r_glm['content'][:400]}")
            if r_glm.get('json_error'):
                print(f"  JSON: {r_glm['json_error']}")
    else:
        print(f"  FAILED: {r_glm['error'][:250]}")

    print(f"\n[DeepSeek-chat]")
    if r_ds["success"]:
        t = r_ds.get('tokens', {})
        print(f"  Latency: {r_ds['elapsed']}s | Speed: {r_ds.get('tps')} tok/s")
        print(f"  Tokens: prompt={t.get('prompt')}, completion={t.get('completion')}, total={t.get('total')}")
        if r_ds.get('parsed'):
            print(f"  JSON OK: {json.dumps(r_ds['parsed'], ensure_ascii=False)}")
    else:
        print(f"  FAILED: {r_ds.get('error', '')}")

    # ── Compare ──
    if r_glm["success"] and r_ds["success"]:
        ratio = r_glm['elapsed'] / r_ds['elapsed']
        print(f"\n=== Speed Ratio: GLM-5.2 / DeepSeek = {ratio:.1f}x ===")
        if ratio < 1:
            print(f"    GLM-5.2 is {1/ratio:.1f}x FASTER")
        else:
            print(f"    GLM-5.2 is {ratio:.1f}x SLOWER")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
