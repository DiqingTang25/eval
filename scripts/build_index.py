"""Build index.html with inline CSS + full dashboard functionality."""
import os
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

css = open('frontend/css/style.css', 'r', encoding='utf-8').read()

html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AI Agent 评测平台</title>
<script>try{document.documentElement.setAttribute('data-theme',localStorage.getItem('theme')||'light')}catch(e){}</script>
<style>
''' + css + '''</style>
</head>
<body>

<div class="header">
  <h1>AI Agent 评测平台 v3.6</h1>
  <div class="header-right">
    <button class="lang-toggle" onclick="toggleTheme()">🌙</button>
    <button class="lang-toggle" onclick="toggleLang()">EN</button>
    <span id="sysStatus"><span class="live-dot"></span>在线</span>
  </div>
</div>

<nav class="nav">
  <a class="active" data-page="dashboard" onclick="showPage('dashboard')">📊 首页</a>
  <a data-page="platform-health" onclick="showPage('platform-health')">🔌 平台监控</a>
  <a data-page="test_runner" onclick="showPage('test_runner')">🧪 测试运行</a>
  <a data-page="reports" onclick="showPage('reports')">📋 报告</a>
  <a data-page="calibration" onclick="showPage('calibration')">🎯 校准</a>
</nav>

<div id="page-dashboard" class="page active">
  <div class="stat-grid">
    <div class="card"><h3>📊 历史测试</h3><div class="val" id="totalTests">-</div></div>
    <div class="card"><h3>⭐ 平均综合分</h3><div class="val" id="avgScore">-</div></div>
    <div class="card"><h3>✅ 已审核QA</h3><div class="val" id="qaApproved">-</div></div>
    <div class="card"><h3>🕐 待审</h3><div class="val" id="qaPending">-</div></div>
  </div>
  <div class="controls">
    <select id="agentSelect"></select>
    <select id="evalProfile" style="width:auto" onchange="onProfileChange()">
      <option value="patrol">🔍 巡检 (~5min)</option>
      <option value="full" selected>📋 全平台 (~18min)</option>
      <option value="deep">🔬 深度 (~30min)</option>
      <option value="custom">⚙️ 自定义</option>
    </select>
    <span id="customOpts" style="display:none;gap:4px">
      <input id="numQuestions" type="number" value="3" min="1" max="20" style="width:55px">
      <span>题×</span><input id="maxTurns" type="number" value="3" min="1" max="10" style="width:55px"><span>轮</span>
    </span>
    <button class="btn btn-primary" onclick="startEval()">▶ 开始测评</button>
    <button class="btn btn-outline btn-sm" onclick="loadDashboard()">🔄 刷新</button>
  </div>
  <div id="evalModeHint" style="font-size:11px;color:var(--dim);margin:4px 0">全平台: 22Days+Quiz+Phase5, ~18min</div>
  <div id="evalStatusBar" style="display:none;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin:8px 0;font-size:12px">
    <span id="wsIndicator" style="color:#dc2626">🔌 WS断开</span> |
    <span>⏱️ <b id="evalElapsed">00:00</b></span> |
    <span>📍 <span id="evalStep">就绪</span></span>
  </div>
  <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
  <div id="liveEvalPanel" style="display:none">
    <div class="live-eval-header"><h3>🔍 实时评测</h3><button class="btn btn-outline btn-sm" onclick="document.getElementById('liveEvalBody').innerHTML=''">清空</button></div>
    <div class="live-eval-body" id="liveEvalBody"><div class="qa-empty">点击"开始测评"查看过程</div></div>
  </div>
  <div class="score-mini-grid" id="scoreMiniGrid"></div>
  <div class="two-col">
    <div class="card"><h3>📈 得分趋势</h3><canvas id="trendChart"></canvas></div>
    <div class="card"><h3>🎯 维度分布</h3><canvas id="radarChart"></canvas></div>
  </div>
  <div class="card"><h3>📋 最近报告</h3><div id="recentReports">加载中...</div></div>
</div>

