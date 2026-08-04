#!/usr/bin/env python3
"""
Quiz 完整流程测试 — 浏览器内 API 调用
启动 → 获取题目 → 自动答题 → 提交 → 验证评分
"""
import json, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "http://124.174.108.70"
USERNAME = "student001"
PASSWORD = "123456"
OUTPUT = Path(__file__).parent.parent / "explore_output" / "quiz_results.json"

def api(page, url, method="GET", body=None):
    body_j = json.dumps(body) if body else "null"
    code = f"""
        (async () => {{
            const t = localStorage.getItem('aix_token') || localStorage.getItem('token') || localStorage.getItem('auth_token') || '';
            const h = {{ 'Content-Type': 'application/json' }};
            if (t) h['Authorization'] = 'Bearer ' + t;
            const o = {{ method: '{method}', headers: h }};
            if ({body_j}) o.body = JSON.stringify({body_j});
            try {{
                const r = await fetch('{url}', o);
                const txt = await r.text();
                return {{ ok: r.ok, status: r.status, body: txt }};
            }} catch(e) {{ return {{ ok: false, error: e.message }}; }}
        }})()
    """
    try:
        r = page.evaluate(code)
        if r and r.get("body"):
            try: r["json"] = json.loads(r["body"])
            except: pass
        return r
    except Exception as e:
        return {"ok": False, "error": str(e)}

def login(page):
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    body = page.locator("body").first.text_content() or ""
    if "Phase" in body and "登录" not in body[:500]:
        return True

    for inp in page.locator("input:not([type='hidden'])").all():
        if not inp.is_visible(): continue
        t = inp.get_attribute("type") or "text"
        if t == "text": inp.fill(USERNAME)
        elif t == "password": inp.fill(PASSWORD)
    for btn in page.locator("button").all():
        if btn.is_visible() and "登录" in (btn.text_content() or ""):
            btn.click(); break
    time.sleep(4)
    page.wait_for_load_state("networkidle", timeout=15000)
    body = page.locator("body").first.text_content() or ""
    return "Phase" in body

def main():
    print("📝 Quiz 完整流程测试")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        if not login(page):
            print("❌ 登录失败"); browser.close(); return

        print("✅ 已登录\n")

        # ── 1. Discover: 哪些 lesson 有 quiz? ──
        print("🔍 1. 发现Quiz课时...")
        quiz_lessons = []
        for pid in range(1, 6):
            r = api(page, f"{BASE_URL}/api/lessons?phase_id={pid}")
            if r.get("json"):
                lessons = r["json"] if isinstance(r["json"], list) else r["json"].get("lessons", [])
                for l in lessons:
                    has_q = l.get("has_quiz") or l.get("quiz_enabled")
                    if has_q:
                        quiz_lessons.append({
                            "id": l["id"], "title": l.get("title", ""),
                            "phase_id": pid, "has_quiz": True
                        })

        # Also try /phase3-api
        if not quiz_lessons:
            for pid in range(1, 6):
                r = api(page, f"{BASE_URL}/phase3-api/lessons?phase_id={pid}")
                if r.get("json"):
                    lessons = r["json"] if isinstance(r["json"], list) else r["json"].get("lessons", [])
                    for l in lessons:
                        quiz_lessons.append({"id": l["id"], "title": l.get("title", ""),
                                           "phase_id": pid})

        print(f"   找到 {len(quiz_lessons)} 个带Quiz课时")
        for ql in quiz_lessons[:10]:
            print(f"     L{ql['id']} (Phase {ql['phase_id']}): {ql.get('title', '')[:50]}")

        # ── 2. Try to start Quiz ──
        results = []

        # Try both token types
        tokens_found = page.evaluate("""
            JSON.stringify({
                token: localStorage.getItem('token'),
                auth_token: localStorage.getItem('auth_token'),
                keys: Object.keys(localStorage)
            })
        """)
        print(f"\n   localStorage keys: {tokens_found}")

        for ql in (quiz_lessons[:5] or [{"id": 20, "phase_id": 1}, {"id": 26, "phase_id": 5}]):
            lid = ql["id"]
            print(f"\n{'─'*40}")
            print(f"📝 测试 L{lid} Quiz")

            test = {"lesson_id": lid}

            # Try both prefixes
            for prefix in ["/phase3-api", "/api"]:
                # Step 1: Start
                start_r = api(page, f"{BASE_URL}{prefix}/quiz/start",
                             method="POST", body={"lesson_id": lid})
                test[f"start_{prefix}"] = {
                    "status": start_r.get("status"),
                    "ok": start_r.get("ok"),
                }

                if start_r.get("json"):
                    j = start_r["json"]
                    test["questions"] = j.get("questions", [])
                    test["quiz_session_id"] = j.get("quiz_session_id")
                    test["next_lesson_id"] = j.get("next_lesson_id")
                    sid = test.get('quiz_session_id')
                    sid_str = str(sid)[:20] if sid is not None else 'none'
                    print(f"   {prefix}: {len(test['questions'])} 题, "
                          f"session={sid_str}")

                    qs = test["questions"]
                    if qs:
                        # Step 2: Build answers (pick option A for each)
                        answers = []
                        for q in qs:
                            opts = q.get("options", [])
                            opt_id = None
                            if opts:
                                opt_id = opts[0].get("id") or opts[0].get("value") or "A"
                            answers.append({
                                "question_id": q.get("id") or q.get("question_id"),
                                "selected_answer": opt_id,
                            })

                        # Step 3: Submit
                        submit_r = api(page, f"{BASE_URL}{prefix}/quiz/submit",
                                      method="POST", body={
                                          "quiz_session_id": test["quiz_session_id"],
                                          "answers": answers,
                                      })
                        test[f"submit_{prefix}"] = {
                            "status": submit_r.get("status"),
                            "ok": submit_r.get("ok"),
                        }
                        if submit_r.get("json"):
                            sj = submit_r["json"]
                            test["score"] = sj.get("score")
                            test["results"] = sj.get("results", [])[:3]
                            test["submit_next"] = sj.get("next_lesson_id")
                            print(f"   提交: ✅ score={test['score']}, "
                                  f"next_lesson={test['submit_next']}")
                        else:
                            print(f"   提交: ❌ HTTP {submit_r.get('status')}")
                            test["submit_error_body"] = submit_r.get("body", "")[:200]
                        break
                else:
                    print(f"   {prefix}: ❌ HTTP {start_r.get('status')} "
                          f"body={start_r.get('body', '')[:100]}")

            results.append(test)

        browser.close()

        # ── Save ──
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str),
                         encoding="utf-8")

        # ── Summary ──
        print(f"\n{'='*60}")
        print("📊 Quiz 测试摘要")
        for r in results:
            qs = r.get("questions", [])
            score = r.get("score")
            print(f"  L{r['lesson_id']}: {len(qs)}题, 得分={score}")

if __name__ == "__main__":
    main()
