/* ───────────────────────────────────────────
   AI Agent 评测平台 v3.6 — Frontend App
   Plain JS, no ES modules, no dynamic imports.
   Loaded via <script src="/test/js/app.js">
   ─────────────────────────────────────────── */
(function () {
  'use strict';

  var API = (function () {
    try { var p = location.pathname; return (p.startsWith('/test/') || p === '/test') ? '/test' : ''; }
    catch (e) { return ''; }
  })();

  var DIMS = ['correctness','relevancy','completeness','guidance','followup_quality','boundary_compliance','turn_consistency','knowledge_scaffolding','overhelping','fairness_bias'];

  function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
  function get(url) { return fetch(API + url).then(function(r){return r.json()}); }
  function post(url, body) { return fetch(API + url, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(function(r){return r.json()}); }
  function toast(msg, type) { type = type || 'info'; var c = document.getElementById('toastContainer'); if(!c) return; var t = document.createElement('div'); t.className = 'toast toast-'+type; t.textContent = msg; c.appendChild(t); setTimeout(function(){t.style.opacity='0';t.style.transition='opacity .3s';setTimeout(function(){t.remove()},300)},3000); }

  function showPage(name) {
    document.querySelectorAll('.page').forEach(function(p){p.classList.remove('active')});
    document.querySelectorAll('.nav a').forEach(function(a){a.classList.remove('active')});
    var el = document.getElementById('page-'+name); if(!el) return;
    el.classList.add('active');
    var nv = document.querySelector('.nav a[data-page="'+name+'"]'); if(nv) nv.classList.add('active');
    if(name === 'dashboard') { loadDashboard(); return; }
    if(name === 'platform-health') { phLoad(); return; }
    if(name === 'test-runner') { trLoad(); return; }
    if(name === 'reports') { reportsLoad(); return; }
    if(name === 'calibration') { calInit(); return; }
  }

  function toggleTheme() {
    var e = document.documentElement, th = e.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    e.setAttribute('data-theme', th); localStorage.setItem('theme', th);
  }

  function toggleLang() {
    var cur = localStorage.getItem('lang') || 'zh', next = cur === 'zh' ? 'en' : 'zh';
    localStorage.setItem('lang', next);
    if (window.setLang) window.setLang(next);
    document.getElementById('langToggle').textContent = next === 'zh' ? 'EN' : '中';
    // Refresh current page
    var active = document.querySelector('.page.active');
    if (active) showPage(active.id.replace('page-', ''));
  }

  // ═══════════════════ Dashboard ═══════════════════
  var trendChart = null, radarChart = null;

  function loadDashboard() {
    get('/api/dashboard/summary').then(function(d){
      var g = function(id){return document.getElementById(id)};
      g('totalTests').textContent = d.total_tests || 0;
      g('avgScore').textContent = (d.avg_overall || 0).toFixed(2);
      g('qaApproved').textContent = d.qa_approved || 0;
      g('qaPending').textContent = d.qa_pending || 0;
      renderCharts(d);
    }).catch(function(){});

    get('/api/dashboard/sessions?page_size=5').then(function(r){
      var el = document.getElementById('recentReports'); if(!el) return;
      if(r && r.items && r.items.length) el.innerHTML = r.items.map(function(x){return '<span class="badge badge-blue" style="margin:2px">'+escHtml(x.agent_id)+' - '+(x.status||'?')+'</span>'}).join('');
      else el.innerHTML = '<span class="text-muted">暂无报告</span>';
    }).catch(function(){});

    get('/api/agents').then(function(a){
      var sel = document.getElementById('agentSelect'); if(!sel) return;
      var keys = Object.keys(a||{}).filter(function(k){return k==='platform'});
      sel.innerHTML = keys.length ? keys.map(function(k){return '<option value="'+k+'">'+(a[k]&&a[k].name||k)+'</option>'}).join('') : '<option value="platform">实训教学平台</option>';
    }).catch(function(){});
  }

  function renderCharts(d) {
    if(typeof Chart==='undefined') return;
    var labels = DIMS.slice(0,8).map(function(k){return (window.t||function(x){return x})('dim_'+k)});
    var dark = document.documentElement.getAttribute('data-theme')==='dark';
    var grid = dark ? 'rgba(148,163,184,.16)' : 'rgba(100,116,139,.14)';
    var tick = dark ? '#94a3b8' : '#64748b';
    var sky = dark ? '#38bdf8' : '#0ea5e9';
    var fill = dark ? 'rgba(56,189,248,.14)' : 'rgba(14,165,233,.12)';
    Chart.defaults.color = tick;

    var tEl = document.getElementById('trendChart');
    if(tEl) {
      var trend = (d.trend||[]).slice().reverse();
      if(trendChart) trendChart.destroy();
      trendChart = new Chart(tEl, {type:'line',data:{labels:trend.map(function(p,i){return p.ts?String(p.ts).replace('T',' ').substring(5,16):(i+1)}),datasets:[{data:trend.map(function(p){return p.score}),borderColor:sky,backgroundColor:fill,fill:true,tension:.35,borderWidth:2,pointRadius:3,pointBackgroundColor:sky}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{min:0,max:5,ticks:{stepSize:1},grid:{color:grid}},x:{grid:{color:grid}}}}});
    }
    var rEl = document.getElementById('radarChart');
    if(rEl) {
      var latest = d.latest||{};
      if(radarChart) radarChart.destroy();
      radarChart = new Chart(rEl, {type:'radar',data:{labels:labels,datasets:[{data:DIMS.slice(0,8).map(function(k){return latest[k]||0}),borderColor:sky,backgroundColor:fill,borderWidth:2,pointRadius:3,pointBackgroundColor:sky}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{r:{min:0,max:5,ticks:{stepSize:1,backdropColor:'transparent'},grid:{color:grid},pointLabels:{color:tick}}}}});
    }
  }

  function onProfileChange() {
    var v = document.getElementById('evalProfile').value;
    document.getElementById('customOpts').style.display = v==='custom' ? 'inline-flex' : 'none';
    var hints = {patrol:'巡检: 每Phase抽1Day, ~5min', full:'全平台: 22Days+Quiz验证, ~18min', deep:'深度: 双模式+逐Step, ~30min', custom:'自定义: 自由设置题目数x轮数'};
    document.getElementById('evalModeHint').textContent = hints[v]||'';
  }

  function startEval() {
    var profile = document.getElementById('evalProfile').value;
    var panel = document.getElementById('liveEvalPanel'), body = document.getElementById('liveEvalBody'), bar = document.getElementById('evalStatusBar');
    if(panel) panel.style.display = 'block'; if(bar) bar.style.display = 'flex';
    if(body) body.innerHTML = '<div class="qa-empty">启动中...</div>';
    var presets = {patrol:{phases:[1,2,3,4,5],mode:'guided',include_quiz:true},full:{phases:[1,2,3,4,5],mode:'guided',include_quiz:true},deep:{phases:[1,2,3,4,5],mode:'both',include_quiz:true}};
    var params, endpoint;
    if(profile==='custom') {
      params = {agent_id:'platform',num_questions:parseInt(document.getElementById('numQuestions').value)||3,max_turns:parseInt(document.getElementById('maxTurns').value)||3,profile:'custom'};
      endpoint = '/api/tests/run';
    } else {
      params = presets[profile]||presets.full;
      endpoint = '/api/tests/run-browser';
    }
    post(endpoint, params).then(function(data){
      if(body) body.innerHTML = data.status==='started' ? '<div class="qa-empty" style="color:#16a34a">已启动: '+data.session_id+'</div>' : '<div class="qa-empty" style="color:#dc2626">失败: '+JSON.stringify(data)+'</div>';
    }).catch(function(e){ if(body) body.innerHTML = '<div class="qa-empty" style="color:#dc2626">错误: '+e.message+'</div>' });
  }

  // ═══════════════════ Platform Health ═══════════════════
  function phLoad() {
    get('/api/dashboard/heartbeat').then(function(hb){
      var s = document.getElementById('phStatus'); if(!s) return;
      var ok = hb && hb.status === 'ok';
      s.innerHTML = '<span class="badge '+(ok?'badge-approved':'badge-rejected')+'">'+(ok?('✅ 平台在线 · '+(hb.latency_ms||0).toFixed(0)+'ms'):'❌ 平台不可达')+'</span>';
    }).catch(function(){});
    get('/api/dashboard/interaction').then(function(d){
      var el = document.getElementById('phInteraction'); if(!el) return;
      if(!d) { el.innerHTML = '<span class="text-muted">暂无数据</span>'; return; }
      function row(l,v){return '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--line-soft)"><span>'+l+'</span><strong>'+v+'</strong></div>'}
      el.innerHTML = [row('健康得分',((d.health_score||0)*100).toFixed(0)+'%'),row('功能通过',(d.features_ok||0)+'/'+(d.features_total||0)),row('API P50',(d.latency_p50||0)+'ms'),row('API P95',(d.latency_p95||0)+'ms')].join('');
    }).catch(function(){});
    get('/api/dashboard/technical-metrics').then(function(d){
      var el = document.getElementById('phTechMetrics'); if(!el) return;
      if(!d) { el.innerHTML = '<span class="text-muted">暂无数据</span>'; return; }
      function row(l,v){return '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--line-soft)"><span>'+l+'</span><strong>'+v+'</strong></div>'}
      el.innerHTML = [row('评估总数',d.total_evals||0),row('平均分数',(d.avg_score||0).toFixed(2)),row('Token',d.total_tokens?(d.total_tokens/1000).toFixed(0)+'K':'-'),row('平均耗时',d.avg_duration?(d.avg_duration/60).toFixed(1)+'min':'-')].join('');
    }).catch(function(){});
    document.getElementById('phRefreshBtn').onclick = phLoad;
    document.getElementById('phFullRefreshBtn').onclick = function(){ get('/api/dashboard/interaction/refresh').then(function(){toast('全量检测已触发，请等待2-3分钟','info')}) };
  }

  // ═══════════════════ Test Runner ═══════════════════
  var _trRunning = false, _trSid = null;
  function trLoad() {
    get('/api/agents').then(function(a){
      var sel = document.getElementById('trAgent'); if(!sel) return;
      sel.innerHTML = '<option value="platform">实训教学平台</option>';
    }).catch(function(){});
    trSessions();
    document.getElementById('trStartBtn').onclick = trStart;
    document.getElementById('trStopBtn').onclick = trStop;
  }
  function trStart() {
    var profile = document.getElementById('trProfile').value;
    var presets = {patrol:{phases:[1,2,3,4,5],mode:'guided',include_quiz:true},full:{phases:[1,2,3,4,5],mode:'guided',include_quiz:true},deep:{phases:[1,2,3,4,5],mode:'both',include_quiz:true}};
    var params = presets[profile]||presets.full;
    params.num_questions = parseInt(document.getElementById('trScenarios').value)||3;
    post('/api/tests/run-browser', params).then(function(data){
      if(data.status==='started') {
        _trRunning = true; _trSid = data.session_id;
        document.getElementById('trStartBtn').style.display = 'none';
        document.getElementById('trStopBtn').style.display = '';
        document.getElementById('trStatus').innerHTML = '<span style="color:#16a34a">✅ 运行中: '+data.session_id+'</span>';
        document.getElementById('trEventLog').innerHTML = '';
        trPoll();
      } else toast('启动失败: '+JSON.stringify(data),'error');
    }).catch(function(e){toast('错误: '+e.message,'error')});
  }
  function trStop() {
    if(!_trSid) return;
    post('/api/tests/cancel',{session_id:_trSid}).then(function(){
      _trRunning = false; _trSid = null;
      document.getElementById('trStartBtn').style.display = '';
      document.getElementById('trStopBtn').style.display = 'none';
      document.getElementById('trStatus').innerHTML = '<span style="color:var(--text-muted)">已停止</span>';
      trSessions();
    }).catch(function(){});
  }
  function trPoll() {
    if(!_trRunning||!_trSid) return;
    get('/api/tests/sessions/'+_trSid+'/logs').then(function(data){
      var el = document.getElementById('trEventLog'); if(!el||!data.logs) return;
      el.innerHTML = data.logs.map(function(l){return '<div style="padding:2px 0;border-bottom:1px solid var(--line-soft)"><span class="text-muted">'+(l.ts||'').substring(11,19)+'</span> '+escHtml(l.msg||l.event||'')+'</div>'}).join('');
      el.scrollTop = el.scrollHeight;
    }).catch(function(){});
    if(_trRunning) setTimeout(trPoll,2000);
  }
  function trSessions() {
    get('/api/tests/sessions').then(function(data){
      var el = document.getElementById('trSessions'); if(!el) return;
      var items = data.items||[]; if(!items.length) {el.innerHTML='<span class="text-muted">暂无历史会话</span>';return}
      el.innerHTML = items.map(function(s){return '<div style="padding:6px 8px;border:1px solid var(--line);border-radius:6px;margin:4px 0;font-size:12px"><strong>'+escHtml(s.agent_id)+'</strong> · '+(s.status||'?')+' · '+(s.created_at||'').substring(0,16)+'</div>'}).join('');
    }).catch(function(){});
  }

  // ═══════════════════ Reports ═══════════════════
  var _rpCmpIds = [];
  function reportsLoad() {
    get('/api/reports?page_size=50').then(function(data){
      var el = document.getElementById('rpList'); if(!el) return;
      var items = data.items||[]; if(!items.length){el.innerHTML='<span class="text-muted">暂无报告</span>';return}
      el.innerHTML = items.map(function(r){
        return '<div style="padding:6px 8px;border:1px solid var(--line);border-radius:6px;margin:4px 0;cursor:pointer;font-size:12px" onclick="App.rpSelect(\''+r.id+'\')"><strong>'+escHtml(r.agent_id||'?')+'</strong> · '+(r.overall_score!=null?r.overall_score.toFixed(1):'?')+'分 · '+(r.created_at||'').substring(0,16)+(_rpCmpIds.indexOf(r.id)>=0?' <span class="badge badge-blue">已选</span>':'')+'</div>';
      }).join('');
    }).catch(function(){});
  }
  function rpSelect(id) {
    if(_rpCmpIds.length>0) {
      var idx = _rpCmpIds.indexOf(id); if(idx>=0) _rpCmpIds.splice(idx,1); else if(_rpCmpIds.length<5) _rpCmpIds.push(id);
      reportsLoad(); if(_rpCmpIds.length>=2) rpCompare(); return;
    }
    get('/api/reports/'+id).then(function(r){
      var el = document.getElementById('rpDetail'); if(!el) return;
      var html = '<h4>'+escHtml(r.agent_id||'报告')+'</h4>';
      html += '<p>综合分: <strong>'+(r.overall_score!=null?r.overall_score.toFixed(2):'?')+'</strong> · '+ (r.created_at||'')+'</p>';
      if(r.scores) { html+='<table style="width:100%;font-size:12px"><tr><th>维度</th><th>得分</th></tr>';
        DIMS.forEach(function(d){var v=r.scores[d]; if(v!=null) html+='<tr><td>'+(window.t||function(x){return x})('dim_'+d)+'</td><td>'+Number(v).toFixed(1)+'</td></tr>'});
        html+='</table>'; }
      if(r.html_content) html+='<div style="margin-top:12px">'+r.html_content+'</div>';
      else if(r.markdown_content) html+='<pre style="white-space:pre-wrap;font-size:12px;margin-top:12px;background:var(--bg-primary);padding:12px;border-radius:6px">'+escHtml(r.markdown_content.substring(0,5000))+'</pre>';
      el.innerHTML = html;
    }).catch(function(){document.getElementById('rpDetail').innerHTML='<span style="color:var(--red)">加载失败</span>'});
  }
  function reportsCompare() { _rpCmpIds=[]; document.getElementById('rpCompareBtn').style.display='none'; document.getElementById('rpExitCompareBtn').style.display=''; reportsLoad(); }
  function reportsExitCompare() { _rpCmpIds=[]; document.getElementById('rpCompareBtn').style.display=''; document.getElementById('rpExitCompareBtn').style.display='none'; document.getElementById('rpDetail').innerHTML='<span class="text-muted">← 选择一个报告查看详情</span>'; reportsLoad(); }
  function rpCompare() {
    Promise.all(_rpCmpIds.map(function(id){return get('/api/reports/'+id)})).then(function(results){
      var el = document.getElementById('rpDetail'); if(!el) return;
      var html = '<h4>⚖️ 报告对比 ('+results.length+'个)</h4><div style="overflow-x:auto"><table style="width:100%;font-size:11px"><tr><th>维度</th>';
      results.forEach(function(r){html+='<th>'+escHtml((r.agent_id||'').substring(0,10))+'</th>'});
      html+='</tr>';
      DIMS.forEach(function(d){html+='<tr><td>'+(window.t||function(x){return x})('dim_'+d)+'</td>';results.forEach(function(r){var v=(r.scores||{})[d];html+='<td>'+(v!=null?Number(v).toFixed(1):'-')+'</td>'});html+='</tr>'});
      html+='</table></div>'; el.innerHTML = html;
    });
  }

  // ═══════════════════ Calibration ═══════════════════
  var _calItems=[], _calIdx=0, _calScores={};
  function calInit() {
    document.getElementById('calLoadBtn').onclick = calLoad;
    document.getElementById('calResultsBtn').onclick = calStats;
    document.getElementById('calGenBtn').onclick = function(){post('/api/calibration/generate',{count:20}).then(function(){toast('校准集已生成','success');calLoad()}).catch(function(e){toast('生成失败: '+e.message,'error')})};
    calLoad();
  }
  function calLoad() {
    get('/api/calibration/items?limit=20&unscored_only=true').then(function(data){
      _calItems=data.items||data||[]; _calIdx=0; _calScores={}; calRenderList();
      get('/api/calibration/progress').then(function(p){document.getElementById('calProg').textContent=(p.scored||0)+'/'+(p.total||0)+' 已评'});
      if(_calItems.length>0) calSelect(0);
    }).catch(function(e){document.getElementById('calItems').innerHTML='<div class="qa-empty">加载失败: '+escHtml(e.message)+'</div>'});
  }
  function calRenderList() {
    var el = document.getElementById('calItems'); if(!el) return;
    if(!_calItems.length){el.innerHTML='<div class="qa-empty">无待校准项</div>';return}
    el.innerHTML = _calItems.map(function(item,i){
      return '<div style="padding:6px 8px;border:1px solid var(--line);border-radius:6px;margin:4px 0;cursor:pointer;font-size:12px'+(i===_calIdx?' background:var(--bg-tertiary)':'')+'" onclick="App.calSelect('+i+')"><strong>#'+(item.qa_id||item.id||i+1)+'</strong> '+escHtml((item.question||'').substring(0,50))+(item.scored?' <span class="badge badge-approved">✓</span>':' <span class="badge badge-warn">待评</span>')+'</div>';
    }).join('');
  }
  function calSelect(idx) {
    _calIdx = idx; calRenderList(); var item = _calItems[idx]; if(!item) return;
    var el = document.getElementById('calScore'); if(!el) return;
    var html = '<div style="margin-bottom:8px"><strong>问题:</strong> '+escHtml(item.question||'')+'</div>';
    html += '<div style="margin-bottom:8px"><strong>Agent回答:</strong> '+escHtml((item.agent_answer||item.answer||'').substring(0,500))+'</div>';
    html += '<div style="margin-bottom:12px">';
    DIMS.forEach(function(d){
      html += '<div style="display:flex;align-items:center;margin:4px 0;font-size:12px"><span style="width:90px">'+(window.t||function(x){return x})('dim_'+d)+'</span>';
      for(var s=1;s<=5;s++) html += '<button style="width:26px;height:22px;margin:0 1px;font-size:11px;border:1px solid var(--line);border-radius:4px;cursor:pointer' + (_calScores[d]===s?' background:var(--sky);color:#fff':'') + '" onclick="App.calScore(\''+d+'\','+s+')">'+s+'</button>';
      html += '<span style="margin-left:8px;font-size:11px">'+(_calScores[d]?_calScores[d]+'/5':'未评')+'</span></div>';
    });
    html += '</div><button class="btn btn-primary btn-sm" onclick="App.calSubmit()">✅ 提交</button> <button class="btn btn-outline btn-sm" onclick="App.calSkip()">⏭ 跳过</button>';
    el.innerHTML = html;
  }
  function calScore(dim,s){_calScores[dim]=s;calSelect(_calIdx)}
  function calSubmit(){
    var item=_calItems[_calIdx]; if(!item) return;
    if(Object.keys(_calScores).length<8){toast('请至少完成8个维度的评分','warn');return}
    post('/api/calibration/score',{qa_id:item.qa_id||item.id,scores:_calScores}).then(function(){
      toast('评分已提交','success'); _calItems[_calIdx].scored=true; _calScores={};
      calLoad(); calStats(); var next=_calIdx+1; if(next<_calItems.length) calSelect(next);
    }).catch(function(e){toast('提交失败: '+e.message,'error')});
  }
  function calSkip(){var next=_calIdx+1;if(next<_calItems.length){_calScores={};calSelect(next)}}
  function calStats(){
    get('/api/calibration/results').then(function(r){
      var el=document.getElementById('calStats'); if(!el) return;
      var html='<div style="font-size:12px">';
      html+='<div>Cohens κ: <strong>'+((r.cohens_kappa||0).toFixed(3))+'</strong></div>';
      html+='<div>Spearman ρ: <strong>'+((r.spearman_rho||0).toFixed(3))+'</strong></div>';
      html+='<div>MAE: <strong>'+((r.mae||0).toFixed(2))+'</strong></div>';
      html+='<div>已标注: <strong>'+(r.scored_count||0)+'/'+(r.total_count||0)+'</strong></div>';
      if(r.per_dimension) Object.keys(r.per_dimension).forEach(function(d){var v=r.per_dimension[d];html+='<div>'+(window.t||function(x){return x})('dim_'+d)+': 偏差 '+((v.bias||0).toFixed(2))+'</div>'});
      html+='</div>'; el.innerHTML=html;
    }).catch(function(){});
  }

  // ═══════════════════ WebSocket ═══════════════════
  var _ws=null,_wsRc=0;
  function connectWS(){
    try{
      var proto=location.protocol==='https:'?'wss':'ws';
      _ws=new WebSocket(proto+'://'+location.host+API+'/ws');
      _ws.onopen=function(){_wsRc=0;var el=document.getElementById('wsIndicator');if(el){el.innerHTML='🟢 WS已连接';el.style.color='#16a34a'}};
      _ws.onclose=function(){var el=document.getElementById('wsIndicator');if(el){el.innerHTML='🔌 WS断开';el.style.color='#dc2626'}var d=Math.min(30000,1000*Math.pow(2,_wsRc++));setTimeout(connectWS,d)};
      _ws.onmessage=function(e){
        try{
          var m=JSON.parse(e.data); if(m.type!=='eval_event') return;
          var ev=m.event,data=m.data||{};
          if(ev==='browser_log'){var body=document.getElementById('liveEvalBody');if(body){body.innerHTML+='<div style="font-size:11px;padding:2px 0;border-bottom:1px solid var(--line-soft)">'+escHtml(data.msg||'')+'</div>';body.scrollTop=body.scrollHeight}}
          if(ev==='browser_done'){var b=document.getElementById('liveEvalBody');if(b)b.innerHTML+='<div style="color:#16a34a;padding:8px;font-weight:600">测评完成!</div>';setTimeout(loadDashboard,2000)}
        }catch(ex){}
      };
    }catch(ex){}
  }

  // ═══════════════════ Export ═══════════════════
  window.App = {
    showPage:showPage, loadDashboard:loadDashboard, startEval:startEval, onProfileChange:onProfileChange,
    toggleTheme:toggleTheme, toggleLang:toggleLang,
    phLoad:phLoad, trLoad:trLoad, trStart:trStart, trStop:trStop,
    reportsLoad:reportsLoad, reportsCompare:reportsCompare, reportsExitCompare:reportsExitCompare, rpSelect:rpSelect,
    calInit:calInit, calSelect:calSelect, calScore:calScore, calSubmit:calSubmit, calSkip:calSkip,
    testStart:trStart, testStop:trStop
  };

  document.addEventListener('DOMContentLoaded', function(){
    document.getElementById('langToggle').textContent = (localStorage.getItem('lang')||'zh')==='zh' ? 'EN' : '中';
    loadDashboard(); onProfileChange(); setTimeout(connectWS,500);
  });
})();
