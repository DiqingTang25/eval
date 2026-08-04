"""Trim index.html platform-health section to skeleton"""
with open('frontend/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

start = content.find('<div id="page-platform-health" class="page">')
end = content.find('<!-- CALIBRATION')

if start >= 0 and end > start:
    skeleton = '<div id="page-platform-health" class="page">\n  <!-- 由 frontend/js/pages/platform-health.js 动态渲染 -->\n  <div class="qa-empty" style="padding:60px">\U0001f4e1 加载中...</div>\n</div>\n\n'
    content = content[:start] + skeleton + content[end:]
    with open('frontend/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'OK: replaced {end - start} chars')
else:
    print(f'NOT FOUND: start={start}, end={end}')
