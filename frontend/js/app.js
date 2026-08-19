/* AI Agent Evaluation Platform v3.6 — Application */
(function(){'use strict';

var API=(function(){try{var p=location.pathname;return(p.startsWith('/test/')||p==='/test')?'/test':''}catch(e){return''}})();
var DIMS=['correctness','relevancy','completeness','guidance','followup_quality','boundary_compliance','turn_consistency','knowledge_scaffolding','overhelping','fairness_bias'];

// ═══════════════════ Built-in i18n ═══════════════════
var _lang=(function(){try{return localStorage.getItem('lang')||'zh'}catch(e){return'zh'}})();
var _dict={
  nav_home:{zh:'Overview',en:'Overview'},
  nav_platform_health:{zh:'Platform Health',en:'Platform Health'},
  nav_test:{zh:'Test Runner',en:'Test Runner'},
  nav_reports:{zh:'Reports',en:'Reports'},
  nav_calibration:{zh:'Calibration',en:'Calibration'},
  sys_online:{zh:'Online',en:'Online'},
  sys_ws_connected:{zh:'Connected',en:'Connected'},
  sys_ws_disconnected:{zh:'Disconnected',en:'Disconnected'},
  home_title:{zh:'Evaluation Overview',en:'Evaluation Overview'},
  live_title:{zh:'Live Evaluation',en:'Live Evaluation'},
  chart_trend:{zh:'Score Trend',en:'Score Trend'},
  chart_radar:{zh:'Dimension Radar',en:'Dimension Radar'},
  recent_reports:{zh:'Recent Reports',en:'Recent Reports'},
  reports_no_data:{zh:'No reports yet',en:'No reports yet'},
  test_start_btn:{zh:'Start Evaluation',en:'Start Evaluation'},
  test_stop_btn:{zh:'Stop',en:'Stop'},
  test_title:{zh:'Test Runner',en:'Test Runner'},
  test_event_log:{zh:'Live Event Log',en:'Live Event Log'},
  test_history:{zh:'Session History',en:'Session History'},
  test_no_history:{zh:'No session history',en:'No session history'},
  btn_refresh:{zh:'Refresh',en:'Refresh'},
  reports_title:{zh:'Evaluation Reports',en:'Evaluation Reports'},
  health_title:{zh:'Platform Health',en:'Platform Health'},
  health_refresh_btn:{zh:'Refresh Check',en:'Refresh Check'},
  health_refresh_text:{zh:'Full Health Check',en:'Full Health Check'},
  cal_title:{zh:'Human Calibration Workspace',en:'Human Calibration Workspace'},
  cal_load_btn:{zh:'Load Items',en:'Load Items'},
  cal_results_btn:{zh:'View Statistics',en:'View Statistics'},
  cal_generate_btn:{zh:'Generate Calibration Set',en:'Generate Calibration Set'},
  card_total_tests:{zh:'Total Tests',en:'Total Tests'},
  card_avg_score:{zh:'Avg Score',en:'Avg Score'},
  card_qa_approved:{zh:'Approved QA',en:'Approved QA'},
  card_qa_pending:{zh:'Pending',en:'Pending'},
  dim_correctness:{zh:'Correctness',en:'Correctness'},
  dim_relevancy:{zh:'Relevancy',en:'Relevancy'},
  dim_completeness:{zh:'Completeness',en:'Completeness'},
  dim_guidance:{zh:'Guidance',en:'Guidance'},
  dim_followup_quality:{zh:'Follow-up Quality',en:'Follow-up Quality'},
  dim_boundary_compliance:{zh:'Boundary Compliance',en:'Boundary Compliance'},
  dim_turn_consistency:{zh:'Turn Consistency',en:'Turn Consistency'},
  dim_knowledge_scaffolding:{zh:'Knowledge Scaffolding',en:'Knowledge Scaffolding'},
  dim_overhelping:{zh:'Over-helping',en:'Over-helping'},
  dim_fairness_bias:{zh:'Fairness',en:'Fairness'},
  nav_explorer:{zh:'🔍 平台探索',en:'🔍 Explorer'},
  explorer_title:{zh:'平台探索器',en:'Platform Explorer'},
  explorer_desc:{zh:'自动发现教学平台结构：阶段、课时、步骤、API端点和AI助手交互模式。',en:'Auto-discover teaching platform structure: phases, lessons, steps, APIs, and AI agent endpoints.'},
  explorer_config:{zh:'探索配置',en:'Exploration Config'},
  explorer_hint:{zh:'留空凭证以自动检测认证方式。服务器模式推荐使用无头浏览器。',en:'Leave credentials empty to auto-detect auth. Headless mode recommended for servers.'},
  explorer_history:{zh:'探索历史',en:'Exploration History'},
  explorer_no_history:{zh:'暂无探索记录',en:'No exploration sessions yet'},
  explorer_url_required:{zh:'请输入目标平台URL',en:'Please enter a target URL'},
  explorer_phases:{zh:'阶段',en:'Phases'},
  explorer_steps:{zh:'步骤',en:'Steps'},
  explorer_apis:{zh:'API',en:'APIs'},
  explorer_conf:{zh:'置信度',en:'Conf'},
  explorer_start_btn:{zh:'🚀 开始探索',en:'🚀 Start Exploration'},
  explorer_cancel_btn:{zh:'⏹ 取消',en:'⏹ Cancel'},
  explorer_use_schema:{zh:'✅ 使用此Schema进行测评',en:'✅ Use This Schema for Evaluation'},
  explorer_view_schema:{zh:'📄 查看Schema',en:'📄 View Schema'},
  explorer_download_schema:{zh:'💾 下载Schema',en:'💾 Download Schema'},
  explorer_schema_active:{zh:'🧬 Schema-Driven 模式已激活',en:'🧬 Schema-Driven Mode Active'},
  schema_indicator:{zh:'🧬 Schema模式',en:'🧬 Schema Mode'},
  explorer_chat_title:{zh:'对话式探索',en:'Conversational Explorer'},
  explorer_chat_hint:{zh:'用自然语言描述探索任务，缺什么我会问你',en:'Describe the exploration in natural language — I will ask for what is missing.'},
  explorer_chat_send:{zh:'发送',en:'Send'},
  explorer_chat_starting:{zh:'探索已启动',en:'Exploration started'},
  intv_title:{zh:'⚠️ 评测遇到卡点 — 需要你的输入',en:'⚠️ Evaluation blocked — your input needed'},
  intv_submit:{zh:'提交',en:'Submit'},
  intv_timeout:{zh:'秒后自动按默认处理',en:'s before default action'}
};
function t(k){var e=_dict[k];return e?e[_lang]||e.zh||k:k}
function setLang(l){_lang=l;_dict=window._i18nExt||_dict}

// Merge external i18n.js dictionary if loaded
window._i18nExt=null;
window._mergeI18n=function(ext){window._i18nExt=ext}

function escHtml(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function get(u){return fetch(API+u).then(function(r){return r.json()})}
function post(u,b){return fetch(API+u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(function(r){return r.json()})}
function toast(msg,type){type=type||'info';var c=document.getElementById('toastContainer');if(!c)return;var d=document.createElement('div');d.className='toast-item';d.style.background=type==='error'?'var(--red2)':type==='success'?'var(--green2)':'var(--surface)';d.style.borderColor=type==='error'?'var(--red)':type==='success'?'var(--green)':'var(--border)';d.textContent=msg;c.appendChild(d);setTimeout(function(){d.style.opacity='0';d.style.transition='opacity .3s';setTimeout(function(){d.remove()},300)},3500)}

var _currentPage='dashboard', _targetUrl='http://124.174.108.70';

function setTargetUrl(url){_targetUrl=url;localStorage.setItem('targetUrl',url);if(_currentPage==='platform-health')phLoad()}

function showPage(name){
  _currentPage=name;
  document.querySelectorAll('.page').forEach(function(p){p.classList.remove('active')});
  document.querySelectorAll('.sidebar-nav a').forEach(function(a){a.classList.remove('active')});
  var el=document.getElementById('page-'+name);if(!el)return;
  el.classList.add('active');el.style.animation='none';el.offsetHeight;el.style.animation='fadeIn .35s var(--transition)';
  var nv=document.querySelector('.sidebar-nav a[data-page="'+name+'"]');if(nv)nv.classList.add('active');
  if(name==='dashboard'){loadDashboard();return}
  if(name==='platform-health'){phLoad();return}
  if(name==='test-runner'){trLoad();return}
  if(name==='reports'){reportsLoad();return}
  if(name==='calibration'){calInit();return}
  if(name==='explorer'){exploreInit();return}
}

function applyI18n(){
  document.querySelectorAll('[data-i18n]').forEach(function(el){var k=el.getAttribute('data-i18n');if(k)el.textContent=t(k)});
  document.querySelectorAll('[data-i18n-opt]').forEach(function(el){var k=el.getAttribute('data-i18n-opt');if(k)el.textContent=t(k)});
}

function toggleTheme(){
  var e=document.documentElement,th=e.getAttribute('data-theme')==='dark'?'light':'dark';
  e.setAttribute('data-theme',th);localStorage.setItem('theme',th);
  if(_currentPage==='dashboard'&&typeof Chart!=='undefined'&&trendChart){loadDashboard()}
}

function toggleLang(){
  _lang=_lang=="zh"?"en":"zh";localStorage.setItem("lang",_lang);
  if(window.setLang)window.setLang(_lang);
  document.getElementById("langToggle").textContent=_lang=="zh"?"EN":"CN";
  applyI18n();showPage(_currentPage);
}

// ── Animated number counting ──
function animateValue(el,v){if(!el)return;el.textContent=String(v)}

// ═══════════════════ Dashboard ═══════════════════
var trendChart=null,radarChart=null;

function loadDashboard(){
  get('/api/dashboard/summary').then(function(d){
    var vals=[
      {v:d.total_tests||0,l:'Total Tests'},
      {v:(d.avg_overall||0).toFixed(2),l:'Avg Score'},
      {v:d.qa_approved||0,l:'Approved QA'},
      {v:d.qa_pending||0,l:'Pending'}
    ];
    for(var i=0;i<4;i++){
      var el=document.getElementById('statVal'+i);if(el)el.textContent=vals[i].v;
    }
    renderCharts(d);
  }).catch(function(){});

  // Schema-driven indicator
  var si=document.getElementById('schemaIndicator');
  if(si){si.style.display=localStorage.getItem('schemaDriven')==='true'?'':'none'}

  get('/api/dashboard/sessions?page_size=5').then(function(r){
    var el=document.getElementById('recentReports');if(!el)return;
    if(r&&r.items&&r.items.length)el.innerHTML=r.items.map(function(x){return'<span class="badge badge-blue" style="margin:2px;animation:fadeIn .3s var(--transition) both">'+escHtml(x.agent_id)+' &middot; '+(x.status||'?')+'</span>'}).join(' ');
    else el.innerHTML='<div class="empty-state">'+t('reports_no_data')+'</div>';
  }).catch(function(){});
}

function renderCharts(d){
  if(typeof Chart==='undefined')return;
  var labels=DIMS.slice(0,8).map(function(k){return t('dim_'+k)});
  var dark=document.documentElement.getAttribute('data-theme')==='dark';
  var grid=dark?'rgba(148,163,184,.1)':'rgba(100,116,139,.08)';
  var tick=dark?'#9ca3af':'#6b7280';
  Chart.defaults.color=tick;Chart.defaults.font={family:'system-ui',size:11};
  var gradCtx=document.createElement('canvas').getContext('2d');

  var tEl=document.getElementById('trendChart');
  if(tEl){
    var trend=(d.trend||[]).slice().reverse();
    if(trendChart)trendChart.destroy();
    trendChart=new Chart(tEl,{
      type:'line',
      data:{
        labels:trend.map(function(p,i){return p.ts?String(p.ts).replace('T',' ').substring(5,16):(i+1)}),
        datasets:[{
          data:trend.map(function(p){return p.score}),
          borderColor:dark?'#818cf8':'#6366f1',
          backgroundColor:dark?'rgba(129,140,248,.1)':'rgba(99,102,241,.08)',
          fill:true,tension:.4,borderWidth:2.5,pointRadius:4
        }]
      },
      options:{
        responsive:true,maintainAspectRatio:false,
        plugins:{legend:{display:false}},
        scales:{y:{min:0,max:5,ticks:{stepSize:1},grid:{color:grid}},x:{grid:{color:grid}}}
      }
    });
  }
  var rEl=document.getElementById('radarChart');
  if(rEl){
    var latest=d.latest||{};
    if(radarChart)radarChart.destroy();
    radarChart=new Chart(rEl,{
      type:'radar',
      data:{
        labels:labels,
        datasets:[{
          data:DIMS.slice(0,8).map(function(k){return latest[k]||0}),
          borderColor:dark?'#818cf8':'#6366f1',
          backgroundColor:dark?'rgba(129,140,248,.15)':'rgba(99,102,241,.1)',
          borderWidth:2.5,pointRadius:4
        }]
      },
      options:{
        responsive:true,maintainAspectRatio:false,
        plugins:{legend:{display:false}},
        scales:{r:{min:0,max:5,ticks:{stepSize:1,backdropColor:'transparent'},grid:{color:grid},pointLabels:{color:tick,font:{size:11}}}}
      }
    });
  }
}

function onProfileChange(){
  var v=document.getElementById('evalProfile').value;
  document.getElementById('customOpts').style.display=v==='custom'?'flex':'none';
}

function startEval(){
  var profile=document.getElementById('evalProfile').value;
  var panel=document.getElementById('liveEvalPanel'),body=document.getElementById('liveEvalBody'),bar=document.getElementById('evalStatus');
  if(panel)panel.style.display='block';if(bar){bar.style.display='block';bar.innerHTML='<span class="badge badge-blue" style="animation:pulse 1.5s infinite">Starting evaluation...</span>'}
  if(body)body.innerHTML='';
  var pBar=document.getElementById('progressFill');pBar.style.width='10%';pBar.classList.add('active');
  var presets={patrol:{phases:[1,2,3,4,5],mode:'guided',include_quiz:true},full:{phases:[1,2,3,4,5],mode:'guided',include_quiz:true},deep:{phases:[1,2,3,4,5],mode:'both',include_quiz:true}};
  var params,endpoint;
  if(profile==='custom'){params={agent_id:'platform',num_questions:parseInt(document.getElementById('numQuestions').value)||3,max_turns:parseInt(document.getElementById('maxTurns').value)||3,profile:'custom',target_url:_targetUrl};endpoint='/api/tests/run'}
  else{params=presets[profile]||presets.full;params.target_url=_targetUrl;endpoint='/api/tests/run-browser'}
  // Schema-driven mode (from Platform Explorer)
  if(localStorage.getItem('schemaDriven')==='true'){
    params.schema_driven=true;
    params.platform_schema_path=localStorage.getItem('schemaPath')||'';
  }
  post(endpoint,params).then(function(data){
    if(data.status==='started'){if(body)body.innerHTML='<div class="log-line" style="color:var(--green)">Session started: '+data.session_id+'</div>';if(bar)bar.innerHTML='<span class="badge badge-green">Running: '+data.session_id+'</span>';pBar.style.width='30%'}
    else{if(body)body.innerHTML='<div class="log-line" style="color:var(--red)">Failed: '+JSON.stringify(data)+'</div>';pBar.classList.remove('active')}
  }).catch(function(e){if(body)body.innerHTML='<div class="log-line" style="color:var(--red)">'+e.message+'</div>';pBar.classList.remove('active')});
}

// ═══════════════════ Platform Health ═══════════════════
function phLoad(){
  var intEl=document.getElementById('phInteraction'),techEl=document.getElementById('phTechMetrics');
  if(intEl)intEl.innerHTML='<div class="skeleton" style="height:120px"></div>';
  if(techEl)techEl.innerHTML='<div class="skeleton" style="height:120px"></div>';

  get('/api/dashboard/heartbeat').then(function(hb){
    var s=document.getElementById('phStatus');if(!s)return;
    var ok=hb&&hb.status==='ok';
    s.innerHTML='<span class="badge '+(ok?'badge-green':'badge-red')+'" style="animation:fadeIn .3s var(--transition)">'+(ok?'Platform Online &middot; '+(hb.latency_ms||0).toFixed(0)+'ms latency':'Platform Unreachable')+'</span>';
  }).catch(function(){});

  get('/api/dashboard/interaction').then(function(d){
    if(!intEl)return;
    if(!d){intEl.innerHTML='<div class="empty-state">No data available</div>';return}
    intEl.innerHTML=[
      ['Health Score',((d.health_score||0)*100).toFixed(0)+'%','high'],
      ['Features Passed',(d.features_ok||0)+'/'+(d.features_total||0),(d.features_ok/d.features_total)>.8?'high':'mid'],
      ['API Latency P50',(d.latency_p50||0)+'ms','high'],
      ['API Latency P95',(d.latency_p95||0)+'ms','mid']
    ].map(function(x,i){return'<div class="kv-row" style="animation:fadeIn .3s '+(.05*i).toFixed(2)+'s both"><span>'+x[0]+'</span><span class="kv-val">'+x[1]+'</span></div>'}).join('');
  }).catch(function(){if(intEl)intEl.innerHTML='<div class="empty-state">Failed to load</div>'});

  get('/api/dashboard/technical-metrics').then(function(d){
    if(!techEl)return;
    if(!d){techEl.innerHTML='<div class="empty-state">No data available</div>';return}
    techEl.innerHTML=[
      ['Total Evaluations',d.total_evals||0],
      ['Average Score',(d.avg_score||0).toFixed(2)],
      ['Total Tokens',d.total_tokens?(d.total_tokens/1000).toFixed(0)+'K':'-'],
      ['Avg Duration',d.avg_duration?(d.avg_duration/60).toFixed(1)+'min':'-']
    ].map(function(x,i){return'<div class="kv-row" style="animation:fadeIn .3s '+(.05*i).toFixed(2)+'s both"><span>'+x[0]+'</span><span class="kv-val">'+x[1]+'</span></div>'}).join('');
  }).catch(function(){if(techEl)techEl.innerHTML='<div class="empty-state">Failed to load</div>'});

  document.getElementById('phRefreshBtn').onclick=phLoad;
  document.getElementById('phFullRefreshBtn').onclick=function(){get('/api/dashboard/interaction/refresh').then(function(){toast('Full health check triggered','success');setTimeout(phLoad,2000)})};
}

// ═══════════════════ Test Runner ═══════════════════
var _trRunning=false,_trSid=null;
function trLoad(){
  get('/api/agents').then(function(a){
    var sel=document.getElementById('trAgent');if(!sel)return;
    sel.innerHTML='<option value="platform">Teaching Platform</option>';
  }).catch(function(){});
  trSessions();
  document.getElementById('trStartBtn').onclick=trStart;
  document.getElementById('trStopBtn').onclick=trStop;
}
function trStart(){
  var profile=document.getElementById('trProfile').value;
  var presets={patrol:{phases:[1,2,3,4,5],mode:'guided',include_quiz:true},full:{phases:[1,2,3,4,5],mode:'guided',include_quiz:true},deep:{phases:[1,2,3,4,5],mode:'both',include_quiz:true}};
  var params=presets[profile]||presets.full;
  params.num_questions=parseInt(document.getElementById('trScenarios').value)||3;
  params.target_url=_targetUrl;
  post('/api/tests/run-browser',params).then(function(data){
    if(data.status==='started'){
      _trRunning=true;_trSid=data.session_id;
      document.getElementById('trStartBtn').style.display='none';
      document.getElementById('trStopBtn').style.display='';
      document.getElementById('trStatus').innerHTML='<span class="badge badge-green" style="animation:pulse 2s infinite">Running: '+data.session_id+'</span>';
      document.getElementById('trEventLog').innerHTML='';
      trPoll();
    }else toast('Start failed: '+JSON.stringify(data),'error');
  }).catch(function(e){toast('Error: '+e.message,'error')});
}
function trStop(){
  if(!_trSid)return;
  post('/api/tests/cancel',{session_id:_trSid}).then(function(){
    _trRunning=false;_trSid=null;
    document.getElementById('trStartBtn').style.display='';document.getElementById('trStopBtn').style.display='none';
    document.getElementById('trStatus').innerHTML='<span class="badge badge-amber">Stopped</span>';
    trSessions();
  }).catch(function(){});
}
function trPoll(){
  if(!_trRunning||!_trSid)return;
  get('/api/tests/sessions/'+_trSid+'/logs').then(function(data){
    var el=document.getElementById('trEventLog');if(!el||!data.logs)return;
    el.innerHTML=data.logs.map(function(l){return'<div class="log-line"><span class="log-time">'+(l.ts||'').substring(11,19)+'</span>'+escHtml(l.msg||l.event||'')+'</div>'}).join('');
    el.scrollTop=el.scrollHeight;
  }).catch(function(){});
  if(_trRunning)setTimeout(trPoll,2000);
}
function trSessions(){
  get('/api/tests/sessions').then(function(data){
    var el=document.getElementById('trSessions');if(!el)return;
    var items=data.items||[];if(!items.length){el.innerHTML='<div class="empty-state">'+t('test_no_history')+'</div>';return}
    el.innerHTML=items.map(function(s,i){return'<div class="list-item" style="animation:fadeIn .3s '+(.03*i).toFixed(2)+'s both"><div class="flex-between"><strong>'+escHtml(s.agent_id)+'</strong><span class="badge '+(s.status==='completed'?'badge-green':s.status==='running'?'badge-blue':'badge-amber')+'">'+s.status+'</span></div><div style="font-size:11px;color:var(--text3);margin-top:4px">'+(s.created_at||'').substring(0,16)+' &middot; '+(s.total_scenarios||'?')+' scenarios</div></div>'}).join('');
  }).catch(function(){});
}

// ═══════════════════ Reports ═══════════════════
var _rpCmpIds=[];
function reportsLoad(){
  get('/api/reports?page_size=50').then(function(data){
    var el=document.getElementById('rpList');if(!el)return;
    var items=data.items||[];if(!items.length){el.innerHTML='<div class="empty-state">'+t('reports_no_data')+'</div>';return}
    el.innerHTML=items.map(function(r,i){return'<div class="list-item" onclick="App.rpSelect(\''+r.id+'\')" style="animation:fadeIn .3s '+(.02*i).toFixed(2)+'s both"><div class="flex-between"><strong>'+escHtml(r.agent_id||'Report #'+r.id)+'</strong><span style="font-weight:700">'+((r.overall||r.overall_score||0)!=null?(r.overall||r.overall_score||0).toFixed(2):'?')+' <span style="font-size:11px;color:var(--text3)">/ 5.0</span></span></div><div style="font-size:11px;color:var(--text3);margin-top:4px">'+(r.created_at||'').substring(0,16)+(_rpCmpIds.indexOf(r.id)>=0?' &middot; <span class="badge badge-blue">Selected</span>':'')+'</div></div>'}).join('');
  }).catch(function(){});
}
function rpSelect(id){
  if(_rpCmpIds.length>0){var idx=_rpCmpIds.indexOf(id);if(idx>=0)_rpCmpIds.splice(idx,1);else if(_rpCmpIds.length<5)_rpCmpIds.push(id);reportsLoad();if(_rpCmpIds.length>=2)rpCompare();return}
  get('/api/reports/'+id).then(function(r){
    var el=document.getElementById('rpDetail');if(!el)return;
    var html='<h3 style="margin-bottom:12px">'+escHtml(r.agent_id||'Report')+'</h3>';
    html+='<div class="kv-row"><span>Overall Score</span><span class="kv-val" style="font-size:18px;color:var(--accent)">'+((r.overall||r.overall_score||0)!=null?(r.overall||r.overall_score||0).toFixed(2):'?')+'</span></div>';
    html+='<div class="kv-row"><span>Created</span><span>'+ (r.created_at||'')+'</span></div>';
    if(r.scores){html+='<div style="margin-top:16px"><table><thead><tr><th>Dimension</th><th>Score</th><th></th></tr></thead><tbody>';
      DIMS.forEach(function(d){var v=r.scores[d];if(v!=null){var cls=v>=4?'high':v>=3?'mid':'low';html+='<tr><td>'+t('dim_'+d)+'</td><td><strong>'+Number(v).toFixed(1)+'</strong></td><td style="width:120px"><div class="score-bar"><div class="score-bar-fill '+cls+'" style="width:'+(v*20)+'%"></div></div></td></tr>'}});
      html+='</tbody></table></div>'}
    if(r.html_content)html+='<div style="margin-top:16px">'+r.html_content+'</div>';
    else if(r.markdown_content)html+='<pre style="white-space:pre-wrap;font-size:12px;margin-top:12px;background:var(--bg);padding:12px;border-radius:8px;max-height:400px;overflow-y:auto">'+escHtml(r.markdown_content.substring(0,5000))+'</pre>';
    el.innerHTML=html;
  }).catch(function(){document.getElementById('rpDetail').innerHTML='<div class="empty-state"><span style="color:var(--red)">Failed to load report</span></div>'});
}
function reportsCompare(){_rpCmpIds=[];document.getElementById('rpCompareBtn').style.display='none';document.getElementById('rpExitCompareBtn').style.display='';reportsLoad()}
function reportsExitCompare(){_rpCmpIds=[];document.getElementById('rpCompareBtn').style.display='';document.getElementById('rpExitCompareBtn').style.display='none';document.getElementById('rpDetail').innerHTML='<div class="empty-state">Select a report to view details</div>';reportsLoad()}
function rpCompare(){
  Promise.all(_rpCmpIds.map(function(id){return get('/api/reports/'+id)})).then(function(results){
    var el=document.getElementById('rpDetail');if(!el)return;
    var html='<h3 style="margin-bottom:12px">Comparison ('+results.length+' reports)</h3><div style="overflow-x:auto"><table><thead><tr><th>Dimension</th>';
    results.forEach(function(r){html+='<th>'+escHtml((r.agent_id||'').substring(0,14))+'</th>'});
    html+='</tr></thead><tbody>';
    DIMS.forEach(function(d){html+='<tr><td>'+t('dim_'+d)+'</td>';results.forEach(function(r){var v=(r.scores||{})[d];html+='<td style="font-weight:600">'+(v!=null?Number(v).toFixed(1):'-')+'</td>'});html+='</tr>'});
    html+='</tbody></table></div>';el.innerHTML=html;
  });
}

// ═══════════════════ Calibration ═══════════════════
var _calItems=[],_calIdx=0,_calScores={};
function calInit(){
  document.getElementById('calLoadBtn').onclick=calLoad;
  document.getElementById('calResultsBtn').onclick=calStats;
  document.getElementById('calGenBtn').onclick=function(){post('/api/calibration/generate',{count:20}).then(function(){toast('Calibration set generated','success');calLoad()}).catch(function(e){toast('Generation failed: '+e.message,'error')})};
  calLoad();
}
function calLoad(){
  document.getElementById('calItems').innerHTML='<div class="skeleton" style="height:200px"></div>';
  get('/api/calibration/items?limit=20&unscored_only=true').then(function(data){
    _calItems=data.items||data||[];_calIdx=0;_calScores={};calRenderList();
    get('/api/calibration/progress').then(function(p){document.getElementById('calProg').textContent=(p.scored||0)+'/'+(p.total||0)+' scored'});
    if(_calItems.length>0)calSelect(0);
  }).catch(function(e){document.getElementById('calItems').innerHTML='<div class="empty-state">Load failed: '+escHtml(e.message)+'</div>'});
}
function calRenderList(){
  var el=document.getElementById('calItems');if(!el)return;
  if(!_calItems.length){el.innerHTML='<div class="empty-state">No pending items</div>';return}
  el.innerHTML=_calItems.map(function(item,i){return'<div class="list-item'+(i===_calIdx?' active':'')+'" onclick="App.calSelect('+i+')" style="animation:fadeIn .2s '+(.02*i).toFixed(2)+'s both"><div><strong>#'+(item.qa_id||item.id||i+1)+'</strong> '+escHtml((item.question||'').substring(0,50))+'</div><div style="font-size:11px;color:var(--text3);margin-top:2px">'+(item.phase||'')+' &middot; '+(item.type||'')+' '+(item.scored?'<span class="badge badge-green">Scored</span>':'<span class="badge badge-amber">Pending</span>')+'</div></div>'}).join('');
}
function calSelect(idx){_calIdx=idx;calRenderList();var item=_calItems[idx];if(!item)return;var el=document.getElementById('calScore');if(!el)return;
  var html='<div style="margin-bottom:16px"><div class="kv-row"><span>Question</span><span style="font-size:12px">'+escHtml((item.question||'').substring(0,100))+'</span></div><div class="kv-row"><span>Response</span><span style="font-size:12px">'+escHtml((item.agent_answer||item.answer||'').substring(0,200))+'</span></div></div>';
  DIMS.forEach(function(d){html+='<div class="cal-dim-row"><span class="cal-dim-name">'+t('dim_'+d)+'</span>';for(var s=1;s<=5;s++)html+='<button class="cal-score-btn'+(_calScores[d]===s?' sel':'')+'" onclick="App.calScore(\''+d+'\','+s+')">'+s+'</button>';html+='<span style="margin-left:6px;font-size:11px;color:var(--text3)">'+(_calScores[d]?_calScores[d]+'/5':'-')+'</span></div>'});
  html+='<div class="flex" style="margin-top:14px"><button class="btn btn-primary btn-sm" onclick="App.calSubmit()">Submit</button><button class="btn btn-outline btn-sm" onclick="App.calSkip()">Skip</button></div>';el.innerHTML=html;
}
function calScore(dim,s){_calScores[dim]=s;calSelect(_calIdx)}
function calSubmit(){var item=_calItems[_calIdx];if(!item)return;if(Object.keys(_calScores).length<8){toast('Score at least 8 dimensions','error');return}
  post('/api/calibration/score',{qa_id:item.qa_id||item.id,scores:_calScores}).then(function(){toast('Score submitted','success');_calItems[_calIdx].scored=true;_calScores={};calLoad();calStats();var next=_calIdx+1;if(next<_calItems.length)calSelect(next)}).catch(function(e){toast('Submit failed: '+e.message,'error')});
}
function calSkip(){var next=_calIdx+1;if(next<_calItems.length){_calScores={};calSelect(next)}}
function calStats(){
  document.getElementById('calStats').innerHTML='<div class="skeleton" style="height:120px"></div>';
  get('/api/calibration/results').then(function(r){var el=document.getElementById('calStats');if(!el)return;var html='';
    html+='<div class="kv-row"><span>Cohen\'s Kappa</span><span class="kv-val">'+((r.cohens_kappa||0).toFixed(3))+'</span></div>';
    html+='<div class="kv-row"><span>Spearman Rho</span><span class="kv-val">'+((r.spearman_rho||0).toFixed(3))+'</span></div>';
    html+='<div class="kv-row"><span>MAE</span><span class="kv-val">'+((r.mae||0).toFixed(2))+'</span></div>';
    html+='<div class="kv-row"><span>Scored</span><span class="kv-val">'+(r.scored_count||0)+' / '+(r.total_count||0)+'</span></div>';
    if(r.per_dimension)Object.keys(r.per_dimension).forEach(function(d){var v=r.per_dimension[d];html+='<div class="kv-row"><span>'+t('dim_'+d)+'</span><span>bias: '+((v.bias||0).toFixed(2))+'</span></div>'});
    el.innerHTML=html;
  }).catch(function(){});
}

// ═══════════════════ WebSocket ═══════════════════
var _ws=null,_wsRc=0;
function connectWS(){
  try{var proto=location.protocol==='https:'?'wss':'ws';_ws=new WebSocket(proto+'://'+location.host+API+'/ws');
    _ws.onopen=function(){_wsRc=0;var el=document.getElementById('wsStatusDot');if(el){el.classList.remove('offline');el.classList.add('online')};var lb=document.getElementById('wsStatusLabel');if(lb)lb.textContent=t('sys_ws_connected')};
    _ws.onclose=function(){var el=document.getElementById('wsStatusDot');if(el){el.classList.remove('online');el.classList.add('offline')};var lb=document.getElementById('wsStatusLabel');if(lb)lb.textContent=t('sys_ws_disconnected');setTimeout(connectWS,Math.min(30000,1000*Math.pow(2,_wsRc++)))};
    _ws.onmessage=function(e){try{var m=JSON.parse(e.data);
      // 卡点干预: 评测线程 ask_user → 弹窗询问
      if(m.type==='eval:need_input'){showIntervention(m.data);return}
      if(m.type!=='eval_event')return;
      var ev=m.event,data=m.data||{};if(ev==='browser_log'){var b=document.getElementById('liveEvalBody');if(b){b.innerHTML+='<div class="log-line">'+escHtml(data.msg||'')+'</div>';b.scrollTop=b.scrollHeight;var pBar=document.getElementById('progressFill');if(pBar){var w=parseFloat(pBar.style.width)||30;pBar.style.width=Math.min(95,w+Math.random()*5)+'%'}}if(ev==='browser_done'){var b2=document.getElementById('liveEvalBody');if(b2)b2.innerHTML+='<div class="log-line" style="color:var(--green)">Evaluation complete</div>';var pb2=document.getElementById('progressFill');if(pb2){pb2.style.width='100%';setTimeout(function(){pb2.style.width='0%';pb2.classList.remove('active')},2000)}setTimeout(loadDashboard,2000)}}
    }catch(ex){}}
  }catch(ex){}
}

// ═══════════════════ Platform Explorer ═══════════════════
var _exploreTimer=null,_explorePoll=null,_exploreStartTs=0,_exploreSessionId='',_exploreSchemaPath='';

function _fmtDur(s){s=Math.round(s||0);var m=Math.floor(s/60),sec=s%60;return m>0?m+'m '+sec+'s':sec+'s'}
function _el(id){return document.getElementById(id)}

function exploreInit(){
  var eu=_el('exploreUrl');if(eu&&!_exploreSessionId)eu.value=_targetUrl;
  exploreLoadHistory();
  // 对话式探索: 进入页面即开启对话 (LLM 对话为主)
  if(!_exploreChatStarted)setTimeout(exploreChatStart,100);
}

function exploreStart(){
  var url=(_el('exploreUrl')?(_el('exploreUrl').value||'').trim():'');
  if(!url){toast(t('explorer_url_required')||'Please enter a target URL','error');return}
  if(!url.startsWith('http'))url='https://'+url;

  var body={
    target_url:url,
    username:_el('exploreUser')?_el('exploreUser').value:'',
    password:_el('explorePass')?_el('explorePass').value:'',
    headless:_el('exploreHeadless')?_el('exploreHeadless').checked:true,
    max_depth:parseInt((_el('exploreDepth')||{}).value)||3,
    max_pages:parseInt((_el('explorePages')||{}).value)||50,
    api_threshold:0.50
  };

  var sBtn=_el('exploreStartBtn');if(sBtn)sBtn.disabled=true;
  var cBtn=_el('exploreCancelBtn');if(cBtn)cBtn.style.display='';
  var prog=_el('exploreProgress');if(prog)prog.style.display='';
  var res=_el('exploreResults');if(res)res.style.display='none';
  var st=_el('exploreStatus');if(st)st.textContent='Starting exploration...';
  var bar=_el('exploreProgressBar');if(bar)bar.style.width='5%';
  _exploreStartTs=Date.now();
  if(_exploreTimer)clearInterval(_exploreTimer);
  _exploreTimer=setInterval(function(){var e=_el('exploreElapsed');if(e)e.textContent=_fmtDur((Date.now()-_exploreStartTs)/1000)},1000);

  post('/api/explorer/run',body).then(function(r){
    if(r.status==='started'){
      _exploreSessionId=r.session_id;
      var st2=_el('exploreStatus');if(st2)st2.textContent='Exploring... (L0: Auth)';
      var bar2=_el('exploreProgressBar');if(bar2)bar2.style.width='15%';
      if(_explorePoll)clearInterval(_explorePoll);
      _explorePoll=setInterval(explorePollStatus,2000);
      toast('Exploration started — '+r.session_id,'success');
    }else if(r.status==='busy'){
      toast('An exploration is already running','error');
      exploreResetUI();
    }else{
      toast('Failed: '+(r.error||r.message||'unknown'),'error');
      exploreResetUI();
    }
  }).catch(function(e){
    toast('Network error: '+e.message,'error');
    exploreResetUI();
  });
}

function exploreCancel(){
  post('/api/explorer/cancel').then(function(r){
    toast(r.message||'Exploration cancelled');
    exploreResetUI();
  }).catch(function(){exploreResetUI()});
}

function explorePollStatus(){
  get('/api/explorer/status').then(function(r){
    if(!r.running){
      if(_exploreTimer){clearInterval(_exploreTimer);_exploreTimer=null}
      if(_explorePoll){clearInterval(_explorePoll);_explorePoll=null}
      if(_exploreSessionId)exploreLoadResult(_exploreSessionId);
      exploreResetUI();
    }else{
      var bar=_el('exploreProgressBar');if(bar){var w=parseFloat(bar.style.width)||15;bar.style.width=Math.min(90,w+Math.random()*3)+'%'}
    }
  }).catch(function(){});
}

function exploreLoadResult(sid){
  get('/api/explorer/sessions/'+sid).then(function(r){
    var res=_el('exploreResults');if(res)res.style.display='';
    var el1=_el('expPhases');if(el1)el1.textContent=r.phases_found||0;
    var el2=_el('expLessons');if(el2)el2.textContent=r.lessons_found||0;
    var el3=_el('expSteps');if(el3)el3.textContent=r.steps_found||0;
    var el4=_el('expAPIs');if(el4)el4.textContent=r.api_endpoints_found||0;
    var el5=_el('expConf');if(el5)el5.textContent=Math.round((r.overall_confidence||0)*100)+'%';
    var el6=_el('expDur');if(el6)el6.textContent=_fmtDur(r.duration_seconds||0);
    var bar=_el('exploreProgressBar');if(bar)bar.style.width='100%';
    var st=_el('exploreStatus');if(st)st.textContent=r.status==='completed'?'Completed!':'Failed';
    _exploreSchemaPath=r.schema_path||'';

    if(r.warnings&&r.warnings.items&&r.warnings.items.length>0){
      var ew=_el('expWarnings');if(ew)ew.style.display='';
      var ewl=_el('expWarnList');if(ewl)ewl.innerHTML=r.warnings.items.map(function(w){return '<div>⚠️ '+escHtml(w)+'</div>'}).join('');
    }
    if(r.is_ready){
      var ub=_el('expUseSchemaBtn');if(ub)ub.style.display='';
      toast('Exploration complete! Schema ready.','success');
    }
  }).catch(function(e){toast('Failed to load result: '+e.message,'error')});
}

function exploreUseSchema(){
  if(!_exploreSchemaPath){toast('No schema available','error');return}
  _targetUrl=(_el('exploreUrl')?_el('exploreUrl').value:'')||_targetUrl;
  localStorage.setItem('schemaDriven','true');
  localStorage.setItem('schemaPath',_exploreSchemaPath);
  localStorage.setItem('targetUrl',_targetUrl);
  var tu=_el('targetUrl');if(tu)tu.value=_targetUrl;
  var si=_el('schemaIndicator');if(si)si.style.display='';
  toast('Schema activated! Evaluation will use discovered platform structure.','success');
  setTimeout(function(){showPage('dashboard')},1000);
}

function exploreViewSchema(){
  if(!_exploreSessionId){toast('No exploration session','error');return}
  window.open(API+'/api/explorer/schema/'+_exploreSessionId,'_blank');
}

function exploreDownloadSchema(){
  if(!_exploreSessionId){toast('No exploration session','error');return}
  var a=document.createElement('a');a.href=API+'/api/explorer/schema/'+_exploreSessionId;
  a.download='platform_schema.yaml';document.body.appendChild(a);a.click();document.body.removeChild(a);
}

function exploreLoadHistory(){
  get('/api/explorer/sessions?page=1&page_size=20').then(function(r){
    var el=_el('exploreHistory');if(!el)return;
    var sessions=r.sessions||[];
    if(sessions.length===0){el.innerHTML='<div class="empty-state">'+t('explorer_no_history')+'</div>';return}
    el.innerHTML=sessions.map(function(s){
      var badge=s.status==='completed'?'<span class="badge badge-green">✅ Done</span>':
        s.status==='running'?'<span class="badge badge-blue">🔄 Running</span>':
        s.status==='failed'?'<span class="badge badge-red">❌ Failed</span>':
        '<span class="badge badge-amber">'+escHtml(s.status)+'</span>';
      return '<div style="padding:8px 0;border-bottom:1px solid var(--border);cursor:pointer;font-size:12px" onclick="App.exploreLoadResult(\''+escHtml(s.session_id)+'\')">'+
        badge+' <b>'+escHtml(s.target_url)+'</b><br>'+
        '<span style="color:var(--text3)">'+
        (t('explorer_phases')||'Phases')+':'+(s.phases_found||0)+' '+
        (t('explorer_steps')||'Steps')+':'+(s.steps_found||0)+' '+
        (t('explorer_apis')||'APIs')+':'+(s.api_endpoints_found||0)+' '+
        (t('explorer_conf')||'Conf')+':'+Math.round((s.overall_confidence||0)*100)+'%'+
        ' · '+_fmtDur(s.duration_seconds||0)+' · '+escHtml(s.started_at||'')+'</span></div>';
    }).join('');
  }).catch(function(){});
}

function exploreResetUI(){
  if(_exploreTimer){clearInterval(_exploreTimer);_exploreTimer=null}
  if(_explorePoll){clearInterval(_explorePoll);_explorePoll=null}
  var sBtn=_el('exploreStartBtn');if(sBtn)sBtn.disabled=false;
  var cBtn=_el('exploreCancelBtn');if(cBtn)cBtn.style.display='none';
  var bar=_el('exploreProgressBar');if(bar)bar.style.width='0%';
}

// ═══════════════════ Explorer Chat (对话式探索 — 主交互) ═══════════════════
var _exploreChatId='',_exploreChatStarted=false;

function exploreChatBubble(role,text){
  var msgs=_el('exploreChatMsgs');if(!msgs)return;
  var d=document.createElement('div');
  d.className='chat-msg '+(role==='user'?'user':'assistant');
  d.textContent=text;
  msgs.appendChild(d);
  msgs.scrollTop=msgs.scrollHeight;
}

function exploreChatStart(){
  if(_exploreChatStarted)return;_exploreChatStarted=true;
  var body={
    target_url:(_el('exploreUrl')?_el('exploreUrl').value.trim():'')||_targetUrl||'',
    username:_el('exploreUser')?_el('exploreUser').value:'',
    password:_el('explorePass')?_el('explorePass').value:'',
    headless:_el('exploreHeadless')?_el('exploreHeadless').checked:true,
    max_depth:parseInt((_el('exploreDepth')||{}).value)||3,
    max_pages:parseInt((_el('explorePages')||{}).value)||50
  };
  post('/api/explorer/chat/start',body).then(function(r){
    if(r&&r.chat_id){_exploreChatId=r.chat_id;exploreChatBubble('assistant',r.reply||'你好！')}
  }).catch(function(e){_exploreChatStarted=false;toast('Chat start failed: '+e.message,'error')});
}

function exploreChatSend(){
  var inp=_el('exploreChatInput');if(!inp)return;
  var text=(inp.value||'').trim();if(!text)return;
  if(!_exploreChatId){_exploreChatStarted=false;exploreChatStart();setTimeout(function(){exploreChatSend()},600);return}
  inp.value='';
  exploreChatBubble('user',text);
  var btn=_el('exploreChatSendBtn');if(btn)btn.disabled=true;
  post('/api/explorer/chat/message',{chat_id:_exploreChatId,message:text}).then(function(r){
    if(btn)btn.disabled=false;
    exploreChatBubble('assistant',r.reply||'(no reply)');
    if(r.action==='started'&&r.explore_session_id){
      _exploreSessionId=r.explore_session_id;
      var prog=_el('exploreProgress');if(prog)prog.style.display='';
      var res=_el('exploreResults');if(res)res.style.display='none';
      var st=_el('exploreStatus');if(st)st.textContent=t('explorer_chat_starting')||'Exploration started...';
      var bar=_el('exploreProgressBar');if(bar)bar.style.width='15%';
      _exploreStartTs=Date.now();
      if(_exploreTimer)clearInterval(_exploreTimer);
      _exploreTimer=setInterval(function(){var e=_el('exploreElapsed');if(e)e.textContent=_fmtDur((Date.now()-_exploreStartTs)/1000)},1000);
      if(_explorePoll)clearInterval(_explorePoll);
      _explorePoll=setInterval(explorePollStatus,2000);
      toast(t('explorer_chat_starting')||'Exploration started','success');
    }
  }).catch(function(e){
    if(btn)btn.disabled=false;
    exploreChatBubble('assistant','Network error: '+e.message);
  });
}

// ═══════════════════ 卡点干预 (评测卡点暴露 — 询问用户) ═══════════════════
var _intvSessionId='',_intvTimeoutTs=0,_intvTimeoutS=0,_intvTimer=null;

function showIntervention(data){
  if(!data||!data.question)return;
  var ov=_el('interventionOverlay');if(!ov)return;
  _intvSessionId=data.session_id||'';
  _intvTimeoutS=data.timeout_s||0;
  _intvTimeoutTs=Date.now()+_intvTimeoutS*1000;
  _el('intvQuestion').textContent=data.question;
  var opts=_el('intvOptions');opts.innerHTML='';
  (data.options||[]).forEach(function(o){
    var b=document.createElement('button');
    b.className='btn btn-outline btn-sm intv-opt';
    b.textContent=o;
    b.onclick=function(){intvSubmit(o)};
    opts.appendChild(b);
  });
  var tx=_el('intvText');if(tx)tx.value='';
  ov.classList.add('show');
  if(_intvTimer){clearInterval(_intvTimer);_intvTimer=null}
  if(_intvTimeoutS>0){
    _intvTimer=setInterval(function(){
      var left=Math.max(0,Math.round((_intvTimeoutTs-Date.now())/1000));
      var h=_el('intvTimeoutHint');if(h)h.textContent=left+' '+(t('intv_timeout')||'seconds before default action');
    },1000);
  }
}

function intvSubmit(option){
  var opt=option||'';
  var text=_el('intvText')?_el('intvText').value.trim():'';
  var answer=text?(opt?opt+': '+text:text):opt;
  if(!answer){toast('请选择一个选项或输入信息','error');return}
  var ov=_el('interventionOverlay');if(ov)ov.classList.remove('show');
  if(_intvTimer){clearInterval(_intvTimer);_intvTimer=null}
  var sid=_intvSessionId;_intvSessionId='';
  post('/api/tests/intervention/respond',{session_id:sid,answer:answer}).then(function(r){
    if(r&&r.status==='ok')toast('已提交 — 评测继续');else toast('卡点已超时, 评测按默认动作继续','error');
  }).catch(function(){toast('提交失败','error')});
}

// 轮询兜底: WS 断开时仍能发现卡点 (10s)
setInterval(function(){
  var ov=_el('interventionOverlay');if(ov&&ov.classList.contains('show'))return;
  get('/api/tests/intervention/pending').then(function(r){
    if(r&&r.pending)showIntervention({session_id:r.session_id,question:r.question,options:r.options,timeout_s:r.timeout_s});
  }).catch(function(){});
},10000);

// ═══════════════════ Export ═══════════════════
window.App={showPage:showPage,loadDashboard:loadDashboard,startEval:startEval,onProfileChange:onProfileChange,toggleTheme:toggleTheme,toggleLang:toggleLang,setTargetUrl:setTargetUrl,phLoad:phLoad,trLoad:trLoad,trStart:trStart,trStop:trStop,reportsLoad:reportsLoad,reportsCompare:reportsCompare,reportsExitCompare:reportsExitCompare,rpSelect:rpSelect,calInit:calInit,calSelect:calSelect,calScore:calScore,calSubmit:calSubmit,calSkip:calSkip,testStart:trStart,testStop:trStop,exploreStart:exploreStart,exploreCancel:exploreCancel,exploreUseSchema:exploreUseSchema,exploreViewSchema:exploreViewSchema,exploreDownloadSchema:exploreDownloadSchema,exploreLoadHistory:exploreLoadHistory,exploreLoadResult:exploreLoadResult,exploreChatStart:exploreChatStart,exploreChatSend:exploreChatSend,intvSubmit:intvSubmit,showIntervention:showIntervention};

document.addEventListener('DOMContentLoaded',function(){
  document.getElementById('langToggle').textContent=_lang=='zh'?'EN':'CN';
  var savedUrl=localStorage.getItem('targetUrl');if(savedUrl){_targetUrl=savedUrl;document.getElementById('targetUrl').value=savedUrl}
  loadDashboard();onProfileChange();setTimeout(connectWS,500);
});
})();