<div id="page-platform-health" class="page"><div style="text-align:center;padding:60px;color:var(--muted)">📊 加载中...</div></div>
<div id="page-test_runner" class="page"><div style="text-align:center;padding:60px;color:var(--muted)">📊 加载中...</div></div>
<div id="page-reports" class="page"><div style="text-align:center;padding:60px;color:var(--muted)">📊 加载中...</div></div>
<div id="page-calibration" class="page"><div style="text-align:center;padding:60px;color:var(--muted)">📊 加载中...</div></div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="/js/i18n.js"></script>
<script>
var API=(function(){try{var p=location.pathname;return(p.startsWith("/test/")||p==="/test")?"/test":""}catch(e){return""}})();
function escHtml(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}
async function get(p){var r=await fetch(API+p);return r.json()}
async function post(p,b){var r=await fetch(API+p,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});return r.json()}
function toggleTheme(){var e=document.documentElement,t=e.getAttribute("data-theme")==="dark"?"light":"dark";e.setAttribute("data-theme",t);localStorage.setItem("theme",t)}
function toggleLang(){var c=localStorage.getItem("lang")||"zh",n=c==="zh"?"en":"zh";localStorage.setItem("lang",n);if(window.setLang)window.setLang(n)}
function onProfileChange(){var v=document.getElementById("evalProfile").value;var co=document.getElementById("customOpts");co.style.display=v==="custom"?"inline-flex":"none";var hints={patrol:"巡检: 每Phase抽1Day, ~5min",full:"全平台: 22Days+Quiz, ~18min",deep:"深度: 双模式+逐Step, ~30min",custom:"自定义题目数x轮数"};document.getElementById("evalModeHint").textContent=hints[v]||""}

async function loadDashboard(){
  try{
    var d=await get("/api/dashboard/summary");
    var el=function(id){return document.getElementById(id)};
    if(el("totalTests"))el("totalTests").textContent=d.total_tests||0;
    if(el("avgScore"))el("avgScore").textContent=(d.avg_overall||0).toFixed(2);
    if(el("qaApproved"))el("qaApproved").textContent=d.qa_approved||0;
    if(el("qaPending"))el("qaPending").textContent=d.qa_pending||0;
    var reps=await get("/api/dashboard/sessions?page_size=5"),rl=el("recentReports");
    if(rl&&reps.items&&reps.items.length)rl.innerHTML=reps.items.map(function(r){return'<span class="badge badge-blue" style="margin:2px">'+escHtml(r.agent_id)+" - "+(r.status||"?")+"</span>"}).join(" ");
    else if(rl)rl.innerHTML='<span style="color:var(--dim)">暂无报告</span>';
    renderCharts(d)
  }catch(e){console.error("Dashboard:",e)}
}

async function loadAgents(){
  try{var a=await get("/api/agents"),keys=Object.keys(a||{}).filter(function(k){return k==="platform"}),sel=document.getElementById("agentSelect");
  if(sel)sel.innerHTML=keys.length?keys.map(function(k){return'<option value="'+k+'">'+(a[k]&&a[k].name||k)+"</option>"}).join(""):'<option value="platform">实训教学平台</option>'}catch(e){}
}

