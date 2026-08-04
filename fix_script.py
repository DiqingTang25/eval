import re

with open("/opt/agent_eval/index.html", "r") as f:
    html = f.read()

changes = 0

# 1. Remove v3.4 from all occurrences
for old in [
    "AI Agent 评测平台 v3.4",
    "AI Agent Evaluation Platform v3.4",
    "🤖 AI Agent 评测平台 v3.4",
    "🤖 AI Agent Evaluation Platform v3.4",
]:
    if old in html:
        new = old.replace(" v3.4", "")
        html = html.replace(old, new)
        changes += 1
        print(f"✓ Removed: {old}")

# 2. Fix agent dropdown (home page)
old_select = '<select id="agentSelect"><option value="platform" selected data-i18n="opt_platform">HiAgent API测试</option><option value="web_test" data-i18n="opt_web_test">网站测试 (Playwright)</option></select>'
new_select = '''<select id="agentSelect">
      <option value="hi_phase1">Phase 1 — 国产AI技术基础</option>
      <option value="hi_phase2">Phase 2 — 新型硬件设计</option>
      <option value="hi_phase3_4">Phase 3&4 — 环境感知与触觉反馈</option>
      <option value="hi_phase5" selected>Phase 5 — 具身智能控制</option>
      <option value="platform">实训教学平台 (http://124.174.108.70)</option>
    </select>'''
if old_select in html:
    html = html.replace(old_select, new_select)
    changes += 1
    print("✓ Agent dropdown updated (home)")

# 3. Fix test runner dropdown
old_tr = '<select id="trAgent"><option value="platform" selected data-i18n="opt_platform">HiAgent API测试</option><option value="web_test" data-i18n="opt_web_test">网站测试 (Playwright)</option></select>'
new_tr = '''<select id="trAgent">
        <option value="hi_phase1">Phase 1 — 国产AI技术基础</option>
        <option value="hi_phase2">Phase 2 — 新型硬件设计</option>
        <option value="hi_phase3_4">Phase 3&4 — 环境感知与触觉反馈</option>
        <option value="hi_phase5" selected>Phase 5 — 具身智能控制</option>
        <option value="platform">实训教学平台 (http://124.174.108.70)</option>
      </select>'''
if old_tr in html:
    html = html.replace(old_tr, new_tr)
    changes += 1
    print("✓ Test runner dropdown updated")

# 4. Fix Web Eval GET -> POST
old_we = "const d = await get(`/api/web-eval/run?url=${encodeURIComponent(url)}`);"
new_we = "const d = await post(`/api/web-eval/run?url=${encodeURIComponent(url)}`, {});"
if old_we in html:
    html = html.replace(old_we, new_we)
    changes += 1
    print("✓ Web Eval: GET -> POST")

# 5. Add keyword highlighting function before searchKB
old_kw = "async function searchKB()"
new_kw = '''function highlightKW(text, query) {
  if (!query || !text) return escHtml(text);
  const words = query.split(/\\s+/).filter(w => w.length >= 1).map(w => w.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&'));
  if (!words.length) return escHtml(text);
  const escaped = escHtml(text);
  const regex = new RegExp("(" + words.join("|") + ")", "gi");
  return escaped.replace(regex, '<mark style="background:#fde68a;color:#92400e;padding:0 2px;border-radius:2px">$1</mark>');
}

async function searchKB()'''
if old_kw in html:
    html = html.replace(old_kw, new_kw)
    changes += 1
    print("✓ Keyword highlighting added")

# 6. Fix KB search result count display
old_count = '${t("kb_results_fmt", data.total, data.errors)}'
new_count = '🔍 找到 <b style="color:var(--sky)">${data.total}</b> 条结果，显示前 <b>${Math.min(data.results.length, 10)}</b> 条 ${data.errors?.length ? "· ⚠️"+data.errors.join(", ") : "· ✅ 全部 Phase 连通"}'
html = html.replace(old_count, new_count)
changes += 1
print("✓ KB result count fixed")

# 7. Add keyword highlighting to KB search results content
old_content = r"${escHtml((r.content||'').substring(0,600))}"
new_content = r"${highlightKW((r.content||'').substring(0,600), q)}"
if old_content in html:
    html = html.replace(old_content, new_content)
    changes += 1
    print("✓ KB content highlighting added")

