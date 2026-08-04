"""Fix reports: add file detail endpoint, fix frontend."""
import json

# === 1. Fix backend: add report file detail endpoint ===
with open('backend/api/reports.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_endpoint = '''
@router.get("/file/{report_name}")
async def get_report_file(report_name: str):
    """从 reports/ 目录读取报告 JSON 文件并返回完整数据"""
    import json as _json
    file_path = _REPORTS_DIR / f"{report_name}.json"
    if not file_path.exists():
        raise HTTPException(404, f"Report file not found: {report_name}.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return _json.load(f)
'''

insert_pos = content.rfind('@router.delete')
if insert_pos > 0:
    content = content[:insert_pos] + new_endpoint + '\n' + content[insert_pos:]
else:
    # Fallback: insert before the last route
    content += new_endpoint

with open('backend/api/reports.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('1. Backend: file detail endpoint added')

# === 2. Fix frontend: make reports clickable + detail view ===
with open('frontend/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Replace loadReports() to make rows clickable
old_load = '''async function loadReports() {
  try {
    const d = await get('/api/dashboard/sessions?page_size=20');
    const tbody = document.getElementById('reportTable');
    if (!d.items || !d.items.length) { tbody.innerHTML = `<tr><td colspan="5" class="qa-empty">${t('no_reports')}</td></tr>`; return; }
    tbody.innerHTML = d.items.map(r => `<tr>
      <td>${(r.created_at||'').substring(0,19)}</td>
      <td><span class="badge badge-blue">${escHtml(r.agent_id)}</span></td>
      <td>${r.status==='success'?'✅':'❌'}</td>
      <td>${t('scenarios_count', r.total_scenarios)}</td>
      <td><span class="badge badge-${r.status==='success'?'green':'red'}">${tStatus(r.status)}</span></td>
    </tr>`).join('');
  } catch(e) { console.error(e); }
}'''

new_load = '''let _reportSessions = [];
async function loadReports() {
  try {
    const d = await get('/api/dashboard/sessions?page_size=20');
    _reportSessions = d.items || [];
    const tbody = document.getElementById('reportTable');
    if (!_reportSessions.length) { tbody.innerHTML = '<tr><td colspan="6" class="qa-empty">暂无报告。去「测试运行」启动一次评测。</td></tr>'; return; }
    tbody.innerHTML = _reportSessions.map(function(r) {
      var overall = (r.summary_json&&r.summary_json.avg_scores&&r.summary_json.avg_scores.overall) ? r.summary_json.avg_scores.overall.toFixed(1) : '-';
      var icon = r.status==='success'?'✅':'❌';
      return '<tr onclick=\"viewReportDetail(\\''+r.session_id+'\\')\" style=\"cursor:pointer\" title=\"点击查看详情\">'+
        '<td>'+(r.created_at||'').substring(0,19)+'</td>'+
        '<td><span class=\"badge badge-blue\">'+escHtml(r.agent_id)+'</span></td>'+
        '<td><b>'+overall+'</b></td>'+
        '<td>'+r.total_scenarios+'</td>'+
        '<td>'+icon+'</td>'+
        '<td><button class=\"btn btn-sm btn-outline\">查看</button></td>'+
      '</tr>';
    }).join('');
  } catch(e) { console.error(e); }
}

async function viewReportDetail(sessionId) {
  var el = document.getElementById('reportDetailSection');
  if (!el) {
    // Create detail section after table
    var tbl = document.getElementById('reportTable').closest('table');
    el = document.createElement('div');
    el.id = 'reportDetailSection';
    el.style.cssText = 'margin-top:16px';
    tbl.parentNode.insertBefore(el, tbl.nextSibling);
  }
  el.innerHTML = '<div class=\"cal-loading\"><div class=\"cal-spinner\"></div><span>加载报告详情...</span></div>';
  el.scrollIntoView({behavior:'smooth'});

  try {
    // Fetch full session detail from dashboard API
    var r = await fetch(API+'/api/dashboard/sessions?page_size=100');
    var sessions = await r.json();
    var session = (sessions.items||[]).find(function(s){return s.session_id===sessionId;});

    // Also try to get the report file
    var reportName = 'report_'+(session?.started_at||'').replace(/[:-]/g,'').substring(0,15);
    var fileR = await fetch('/test/api/reports/files');
    var filesData = await fileR.json();

    // Find matching report file
    var reportFile = null;
    var matchingFiles = (filesData.items||[]).filter(function(f){return f.name.includes(sessionId.substring(0,8))||f.name.includes(reportName.substring(0,8));});
    if (matchingFiles.length > 0) {
      var rName = matchingFiles[0].name;
      try {
        var fileDetail = await fetch('/test/api/reports/file/'+rName);
        if (fileDetail.ok) reportFile = await fileDetail.json();
      } catch(e) {}
    }

    renderReportDetail(session, reportFile, el);
  } catch(e) {
    el.innerHTML = '<div class=\"card\" style=\"padding:20px;text-align:center;color:var(--red)\">加载失败: '+escHtml(e.message)+'</div>';
  }
}

function renderReportDetail(session, data, el) {
  if (!data && !session) { el.innerHTML = '<div class=\"card\" style=\"padding:20px;text-align:center;color:var(--muted)\">报告数据不可用</div>'; return; }

  var summary = data?.summary || {};
  var details = data?.details || [];
  var avgScores = summary.avg_scores || {};

  var dims = ['correctness','relevancy','completeness','guidance','followup_quality','boundary_compliance','turn_consistency','knowledge_scaffolding','overhelping'];
  var dimLabels = {correctness:'事实正确性',relevancy:'答案相关性',completeness:'内容完整性',guidance:'教学引导力',followup_quality:'追问响应质量',boundary_compliance:'边界合规性',turn_consistency:'跨轮一致性',knowledge_scaffolding:'知识递进性',overhelping:'过度帮助'};

  var dimRows = dims.map(function(dim){
    var v = avgScores[dim]||0;
    var barW = Math.round(v*20);
    var color = v>=4?'var(--green)':v>=3?'var(--sky)':v>=2?'var(--yellow)':'var(--red)';
    return '<tr><td style=\"font-weight:600\">'+dimLabels[dim]+'</td><td><b style=\"color:'+color+'\">'+(v?Number(v).toFixed(1):'-')+'</b></td><td><div style=\"background:var(--track);border-radius:4px;height:8px;width:100%\"><div style=\"background:'+color+';height:100%;width:'+barW+'%;border-radius:4px\"></div></div></td></tr>';
  }).join('');

  var scenarioCards = details.map(function(sc,i){
    var q = (sc.question_data||sc.question||{});
    var s = sc.score||sc.scores||{};
    var conv = sc.full_conversation||'';
    var questionText = typeof q==='string'?q:(q.question||'');
    var goldenText = typeof q==='string'?null:(q.golden_answer||'');
    return '<div class=\"card\" style=\"margin-bottom:8px;padding:12px\">'+
      '<div style=\"font-weight:700;font-size:13px;margin-bottom:6px\">场景 '+(i+1)+': '+escHtml(questionText.substring(0,100))+'</div>'+
      (goldenText?'<div style=\"font-size:11px;color:var(--muted);margin-bottom:4px\">黄金答案: '+escHtml(goldenText.substring(0,150))+'</div>':'')+
      '<div style=\"font-size:11px;color:var(--dim);max-height:100px;overflow-y:auto;white-space:pre-wrap\">'+escHtml(conv.substring(0,500))+'</div>'+
      '<div style=\"display:flex;gap:8px;flex-wrap:wrap;margin-top:6px\">'+
        dims.map(function(dim){var v=s[dim];if(v==null)return'';return '<span style=\"font-size:10px;padding:2px 6px;border-radius:4px;background:var(--surface-2)\">'+dimLabels[dim]+': <b>'+(typeof v==='number'?v.toFixed(1):v)+'</b></span>';}).join('')+
      '</div>'+
    '</div>';
  }).join('');

  var overall = avgScores.overall||0;
  var overallColor = overall>=4?'var(--green)':overall>=3?'var(--sky)':overall>=2?'var(--yellow)':'var(--red)';

  el.innerHTML =
  '<div class=\"card\" style=\"padding:0;overflow:hidden\">'+
    // Header
    '<div style=\"background:var(--grad-primary);color:#fff;padding:20px 24px\">'+
      '<div style=\"display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px\">'+
        '<div>'+
          '<div style=\"font-size:11px;opacity:.8;text-transform:uppercase;letter-spacing:1px\">AI Agent Evaluation Report</div>'+
          '<h2 style=\"font-size:20px;margin:4px 0;color:#fff\">评测报告</h2>'+
          '<div style=\"font-size:12px;opacity:.7\">'+(data?.timestamp||session?.started_at||'')+' · Agent: '+escHtml(session?.agent_id||'')+' · '+details.length+' 个场景</div>'+
        '</div>'+
        '<div style=\"text-align:center\">'+
          '<div style=\"font-size:48px;font-weight:800;line-height:1;color:#fff\">'+(overall?Number(overall).toFixed(1):'-')+'</div>'+
          '<div style=\"font-size:12px;opacity:.7\">综合评分 / 5.0</div>'+
        '</div>'+
      '</div>'+
    '</div>'+
    // Dimension scores
    '<div style=\"padding:16px 24px\">'+
      '<h3 style=\"margin-bottom:10px;font-size:15px\">维度评分</h3>'+
      '<table style=\"margin-bottom:0\"><tbody>'+dimRows+'</tbody></table>'+
    '</div>'+
    // Scenarios
    '<div style=\"padding:0 24px 16px\">'+
      '<h3 style=\"margin-bottom:10px;font-size:15px\">场景详情 ('+details.length+')</h3>'+
      scenarioCards+
    '</div>'+
    // Footer
    '<div style=\"padding:12px 24px;border-top:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px\">'+
      '<div style=\"font-size:11px;color:var(--muted)\">报告由 AI Agent 评测平台自动生成 · 评分基于10维度LLM多Judge投票 · 置信度: L3三模型并行取中位数</div>'+
      '<div style=\"display:flex;gap:8px\">'+
        '<button class=\"btn btn-sm btn-outline\" onclick=\"window.print()\">打印 / 导出PDF</button>'+
        '<button class=\"btn btn-sm btn-outline\" onclick=\"this.closest(\\'#reportDetailSection\\').innerHTML=\\'\\'\">关闭</button>'+
      '</div>'+
    '</div>'+
  '</div>';
}'''

# Apply the replacement
if old_load in html:
    html = html.replace(old_load, new_load)
    print('2. Frontend: loadReports + viewReportDetail + renderReportDetail added')
else:
    print('2. WARNING: old loadReports not found')

# Add print CSS for PDF
print_css = '''
/* Print styles for PDF export */
@media print {
  .nav, .header, #reportDetailSection button, .page-header, .controls { display: none !important; }
  body { background: #fff !important; color: #000 !important; }
  .card { box-shadow: none !important; border: 1px solid #ccc !important; break-inside: avoid; }
  table { border-collapse: collapse; } td, th { border: 1px solid #ccc; padding: 4px 8px; }
}
'''

style_end = html.find('</style>')
if style_end > 0:
    html = html[:style_end] + print_css + '\n' + html[style_end:]
    print('3. Print CSS added for PDF export')

with open('frontend/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('DONE - Reports system rebuilt')
