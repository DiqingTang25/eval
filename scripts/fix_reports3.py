"""Fix viewReportDetail: file-first strategy, DB fallback."""
with open('frontend/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Replace the entire viewReportDetail function
old_func_start = 'async function viewReportDetail(sessionId) {'
old_func_end = 'function renderReportDetail(session, data, el) {'

new_viewDetail = '''async function viewReportDetail(reportId) {
  var el = document.getElementById('reportDetailSection');
  if (!el) {
    var tbl = document.getElementById('reportTable');
    if (!tbl) { console.error('reportTable not found'); return; }
    el = document.createElement('div');
    el.id = 'reportDetailSection';
    el.style.cssText = 'margin-top:16px';
    tbl.closest('table').parentNode.insertBefore(el, tbl.closest('table').nextSibling);
  }
  el.innerHTML = '<div class=\"cal-loading\"><div class=\"cal-spinner\"></div><span>加载报告详情...</span></div>';
  el.scrollIntoView({behavior:'smooth'});

  var data = null;
  // Strategy 1: Load from reports/ JSON files (has full data)
  try {
    var filesR = await fetch('/test/api/reports/files');
    var filesData = await filesR.json();
    // Try to match by timestamp in filename
    for (var f of (filesData.items||[])) {
      try {
        var fd = await fetch('/test/api/reports/file/'+f.name);
        if (fd.ok) {
          var candidate = await fd.json();
          // Accept first valid report file
          if (!data || (candidate.timestamp > (data.timestamp||''))) {
            data = candidate;
          }
        }
      } catch(e) {}
    }
  } catch(e) { console.log('File reports not available:', e.message); }

  // Strategy 2: DB report as metadata supplement
  var dbReport = null;
  try {
    var rr = await fetch(API+'/api/reports/'+reportId);
    if (rr.ok) dbReport = await rr.json();
  } catch(e) {}

  if (!data && !dbReport) {
    el.innerHTML = '<div class=\"card\" style=\"padding:20px;text-align:center;color:var(--muted)\">报告数据不可用。请先运行一次评测生成报告。</div>';
    return;
  }
  renderReportDetail(dbReport, data, el);
}

'''

# Find and replace
start = html.find(old_func_start)
end = html.find(old_func_end)
if start > 0 and end > start:
    html = html[:start] + new_viewDetail + html[end:]

with open('frontend/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('viewReportDetail rewritten: file-first strategy')
