#!/usr/bin/env python3
"""
Full platform exploration script — login, traverse all phases/lessons/steps,
identify all interactive elements, and detect Quiz availability.
"""
import requests
import json
import sys
import os

BASE = "http://124.174.108.70"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

session = requests.Session()
session.trust_env = False
session.proxies = {"http": None, "https": None}

def api(method, path, **kwargs):
    """Wrapper with timeout and error handling."""
    url = f"{BASE}{path}"
    try:
        if method == "GET":
            resp = session.get(url, timeout=15, **kwargs)
        else:
            resp = session.post(url, timeout=15, **kwargs)
        return resp
    except Exception as e:
        print(f"  [ERROR] {method} {path}: {e}")
        return None

# ── Login ─────────────────────────────────────────────
print("=" * 60)
print("STEP 1: LOGIN")
resp = api("POST", "/api/auth/login", json={"username": "student001", "password": "123456"})
if not resp or resp.status_code != 200:
    print(f"Login failed: {resp.status_code if resp else 'no response'}")
    sys.exit(1)
data = resp.json()
token = data["token"]
user = data["user"]
print(f"  ✅ Logged in as {user['display_name']} ({user['role']}), class={user.get('class_name')}, group={user.get('group_name')}")
session.headers.update({"Authorization": f"Bearer {token}"})

# ── Fetch SPA frontend ────────────────────────────────
print("\n" + "=" * 60)
print("STEP 2: FRONTEND ANALYSIS")
resp = api("GET", "/")
if resp:
    html = resp.text
    print(f"  HTML size: {len(html)} chars")
    # Look for JS bundles
    import re
    scripts = re.findall(r'<script[^>]*src="([^"]*)"', html)
    styles = re.findall(r'<link[^>]*href="([^"]*)"', html)
    print(f"  Scripts: {scripts}")
    print(f"  Stylesheets: {styles}")
    # Look for key words
    for kw in ["quiz", "Quiz", "agent", "Agent", "chat", "Chat", "step", "Step"]:
        count = html.count(kw)
        if count > 0:
            print(f"  '{kw}' mentions: {count}")

# Try to fetch JS bundles
for js_file in ["/assets/index.js", "/assets/main.js", "/static/js/main.js", "/js/app.js"]:
    resp = api("GET", js_file)
    if resp and resp.status_code == 200:
        print(f"  ✅ JS: {js_file} ({len(resp.text)} chars)")
        # Search for quiz-related code
        text = resp.text
        for kw in ["quiz", "Quiz", "question", "answer", "choice", "submitQuiz"]:
            count = text.count(kw)
            if count > 0:
                print(f"    '{kw}' in JS: {count}")
    elif resp and resp.status_code != 404:
        print(f"  {js_file}: {resp.status_code}")

# ── All Phases ────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 3: ALL PHASES")
resp = api("GET", "/api/phases")
if not resp:
    sys.exit(1)
phases = resp.json()
main_phases = [p for p in phases if p.get("phase_code", "").startswith("phase")]
print(f"  Main phases: {len(main_phases)}")
for p in sorted(phases, key=lambda x: x.get("order_index", 99)):
    tag = "⭐" if p.get("phase_code", "").startswith("phase") else "  "
    print(f"  {tag} ID={p['id']} | {p.get('phase_code','?'):12s} | {p['title'][:50]}")

# ── All Lessons + Steps ───────────────────────────────
print("\n" + "=" * 60)
print("STEP 4: ALL LESSONS WITH STEPS & INTERACTIVE ELEMENTS")

total_steps = 0
total_resources = 0
total_videos = 0
lessons_with_quiz_hint = []
interactive_features = {
    "agent_chat": [],       # Lessons with agent chat capability
    "resources_download": [],  # Downloadable resources
    "video_content": [],    # Video content
    "checklist_steps": [],  # Steps with checklists
    "safety_checks": [],    # Steps with safety checks
    "quiz_related": [],     # Any quiz-related data
}

