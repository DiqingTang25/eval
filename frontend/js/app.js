/* AI Agent Evaluation Platform v3.6 — Frontend App */
(function(){'use strict';

var API=(function(){try{var p=location.pathname;return(p.startsWith('/test/')||p==='/test')?'/test':''}catch(e){return''}})();
var DIMS=['correctness','relevancy','completeness','guidance','followup_quality','boundary_compliance','turn_consistency','knowledge_scaffolding','overhelping','fairness_bias'];

function escHtml(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function get(u){return fetch(API+u).then(function(r){return r.json()})}
function post(u,b){return fetch(API+u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(function(r){return r.json()})}
function t(k){var fn=window.t||function(x){return x};return fn.apply(null,arguments)}
function toast(msg,type){type=type||'info';var c=document.getElementById('toastContainer');if(!c)return;var d=document.createElement('div');d.className='toast-item';d.style.background=type==='error'?'var(--red2)':type==='success'?'var(--green2)':'var(--surface)';d.style.borderColor=type==='error'?'var(--red)':type==='success'?'var(--green)':'var(--border)';d.textContent=msg;c.appendChild(d);setTimeout(function(){d.style.opacity='0';d.style.transition='opacity .3s';setTimeout(function(){d.remove()},300)},3000)}

var _currentPage='dashboard';

function showPage(name){
  _currentPage=name;
  document.querySelectorAll('.page').forEach(function(p){p.classList.remove('active')});
  document.querySelectorAll('.sidebar-nav a').forEach(function(a){a.classList.remove('active')});
  var el=document.getElementById('page-'+name);if(!el)return;
  el.classList.add('active');
  var nv=document.querySelector('.sidebar-nav a[data-page="'+name+'"]');if(nv)nv.classList.add('active');
  if(name==='dashboard'){loadDashboard();return}
  if(name==='platform-health'){phLoad();return}
  if(name==='test-runner'){trLoad();return}
  if(name==='reports'){reportsLoad();return}
  if(name==='calibration'){calInit();return}
}

function applyI18n(){
  var els=document.querySelectorAll('[data-i18n]');
  for(var i=0;i<els.length;i++){var k=els[i].getAttribute('data-i18n');if(k)els[i].textContent=t(k)}
  var opts=document.querySelectorAll('[data-i18n-opt]');
  for(var j=0;j<opts.length;j++){var ok=opts[j].getAttribute('data-i18n-opt');if(ok)opts[j].textContent=t(ok)}
}

function toggleTheme(){
  var e=document.documentElement,th=e.getAttribute('data-theme')==='dark'?'light':'dark';
  e.setAttribute('data-theme',th);localStorage.setItem('theme',th);
}

function toggleLang(){
  var cur=localStorage.getItem('lang')||'zh',next=cur==='zh'?'en':'zh';
  localStorage.setItem('lang',next);
  if(window.setLang)window.setLang(next);
  document.getElementById('langToggle').textContent=next==='zh'?'EN':'CN';
  applyI18n();
  showPage(_currentPage);
}

// ═══════════════════ Dashboard ═══════════════════
var trendChart=null,radarChart=null;

function loadDashboard(){
  var s=document.getElementById('statGrid');
  get('/api/dashboard/summary').then(function(d){
    s.innerHTML=[
      {v:d.total_tests||0,l:'card_total_tests'},
      {v:(d.avg_overall||0).toFixed(2),l:'card_avg_score'},
      {v:d.qa_approved||0,l:'card_qa_approved'},
      {v:d.qa_pending||0,l:'card_qa_pending'}
    ].map(function(x){return'<div class="card"><div class="stat-label">'+t(x.l)+'</div><div class="stat-val">'+x.v+'</div></div>'}).join('');
    renderCharts(d);
  }).catch(function(){});

  get('/api/dashboard/sessions?page_size=5').then(function(r){
    var el=document.getElementById('recentReports');if(!el)return;
    if(r&&r.items&&r.items.length)el.innerHTML=r.items.map(function(x){return'<span class="badge badge-blue" style="margin:2px">'+escHtml(x.agent_id)+' &middot; '+(x.status||'?')+'</span>'}).join(' ');
    else el.innerHTML='<div class="empty-state">'+t('reports_no_data')+'</div>';
  }).catch(function(){});

  get('/api/agents').then(function(a){
    var sel=document.getElementById('agentSelect');if(!sel)return;
    var keys=Object.keys(a||{}).filter(function(k){return k==='platform'});
    sel.innerHTML=keys.length?keys.map(function(k){return'<option value="'+k+'">'+(a[k]&&a[k].name||k)+'</option>'}).join(''):'<option value="platform">Teaching Platform</option>';
  }).catch(function(){});
}

function renderCharts(d){
  if(typeof Chart==='undefined')return;
  var labels=DIMS.slice(0,8).map(function(k){return t('dim_'+k)});
  var dark=document.documentElement.getAttribute('data-theme')==='dark';
  var grid=dark?'rgba(148,163,184,.12)':'rgba(100,116,139,.1)';
  var tick=dark?'#9498b0':'#5a5f72';
  var sky=dark?'#6b8cff':'#4f6ef7';
  var fill=dark?'rgba(107,140,255,.1)':'rgba(79,110,247,.08)';
  Chart.defaults.color=tick;

  var tEl=document.getElementById('trendChart');
  if(tEl){
    var trend=(d.trend||[]).slice().reverse();
    if(trendChart)trendChart.destroy();
    trendChart=new Chart(tEl,{type:'line',data:{labels:trend.map(function(p,i){return p.ts?String(p.ts).replace('T',' ').substring(5,16):(i+1)}),datasets:[{data:trend.map(function(p){return p.score}),borderColor:sky,backgroundColor:fill,fill:true,tension:.35,borderWidth:2,pointRadius:3,pointBackgroundColor:sky}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{min:0,max:5,ticks:{stepSize:1},grid:{color:grid}},x:{grid:{color:grid}}}}});
  }
  var rEl=document.getElementById('radarChart');
  if(rEl){
    var latest=d.latest||{};
    if(radarChart)radarChart.destroy();
    radarChart=new Chart(rEl,{type:'radar',data:{labels:labels,datasets:[{data:DIMS.slice(0,8).map(function(k){return latest[k]||0}),borderColor:sky,backgroundColor:fill,borderWidth:2,pointRadius:3,pointBackgroundColor:sky}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{r:{min:0,max:5,ticks:{stepSize:1,backdropColor:'transparent'},grid:{color:grid},pointLabels:{color:tick}}}}});
  }
}

function onProfileChange(){
  var v=document.getElementById('evalProfile').value;
  document.getElementById('customOpts').style.display=v==='custom'?'inline-flex':'none';
}

function startEval(){
  var profile=document.getElementById('evalProfile').value;
  var panel=document.getElementById('liveEvalPanel'),body=document.getElementById('liveEvalBody'),bar=document.getElementById('evalStatus');
  if(panel)panel.style.display='block';if(bar){bar.style.display='block';bar.innerHTML='<span style="color:var(--accent)">Starting evaluation...</span>'}
  if(body)body.innerHTML='';
  var presets={patrol:{phases:[1,2,3,4,5],mode:'guided',include_quiz:true},full:{phases:[1,2,3,4,5],mode:'guided',include_quiz:true},deep:{phases:[1,2,3,4,5],mode:'both',include_quiz:true}};
  var params,endpoint;
  if(profile==='custom'){params={agent_id:'platform',num_questions:parseInt(document.getElementById('numQuestions').value)||3,max_turns:parseInt(document.getElementById('maxTurns').value)||3,profile:'custom'};endpoint='/api/tests/run'}
  else{params=presets[profile]||presets.full;endpoint='/api/tests/run-browser'}
  post(endpoint,params).then(function(data){
    if(body)body.innerHTML=data.status==='started'?'<div class="log-line" style="color:var(--green)">Started: '+data.session_id+'</div>':'<div class="log-line" style="color:var(--red)">Failed: '+JSON.stringify(data)+'</div>';
  }).catch(function(e){if(body)body.innerHTML='<div class="log-line" style="color:var(--red)">Error: '+e.message+'</div>'});
}

// ═══════════════════ Platform Health ═══════════════════
function phLoad(){
  get('/api/dashboard/heartbeat').then(function(hb){
    var s=document.getElementById('phStatus');if(!s)return;
    var ok=hb&&hb.status==='ok';
    s.innerHTML='<span class="badge '+(ok?'badge-green':'badge-red')+'">'+(ok?'Platform Online &middot; '+(hb.latency_ms||0).toFixed(0)+'ms':'Platform Unreachable')+'</span>';
  }).catch(function(){});
  get('/api/dashboard/interaction').then(function(d){
    var el=document.getElementById('phInteraction');if(!el||!d){if(el)el.innerHTML='<span class="text-muted">No data</span>';return}
    el.innerHTML=[
      ['Health Score',((d.health_score||0)*100).toFixed(0)+'%'],
      ['Features Passed',(d.features_ok||0)+'/'+(d.features_total||0)],
      ['API Latency P50',(d.latency_p50||0)+'ms'],
      ['API Latency P95',(d.latency_p95||0)+'ms']
    ].map(function(x){return'<div class="key-val"><span>'+x[0]+'</span><strong>'+x[1]+'</strong></div>'}).join('');
  }).catch(function(){});
  get('/api/dashboard/technical-metrics').then(function(d){
    var el=document.getElementById('phTechMetrics');if(!el||!d){if(el)el.innerHTML='<span class="text-muted">No data</span>';return}
    el.innerHTML=[
      ['Total Evaluations',d.total_evals||0],
      ['Average Score',(d.avg_score||0).toFixed(2)],
      ['Total Tokens',d.total_tokens?(d.total_tokens/1000).toFixed(0)+'K':'-'],
      ['Avg Duration',d.avg_duration?(d.avg_duration/60).toFixed(1)+'min':'-']
    ].map(function(x){return'<div class="key-val"><span>'+x[0]+'</span><strong>'+x[1]+'</strong></div>'}).join('');
  }).catch(function(){});
  document.getElementById('phRefreshBtn').onclick=phLoad;
  document.getElementById('phFullRefreshBtn').onclick=function(){get('/api/dashboard/interaction/refresh').then(function(){toast('Full health check triggered, please wait 2-3 minutes')})};
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
  post('/api/tests/run-browser',params).then(function(data){
    if(data.status==='started'){
      _trRunning=true;_trSid=data.session_id;
      document.getElementById('trStartBtn').style.display='none';
      document.getElementById('trStopBtn').style.display='';
      document.getElementById('trStatus').innerHTML='<span class="badge badge-green">Running: '+data.session_id+'</span>';
      document.getElementById('trEventLog').innerHTML='';
      trPoll();
    }else toast('Start failed: '+JSON.stringify(data),'error');
  }).catch(function(e){toast('Error: '+e.message,'error')});
}
function trStop(){
  if(!_trSid)return;
  post('/api/tests/cancel',{session_id:_trSid}).then(function(){
    _trRunning=false;_trSid=null;
    document.getElementById('trStartBtn').style.display='';
    document.getElementById('trStopBtn').style.display='none';
    document.getElementById('trStatus').innerHTML='<span class="badge badge-amber">Stopped</span>';
    trSessions();
  }).catch(function(){});
}
function trPoll(){
  if(!_trRunning||!_trSid)return;
  get('/api/tests/sessions/'+_trSid+'/logs').then(function(data){
    var el=document.getElementById('trEventLog');if(!el||!data.logs)return;
    el.innerHTML=data.logs.map(function(l){return'<div class="log-line"><span style="color:var(--text3)">'+(l.ts||'').substring(11,19)+'</span>  '+escHtml(l.msg||l.event||'')+'</div>'}).join('');
    el.scrollTop=el.scrollHeight;
  }).catch(function(){});
  if(_trRunning)setTimeout(trPoll,2000);
}
function trSessions(){
  get('/api/tests/sessions').then(function(data){
    var el=document.getElementById('trSessions');if(!el)return;
    var items=data.items||[];if(!items.length){el.innerHTML='<div class="empty-state">'+t('test_no_history')+'</div>';return}
    el.innerHTML=items.map(function(s){return'<div class="list-item"><div class="flex-between"><strong>'+escHtml(s.agent_id)+'</strong><span class="badge '+(s.status==='completed'?'badge-green':s.status==='running'?'badge-blue':'badge-amber')+'">'+s.status+'</span></div><div style="font-size:11px;color:var(--text3);margin-top:4px">'+(s.created_at||'').substring(0,16)+' &middot; '+(s.total_scenarios||'?')+' scenarios</div></div>'}).join('');
  }).catch(function(){});
}

// ═══════════════════ Reports ═══════════════════
var _rpCmpIds=[];
function reportsLoad(){
  get('/api/reports?page_size=50').then(function(data){
    var el=document.getElementById('rpList');if(!el)return;
    var items=data.items||[];if(!items.length){el.innerHTML='<div class="empty-state">'+t('reports_no_data')+'</div>';return}
    el.innerHTML=items.map(function(r){
      return'<div class="list-item" onclick="App.rpSelect(\''+r.id+'\')"><div class="flex-between"><strong>'+escHtml(r.agent_id||'?')+'</strong><span>'+(r.overall_score!=null?r.overall_score.toFixed(2):'?')+' / 5.0</span></div><div style="font-size:11px;color:var(--text3);margin-top:4px">'+(r.created_at||'').substring(0,16)+(_rpCmpIds.indexOf(r.id)>=0?' &middot; <span class="badge badge-blue">Selected</span>':'')+'</div></div>';
    }).join('');
  }).catch(function(){});
}
function rpSelect(id){
  if(_rpCmpIds.length>0){var idx=_rpCmpIds.indexOf(id);if(idx>=0)_rpCmpIds.splice(idx,1);else if(_rpCmpIds.length<5)_rpCmpIds.push(id);reportsLoad();if(_rpCmpIds.length>=2)rpCompare();return}
  get('/api/reports/'+id).then(function(r){
    var el=document.getElementById('rpDetail');if(!el)return;
    var html='<h3>'+escHtml(r.agent_id||'Report')+'</h3>';
    html+='<div class="key-val"><span>Overall Score</span><strong>'+(r.overall_score!=null?r.overall_score.toFixed(2):'?')+'</strong></div>';
    html+='<div class="key-val"><span>Created</span><span>'+(r.created_at||'')+'</span></div>';
    if(r.scores){html+='<table style="margin-top:12px"><thead><tr><th>Dimension</th><th>Score</th></tr></thead><tbody>';
      DIMS.forEach(function(d){var v=r.scores[d];if(v!=null)html+='<tr><td>'+t('dim_'+d)+'</td><td><strong>'+Number(v).toFixed(1)+'</strong></td></tr>'});
      html+='</tbody></table>'}
    if(r.html_content)html+='<div style="margin-top:16px">'+r.html_content+'</div>';
    else if(r.markdown_content)html+='<pre style="white-space:pre-wrap;font-size:12px;margin-top:12px;background:var(--bg);padding:12px;border-radius:6px">'+escHtml(r.markdown_content.substring(0,5000))+'</pre>';
    el.innerHTML=html;
  }).catch(function(){document.getElementById('rpDetail').innerHTML='<div class="empty-state" style="color:var(--red)">Load failed</div>'});
}
function reportsCompare(){_rpCmpIds=[];document.getElementById('rpCompareBtn').style.display='none';document.getElementById('rpExitCompareBtn').style.display='';reportsLoad()}
function reportsExitCompare(){_rpCmpIds=[];document.getElementById('rpCompareBtn').style.display='';document.getElementById('rpExitCompareBtn').style.display='none';document.getElementById('rpDetail').innerHTML='<div class="empty-state">Select a report to view details</div>';reportsLoad()}
function rpCompare(){
  Promise.all(_rpCmpIds.map(function(id){return get('/api/reports/'+id)})).then(function(results){
    var el=document.getElementById('rpDetail');if(!el)return;
    var html='<h3>Report Comparison ('+results.length+')</h3><div style="overflow-x:auto"><table><thead><tr><th>Dimension</th>';
    results.forEach(function(r){html+='<th>'+escHtml((r.agent_id||'').substring(0,12))+'</th>'});
    html+='</tr></thead><tbody>';
    DIMS.forEach(function(d){html+='<tr><td>'+t('dim_'+d)+'</td>';results.forEach(function(r){var v=(r.scores||{})[d];html+='<td>'+(v!=null?Number(v).toFixed(1):'-')+'</td>'});html+='</tr>'});
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
  get('/api/calibration/items?limit=20&unscored_only=true').then(function(data){
    _calItems=data.items||data||[];_calIdx=0;_calScores={};calRenderList();
    get('/api/calibration/progress').then(function(p){document.getElementById('calProg').textContent=(p.scored||0)+'/'+(p.total||0)+' scored'});
    if(_calItems.length>0)calSelect(0);
  }).catch(function(e){document.getElementById('calItems').innerHTML='<div class="empty-state">Load failed: '+escHtml(e.message)+'</div>'});
}
function calRenderList(){
  var el=document.getElementById('calItems');if(!el)return;
  if(!_calItems.length){el.innerHTML='<div class="empty-state">No pending items</div>';return}
  el.innerHTML=_calItems.map(function(item,i){
    return'<div class="list-item'+(i===_calIdx?' active':'')+'" onclick="App.calSelect('+i+')"><div>#'+(item.qa_id||item.id||i+1)+' '+escHtml((item.question||'').substring(0,50))+'</div><div style="font-size:11px;color:var(--text3);margin-top:2px">'+(item.phase||'')+' &middot; '+(item.type||'')+' '+(item.scored?'<span class="badge badge-green">Scored</span>':'<span class="badge badge-amber">Pending</span>')+'</div></div>';
  }).join('');
}
function calSelect(idx){
  _calIdx=idx;calRenderList();var item=_calItems[idx];if(!item)return;
  var el=document.getElementById('calScore');if(!el)return;
  var html='<div style="margin-bottom:12px"><div class="key-val"><span>Question</span><span>'+escHtml(item.question||'')+'</span></div>';
  html+='<div class="key-val"><span>Agent Response</span><span>'+escHtml((item.agent_answer||item.answer||'').substring(0,300))+'</span></div></div>';
  DIMS.forEach(function(d){
    html+='<div class="cal-dim-row"><span class="cal-dim-name">'+t('dim_'+d)+'</span>';
    for(var s=1;s<=5;s++)html+='<button class="cal-score-btn'+( _calScores[d]===s?' sel':'')+'" onclick="App.calScore(\''+d+'\','+s+')">'+s+'</button>';
    html+='<span style="margin-left:6px;font-size:11px;color:var(--text3)">'+(_calScores[d]?_calScores[d]+'/5':'-')+'</span></div>';
  });
  html+='<div class="flex" style="margin-top:12px"><button class="btn btn-primary btn-sm" onclick="App.calSubmit()">Submit Score</button><button class="btn btn-outline btn-sm" onclick="App.calSkip()">Skip</button></div>';
  el.innerHTML=html;
}
function calScore(dim,s){_calScores[dim]=s;calSelect(_calIdx)}
function calSubmit(){
  var item=_calItems[_calIdx];if(!item)return;
  if(Object.keys(_calScores).length<8){toast('Please score at least 8 dimensions','error');return}
  post('/api/calibration/score',{qa_id:item.qa_id||item.id,scores:_calScores}).then(function(){
    toast('Score submitted','success');_calItems[_calIdx].scored=true;_calScores={};
    calLoad();calStats();var next=_calIdx+1;if(next<_calItems.length)calSelect(next);
  }).catch(function(e){toast('Submit failed: '+e.message,'error')});
}
function calSkip(){var next=_calIdx+1;if(next<_calItems.length){_calScores={};calSelect(next)}}
function calStats(){
  get('/api/calibration/results').then(function(r){
    var el=document.getElementById('calStats');if(!el)return;
    var html='';
    html+='<div class="key-val"><span>Cohen\'s Kappa</span><strong>'+((r.cohens_kappa||0).toFixed(3))+'</strong></div>';
    html+='<div class="key-val"><span>Spearman Rho</span><strong>'+((r.spearman_rho||0).toFixed(3))+'</strong></div>';
    html+='<div class="key-val"><span>MAE</span><strong>'+((r.mae||0).toFixed(2))+'</strong></div>';
    html+='<div class="key-val"><span>Scored</span><strong>'+(r.scored_count||0)+'/'+(r.total_count||0)+'</strong></div>';
    if(r.per_dimension)Object.keys(r.per_dimension).forEach(function(d){var v=r.per_dimension[d];html+='<div class="key-val"><span>'+t('dim_'+d)+'</span><span>bias: '+((v.bias||0).toFixed(2))+'</span></div>'});
    el.innerHTML=html;
  }).catch(function(){});
}

// ═══════════════════ WebSocket ═══════════════════
var _ws=null,_wsRc=0;
function connectWS(){
  try{
    var proto=location.protocol==='https:'?'wss':'ws';
    _ws=new WebSocket(proto+'://'+location.host+API+'/ws');
    _ws.onopen=function(){_wsRc=0;var el=document.getElementById('wsDot');if(el)el.style.background='var(--green)';var lb=document.getElementById('wsLabel');if(lb)lb.textContent=t('sys_ws_connected')};
    _ws.onclose=function(){var el=document.getElementById('wsDot');if(el)el.style.background='var(--red)';var lb=document.getElementById('wsLabel');if(lb)lb.textContent=t('sys_ws_disconnected');var d=Math.min(30000,1000*Math.pow(2,_wsRc++));setTimeout(connectWS,d)};
    _ws.onmessage=function(e){
      try{
        var m=JSON.parse(e.data);if(m.type!=='eval_event')return;
        var ev=m.event,data=m.data||{};
        if(ev==='browser_log'){var body=document.getElementById('liveEvalBody');if(body){body.innerHTML+='<div class="log-line">'+escHtml(data.msg||'')+'</div>';body.scrollTop=body.scrollHeight}}
        if(ev==='browser_done'){var b=document.getElementById('liveEvalBody');if(b)b.innerHTML+='<div class="log-line" style="color:var(--green)">Evaluation complete</div>';setTimeout(loadDashboard,2000)}
      }catch(ex){}
    };
  }catch(ex){}
}

// ═══════════════════ Export & Init ═══════════════════
window.App={
  showPage:showPage,loadDashboard:loadDashboard,startEval:startEval,onProfileChange:onProfileChange,
  toggleTheme:toggleTheme,toggleLang:toggleLang,
  phLoad:phLoad,trLoad:trLoad,trStart:trStart,trStop:trStop,
  reportsLoad:reportsLoad,reportsCompare:reportsCompare,reportsExitCompare:reportsExitCompare,rpSelect:rpSelect,
  calInit:calInit,calSelect:calSelect,calScore:calScore,calSubmit:calSubmit,calSkip:calSkip,
  testStart:trStart,testStop:trStop
};

document.addEventListener('DOMContentLoaded',function(){
  var lang=localStorage.getItem('lang')||'zh';
  document.getElementById('langToggle').textContent=lang==='zh'?'EN':'CN';
  loadDashboard();onProfileChange();setTimeout(connectWS,500);
});
})();
