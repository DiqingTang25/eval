#!/usr/bin/env python3
"""Fix reports page - add clickable detail view"""
import re

with open("/opt/agent_eval/index.html", "r") as f:
    html = f.read()

changes = 0

# 1. Replace old loadReports with clickable version
old_fn = """async function loadReports() {
  try {
    const d = await get('/api/dashboard/sessions?page_size=20');
    const tbody = document.getElementById('reportTable');
    if (!d.items || !d.items.length) { if(tbody) tbody.innerHTML = '<tr><td colspan=\"5\" class=\"qa-empty\">暂无报告。完成一次评测后在此查看。</td></tr>'; return; }
    if (tbody) {
      tbody.innerHTML = d.items.map(r => '<tr>
        <td>'+(r.created_at||'').substring(0,19)+'</td>
        <td><span class=\"badge badge-blue\">'+escHtml(r.agent_id)+'</span></td>
        <td>'+(r.overall_score != null ? r.overall_score.toFixed(2) : '-')+'</td>
        <td>'+r.total_scenarios+'场景</td>
        <td><span class=\"badge badge-'+(r.status==='success'?'green':'red')+'\">'+tStatus(r.status)+'</span></td>
      </tr>').join('');
    }
  } catch(e) { console.error('Reports:', e); }
}"""