for p in sorted(phases, key=lambda x: x.get("order_index", 99)):
    phase_code = p.get("phase_code", "")
    is_main = phase_code.startswith("phase")
    if not is_main:
        continue

    resp = api("GET", f"/api/lessons?phase_id={p['id']}")
    if not resp:
        continue
    lessons = resp.json() if isinstance(resp.json(), list) else []

    for i, l_summary in enumerate(lessons):
        lid = l_summary["id"]
        resp = api("GET", f"/api/lessons/{lid}")
        if not resp:
            continue
        lesson = resp.json()

        steps = lesson.get("steps", [])
        resources = lesson.get("resources", [])
        videos = lesson.get("videos", [])

        total_steps += len(steps)
        total_resources += len(resources)
        total_videos += len(videos)

        # Analyze interactive elements in steps
        has_checklist = False
        has_safety = False
        has_agent_hint = False
        has_evidence = False

        for s in steps:
            rp = s.get("render_payload", {})
            guide = rp.get("guide", {})
            detailed = rp.get("detailed", {})

            if guide.get("checklist"):
                has_checklist = True
            if guide.get("safety_check"):
                has_safety = True
            if guide.get("agent_help_hint"):
                has_agent_hint = True
            if guide.get("evidence_requirement"):
                has_evidence = True

        if has_checklist:
            interactive_features["checklist_steps"].append(lid)
        if has_safety:
            interactive_features["safety_checks"].append(lid)

        # Check for quiz hints
        quiz_keys = [k for k in lesson.keys() if "quiz" in k.lower()]
        if quiz_keys:
            lessons_with_quiz_hint.append((lid, quiz_keys))

        # Check agent chat
        resp_agent = api("POST", "/api/agent/chat", json={
            "lesson_id": lid,
            "message": "test"
        })
        agent_status = resp_agent.status_code if resp_agent else "no_response"

        # Only print last lesson of each phase (most likely to have quiz)
        is_last = (i == len(lessons) - 1)
        marker = " ◀ LAST" if is_last else ""
        print(f"  P{p['id']} L{lid} Day{l_summary.get('day_index')}: {len(steps)} steps, {len(resources)} res, {len(videos)} vids{marker}")

        if is_last:
            # Detailed analysis of last lesson
            print(f"    Keys: {sorted(lesson.keys())}")
            print(f"    Quiz keys: {quiz_keys if quiz_keys else 'NONE'}")
            print(f"    Agent Chat: HTTP {agent_status}")

            # Print step details
            for s in steps:
                rp = s.get("render_payload", {})
                guide = rp.get("guide", {})
                kps = s.get("knowledge_points", [])
                print(f"    Step {s['order_index']}: {s['title'][:50]}")
                print(f"      knowledge_points: {len(kps)}")
                print(f"      guide keys: {list(guide.keys()) if guide else 'EMPTY'}")

print(f"\n  TOTALS: {total_steps} steps, {total_resources} resources, {total_videos} videos")
print(f"  Lessons with quiz fields: {len(lessons_with_quiz_hint)}")

# ── Check for hidden/alternative Quiz APIs ────────────
print("\n" + "=" * 60)
print("STEP 5: QUIZ API DISCOVERY")

quiz_endpoints = [
    ("GET", "/api/quiz"),
    ("GET", "/api/quizzes"),
    ("GET", "/api/quiz/list"),
    ("POST", "/api/quiz/generate"),
    ("POST", "/api/quiz/submit"),
    ("GET", "/api/quiz/session"),
    ("GET", "/api/quiz/session/1"),
    ("GET", "/api/lessons/20/quiz"),
    ("GET", "/api/quiz?lesson_id=20"),
    ("GET", "/api/exam"),
    ("GET", "/api/assessment"),
    ("GET", "/api/questions"),
    ("POST", "/api/agent/quiz"),
]

for method, path in quiz_endpoints:
    if method == "GET":
        resp = api("GET", path)
    else:
        resp = api("POST", path, json={"lesson_id": 20})

    status = resp.status_code if resp else "NO_RESP"
    if status != 404:
        tag = "✅" if status == 200 else "⚠️"
        print(f"  {tag} {method} {path}: {status}")
        if status == 200:
            try:
                print(f"    Response: {json.dumps(resp.json(), ensure_ascii=False)[:200]}")
            except:
                print(f"    Response: {resp.text[:200]}")

# ── Summary ───────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 6: SUMMARY")
print(f"""
Platform Interactive Features Found:
  - Steps with checklists: {len(interactive_features['checklist_steps'])} lessons
  - Steps with safety checks: {len(interactive_features['safety_checks'])} lessons
  - Total downloadable resources: {total_resources}
  - Total videos: {total_videos}
  - Agent Chat: Checked (results above)
  - Quiz: {len(lessons_with_quiz_hint)} lessons with quiz fields, {'SOME APIs found' if any(True for _ in []) else 'APIs explored above'}
""")

# Save full data
output = {
    "phases": phases,
    "interactive_features": interactive_features,
    "total_steps": total_steps,
    "total_resources": total_resources,
    "total_videos": total_videos,
    "lessons_with_quiz_hint": [(lid, keys) for lid, keys in lessons_with_quiz_hint],
}
with open(os.path.join(OUTPUT_DIR, "platform_exploration_full.json"), "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\nFull data saved to data/platform_exploration_full.json")
