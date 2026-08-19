"""捕获登录JWT + 直接调API"""
from playwright.sync_api import sync_playwright
import time, requests, json

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()

    # 拦截auth/login响应, 捕获JWT
    captured_jwt = []
    def on_response(resp):
        if 'auth/login' in resp.url:
            try:
                body = resp.json()
                print(f'LOGIN RESPONSE: {json.dumps(body, ensure_ascii=False)[:300]}')
                if 'accessToken' in body:
                    captured_jwt.append(body['accessToken'])
            except: pass
    page.on('response', on_response)

    page.goto('http://124.174.108.70/personalized-secure',
              wait_until='domcontentloaded', timeout=30000)

    for i in range(20):
        time.sleep(1)
        if page.locator('input:visible').count() >= 2:
            break
    time.sleep(2)

    page.locator('input').first.fill('111')
    page.locator('input[type=password]').first.fill('123456')

    # React Fiber login
    page.evaluate('''() => {
        const s = document.createElement("script");
        s.textContent = "(" + function() {
            setTimeout(function() {
                var f = document.querySelector("form");
                if (!f) return;
                var k = Object.keys(f).find(function(x) { return x.startsWith("__reactFiber"); });
                if (!k) return;
                f[k].pendingProps.onSubmit({preventDefault: function(){}, currentTarget: f});
            }, 300);
        } + ")()";
        document.body.appendChild(s);
    }''')
    time.sleep(8)

    jwt = captured_jwt[0] if captured_jwt else ''
    print(f'JWT captured: {jwt[:50] if jwt else "NONE"}...')

    if jwt:
        s = requests.Session()
        s.headers['Authorization'] = f'Bearer {jwt}'
        for api in ['graph-source', 'careers', 'digital-teacher/context']:
            url = f'http://124.174.108.70/personalized-secure-api/v1/{api}'
            r = s.get(url, timeout=10)
            print(f'{api}: status={r.status_code} len={len(r.text)}')
            if r.status_code == 200:
                try:
                    d = r.json()
                    keys = list(d.keys()) if isinstance(d, dict) else f'[{len(d)}]'
                    print(f'  keys: {keys}')
                except: pass

    b.close()
