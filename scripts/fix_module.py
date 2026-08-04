with open('frontend/index.html','r',encoding='utf-8') as f:
    html=f.read()
old="'reports': 'reports',\n\t    "
if old in html:
    html=html.replace(old,'')
    print('Removed reports from module map')
else:
    print('NOT FOUND - checking variants')
    for variant in ["'reports': 'reports'", "'reports':"]:
        if variant in html:
            print(f'  Found: {variant}')
with open('frontend/index.html','w',encoding='utf-8') as f:
    f.write(html)
