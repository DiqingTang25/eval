#!/usr/bin/env python3
"""Remove overall_score column from report list table"""
with open('/opt/agent_eval/index.html', 'r') as f:
    html = f.read()

# 1. Fix thead
html = html.replace(
    '<thead><tr><th>时间</th><th>Agent</th><th>综合分</th><th>场景数</th><th>状态</th></tr></thead>',
    '<thead><tr><th>时间</th><th>Agent</th><th>场景数</th><th>状态</th></tr></thead>'
)
print('1. thead fixed')

# 2. Fix colspan
html = html.replace('colspan="5" class="qa-empty"', 'colspan="4" class="qa-empty"')
print('2. colspan fixed')

# 3. Remove score cell - actual pattern uses single quotes
old_score = "+'<td><b style=\"color:var(--sky)\">'+(r.overall_score != null ? r.overall_score.toFixed(2) : '-')+'</b></td>'+"
if old_score in html:
    html = html.replace(old_score, "+")
    print('3. score cell removed')
else:
    print('3. trying alt pattern...')
    # Try with escaped single quotes
    alt = "<td><b style=\"color:var(--sky)\">'+(r.overall_score != null ? r.overall_score.toFixed(2) : '-')+'</b></td>"
    if alt in html:
        html = html.replace(alt, "")
        print('3. alt pattern removed')
    else:
        print('3. FAILED - manual fix needed')

with open('/opt/agent_eval/index.html', 'w') as f:
    f.write(html)
with open('/opt/agent_eval/frontend/index.html', 'w') as f:
    f.write(html)
print('Done')
