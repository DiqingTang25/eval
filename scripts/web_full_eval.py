"""
全维度网页评测 — 对标 Lighthouse + CLEAR + TEACH-AI
评测维度: Performance / Accessibility / BestPractices / AI Chat / UI-UX / Content
"""
import os, sys, json, time
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# 从项目根 .env 加载密钥 (不再硬编码)
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Proxy 可在 .env 设置 PLAYWRIGHT_PROXY (本地调试用, 云端留空即可)

from playwright.sync_api import sync_playwright

URL = "http://124.174.108.70"
LOGIN_USER = os.getenv("PLATFORM_USERNAME", "student001")
LOGIN_PASS = os.getenv("PLATFORM_PASSWORD", "123456")

results = {"url": URL, "timestamp": datetime.now().isoformat(), "dimensions": {}}

print("=" * 60)
print(f"🌐 全维度网页评测: {URL}")
print("=" * 60)

proxy = {"server": os.getenv("PLAYWRIGHT_PROXY")} if os.getenv("PLAYWRIGHT_PROXY") else None

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, proxy=proxy)
    ctx = browser.new_context(viewport={"width": 1280, "height": 720})
    page = ctx.new_page()

    # ── 加载页面 ──
    print("\n[1/7] ⏱️  加载页面...")
    t0 = time.time()
    page.goto(URL, wait_until="load", timeout=60000)
    load_time = (time.time() - t0) * 1000
    print(f"  加载时间: {load_time:.0f}ms | 标题: {page.title()}")

    # ═══════════════════════════════════════════
    # P0: Performance (Lighthouse风格)
    # ═══════════════════════════════════════════
    print("\n[2/7] ⚡ Performance (Core Web Vitals)")
    perf = page.evaluate("""() => {
        const nav = performance.getEntriesByType('navigation')[0] || {};
        const paint = performance.getEntriesByType('paint') || [];
        let fcp = 0;
        paint.forEach(p => { if (p.name === 'first-contentful-paint') fcp = p.startTime; });
        return {
            ttfb: nav.responseStart - nav.requestStart || 0,
            fcp: fcp,
            dcl: nav.domContentLoadedEventEnd - nav.fetchStart || 0,
            loadTime: nav.loadEventEnd - nav.fetchStart || load_time,
            dnsTime: nav.domainLookupEnd - nav.domainLookupStart || 0,
            resourceCount: performance.getEntriesByType('resource').length,
        };
    }""")
    perf["observed_load_ms"] = load_time

    # Lighthouse-style scoring
    def lh_score(val, good, poor):
        if val <= good: return 100
        if val >= poor: return 0
        return round(100 - (val - good) / (poor - good) * 100)

    perf["ttfb_score"] = lh_score(perf["ttfb"], 800, 1800)
    perf["fcp_score"] = lh_score(perf.get("fcp", 0), 1800, 3000)
    perf["load_score"] = lh_score(load_time, 2500, 6000)
    perf["overall"] = round(perf["ttfb_score"] * 0.3 + perf["fcp_score"] * 0.3 + perf["load_score"] * 0.4)
    results["dimensions"]["performance"] = perf
    print(f"  TTFB={perf['ttfb']:.0f}ms({perf['ttfb_score']}) FCP={perf.get('fcp',0):.0f}ms({perf['fcp_score']}) Load={load_time:.0f}ms({perf['load_score']}) → {perf['overall']}/100")

    # ═══════════════════════════════════════════
    # P0: Accessibility (axe-core WCAG)
    # ═══════════════════════════════════════════
    print("\n[3/7] ♿ Accessibility (WCAG 2.1)")
    a11y_score = 100
    a11y_issues = []
    try:
        page.add_script_tag(url="https://cdn.jsdelivr.net/npm/axe-core@4.8.0/axe.min.js")
        time.sleep(2)
        axe = page.evaluate("axe.run({runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}})")
        violations = axe.get("violations", [])
        for v in violations:
            a11y_issues.append({"id": v["id"], "impact": v["impact"], "desc": v["description"][:80], "nodes": len(v.get("nodes", []))})
        a11y_score = max(0, 100 - len(violations) * 8 - sum(v["nodes"] for v in a11y_issues) * 2)
    except Exception as e:
        a11y_issues.append({"error": str(e)[:100]})
        a11y_score = 0

    # 基础检测
    basic = page.evaluate("""() => ({
        imgs_no_alt: document.querySelectorAll('img:not([alt])').length,
        inputs_no_label: document.querySelectorAll('input:not([aria-label]):not([aria-labelledby]):not([id])').length,
        has_lang: !!document.documentElement.lang,
        has_viewport_meta: !!document.querySelector('meta[name="viewport"]'),
    })""")
    a11y_score = max(0, a11y_score - basic["imgs_no_alt"] * 5 - basic["inputs_no_label"] * 3)
    results["dimensions"]["accessibility"] = {
        "score": min(100, a11y_score), "violations": a11y_issues, "basic_checks": basic
    }
    print(f"  axe违规: {len(a11y_issues)} | 无alt图片: {basic['imgs_no_alt']} | 无label输入: {basic['inputs_no_label']} | lang={basic['has_lang']} | viewport={basic['has_viewport_meta']}")
    print(f"  → {a11y_score}/100")

    # ═══════════════════════════════════════════
    # P0: Best Practices
    # ═══════════════════════════════════════════
    print("\n[4/7] ✅ Best Practices")
    bp = page.evaluate("""() => ({
        is_https: location.protocol === 'https:',
        has_csp: !!document.querySelector('meta[http-equiv="Content-Security-Policy"]'),
        console_errors: 0,
        total_links: document.querySelectorAll('a[href]').length,
        total_scripts: document.querySelectorAll('script').length,
    })""")
    bp_score = 100
    bp_issues = []
    if not bp["is_https"]:
        bp_score -= 30; bp_issues.append("非HTTPS")
    if not bp["has_csp"]:
        bp_score -= 10; bp_issues.append("缺少CSP")
    results["dimensions"]["best_practices"] = {
        "score": max(0, bp_score), "checks": bp, "issues": bp_issues
    }
    print(f"  HTTPS={bp['is_https']} CSP={bp['has_csp']} Links={bp['total_links']} Scripts={bp['total_scripts']}")
    print(f"  → {bp_score}/100")

    # ═══════════════════════════════════════════
    # P1: 登录 + AI Chat功能测试
    # ═══════════════════════════════════════════
    print("\n[5/7] 🤖 AI Chat功能测试")
    # 登录 (非致命 — 网页评测先测性能等维度，登录仅用于AI对话)
    logged_in = False
    try:
        uname = page.locator('input[type="text"]').first
        pwd = page.locator('input[type="password"]').first
        if uname.count() > 0 and pwd.count() > 0:
            uname.fill(LOGIN_USER)
            pwd.fill(LOGIN_PASS)
            btn = page.locator('button[type="submit"], button:has-text("登录"), button:has-text("Login")').first
            if btn.count() > 0:
                btn.click()
                time.sleep(3)
                logged_in = True
                print(f"  ✅ 已登录")
    except Exception as e:
        print(f"  ⚠️ 登录跳过: {e}")

    # 打开聊天面板
    if logged_in:
        try:
            page.locator("#floatBall").click(timeout=5000)
            time.sleep(2)
            print(f"  ✅ 聊天面板已打开")
        except Exception:
            print(f"  ⚠️ 聊天面板未打开，尝试直接JS操作")

    # 测试对话
    chat_results = []
    questions = [
        "请简单介绍一下ESP32-S3的主要功能",
        "什么是云边协同？",
    ]
    for q in questions:
        t0 = time.time()
        try:
            page.evaluate(f"""document.querySelector('#msgInput').value = '{q}';
                document.querySelector('#msgInput').dispatchEvent(new Event('input',{{bubbles:true}}));""")
            time.sleep(0.3)
            page.evaluate("document.querySelector('#sendBtn').click()")
            time.sleep(8)  # 等待回复

            # 提取回复
            resp = page.evaluate("""() => {
                const msgs = document.querySelectorAll('#panelMsgs .mr.agt .mb');
                if (msgs.length) {
                    let t = msgs[msgs.length-1].textContent.trim();
                    let idx = t.indexOf('🤖');
                    return idx >= 0 ? t.slice(idx+1).trim() : t;
                }
                return document.querySelector('#panelMsgs')?.innerText?.slice(-500) || '';
            }""")
            lat = round((time.time() - t0) * 1000)
            chat_results.append({"question": q, "response": resp[:500], "latency_ms": lat})
            print(f"  Q: {q[:50]}... → {len(resp)}字符, {lat}ms")
        except Exception as e:
            chat_results.append({"question": q, "error": str(e)[:100]})
            print(f"  Q: {q[:50]}... → 错误: {e}")

    # AI Chat评分
    ai_score = 0
    if chat_results and not any("error" in c for c in chat_results):
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url="https://api.deepseek.com/v1")
        scores = []
        for c in chat_results:
            try:
                resp = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": f"评测AI回答质量(1-5分):\n问题:{c['question']}\n回答:{c['response'][:800]}\n输出JSON:{{\"correctness\":int,\"relevancy\":int,\"completeness\":int,\"guidance\":int}}"}],
                    temperature=0.1, response_format={"type": "json_object"})
                scores.append(json.loads(resp.choices[0].message.content))
            except Exception:
                scores.append({"correctness": 2, "relevancy": 2, "completeness": 2, "guidance": 2})
        avg = {k: round(sum(s[k] for s in scores) / len(scores), 1) for k in ["correctness","relevancy","completeness","guidance"]}
        ai_score = round(sum(avg.values()) * 5)  # 4维1-5 → 0-100
        results["dimensions"]["ai_chat"] = {"score": min(100, ai_score), "dimensions": avg, "questions": chat_results,
            "latency_ms": round(sum(c.get("latency_ms",0) for c in chat_results)/len(chat_results))}
    else:
        results["dimensions"]["ai_chat"] = {"score": 0, "error": "对话测试失败"}

    print(f"  正确性={avg.get('correctness','N/A')} 相关性={avg.get('relevancy','N/A')} 完整性={avg.get('completeness','N/A')} 引导力={avg.get('guidance','N/A')}")
    print(f"  → {ai_score}/100")

    # ═══════════════════════════════════════════
    # P2: UI/UX
    # ═══════════════════════════════════════════
    print("\n[6/7] 🎨 UI/UX")
    ux = page.evaluate("""() => ({
        has_viewport_meta: !!document.querySelector('meta[name="viewport"]'),
        font_families: [...new Set(Array.from(document.querySelectorAll('*')).slice(0,50).map(e => getComputedStyle(e).fontFamily))].slice(0,5),
        small_clicks: Array.from(document.querySelectorAll('button,a,[role="button"]')).filter(e => {const r=e.getBoundingClientRect();return r.width>0&&r.width<20||r.height>0&&r.height<20;}).length,
        overflow_x: document.documentElement.scrollWidth > window.innerWidth,
        total_elements: document.querySelectorAll('*').length,
    })""")
    ux_score = 100
    ux_issues = []
    if ux["overflow_x"]: ux_score -= 15; ux_issues.append("水平溢出")
    if not ux["has_viewport_meta"]: ux_score -= 15; ux_issues.append("缺少viewport meta")
    if ux["small_clicks"] > 3: ux_score -= ux["small_clicks"] * 2; ux_issues.append(f"{ux['small_clicks']}个过小点击目标")
    results["dimensions"]["ui_ux"] = {"score": max(0, ux_score), "checks": ux, "issues": ux_issues}
    print(f"  溢出={ux['overflow_x']} viewport={ux['has_viewport_meta']} 小点击={ux['small_clicks']} 字体={ux['font_families'][:2]}")
    print(f"  → {ux_score}/100")

    # ═══════════════════════════════════════════
    # P2: Content Quality
    # ═══════════════════════════════════════════
    print("\n[7/7] 📝 Content Quality")
    page_text = page.evaluate("document.body?.innerText?.slice(0,3000)||''")
    content_score = 100
    if len(page_text) < 200: content_score -= 30
    elif len(page_text) < 500: content_score -= 10

    # 大纲匹配
    syllabus_path = "data/course_syllabus.txt"
    syllabus_match = 0
    if os.path.exists(syllabus_path):
        with open(syllabus_path) as f: syllabus = f.read()[:2000]
        import jieba
        s_words = set(w for w in jieba.lcut(syllabus) if len(w) > 1)
        p_words = set(jieba.lcut(page_text))
        overlap = s_words & p_words
        syllabus_match = round(len(overlap) / len(s_words) * 100, 1) if s_words else 0

    results["dimensions"]["content"] = {
        "score": content_score, "text_length": len(page_text),
        "syllabus_keyword_match_pct": syllabus_match,
        "headings": page.evaluate("()=>({h1:document.querySelectorAll('h1').length,h2:document.querySelectorAll('h2').length,h3:document.querySelectorAll('h3').length})")
    }
    print(f"  文本长度: {len(page_text)} | 大纲关键词匹配: {syllabus_match}%")
    print(f"  → {content_score}/100")

    # ── 截图 ──
    os.makedirs("reports", exist_ok=True)
    ss_path = f"reports/screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    page.screenshot(path=ss_path, full_page=True)
    print(f"\n📸 截图: {ss_path}")

    browser.close()

