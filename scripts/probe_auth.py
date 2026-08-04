"""认证后交互探查: API拿JWT → 注入SPA → 探测自测题/课时/解锁/视频, 并尝试触发自测。"""
import os, time, json, requests
os.environ.pop("PLAYWRIGHT_PROXY", None)
from playwright.sync_api import sync_playwright

BASE = "http://124.174.108.70"

s = requests.Session(); s.trust_env = False; s.proxies = {"http": None, "https": None}
# P1-11: 测试凭据从环境变量读取 (默认值仅用于本地开发)
PLATFORM_USER = os.getenv("PLATFORM_USERNAME", "student001")
PLATFORM_PASS = os.getenv("PLATFORM_PASSWORD", "123456")
tok = s.post(BASE + "/api/auth/login", json={"username": PLATFORM_USER, "password": PLATFORM_PASS}, timeout=15).json()["token"]
print("JWT:", tok[:24], "...")

DUMP = r"""() => {
  const q = s => Array.from(document.querySelectorAll(s));
  const t = e => (e.innerText || '').trim().replace(/\s+/g,' ').slice(0,50);
  const h1 = (document.querySelector('h1')||{}).innerText || '';
  return {
    h1: h1,
    loggedIn: !/登录平台/.test(h1),
    selftest_btns: q('button,[role=button],.el-button').filter(e=>/自测|开始测试|答题|测验|开始自测|提交/.test(e.innerText||'')).map(t).slice(0,15),
    lesson_cards: q('button,[role=button],.card,[class*=card],[class*=lesson]').filter(e=>/Day ?\d|课时|Lesson|导学/i.test(e.innerText||'')).map(t).slice(0,20),
    unlock: q('*').filter(e=>e.children.length<2 && /解锁|未解锁|已完成|标记完成|完成本课|下一课/.test(e.innerText||'')).map(t).slice(0,15),
    radios: q('input[type=radio]').length,
    checkboxes: q('input[type=checkbox]').length,
    videos: q('video').map(v=>({src:(v.src||v.currentSrc||'').slice(0,60), dur:v.duration, ready:v.readyState})),
    buttons_all: q('button,[role=button]').filter(e=>e.offsetParent).map(t).filter(Boolean).slice(0,40),
  };
}"""

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--no-proxy-server"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    for pat in ["**/fonts.googleapis.com/**", "**/fonts.gstatic.com/**", "**/*.{woff,woff2,ttf,otf,eot}"]:
        ctx.route(pat, lambda r: r.abort())
    pg = ctx.new_page()
    pg.goto(BASE, wait_until="commit", timeout=60000)
    pg.wait_for_timeout(2000)
    pg.evaluate("(t)=>{for(const k of ['token','jwt','authToken','access_token','auth_token','userToken']) localStorage.setItem(k,t);}", tok)
    pg.reload(wait_until="commit")
    pg.wait_for_timeout(3500)

    st = pg.evaluate(DUMP)
    print("\n== 认证后状态 ==")
    print("h1:", st["h1"][:40], "| loggedIn:", st["loggedIn"])
    print("自测按钮:", st["selftest_btns"])
    print("课时卡:", st["lesson_cards"])
    print("解锁相关:", st["unlock"])
    print("radio:", st["radios"], "checkbox:", st["checkboxes"])
    print("视频:", st["videos"])
    print("可见按钮(前40):", st["buttons_all"])

    # 尝试触发自测
    print("\n== 尝试触发自测题 ==")
    for kw in ["开始自测", "带带我课前自测", "课前自测", "自测", "开始测试", "10 题自测"]:
        try:
            el = pg.query_selector(f"text={kw}")
            if el and el.is_visible():
                el.scroll_into_view_if_needed(timeout=3000)
                el.click(timeout=5000)
                print(f"  点击: {kw}")
                pg.wait_for_timeout(2500)
                quiz = pg.evaluate(r"""()=>{const q=s=>Array.from(document.querySelectorAll(s));const t=e=>(e.innerText||'').trim().replace(/\s+/g,' ').slice(0,80);
                  return {radios:q('input[type=radio]').length, opts:q('input[type=radio],[class*=option],[class*=choice]').map(t).slice(0,12),
                  question:q('*').filter(e=>e.children.length<3&&/\?|？|判断|选择|下列|哪个|正确/.test(e.innerText||'')).map(t).slice(0,6),
                  submit:q('button').filter(e=>/提交|确认|下一题|完成/.test(e.innerText||'')).map(t).slice(0,6)};}""")
                print("  自测DOM:", quiz)
                break
        except Exception as e:
            print(f"  {kw} 失败: {str(e)[:50]}")

    try:
        pg.screenshot(path="reports/probe_auth.png", timeout=10000, full_page=True)
        print("\n截图: reports/probe_auth.png")
    except Exception as e:
        print("截图跳过:", str(e)[:40])
    with open("reports/probe_auth.json", "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    b.close()
