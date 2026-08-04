"""Clean up frontend: remove broken i18n, v3.4 version, productize."""
import re

with open('frontend/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# 1. Remove version from title
old = '<title>AI Agent 评测平台 v3.4</title>'
new = '<title>AI Agent 评测平台</title>'
if old in content:
    content = content.replace(old, new); changes += 1

# 2. Remove version from h1
old = '<h1 data-i18n="app_h1">\U0001f916 AI Agent 评测平台 v3.4</h1>'
new = '<h1>AI Agent 评测平台</h1>'
if old in content:
    content = content.replace(old, new); changes += 1

# 3. Remove EN toggle button
old = '    <button id="langToggle" class="lang-toggle" onclick="toggleLang()" title="切换语言 / Switch language">EN</button>\n'
if old in content:
    content = content.replace(old, ''); changes += 1

# 4. Remove I18N object (between markers)
i18n_start = content.find('// ==================== I18N ====================')
i18n_obj_end = content.find('\n};\n', i18n_start + 400)  # Skip past the zh block, find }; of I18N
if i18n_start > 0 and i18n_obj_end > 0:
    # Find the actual end of I18N const (after en block closes)
    # The I18N object ends with '  }\n};'
    obj_end = content.find('  }\n};', i18n_obj_end - 100)
    if obj_end < 0:
        obj_end = content.find('\n};\n\n', i18n_obj_end)
    if obj_end > 0:
        content = content[:i18n_start] + content[obj_end+3:]
        changes += 1

# 5. Remove t() and tStatus() functions
old_funcs = '''function t(key, ...args) {
  const dict = I18N[LANG] || I18N.zh;
  let v = dict[key];
  if (v === undefined) v = (I18N.zh[key] !== undefined ? I18N.zh[key] : key);
  if (typeof v !== 'string') return v;
  if (args.length) return v.replace(/\{(\d+)\}/g, (_, n) => args[+n] ?? '');
  return v;
}
function tStatus(s) { const v = (I18N[LANG]||I18N.zh)['status_'+s]; return v || s; }
'''
if old_funcs in content:
    content = content.replace(old_funcs, ''); changes += 1

# 6. Remove LANG variable
old_lang = "let LANG = (localStorage.getItem('lang')||'zh');\n"
if old_lang in content:
    content = content.replace(old_lang, ''); changes += 1

# 7. Remove applyI18n function
start = content.find('function applyI18n() {')
if start > 0:
    depth = 0; i = start; found_brace = False
    while i < len(content):
        if content[i] == '{': depth += 1; found_brace = True
        elif content[i] == '}':
            depth -= 1
            if found_brace and depth == 0:
                end = i + 1
                if end < len(content) and content[end] == '\n': end += 1
                content = content[:start] + content[end:]
                changes += 1
                break
        i += 1

# 8. Remove currentPage function
start = content.find('function currentPage() {')
if start > 0:
    depth = 0; i = start; found_brace = False
    while i < len(content):
        if content[i] == '{': depth += 1; found_brace = True
        elif content[i] == '}':
            depth -= 1
            if found_brace and depth == 0:
                end = i + 1
                if end < len(content) and content[end] == '\n': end += 1
                content = content[:start] + content[end:]
                changes += 1
                break
        i += 1

# 9. Remove refreshActivePage function
start = content.find('function refreshActivePage() {')
if start > 0:
    depth = 0; i = start; found_brace = False
    while i < len(content):
        if content[i] == '{': depth += 1; found_brace = True
        elif content[i] == '}':
            depth -= 1
            if found_brace and depth == 0:
                end = i + 1
                if end < len(content) and content[end] == '\n': end += 1
                content = content[:start] + content[end:]
                changes += 1
                break
        i += 1

# 10. Remove setLang and toggleLang functions
for fname in ['setLang', 'toggleLang']:
    start = content.find(f'function {fname}(')
    if start > 0:
        depth = 0; i = start; found_brace = False
        while i < len(content):
            if content[i] == '{': depth += 1; found_brace = True
            elif content[i] == '}':
                depth -= 1
                if found_brace and depth == 0:
                    end = i + 1
                    if end < len(content) and content[end] == '\n': end += 1
                    content = content[:start] + content[end:]
                    changes += 1
                    break
            i += 1

# 11. Remove applyI18n call from init
content = content.replace('applyI18n();\n', '')
# Fix the LANG set call inside setLang
content = content.replace("LANG = l;\n  try { localStorage.setItem('lang', l); } catch(e) {}\n  applyI18n();\n  refreshActivePage();\n", '')
# Clean up lone refreshActivePage calls
content = content.replace('  refreshActivePage();\n', '')

# 12. Remove clearBox t() reference - replace with string
content = content.replace("el.innerHTML = `<div class=\"qa-empty\">${t('log_cleared')}</div>`;",
                          "el.innerHTML = '<div class=\"qa-empty\">已清空</div>';")

# 13. Remove data-i18n attributes
content = re.sub(r' data-i18n="[^"]*"', '', content)
content = re.sub(r' data-i18n-ph="[^"]*"', '', content)

# 14. Remove escHtml duplicate (it's in calibration.js too, keep inline version)
# escHtml is used inline, keep it

# 15. Clean up whitespace
while '\n\n\n\n' in content: content = content.replace('\n\n\n\n', '\n\n\n')

with open('frontend/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print(f'DONE - {changes} changes made')
