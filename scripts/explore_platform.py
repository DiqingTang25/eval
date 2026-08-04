"""
全面探索教学平台所有功能 — 像真实用户一样
登录 → 浏览每个页面 → 发现所有可交互功能
"""
import sys, os, json, time
sys.path.insert(0, '.')
from src.platform_client import PlatformClient

c = PlatformClient(verbose=False, min_interval=0.5)
c.login()

print("=" * 60)
print("🔍 教学平台全功能探索")
print(f"平台: {c.base_url}")
user = c.user if hasattr(c, 'user') and c.user else {}
print(f"用户: {user.get('display_name', '?')} ({user.get('role', '?')})")
print(f"班级: {user.get('class_name', '?')} | 组: {user.get('group_name', '?')}")
print("=" * 60)

# ── 1. PHASES ──
print("\n📚 1. 课程阶段 (Phases)")
import requests
h = {"Authorization": f"Bearer {c.token}"}
phases_r = requests.get(f"{c.base_url}{c.api_prefix}/phases", headers=h, timeout=15)
if phases_r.status_code == 200:
    phases = phases_r.json()
    if isinstance(phases, dict):
        phases = phases.get('phases', phases.get('data', []))
    if not isinstance(phases, list):
        phases = [phases] if phases else []
    for p in phases:
        pid = p.get('id', p.get('phase_id', '?'))
        pname = p.get('name', p.get('title', f'Phase {pid}'))
        lcount = p.get('lesson_count', p.get('lessons_count', '?'))
        print(f"  Phase {pid}: {pname} ({lcount} lessons)")
else:
    print(f"  ❌ HTTP {phases_r.status_code}: {phases_r.text[:100]}")

# ── Try /api/ prefix for phases ──
print("\n  Trying /api/ prefix...")
phases_r2 = requests.get(f"{c.base_url}/api/phases", headers={"Authorization": f"Bearer {c.content_token}"}, timeout=15)
if phases_r2.status_code == 200:
    data = phases_r2.json()
    if isinstance(data, dict):
        data = data.get('phases', data.get('data', []))
    if isinstance(data, list):
        for p in data:
            print(f"  Phase {p.get('id')}: {p.get('name', '?')} (lessons: {p.get('lesson_count', '?')})")
else:
    print(f"  ❌ HTTP {phases_r2.status_code}")

# ── 2. LESSONS ──
print("\n📖 2. 课时列表 (Lessons)")
lessons_r = requests.get(f"{c.base_url}{c.api_prefix}/lessons", headers=h, timeout=15)
if lessons_r.status_code == 200:
    lessons = lessons_r.json()
    if isinstance(lessons, dict):
        lessons = lessons.get('lessons', lessons.get('data', []))
    if isinstance(lessons, list):
        print(f"  共 {len(lessons)} 个课时:")
        for i, l in enumerate(lessons[:5]):
            print(f"  L{l.get('id')}: {l.get('title', l.get('name', '?'))} "
                  f"[Phase {l.get('phase_id', '?')}] "
                  f"steps={l.get('step_count', l.get('steps_count', '?'))} "
                  f"quiz={l.get('has_quiz', l.get('quiz_enabled', '?'))}")
        if len(lessons) > 5:
            print(f"  ... 还有 {len(lessons)-5} 个课时")
        # Find a lesson with steps
        first_lesson = lessons[0] if lessons else None
        if first_lesson:
            lid = first_lesson.get('id')
            print(f"\n  查看第一个课时详情 L{lid}:")
            lesson_r = requests.get(f"{c.base_url}{c.api_prefix}/lessons/{lid}", headers=h, timeout=15)
            if lesson_r.status_code == 200:
                ld = lesson_r.json()
                print(f"    title: {ld.get('title', ld.get('name', '?'))}")
                print(f"    phase_id: {ld.get('phase_id', '?')}")
                steps = ld.get('steps', ld.get('lesson_steps', []))
                print(f"    steps: {len(steps)}")
                for s in (steps or [])[:3]:
                    print(f"      Step#{s.get('step_number',s.get('id','?'))}: {s.get('title',s.get('name','?'))} type={s.get('type','?')}")
                # Check for quiz
                quiz = ld.get('quiz', ld.get('quiz_data', {}))
                if quiz:
                    print(f"    quiz: {len(quiz.get('questions',[])) if isinstance(quiz,dict) else '?'} questions")
                # Check resources
                resources = ld.get('resources', [])
                if resources:
                    print(f"    resources: {len(resources)} files")
            else:
                print(f"    ❌ HTTP {lesson_r.status_code}")
else:
    print(f"  ❌ HTTP {lessons_r.status_code}: {lessons_r.text[:100]}")

# ── Try content API prefix ──
print("\n  Trying /api/ prefix for lessons...")
lessons_r2 = requests.get(f"{c.base_url}/api/lessons", headers={"Authorization": f"Bearer {c.content_token}"}, timeout=15)
if lessons_r2.status_code == 200:
    data = lessons_r2.json()
    if isinstance(data, dict):
        data = data.get('lessons', data.get('data', []))
    if isinstance(data, list):
        print(f"  ✅ /api/lessons: {len(data)} lessons")
        for l in data[:3]:
            print(f"    L{l.get('id')}: {l.get('title','?')} phase={l.get('phase_id','?')}")
else:
    print(f"  ❌ HTTP {lessons_r2.status_code}")

