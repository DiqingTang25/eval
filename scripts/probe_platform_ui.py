"""
平台真实可交互元素探查 (Playwright) — 修正版

关键修复(实测得出):
  - SPA 的 networkidle / 默认 screenshot 会因 webfont 永不加载而挂起 → 用 wait_until="commit"
    + 拦截字体请求(route abort) + 短超时截图。
  - WSL 需 --no-sandbox。
  - DOM 可通过 evaluate/click 完整交互(已验证)。
"""
import os, time, json
os.environ.pop("PLAYWRIGHT_PROXY", None)
from playwright.sync_api import sync_playwright

BASE = "http://124.174.108.70"
USER, PWD = "student001", "123456"

JS_DUMP = """() => {
    const t = el => (el.innerText||el.value||el.getAttribute('aria-label')||'').trim().slice(0,40);
    const q = s => Array.from(document.querySelectorAll(s));
    const vis = el => { const r=el.getBoundingClientRect(); return r.width>0&&r.height>0; };
    return {
        url: location.href, title: document.title,
        headings: q('h1,h2,h3').map(t).filter(Boolean).slice(0,25),
        buttons: q('button,[role=button],.el-button').filter(vis).map(t).filter(Boolean).slice(0,50),
        inputs: q('input,textarea').map(e => (e.type||'ta')+':'+(e.placeholder||e.name||e.id||'')).slice(0,25),
        videos: q('video').length,
        iframes: q('iframe').map(e=>e.src).slice(0,10),
        code_editors: { monaco:q('.monaco-editor').length, codemirror:q('.cm-editor,.CodeMirror').length, textarea:q('textarea').length },
        quiz: q('*').filter(e=>e.children.length<3 && /测试题|测验|答题|选择题|提交答案|单选|多选|判断题|得分|正确答案/.test(e.textContent||'')).map(t).slice(0,20),
        steps: q('*').filter(e=>e.children.length<3 && /步骤|Step|解锁|标记完成|下一步|下一课|preparation|practice|core|guided|challenge/i.test(e.textContent||'')).map(t).slice(0,25),
    };
}"""


def dump(page, tag):
    d = page.evaluate(JS_DUMP)
    print(f"\n===== [{tag}] {d['url']} =====")
    for k in ["title", "headings", "buttons", "inputs", "videos", "iframes", "code_editors", "quiz", "steps"]:
        print(f"  {k}: {d[k]}")
    return d


def shot(page, name):
    try:
        page.screenshot(path=f"reports/{name}", timeout=8000)
        print(f"  📷 {name}")
    except Exception as e:
        print(f"  (截图跳过: {str(e)[:50]})")


with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--no-proxy-server"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    ctx.route("**/*.{woff,woff2,ttf,otf,eot}", lambda r: r.abort())  # 拦截字体, 防挂起
    page = ctx.new_page()
    results = {}
    try:
        page.goto(BASE, wait_until="commit", timeout=60000)
        page.wait_for_selector("input", timeout=15000)
        page.wait_for_timeout(2000)
        results["landing"] = dump(page, "着陆/登录页")
        shot(page, "probe_1_landing.png")

        # ── 登录 ──
        try:
            ins = [e for e in page.query_selector_all("input") if e.is_visible()]
            print(f"\n可见input数: {len(ins)}")
            if len(ins) >= 2:
                ins[0].fill(USER); ins[1].fill(PWD)
            for sel in ["button:has-text('登录')", "button:has-text('登 录')", ".el-button--primary", "button[type=submit]"]:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click(); print(f"点击登录: {sel}"); break
            page.wait_for_timeout(5000)
        except Exception as e:
            print("登录异常:", str(e)[:100])
        results["after_login"] = dump(page, "登录后")
        shot(page, "probe_2_afterlogin.png")

        # ── 进入课程/课时 ──
        for kw in ["Day 1", "电子硬件", "平台导学", "开始学习", "进入学习", "进入", "学习"]:
            try:
                el = page.query_selector(f"text={kw}")
                if el and el.is_visible():
                    el.click(); print(f"\n进入: {kw}"); page.wait_for_timeout(5000); break
            except Exception:
                continue
        results["lesson"] = dump(page, "课时/学习页")
        shot(page, "probe_3_lesson.png")

        with open("reports/probe_platform_ui.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print("\n结构化结果: reports/probe_platform_ui.json")
    except Exception as e:
        print("探查异常:", repr(e)[:150])
    finally:
        b.close()