var trendChartObj=null,radarChartObj=null;
function renderCharts(d){
  if(typeof Chart==="undefined")return;
  var dims=["correctness","relevancy","completeness","guidance","followup_quality","boundary_compliance","turn_consistency","knowledge_scaffolding"];
  var labels=window.getDimLabels?window.getDimLabels():["正确性","相关性","完整性","引导力","追问","边界","一致性","递进性"];
  var dark=document.documentElement.getAttribute("data-theme")==="dark",grid=dark?"rgba(148,163,184,.16)":"rgba(100,116,139,.14)",tick=dark?"#94a3b8":"#64748b",sky=dark?"#38bdf8":"#0ea5e9",fill=dark?"rgba(56,189,248,.14)":"rgba(14,165,233,.12)";
  Chart.defaults.color=tick;
  var tEl=document.getElementById("trendChart");
  if(tEl){var trend=(d.trend||[]).slice().reverse();if(trendChartObj)trendChartObj.destroy();
    trendChartObj=new Chart(tEl,{type:"line",data:{labels:trend.map(function(p,i){return p.ts?String(p.ts).replace("T"," ").substring(5,16):(i+1)}),datasets:[{data:trend.map(function(p){return p.score}),borderColor:sky,backgroundColor:fill,fill:true,tension:.35,borderWidth:2,pointRadius:3,pointBackgroundColor:sky}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{min:0,max:5,ticks:{stepSize:1},grid:{color:grid}},x:{grid:{color:grid}}}}})}
  var rEl=document.getElementById("radarChart");
  if(rEl){var latest=d.latest||{};if(radarChartObj)radarChartObj.destroy();
    radarChartObj=new Chart(rEl,{type:"radar",data:{labels:labels,datasets:[{data:dims.map(function(k){return latest[k]||0}),borderColor:sky,backgroundColor:fill,borderWidth:2,pointRadius:3,pointBackgroundColor:sky}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{r:{min:0,max:5,ticks:{stepSize:1,backdropColor:"transparent"},grid:{color:grid},pointLabels:{color:tick}}}}})}
}

async function startEval(){
  var profile=document.getElementById("evalProfile").value;
  var panel=document.getElementById("liveEvalPanel"),body=document.getElementById("liveEvalBody"),bar=document.getElementById("evalStatusBar");
  if(panel)panel.style.display="block";if(bar)bar.style.display="flex";
  if(body)body.innerHTML='<div class="qa-empty">启动中...</div>';
  var presets={patrol:{phases:[1,2,3,4,5],mode:"guided",include_quiz:true},full:{phases:[1,2,3,4,5],mode:"guided",include_quiz:true},deep:{phases:[1,2,3,4,5],mode:"both",include_quiz:true}};
  var params,endpoint;
  if(profile==="custom"){params={agent_id:"platform",num_questions:parseInt(document.getElementById("numQuestions").value)||3,max_turns:parseInt(document.getElementById("maxTurns").value)||3,profile:"custom"};endpoint="/api/tests/run"}
  else{params=presets[profile]||presets.full;endpoint="/api/tests/run-browser"}
  try{var data=await post(endpoint,params);if(data.status==="started"){if(body)body.innerHTML='<div class="qa-empty" style="color:#16a34a">已启动: '+data.session_id+"</div>"}else{if(body)body.innerHTML='<div class="qa-empty" style="color:#dc2626">失败: '+JSON.stringify(data)+"</div>"}}catch(e){if(body)body.innerHTML='<div class="qa-empty" style="color:#dc2626">错误: '+e.message+"</div>"}
}

var _pageMods={};
function showPage(name){
  document.querySelectorAll(".page").forEach(function(p){p.classList.remove("active")});
  document.querySelectorAll(".nav a").forEach(function(a){a.classList.remove("active")});
  var el=document.getElementById("page-"+name);if(el)el.classList.add("active");
  var nv=document.querySelector('.nav a[data-page="'+name+'"]');if(nv)nv.classList.add("active");
  var modMap={dashboard:"dashboard","platform-health":"platform-health",test_runner:"test_runner",reports:"reports",calibration:"calibration"};
  var modName=modMap[name];if(!modName)return;
  if(_pageMods[name]){var p=_pageMods[name];if(p.render)p.render();return}
  import("/js/pages/"+modName+".js").then(function(m){var p=m.default||m;_pageMods[name]=p;if(p.init)p.init();if(p.render)p.render()}).catch(function(e){console.warn("Page fail:",name,e)})
}

var _ws=null,_wsReconnect=0;
function connectWS(){
  try{var proto=location.protocol==="https:"?"wss":"ws";_ws=new WebSocket(proto+"://"+location.host+"/ws");
  _ws.onopen=function(){_wsReconnect=0;var el=document.getElementById("wsIndicator");if(el){el.innerHTML="WS已连接";el.style.color="#16a34a"}};
  _ws.onclose=function(){var el=document.getElementById("wsIndicator");if(el){el.innerHTML="WS断开";el.style.color="#dc2626"}var d=Math.min(30000,1000*Math.pow(2,_wsReconnect++));setTimeout(connectWS,d)};
  _ws.onmessage=function(e){try{var m=JSON.parse(e.data);if(m.type==="eval_event"){var event=m.event,data=m.data||{};if(event==="browser_log"){var body=document.getElementById("liveEvalBody");if(body){body.innerHTML+='<div style="font-size:11px;padding:2px 0;border-bottom:1px solid var(--line-soft)">'+escHtml(data.msg||"")+"</div>";body.scrollTop=body.scrollHeight}}if(event==="browser_done"){var body=document.getElementById("liveEvalBody");if(body){body.innerHTML+='<div style="color:#16a34a;padding:8px;font-weight:600">测评完成!</div>'}setTimeout(loadDashboard,2000)}}}catch(ex){}}
  }catch(ex){}
}

document.addEventListener("DOMContentLoaded",function(){loadDashboard();loadAgents();onProfileChange();setTimeout(connectWS,500)});
</script>
</body>
</html>'''

with open('frontend/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('Built:', len(html), 'bytes')
