"""Fix reports: use correct API, field mapping."""
with open('frontend/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Fix API endpoint
html = html.replace(
    "const d = await get('/api/dashboard/sessions?page_size=20');",
    "const d = await get('/api/reports?page_size=20');"
)

# 2. Fix field mapping: reports API returns {items:[{id,overall,total,created_at,...}]}
html = html.replace(
    "var overall = (r.summary_json&&r.summary_json.avg_scores&&r.summary_json.avg_scores.overall) ? r.summary_json.avg_scores.overall.toFixed(1) : '-';",
    "var overall = r.overall ? Number(r.overall).toFixed(1) : '-';"
)
html = html.replace(
    "var icon = r.status==='success'?'✅':'❌';",
    "var icon = '✅';"
)
html = html.replace(
    "r.session_id",
    "r.id"
)
html = html.replace(
    "r.total_scenarios",
    "r.total||'-'"
)

# 3. Fix viewReportDetail to use reports API
old_view = "var session = (sessions.items||[]).find(function(s){return s.session_id===sessionId;});"
new_view = "var session = null; try { var rr = await fetch(API+'/api/reports/'+sessionId); if(rr.ok) session = await rr.json(); } catch(e) {}"
html = html.replace(old_view, new_view)

with open('frontend/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('Reports frontend fixed')