# New version with clickable rows
new_fn = """async function loadReports() {
  document.getElementById('reportDetailView').style.display = 'none';
  document.getElementById('reportListView').style.display = '';
  try {
    const d = await get('/api/dashboard/sessions?page_size=100');
    const tbody = document.getElementById('reportTable');
    if (!d.items || !d.items.length) {
      if(tbody) tbody.innerHTML = '<tr><td colspan=\"5\" class=\"qa-empty\">暂无报告。完成一次评测后在此查看。</td></tr>';
      return;
    }
    if (tbody) {
      tbody.innerHTML = d.items.map(function(r) {
        return '<tr onclick=\"viewReportDetail(\\''+escHtml(r.session_id||r.id)+'\\')\" style=\"cursor:pointer\">'+
        '<td>'+(r.created_at||'').substring(0,19)+'</td>'+
        '<td><span class=\"badge badge-blue\">'+escHtml(r.agent_id)+'</span></td>'+
        '<td><b style=\"color:var(--sky)\">'+(r.overall_score != null ? r.overall_score.toFixed(2) : '-')+'</b></td>'+
        '<td>'+r.total_scenarios+'场景</td>'+
        '<td><span class=\"badge badge-'+(r.status==='success'?'green':'red')+'\">'+tStatus(r.status)+'</span></td>'+
        '</tr>';
      }).join('');
    }
  } catch(e) { console.error('Reports:', e); }
}

async function viewReportDetail(sessionId) {
  document.getElementById('reportListView').style.display = 'none';
  var detail = document.getElementById('reportDetailView');
  detail.style.display = '';
  detail.innerHTML = '<div class=\"qa-empty\"><div style=\"width:24px;height:24px;border:2px solid var(--line);border-top-color:var(--sky);border-radius:50%;animation:spin .6s linear infinite;margin:20px auto\"></div><p style=\"color:var(--muted);margin-top:8px\">加载报告详情...</p></div>';
  try {
    var s = await get('/api/tests/sessions/' + encodeURIComponent(sessionId));
    if (!s || s.detail) {
      detail.innerHTML = '<div class=\"qa-empty\"><button class=\"btn btn-outline btn-sm\" onclick=\"loadReports()\" style=\"margin-bottom:12px\">← 返回列表</button><br>报告不存在: '+escHtml(s?s.detail:'')+'</div>';
      return;
    }
    renderReportDetail(s, detail);
  } catch(e) {
    detail.innerHTML = '<div class=\"qa-empty\">❌ '+escHtml(e.message)+'<br><button class=\"btn btn-outline btn-sm\" style=\"margin-top:12px\" onclick=\"loadReports()\">← 返回列表</button></div>';
  }
}

function renderReportDetail(s, detail) {
  var dims = ['correctness','relevancy','completeness','guidance','followup_quality','boundary_compliance','turn_consistency','knowledge_scaffolding','overhelping','fairness_bias'];
  var labels = ['正确性','相关性','完整性','引导力','追问质量','边界合规','跨轮一致','知识递进','过度帮助','公平性'];
  var scenarios = s.scenarios || [];
  var scoredScenarios = scenarios.filter(function(sc) { return sc.score; });
  var aggScores = {};
  dims.forEach(function(d) {
    var vals = scoredScenarios.map(function(sc) { return sc.score ? sc.score[d] : null; }).filter(function(v) { return v != null; });
    aggScores[d] = vals.length ? +(vals.reduce(function(a,b){return a+b;},0)/vals.length).toFixed(2) : 0;
  });
  var overallAvg = scoredScenarios.length ? +(scoredScenarios.reduce(function(a,sc){return a+(sc.score?sc.score.overall||0:0);},0)/scoredScenarios.length).toFixed(2) : 0;
  var totalTokens = 0, totalCost = 0;
  scenarios.forEach(function(sc) { (sc.turns || []).forEach(function(t) { totalTokens += (t.total_tokens || 0); totalCost += (t.cost_estimate || 0); }); });
  var dark = document.documentElement.getAttribute('data-theme') === 'dark';
  var scoreColor = overallAvg >= 4 ? 'var(--green)' : overallAvg >= 3 ? 'var(--yellow)' : 'var(--red)';
  var bg = dark ? '#1c283d' : '#fff';
  var text = dark ? '#e5edf8' : '#1e293b';
  var muted = dark ? '#94a3b8' : '#64748b';
  var line = dark ? '#2b3a52' : '#dce3eb';
  var surf2 = dark ? 'rgba(13,20,36,.6)' : '#f8fafc';
  var startTime = (s.started_at||s.created_at||'').substring(0,19);
  var endTime = (s.finished_at||'').substring(0,19);
  var turnCount = scenarios.reduce(function(a,sc){return a+(sc.turns?sc.turns.length:0);},0);

  var h = '<div style=\"margin-bottom:16px\"><button class=\"btn btn-outline btn-sm\" onclick=\"loadReports()\">← 返回报告列表</button></div>';
  h += '<div class=\"card\" style=\"padding:20px;margin-bottom:16px\">';
  h += '<div style=\"display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px\">';
  h += '<div><div class=\"eyebrow\" style=\"margin-bottom:4px\">评测报告 #'+escHtml((s.session_id||'').substring(0,8))+'</div>';
  h += '<h2 style=\"font-size:20px;margin:0 0 4px\">Agent: '+escHtml(s.agent_id)+' · '+escHtml(s.profile||'standard')+'</h2>';
  h += '<div style=\"font-size:12px;color:'+muted+'\">'+startTime+(endTime?' → '+endTime:'')+' · '+scenarios.length+'场景 · '+turnCount+'轮对话</div></div>';
  h += '<div style=\"text-align:center;padding:12px 20px;background:'+surf2+';border-radius:12px;border:1px solid '+line+'\">';
  h += '<div style=\"font-size:10px;color:'+muted+';text-transform:uppercase\">综合评分</div>';
  h += '<div style=\"font-size:42px;font-weight:800;color:'+scoreColor+';line-height:1\">'+overallAvg+'</div>';
  h += '<div style=\"font-size:10px;color:'+muted+'\">/ 5.0</div></div></div></div>';

  // Dimension bars
  h += '<div class=\"card\" style=\"padding:16px;margin-bottom:16px\"><h3 style=\"font-size:13px;margin-bottom:12px\">📊 维度评分（10维 · 多Judge投票）</h3>';
  h += '<div style=\"display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px\">';
  dims.forEach(function(d, i) {
    var v = aggScores[d], pct = v/5*100, bar = v >= 4 ? 'var(--green)' : v >= 3 ? 'var(--yellow)' : 'var(--red)';
    h += '<div style=\"padding:8px 12px;background:'+surf2+';border-radius:8px;border:1px solid '+line+'\">';
    h += '<div style=\"display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px\"><span style=\"color:'+muted+'\">'+labels[i]+'</span><b style=\"color:'+bar+'\">'+v.toFixed(1)+'</b></div>';
    h += '<div style=\"height:4px;background:var(--track);border-radius:2px;overflow:hidden\"><div style=\"height:100%;width:'+pct+'%;background:'+bar+';border-radius:2px\"></div></div></div>';
  });
  h += '</div></div>';

  // Meta bar
  h += '<div class=\"card\" style=\"padding:12px 16px;margin-bottom:16px;font-size:12px;color:'+muted+'\">💬 总对话轮次: <b style=\"color:'+text+'\">'+turnCount+'</b> · 💰 Token估算: <b style=\"color:'+text+'\">'+totalTokens.toLocaleString()+'</b> · 💲 成本: <b style=\"color:'+text+'\">$'+totalCost.toFixed(4)+'</b> · 已评分场景: <b style=\"color:'+text+'\">'+scoredScenarios.length+'/'+scenarios.length+'</b></div>';

  // Per-scenario
  scenarios.forEach(function(sc, si) {
    var score = sc.score, turns = sc.turns || [];
    h += '<div class=\"card\" style=\"padding:16px;margin-bottom:12px\">';
    h += '<div style=\"display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:8px\">';
    h += '<div><span class=\"badge badge-blue\">场景 '+(sc.scenario_index||si+1)+'</span>';
    h += '<span class=\"badge badge-'+(sc.status==='success'?'green':'yellow')+'\" style=\"margin-left:4px\">'+(sc.status||'unknown')+'</span>';
    if (score) h += '<span style=\"font-size:16px;font-weight:800;color:'+scoreColor+';margin-left:8px\">'+score.overall.toFixed(2)+'</span><span style=\"font-size:11px;color:'+muted+'\">/5</span>';
    h += '</div>';
    if (sc.error) h += '<span style=\"font-size:11px;color:var(--red)\">⚠ '+escHtml(sc.error.substring(0,100))+'</span>';
    h += '</div>';

    if (turns.length) {
      h += '<div style=\"background:'+surf2+';border-radius:10px;padding:12px;border:1px solid '+line+'\">';
      turns.forEach(function(t, ti) {
        var qText = (t.question||'').substring(0,500);
        var rText = (t.response_text||'').substring(0,800);
        h += '<div style=\"margin-bottom:'+(ti<turns.length-1?'14px':'0')+'\">';
        h += '<div style=\"display:flex;gap:8px;align-items:flex-start;margin-bottom:6px\">';
        h += '<span style=\"font-size:10px;font-weight:700;color:var(--sky);min-width:36px;padding-top:2px\">T'+(t.turn||ti+1)+'</span>';
        h += '<div style=\"flex:1\"><div style=\"background:'+bg+';border:1px solid '+line+';border-radius:8px;padding:8px 12px;font-size:12px;line-height:1.5;color:'+text+'\">';
        h += '<div style=\"font-size:9px;color:var(--sky);text-transform:uppercase;margin-bottom:2px\">👤 用户提问</div>';
        h += escHtml(qText)+(qText.length>=500?' …(截断)':'')+'</div></div></div>';
        h += '<div style=\"display:flex;gap:8px;align-items:flex-start\">';
        h += '<span style=\"font-size:10px;font-weight:700;color:var(--green);min-width:36px;padding-top:2px\">↩</span>';
        h += '<div style=\"flex:1\"><div style=\"background:'+bg+';border:1px solid '+line+';border-left:3px solid var(--sky);border-radius:8px;padding:8px 12px;font-size:12px;line-height:1.5;color:'+text+'\">';
        h += '<div style=\"font-size:9px;color:var(--green);text-transform:uppercase;margin-bottom:2px\">🤖 Agent回复 · '+(t.response_status||'ok')+' · '+(t.response_duration||0).toFixed(1)+'s';
        if (t.model_used) h += ' · '+escHtml(t.model_used);
        h += '</div>'+escHtml(rText)+(rText.length>=800?' …(截断)':'')+'</div></div></div></div>';
      });
      h += '</div>';
    }
    // Score tags
    if (score) {
      h += '<div style=\"margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;font-size:10px\">';
      dims.forEach(function(d) {
        var v = score[d];
        if (v != null) {
          var c = v >= 4 ? 'var(--green)' : v >= 3 ? 'var(--yellow)' : 'var(--red)';
          h += '<span style=\"padding:2px 6px;background:'+surf2+';border-radius:4px;border:1px solid '+line+'\">'+labels[dims.indexOf(d)]+': <b style=\"color:'+c+'\">'+v.toFixed(1)+'</b></span>';
        }
      });
      if (score.n_judges) h += '<span style=\"padding:2px 6px;background:'+surf2+';border-radius:4px;border:1px solid '+line+'\">法官数: <b>'+score.n_judges+'</b></span>';
      if (score.judge_variance != null) h += '<span style=\"padding:2px 6px;background:'+surf2+';border-radius:4px;border:1px solid '+line+'\">方差: <b>'+score.judge_variance.toFixed(3)+'</b></span>';
      if (score.needs_human_review) h += '<span style=\"padding:2px 6px;background:#fef3c7;border-radius:4px;border:1px solid #fcd34d;color:#92400e\">⚠ 需人工复核</span>';
      h += '</div>';
    }
    h += '</div>';
  });

  h += '<div style=\"text-align:center;padding:20px;font-size:11px;color:'+muted+'\">📋 报告由AI Agent评测平台自动生成 · 对话内容来自Agent真实回复 · 评分来自多模型LLM Judge投票 · '+new Date().toISOString().substring(0,10)+'</div>';
  detail.innerHTML = h;
  detail.scrollIntoView({behavior:'smooth',block:'start'});
}

async function deleteReport(sessionId) {
  if (!confirm('确定删除这份报告？此操作不可撤销。')) return;
  try {
    await fetch(API + '/api/tests/sessions/' + encodeURIComponent(sessionId), {method:'DELETE'});
    loadReports();
  } catch(e) { alert('删除失败: '+e.message); }
}

async function deleteAllReports() {
  if (!confirm('⚠️ 确定删除全部历史报告及关联的对话记录、评分数据？此操作不可撤销。')) return;
  try {
    var r = await fetch(API + '/api/tests/sessions', {method:'DELETE'});
    var d = await r.json();
    alert(d.message || '已删除');
    loadReports();
  } catch(e) { alert('删除失败: '+e.message); }
}"""

