"""Final cleanup: remove remaining i18n/v3.4 references."""
import re

with open('frontend/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Remove t() and tStatus() functions
old_t = """function t(key, ...args) {
  const dict = I18N[LANG] || I18N.zh;
  let v = dict[key];
  if (v === undefined) v = (I18N.zh[key] !== undefined ? I18N.zh[key] : key);
  if (typeof v !== 'string') return v;
  if (args.length) return v.replace(/\{(\d+)\}/g, (_, n) => args[+n] ?? '');
  return v;
}
function tStatus(s) { const v = (I18N[LANG]||I18N.zh)['status_'+s]; return v || s; }
"""
if old_t in content:
    content = content.replace(old_t, '')
    print('Removed t() and tStatus()')

# Fix 2: LANG variable
content = content.replace("let LANG = (localStorage.getItem('lang')||'zh');\n", '')

# Fix 3: Replace I18N dim_labels references
old_dim = "(I18N[LANG]||I18N.zh).dim_labels"
new_dim = "{correctness:'事实正确性',relevancy:'答案相关性',completeness:'内容完整性',guidance:'教学引导力',followup_quality:'追问响应质量',boundary_compliance:'边界合规性',turn_consistency:'跨轮一致性',knowledge_scaffolding:'知识递进性',overhelping:'过度帮助',fairness_bias:'公平性偏差'}"
content = content.replace(old_dim, new_dim)

# Fix 4: tStatus fallback
content = content.replace(
    "function tStatus(s) { const v = (I18N[LANG]||I18N.zh)['status_'+s]; return v || s; }",
    "function tStatus(s) { return s; }"
)

# Fix 5: v3.4 in report footer
content = content.replace(
    "AI Agent 评测平台 v3.4 自动生成",
    "AI Agent 评测平台自动生成"
)

# Fix 6: Replace t() calls with key string
t_calls = set(re.findall(r"t\('([^']+)'\)", content))
for key in t_calls:
    content = content.replace(f"t('{key}')", f"'{key}'")

# Fix 7: also fix t("...") calls
t_calls_dq = set(re.findall(r't\("([^"]+)"\)', content))
for key in t_calls_dq:
    content = content.replace(f't("{key}")', f'"{key}"')

# Verify
count = content.count('I18N') + content.count('v3.4') + content.count('toggleLang') + content.count('applyI18n') + content.count('data-i18n') + content.count('setLang') + content.count('refreshActivePage')
print(f'Remaining: {count}')

with open('frontend/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('DONE')
