"""Integration test: verify 3-judge diversity and scoring"""
import os
import sys
import json

# Load .env
env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(env_file):
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k = k.strip()
                if k not in os.environ and not k.startswith("#"):
                    os.environ[k] = v.strip().strip('"').strip("'")

from src.evaluator import Evaluator

# Test 1: Judge initialization
print("=" * 60)
print("Test 1: Judge Client Initialization")
print("=" * 60)

api_key = os.getenv("OPENAI_API_KEY", "")
base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")

ev = Evaluator(api_key=api_key, base_url=base_url, config={
    "use_embedding": True,
    "use_structure": True,
})

print(f"Total judges: {len(ev.judge_clients)}")
for jc in ev.judge_clients:
    print(f"  - {jc['name']:20s} | model={jc['model']:30s} | json_format={jc.get('supports_json_format', True)}")

models = set(jc["model"] for jc in ev.judge_clients)
print(f"\nUnique model families: {len(models)}")
if len(models) >= 3:
    print(">>> GENUINE multi-judge diversity!")
elif len(models) >= 2:
    print(">>> Partial diversity")
else:
    print(">>> WARNING: All judges same model family")

# Test 2: Quick evaluation
print()
print("=" * 60)
print("Test 2: Quick Evaluation")
print("=" * 60)

result = ev.evaluate(
    question="什么是机器学习中的过拟合？",
    agent_answer="过拟合就是模型把训练数据学得太死板了，把噪声都记住了，导致在没见过的新数据上表现不好。",
    golden_answer="过拟合是指模型在训练数据上表现很好，但在测试数据上表现差的现象，通常因为模型过于复杂或训练数据太少。",
    goal="帮助学生理解过拟合概念",
)

print(f"Overall score: {result.get('overall')}")
print(f"Legacy score:  {result.get('overall_legacy')}")
print(f"Judges:        {result.get('n_judges')}")
print(f"Judge variance: {result.get('judge_variance')}")
print(f"Flags:         {result.get('flags')}")
print()

for dim in ev.DIMENSION_NAMES:
    s = result.get(dim)
    c = result.get("confidences", {}).get(dim, "?")
    if s is not None:
        print(f"  {dim:25s}: {s:.1f}  (confidence={c})")
    else:
        print(f"  {dim:25s}: N/A")

print()
for jr in result.get("judge_reasons", []):
    print(f"  Judge: overall={jr.get('overall')}, reason={jr.get('reason', '')[:120]}")

print()
print("=" * 60)
if result.get("overall", 0) > 0:
    print("ALL TESTS PASSED")
else:
    print("SOME TESTS FAILED")
