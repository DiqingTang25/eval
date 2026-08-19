"""测试: page.evaluate(fetch) 是否能拿到API响应"""
from playwright.sync_api import sync_playwright
import time, json

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
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
            }, 500);
        } + ")()";
        document.body.appendChild(s);
    }''')
    time.sleep(8)
    print(f'Logged in. URL: {page.url[:80]}')

    # Test: call API via page.evaluate with fetch
    for api_name, api_url in [
        ("graph-source", "http://124.174.108.70/personalized-secure-api/v1/graph-source"),
        ("careers", "http://124.174.108.70/personalized-secure-api/v1/careers"),
        ("digital-teacher", "http://124.174.108.70/personalized-secure-api/v1/digital-teacher/context"),
    ]:
        result = page.evaluate("""
            async (url) => {
                try {
                    const resp = await fetch(url, {
                        headers: {'Accept': 'application/json'},
                        credentials: 'include'
                    });
                    const text = await resp.text();
                    return {status: resp.status, ok: resp.ok, text: text};
                } catch(e) {
                    return {status: 0, ok: false, text: 'ERROR: ' + e.message};
                }
            }
        """, api_url)
        status = result.get('status', '?')
        ok = result.get('ok', False)
        text_len = len(result.get('text', '')) if result else 0
        print(f'{api_name}: status={status} ok={ok} text_len={text_len}')
        if ok and text_len > 50:
            try:
                data = json.loads(result['text'])
                keys = list(data.keys()) if isinstance(data, dict) else f'[{len(data)}]'
                print(f'  keys: {keys}')
            except: pass

    b.close()
