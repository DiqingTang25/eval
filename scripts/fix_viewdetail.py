with open('frontend/index.html','r',encoding='utf-8') as f:
    html=f.read()

# Replace the entire viewReportDetail function with a simpler version
old_start = 'async function viewReportDetail(reportId) {'
old_end = 'function renderReportDetail(session, data, el) {'

new_func = '''async function viewReportDetail(reportId) {
  var el = document.getElementById('reportDetailSection');
  if (!el) {
    var tbl = document.getElementById('reportTable');
    if (!tbl) return;
    el = document.createElement('div');
    el.id = 'reportDetailSection';
    el.style.cssText = 'margin-top:16px';
    tbl.closest('table').parentNode.insertBefore(el, tbl.closest('table').nextSibling);
  }
  el.innerHTML = '<div class="cal-loading"><div class="cal-spinner"></div><span>加载报告详情...</span></div>';
  el.scrollIntoView({behavior:'smooth'});

  var data = null;
  // Load the most recent file report (file-based, always has full data)
  try {
    var filesR = await fetch('/test/api/reports/files');
    var filesData = await filesR.json();
    var items = filesData.items || [];
    // Sort by mtime descending, pick first with JSON format
    items.sort(function(a,b){return b.mtime - a.mtime;});
    for (var i=0; i<items.length; i++) {
      if (items[i].formats && items[i].formats.json) {
        try {
          var fd = await fetch('/test/api/reports/file/'+items[i].name);
          if (fd.ok) { data = await fd.json(); break; }
        } catch(e) {}
      }
    }
  } catch(e) { console.log('File reports:', e.message); }

  if (!data) {
    el.innerHTML = '<div class="card" style="padding:20px;text-align:center;color:var(--muted)">未找到报告数据。请先运行一次评测。</div>';
    return;
  }
  renderReportDetail(null, data, el);
}

'''

start = html.find(old_start)
end = html.find(old_end)
if start > 0 and end > start:
    html = html[:start] + new_func + html[end:]

with open('frontend/index.html','w',encoding='utf-8') as f:
    f.write(html)
print('viewReportDetail rewritten: loads latest file report')
