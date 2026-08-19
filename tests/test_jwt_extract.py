"""测试: React Fiber登录 → 提取JWT → 直接调API"""
from playwright.sync_api import sync_playwright
import time, requests

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('http://124.174.108.70/personalized-secure',
              wait_until='domcontentloaded', timeout=30000)

    for i in range(20):
        time.sleep(1)
        if page.locator('input:visible').count() >= 2:
            break

    page.locator('input').first.fill('111')
    page.locator('input[type=password]').first.fill('123456')

    # React Fiber submit
    page.evaluate('''() => {
        const s = document.createElement("script");
        s.textContent = "(" + function() {
            setTimeout(function() {
                var f = document.querySelector("form");
                if (!f) return;
                var k = Object.keys(f).find(function(x) { return x.startsWith("__reactFiber"); });
                if (!k) return;
                var o = f[k].pendingProps.onSubmit;
                o({preventDefault: function(){}, currentTarget: f});
            }, 500);
        } + ")()";
        document.body.appendChild(s);
    }''')
    time.sleep(8)

    # Check localStorage
    token = page.evaluate(
        '() => localStorage.getItem("accessToken") || localStorage.getItem("token") || ""'
    )
    print(f'localStorage token: {token[:80] if token else "NONE"}')

    # Check cookies
    cookies = page.context.cookies()
    print(f'Cookies ({len(cookies)}):')
    for c in cookies[:5]:
        print(f'  {c["name"]}: {c["value"][:40]}')

    # Direct API calls
    s = requests.Session()
    for c in cookies:
        s.cookies.set(c['name'], c['value'])
    if token:
        s.headers['Authorization'] = f'Bearer {token}'

    for api in ['graph-source', 'careers', 'digital-teacher/context']:
        url = f'http://124.174.108.70/personalized-secure-api/v1/{api}'
        try:
            r = s.get(url, timeout=10)
            print(f'\n{api}: status={r.status_code} len={len(r.text)}')
            if r.status_code == 200 and len(r.text) > 100:
                print(f'  {r.text[:300]}')
        except Exception as e:
            print(f'\n{api}: ERROR {e}')

    b.close()