if old_fn in html:
    html = html.replace(old_fn, new_fn)
    changes += 1
    print("✓ loadReports + viewReportDetail + deleteAll added")
else:
    print("⚠ old loadReports not found - trying partial match")
    # Try finding just the function signature
    idx = html.find("async function loadReports()")
    if idx > 0:
        # Find the closing brace after this function
        brace_count = 0
        end_idx = idx
        started = False
        for i in range(idx, len(html)):
            if html[i] == '{':
                brace_count += 1
                started = True
            elif html[i] == '}':
                brace_count -= 1
                if started and brace_count == 0:
                    end_idx = i + 1
                    break
        if end_idx > idx:
            old_func = html[idx:end_idx]
            # Simple approach: replace just the function body
            html = html[:idx] + new_fn + html[end_idx:]
            changes += 1
            print("✓ loadReports replaced via brace matching")

# Add reportDetailView div to reports page
old_report_end = '</tbody>\n  </table>\n</div>'
if old_report_end in html:
    new_report_end = '</tbody>\n  </table>\n</div>\n  <div id="reportDetailView" style="display:none"></div>'
    html = html.replace(old_report_end, new_report_end)
    changes += 1
    print("✓ reportDetailView div added")

# Add CSS for spin animation
if "@keyframes spin" not in html:
    css_insert = "@keyframes spin{to{transform:rotate(360deg)}}"
    # Insert before closing style tag
    html = html.replace("</style>", css_insert + "\n</style>")
    changes += 1
    print("✓ spin animation CSS added")

with open("/opt/agent_eval/index.html", "w") as f:
    f.write(html)

print(f"\nTotal changes: {changes}")
print(f"File size: {len(html)} chars, approx {len(html.split(chr(10)))} lines")