# 8. Add highlighting to source too
old_source_block = '<div style="font-size:10px;color:var(--dim);margin-top:4px">📄 ${escHtml(r.source)}</div>'
new_source_block = '<div style="font-size:10px;color:var(--dim);margin-top:4px">📄 ${highlightKW(r.source.substring(0,120), q)}</div>'
if old_source_block in html:
    html = html.replace(old_source_block, new_source_block)
    changes += 1
    print("✓ KB source highlighting added")

# 9. Fix KB info text - add docs count instead of static 20
old_kb_info = '显示 <b>${Math.min(data.results.length, 10)}</b>'
# Already done above

# 10. Add help modal HTML at end of body
help_html = '''
<!-- HELP MODAL -->
<div id="helpModal" style="display:none;position:fixed;inset:0;z-index:100;background:rgba(0,0,0,.5);align-items:center;justify-content:center">
<div style="background:var(--surface);border-radius:var(--radius);max-width:700px;max-height:80vh;overflow-y:auto;padding:24px;margin:20px;box-shadow:var(--shadow-lg)">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
<h3 style="margin:0">📖 使用说明</h3>
<button class="btn btn-outline btn-sm" onclick="document.getElementById(\'helpModal\').style.display=\'none\'">✕ 关闭</button>
</div>
<div style="font-size:13px;line-height:1.8;color:var(--text)">
<p><b>AI Agent 评测平台</b> — 对AI教学Agent进行10维度自动化评测，支持多模型Judge投票，结果持久化到MySQL。</p>
<p style="margin-top:12px"><b>快速开始：</b></p>
<ol style="padding-left:20px;margin:8px 0">
<li>在首页下拉框选择被测Agent（Phase 1-5 对应5个HiAgent课程智能体）</li>
<li>设置评测场景数量（1-10），点击"开始测评"</li>
<li>实时观察右侧评测过程日志和维度评分</li>
<li>评测完成后前往"报告"页查看详细报告</li>
</ol>
<p style="margin-top:12px"><b>功能导航：</b></p>
<ul style="padding-left:20px;margin:8px 0">
<li><b>📊 首页</b> — 评测仪表盘，一键启动评测</li>
<li><b>🧪 测试运行</b> — 详细测试配置 + 实时事件日志</li>
<li><b>📋 报告</b> — 历次评测结果列表和详情</li>
<li><b>🌐 网页评测</b> — 对目标网页做全维度可用性检测</li>
<li><b>📚 知识库</b> — 搜索火山引擎5个Phase课程知识库</li>
<li><b>🎯 人类校准</b> — 人工标注对抗性QA，校准LLM Judge可信度</li>
</ul>
<p style="margin-top:12px"><b>被测Agent：</b></p>
<ul style="padding-left:20px;margin:8px 0">
<li>Phase 1 — 国产AI技术基础（HiAgent API @ aiagent.xjtlu.edu.cn）</li>
<li>Phase 2 — 新型硬件设计（HiAgent API）</li>
<li>Phase 3&4 — 环境感知与触觉反馈（HiAgent API）</li>
<li>Phase 5 — 具身智能控制（HiAgent API）</li>
<li>实训教学平台 — http://124.174.108.70（REST API直连）</li>
</ul>
<p style="margin-top:12px"><b>评分维度（10维，1-5分制）：</b>正确性、相关性、完整性、引导力、追问质量、边界合规、跨轮一致、知识递进、过度帮助、公平性</p>
<p style="margin-top:12px"><b>技术架构：</b>FastAPI + MySQL + Chart.js + WebSocket实时推送</p>
<p style="margin-top:12px;color:var(--muted);font-size:11px">📋 本文档基于实际项目代码生成，所有Agent、API端点、维度名称均与系统实现一致。</p>
</div>
</div>
</div>
'''
html = html.replace('</body>', help_html + '\n</body>')

# 11. Add help button to header
old_header_right = '<div class="header-right">'
new_header_right = '<div class="header-right">\n    <button class="lang-toggle" onclick="document.getElementById(\'helpModal\').style.display=\'flex\'" title="帮助">📖</button>'
html = html.replace(old_header_right, new_header_right)
changes += 1
print("✓ Help modal added")

with open("/opt/agent_eval/index.html", "w") as f:
    f.write(html)

print(f"\n✅ Total changes: {changes}, Lines: {len(html.split(chr(10)))}")
