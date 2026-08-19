"""Local test: LLM step extraction from mock course page DOM"""
import sys, os, io, json, re
sys.path.insert(0, 'src')
from dotenv import load_dotenv
load_dotenv()
from platform_probe.api_keys import get_api_keys
import requests as req

keys = get_api_keys()
text_llm = keys.get_text_llm()
vlm = keys.get_vision_llm()
print("Text:", text_llm.name, "| VLM:", vlm.name if vlm else "NONE")

# Simulate a course page after clicking career card
mock_title = "AI+X Personalized Learning - Blender AI Automation 3D"
mock_body = """
AI+X Personalized Learning
Blender AI 自动化 3D 工作流

学习进度 Step 1 of 5 completed

课程内容
Step 1: Introduction to Blender AI
Step 2: 3D Modeling Basics
Step 3: AI-Assisted Automation
Step 4: Advanced Rendering Techniques
Step 5: Final Project Submission

侧边栏
1. 什么是Blender AI
2. 基础建模工具
3. 自动化脚本编写
4. 高级渲染
5. 项目提交与评估
"""

prompt = (
    "Extract the TEACHING STEP structure from this page.\n\n"
    "Page title: " + mock_title + "\n\n"
    "Page text content:\n" + mock_body[:2500] + "\n\n"
    "TASK: Find the list of teaching STEPS on this page.\n"
    "A step is a numbered learning unit.\n"
    "Return ONLY a JSON array like:\n"
    '[{"title": "Step 1: Intro", "type_guess": "video", "order_index": 1}]\n'
    "If no steps are visible, return empty array []."
)

resp = req.post(
    text_llm.base_url.rstrip("/") + "/chat/completions",
    headers={"Authorization": "Bearer " + text_llm.api_key, "Content-Type": "application/json"},
    json={
        "model": text_llm.model_id or text_llm.models[0],
        "messages": [
            {"role": "system", "content": "You extract teaching step structures. Return ONLY valid JSON array. No markdown."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 1500,
    },
    timeout=20,
)

print("Status:", resp.status_code)
content = resp.json()["choices"][0]["message"]["content"]
print("LLM response:")
print(content[:300])

# Parse JSON
steps = []
try:
    steps = json.loads(content)
    if not isinstance(steps, list):
        steps = []
except json.JSONDecodeError:
    m = re.search(r"\[[\s\S]*\]", content)
    if m:
        try:
            steps = json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

if steps:
    print("\nExtracted {} steps:".format(len(steps)))
    for s in steps:
        print("  {}. {} [{}]".format(s.get("order_index", "?"), s.get("title", "")[:60], s.get("type_guess", "?")))
    print("\nSUCCESS: LLM can extract steps from course page DOM!")
else:
    print("\nFAILED: LLM could not extract steps")
    # Try with different prompt
    prompt2 = (
        "List all numbered learning steps from this teaching platform page.\n"
        "Title: " + mock_title + "\n"
        "Content: " + mock_body[:2000] + "\n"
        "Return ONLY a JSON array of step objects with title and type_guess fields."
    )
    print("Retrying with simpler prompt...")
    resp2 = req.post(
        text_llm.base_url.rstrip("/") + "/chat/completions",
        headers={"Authorization": "Bearer " + text_llm.api_key, "Content-Type": "application/json"},
        json={
            "model": text_llm.model_id or text_llm.models[0],
            "messages": [
                {"role": "system", "content": "Return ONLY a JSON array. No markdown, no explanation."},
                {"role": "user", "content": prompt2},
            ],
            "temperature": 0.1,
            "max_tokens": 1500,
        },
        timeout=20,
    )
    content2 = resp2.json()["choices"][0]["message"]["content"]
    print("Retry:", content2[:300])