# ── 3. STUDENT PROFILE ──
print("\n👤 3. 学生画像 (Profile)")
profile = c.get_profile()
if profile:
    print(f"  ✅ 画像数据:")
    if isinstance(profile, dict):
        for k, v in profile.items():
            if k in ('dimensions', 'scores', 'knowledge_points'):
                print(f"    {k}: {len(v) if isinstance(v,(list,dict)) else str(v)[:100]}")
            elif not k.startswith('_'):
                print(f"    {k}: {str(v)[:100]}")
else:
    print(f"  ❌ 无法获取画像")

# ── 4. KNOWLEDGE SEARCH ──
print("\n🔍 4. 知识库搜索 (Knowledge Search)")
ks_r = requests.get(f"{c.base_url}{c.api_prefix}/knowledge/search?q=AI", headers=h, timeout=15)
if ks_r.status_code == 200:
    kd = ks_r.json()
    chunks = kd.get('chunks', kd.get('results', []))
    print(f"  ✅ 搜索'AI': {len(chunks)} 条结果")
    for ch in chunks[:2]:
        print(f"    {str(ch)[:120]}")
else:
    print(f"  ❌ HTTP {ks_r.status_code}: {ks_r.text[:100]}")

# ── 5. EVENTS TRACKING ──
print("\n📊 5. 事件追踪 (Events)")
ev_r = requests.post(f"{c.base_url}{c.api_prefix}/events",
    headers={**h, "Content-Type": "application/json"},
    json={"event_type": "lesson_entered", "lesson_id": 1, "timestamp": int(time.time())},
    timeout=15)
print(f"  POST lesson_entered: HTTP {ev_r.status_code}")

# ── 6. STEP PROGRESS ──
print("\n📝 6. Step进度管理")
# Need a real lesson with steps - try lesson 20 (Phase 1 last lesson)
sp_r = requests.post(f"{c.base_url}{c.api_prefix}/steps/1/progress",
    headers={**h, "Content-Type": "application/json"},
    json={"completed": True},
    timeout=15)
print(f"  POST steps/1/progress: HTTP {sp_r.status_code}")
if sp_r.status_code != 200:
    print(f"    {sp_r.text[:150]}")

# ── 7. NEXT STEP ──
print("\n⏭️ 7. Next Step导航")
ns_r = requests.post(f"{c.base_url}{c.api_prefix}/lessons/1/next-step",
    headers={**h, "Content-Type": "application/json"},
    json={"current_step": 1},
    timeout=15)
print(f"  POST lessons/1/next-step: HTTP {ns_r.status_code}")
if ns_r.status_code == 200:
    nsd = ns_r.json()
    print(f"    next_step: {nsd.get('next_step')}, done: {nsd.get('done')}")
else:
    print(f"    {ns_r.text[:150]}")

# ── 8. AGENT CHAT ──
print("\n🤖 8. Agent对话 (不同Phase)")
for phase_label, lid in [("Phase1", 20), ("Phase3", 9), ("Phase5", 26)]:
    try:
        chat = c.chat(lid, "你好，介绍一下这个阶段的学习目标")
        print(f"  {phase_label} (L{lid}): {'✅' if chat.is_usable else '❌'} "
              f"{len(chat.answer)} chars, {chat.duration:.1f}s"
              f"{' [RATE_LIMITED]' if chat.rate_limited else ''}")
    except Exception as e:
        print(f"  {phase_label} (L{lid}): ❌ {str(e)[:80]}")
    time.sleep(2)  # Avoid QPS limit

# ── 9. QUIZ ──
print("\n📝 9. Quiz功能")
for phase_name, lid in [("Phase1", 20), ("Phase5", 26)]:
    quiz = c.quiz_start(lid)
    if quiz.get('ok'):
        qs = quiz.get('questions', [])
        print(f"  {phase_name} (L{lid}): ✅ {len(qs)} questions")
    else:
        print(f"  {phase_name} (L{lid}): ❌ {quiz.get('error', '?')[:100]}")
    time.sleep(0.5)

# ── 10. AGENT RESOLVE ──
print("\n✅ 10. Agent反馈标记 (Resolve)")
# Need a real message_id from a chat
try:
    chat = c.chat(20, "测试消息")
    if chat.ok and hasattr(c, 'agent_resolve'):
        import re
        # Try to find message_id from chat response
        resolve_r = c.agent_resolve(999, resolved=True)  # Will likely fail but tests endpoint
        print(f"  Endpoint test: done")
except Exception as e:
    print(f"  ⚠️ {str(e)[:80]}")

# ── 11. RESOURCES ──
print("\n📁 11. 资源下载 (Resources)")
res_r = requests.get(f"{c.base_url}/resources/", headers=h, timeout=10, allow_redirects=True)
print(f"  GET /resources/: HTTP {res_r.status_code}")

# ── 12. LEARNING MODES ──
print("\n🎓 12. 学习模式")
# Check lesson render_payload for guide/detailed/standard modes
try:
    detail_r = requests.get(f"{c.base_url}/api/lessons/20",
        headers={"Authorization": f"Bearer {c.content_token}"}, timeout=15)
    if detail_r.status_code == 200:
        ld = detail_r.json()
        rp = ld.get('render_payload', {})
        modes = {k: bool(v) for k, v in rp.items() if k in ('guide', 'detailed', 'standard')}
        print(f"  Lesson 20 render modes: {modes}")
except Exception as e:
    print(f"  ⚠️ {e}")

print(f"\n{'='*60}")
print("探索完成")
print(f"{'='*60}")