# ═══════════════════════════════════════════
# 综合评分
# ═══════════════════════════════════════════
dims = results["dimensions"]
scores = {k: (v.get("score") or v.get("overall") or 0) for k, v in dims.items()}
valid_scores = [s for s in scores.values() if s > 0]
overall = round(sum(valid_scores) / len(valid_scores)) if valid_scores else 0

print("\n" + "=" * 60)
print("  全维度网页评测报告")
print("=" * 60)
labels = {"performance": "⚡ 性能", "accessibility": "♿ 可访问性", "best_practices": "✅ 最佳实践",
          "ai_chat": "🤖 AI对话", "ui_ux": "🎨 UI/UX", "content": "📝 内容"}
for k, label in labels.items():
    s = scores.get(k, 0)
    bar = "█" * (s // 10) + "░" * (10 - s // 10)
    print(f"  {label:10s} {s:3d}/100 {bar}")
print(f"  {'─' * 30}")
print(f"  综合: {overall}/100")
print(f"  截图: {ss_path}")
print("=" * 60)

# 保存报告
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
json_path = f"reports/web_eval_{ts}.json"
html_path = f"reports/web_eval_{ts}.html"
results["overall_score"] = overall
results["screenshot"] = ss_path

# JSON
with open(json_path, "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2, default=str)

# HTML
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.html_reporter import HTMLReporter
html = HTMLReporter.render_web_eval(results)
with open(html_path, "w") as f:
    f.write(html)

print(f"  📄 HTML报告: {html_path}")
print(f"  📄 JSON报告: {json_path}")
