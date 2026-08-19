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
  nav_explorer:{zh:'平台探索',en:'Explorer'},
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
  explorer_start_btn:{zh:'开始探索',en:'Start Exploration'},
  explorer_cancel_btn:{zh:'取消',en:'Cancel'},
  explorer_use_schema:{zh:'使用此 Schema',en:'Use Schema'},
  explorer_view_schema:{zh:'查看 Schema',en:'View Schema'},
  explorer_download_schema:{zh:'下载 Schema',en:'Download'},
  explorer_schema_active:{zh:'Schema 模式已激活',en:'Schema Active'},
  schema_indicator:{zh:'Schema 模式',en:'Schema Mode'},
  explorer_chat_title:{zh:'对话式探索',en:'Conversational Explorer'},
  explorer_chat_hint:{zh:'用自然语言描述探索任务，缺什么我会问你',en:'Describe the exploration in natural language — I will ask for what is missing.'},
  explorer_chat_send:{zh:'发送',en:'Send'},
  explorer_chat_starting:{zh:'探索已启动',en:'Exploration started'},
  explorer_chat_start:{zh:'开始探索',en:'Start exploration'},
  explorer_chat_adjust:{zh:'先调整',en:'Adjust first'},
  intv_reason:{zh:'为什么',en:'Why'},
  intv_recovery:{zh:'怎么办',en:'What to do'},
  intv_title:{zh:'⚠️ 评测遇到卡点 — 需要你的输入',en:'⚠️ Evaluation blocked — your input needed'},
  intv_submit:{zh:'提交',en:'Submit'},
  intv_timeout:{zh:'秒后自动按默认处理',en:'s before default action'},
  wf_heading:{zh:'开始使用',en:'Getting Started'},
  wf_step1_title:{zh:'探索平台结构',en:'Explore Platform'},
  wf_step1_desc:{zh:'自动发现教学阶段、课时步骤和 API 端点，生成平台结构描述文件，为后续测评提供准确的对接信息。',en:'Auto-discover teaching phases, lessons, and API endpoints. Generate a platform schema to power accurate evaluations.'},
  wf_step1_link:{zh:'前往 Explorer',en:'Go to Explorer'},
  wf_step2_title:{zh:'运行智能测评',en:'Run Evaluation'},
  wf_step2_desc:{zh:'基于平台结构自动生成测试场景，从正确性、完整性、引导质量等 10 个维度评估 AI Agent 表现。',en:'Auto-generate test scenarios from the platform schema. Evaluate AI agent quality across 10 dimensions including correctness, completeness, and guidance.'},
  wf_step2_link:{zh:'前往 Test Runner',en:'Go to Test Runner'},
  wf_step3_title:{zh:'查看详细报告',en:'Review Reports'},
  wf_step3_desc:{zh:'查看分数趋势与维度雷达图，对比多次测评结果，通过人工校准持续提升评分可信度。',en:'Explore score trends and dimension radar charts. Compare evaluations and calibrate scores for maximum reliability.'},
  wf_step3_link:{zh:'前往 Reports',en:'Go to Reports'},
  tr_no_schema:{zh:'尚未探索 — 将使用默认配置。',en:'No schema yet — using default config.'},
  tr_explore_first:{zh:'先探索平台 →',en:'Explore platform first →'},
  schema_badge_explored:{zh:'Schema 就绪',en:'Schema Ready'},
  schema_badge_none:{zh:'未探索',en:'Not Explored'},
  ph_working:{zh:'正常',en:'Working'},
  ph_degraded:{zh:'降级',en:'Degraded'},
  ph_broken:{zh:'故障',en:'Broken'},
  health_no_data:{zh:'暂无健康度数据，点击下方 Refresh 触发检查',en:'No health data. Click Refresh to run a check.'},
  health_load_failed:{zh:'加载失败',en:'Failed to load'},
  health_all_ok:{zh:'所有功能正常',en:'All features working'},
  health_refresh_triggered:{zh:'全量健康检查已触发，预计2-3分钟完成',en:'Full health check triggered, takes 2-3 min'},
  health_refresh_btn:{zh:'刷新检查',en:'Refresh Check'},
  health_full_check:{zh:'全量健康检查',en:'Full Health Check'},
  health_categories:{zh:'功能分类',en:'Feature Categories'},
  health_issues:{zh:'关键问题',en:'Critical Issues'},
  health_score_label:{zh:'健康度',en:'Health'},
  health_stale:{zh:'数据过期',en:'Stale'},
  health_stale_hint:{zh:'点击触发全量健康检查',en:'Click to run full health check'},
  health_no_data_short:{zh:'暂无数据 — 点击下方全量健康检查',en:'No data — run Full Health Check below'},
  health_refreshing:{zh:'检查中...',en:'Checking...'},
  ph_blocked:{zh:'阻塞',en:'blocked'},
  ph_working_short:{zh:'正常',en:'OK'},
  ph_degraded_short:{zh:'降级',en:'DEG'},
  ph_broken_short:{zh:'故障',en:'BRK'},
  ph_trigger_full:{zh:'触发全量检查',en:'Run full check'},
  eval_starting:{zh:'正在初始化测评...',en:'Initializing evaluation...'},
  eval_login:{zh:'正在登录教学平台',en:'Logging into platform'},
  eval_navigating:{zh:'正在进入课程内容',en:'Navigating to course content'},
  eval_learning:{zh:'正在进入学习模式',en:'Entering learning mode'},
  eval_completing_steps:{zh:'正在完成教学步骤',en:'Completing teaching steps'},
  eval_agent_chat:{zh:'正在测评AI Agent对话',en:'Evaluating AI Agent chat'},
  eval_quiz:{zh:'正在检查Quiz功能',en:'Checking quiz functionality'},
  eval_complete:{zh:'测评完成',en:'Evaluation complete'},
  eval_error:{zh:'测评出错',en:'Evaluation error'},
  eval_phase:{zh:'阶段',en:'Phase'},
  eval_phase_short:{zh:'阶段',en:'Ph'},
  eval_day:{zh:'第',en:'Day'},
  health_target:{zh:'目标平台',en:'Target Platform'},
  health_system:{zh:'评测系统',en:'Evaluation System'},
  health_platform_url:{zh:'平台地址',en:'Platform URL'},
  health_total_tests:{zh:'历史测评总数',en:'Total Evaluations'},
  health_avg_score:{zh:'最近平均分',en:'Latest Avg Score'},
  health_qa_approved:{zh:'已审核QA',en:'Approved QA'},
  health_ws_status:{zh:'WebSocket',en:'WebSocket'},
  health_ws_connecting:{zh:'连接中...',en:'Connecting...'},
  health_reachable:{zh:'平台可达性',en:'Reachability'},
  health_target_help:{zh:'检查被测评的教学平台是否在线、能否正常登录和对话',en:'Checks if the target teaching platform is online, login works, and the AI agent can respond'},
  health_system_help:{zh:'评测平台自身运行状态：API服务、数据库连接、实时通信',en:'Status of the evaluation platform: API server, database, real-time communication'},
  rp_strength:{zh:'优势维度',en:'Strengths'},
  rp_weakness:{zh:'待提升',en:'Needs Work'},
  rp_dimension:{zh:'评测维度',en:'Dimension'},
  rp_score:{zh:'得分',en:'Score'},
  home_hero_title:{zh:'AI Agent 评测平台',en:'AI Agent Evaluation Platform'},
  home_hero_desc:{zh:'自动化评估教学平台 AI Agent 质量',en:'Automated quality evaluation for teaching platform AI agents'},
  home_chart_empty:{zh:'完成首次测评后自动生成',en:'Charts appear after first evaluation'},
  tr_preflight_title:{zh:'测评预检',en:'Pre-Flight Check'},
  tr_preflight_url:{zh:'目标平台',en:'Target Platform'},
  tr_preflight_profile:{zh:'使用已探索的平台结构',en:'Using explored platform structure'},
  tr_preflight_no_profile:{zh:'未探索 — 将使用默认配置',en:'Not explored — using default config'},
  tr_preflight_confirm:{zh:'确认启动',en:'Confirm & Start'},
  tr_preflight_cancel:{zh:'取消',en:'Cancel'},
  rp_download:{zh:'下载报告',en:'Download Report'},
  // Multi-Agent
  ma_mode_browser:{zh:'浏览器',en:'Browser'},
  ma_mode_multi:{zh:'Multi-Agent',en:'Multi-Agent'},
  ma_strategy:{zh:'策略',en:'Strategy'},
  ma_phases:{zh:'阶段',en:'Phases'},
  ma_estimated:{zh:'预计',en:'Estimated'},
  ma_planner:{zh:'计划生成',en:'Planner'},
  ma_executor:{zh:'执行',en:'Executor'},
  ma_verifier:{zh:'验证',en:'Verifier'},
  ma_reporter:{zh:'报告',en:'Reporter'},
  ma_plan_ready:{zh:'计划就绪',en:'Plan ready'},
  ma_step_verifying:{zh:'验证中',en:'Verifying'},
  ma_verdict_pass:{zh:'通过',en:'PASS'},
  ma_verdict_fail:{zh:'失败',en:'FAIL'},
  ma_text:{zh:'文本',en:'Text'},
  ma_visual:{zh:'视觉',en:'Visual'},
  ma_api:{zh:'API',en:'API'},
  ma_channels:{zh:'通道',en:'Channels'},
  ma_no_schema:{zh:'未探索平台结构，无法使用 Multi-Agent 模式',en:'No platform schema — Multi-Agent mode unavailable'},
  ma_done:{zh:'Multi-Agent 测评完成',en:'Multi-Agent evaluation complete'},
  health_self_healing:{zh:'自愈事件',en:'Self-Healing'},
  health_visual_assert:{zh:'视觉断言',en:'Visual Assertion'},
  health_coverage:{zh:'覆盖率',en:'Coverage'}
};
function t(k){if(window.I18n&&window.I18n.t){var ext=window.I18n.t(k);if(ext&&ext!==k&&ext!==_keyToTextFallback(k))return ext}var e=_dict[k];if(e){var v=e[_lang]||e.zh;if(v)return v}return k}
function _keyToTextFallback(k){return k.replace(/_/g,' ').replace(/\b\w/g,function(c){return c.toUpperCase()})}
function setLang(l){_lang=l;if(window._i18nExt){for(var k in window._i18nExt){if(!_dict[k])_dict[k]=window._i18nExt[k]}}}

// Merge external i18n.js dictionary if loaded
window._i18nExt=null;
window._mergeI18n=function(ext){window._i18nExt=ext}

function escHtml(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function get(u){return fetch(API+u).then(function(r){return r.json()})}
function post(u,b){return fetch(API+u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(function(r){return r.json()})}
function toast(msg,type){type=type||'info';var c=document.getElementById('toastContainer');if(!c)return;var d=document.createElement('div');d.className='toast-item';d.style.background=type==='error'?'var(--red2)':type==='success'?'var(--green2)':'var(--surface)';d.style.borderColor=type==='error'?'var(--red)':type==='success'?'var(--green)':'var(--border)';d.textContent=msg;c.appendChild(d);setTimeout(function(){d.style.opacity='0';d.style.transition='opacity .3s';setTimeout(function(){d.remove()},300)},3500)}

var _currentPage='dashboard', _targetUrl='', _platformProfile=null;

function setTargetUrl(url){_targetUrl=url||'';localStorage.setItem('targetUrl',_targetUrl);var i=_el('targetUrl');if(i)i.value=_targetUrl;if(_currentPage==='platform-health')phLoad()}

var _platformProfile=null,_profilePolling=false;

function loadProfile(){
  if(_profilePolling)return;
  _profilePolling=true;
  fetch(API+'/api/explorer/profile/latest').then(function(r){
    if(!r.ok)throw new Error('HTTP '+r.status);
    return r.json();
  }).then(function(p){
    _platformProfile=p;
    if(p&&p.available){
      // 自动填入URL
      if(p.target_url&&!_targetUrl){_targetUrl=p.target_url;var tu=_el('targetUrl');if(tu)tu.value=p.target_url}
      // 自动启用schema模式
      if(p.schema_path){localStorage.setItem('schemaDriven','true');localStorage.setItem('schemaPath',p.schema_path)}
      // 更新凭证 (供Health Check使用)
      if(p.credentials){localStorage.setItem('profileCreds',JSON.stringify(p.credentials))}
    }
    updateSchemaBadge();
    updateSchemaIndicator();
  }).catch(function(e){
    console.error('loadProfile failed:',e);
    // 如果API失败, 尝试从localStorage恢复
    var cached=localStorage.getItem('schemaPath');
    if(cached&&!_platformProfile){
      _platformProfile={available:true,phases_found:0,schema_path:cached,target_url:localStorage.getItem('targetUrl')||''};
    }
  }).finally(function(){_profilePolling=false});
}

function updateSchemaIndicator(){
  var si=_el('schemaIndicator');
  if(si){
    var hasProfile=_platformProfile&&_platformProfile.available;
    var hasLocal=localStorage.getItem('schemaDriven')==='true';
    si.style.display=(hasProfile||hasLocal)?'':'none';
    if(hasProfile)si.textContent='🧬 '+(_platformProfile.session_id||'').slice(-8);
  }
}

function updateSchemaBadge(){
  var dot=_el('schemaDot');if(!dot)return;
  var hasProfile=_platformProfile&&_platformProfile.available;
  var hasLocal=localStorage.getItem('schemaDriven')==='true';
  if(hasProfile||hasLocal){
    dot.style.background='var(--green)';
    dot.title=(hasProfile?'Explored: '+_platformProfile.session_id:'Schema ready');
    dot.style.cursor='default';
    dot.onclick=null;
  }else{
    dot.style.background='var(--text3)';
    dot.title='Not explored — click to discover platform';
    dot.style.cursor='pointer';
    dot.onclick=function(){App.showPage('explorer')};
  }
}

function showPage(name){
  _currentPage=name;
  document.querySelectorAll('.page').forEach(function(p){p.classList.remove('active')});
  document.querySelectorAll('.sidebar-nav a').forEach(function(a){a.classList.remove('active')});
  var el=document.getElementById('page-'+name);if(!el)return;
  el.classList.add('active');el.style.animation='none';el.offsetHeight;el.style.animation='fadeIn .35s var(--transition)';
  var nv=document.querySelector('.sidebar-nav a[data-page="'+name+'"]');if(nv)nv.classList.add('active');
  updateSchemaBadge();
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
  document.getElementById("langToggle").textContent=_lang=="zh"?"EN":"CN";
  showPage(_currentPage);
  if(window.setLang)window.setLang(_lang);
  // Re-apply after async page content renders
  setTimeout(function(){if(window.I18n&&window.I18n.applyStaticI18n)window.I18n.applyStaticI18n()},200);
  setTimeout(function(){if(window.I18n&&window.I18n.applyStaticI18n)window.I18n.applyStaticI18n()},700);
}

// ── Animated number counting ──
function animateValue(el,v){if(!el)return;el.textContent=String(v)}

// ═══════════════════ Dashboard ═══════════════════
var trendChart=null,radarChart=null,_dashboardData=null;

function loadDashboard(){
  get('/api/dashboard/summary').then(function(d){
    _dashboardData=d; // 缓存
    var hasData=d&&d.total_tests>0;
    // Toggle hero vs stat cards
    var hero=_el('dashboardHero');if(hero)hero.style.display=hasData?'none':'';
    var sg=_el('statGrid');if(sg)sg.style.display=hasData?'grid':'none';
    if(hasData){
      var vals=[d.total_tests||0,(d.avg_overall||0).toFixed(2),d.qa_approved||0,d.qa_pending||0];
      for(var i=0;i<4;i++){var el=_el('statVal'+i);if(el)el.textContent=vals[i]}
    }
    // Platform profile card
    var pc=_el('platformCard');
    if(pc&&_platformProfile&&_platformProfile.available){
      pc.style.display='';
      var pu=_el('pfUrl');if(pu)pu.textContent=(_platformProfile.target_url||'').replace(/https?:\/\//,'').substring(0,40);
      var pp=_el('pfPhases');if(pp)pp.textContent=_platformProfile.phases_found||'?';
      var pa=_el('pfAPIs');if(pa)pa.textContent=_platformProfile.api_endpoints_found||'?';
      var pt=_el('pfTime');if(pt)pt.textContent=_platformProfile.explored_at?_platformProfile.explored_at.substring(0,10):'';
    }else if(pc){pc.style.display='none'}
    // Charts: canvas CSS !important 会阻止 Chart.js 内联样式, 创建后必须 resize
    if(hasData&&typeof Chart!=='undefined'){
      renderCharts(d);
      if(trendChart)trendChart.resize();
      if(radarChart)radarChart.resize();
    }else if(hasData){
      // Chart.js 尚未就绪 (本地 chart.umd.min.js 未加载/加载慢) → 重试, 避免图表区空白
      var chartRetry=0;
      (function tryChart(){
        if(typeof Chart!=='undefined'){renderCharts(d);if(trendChart)trendChart.resize();if(radarChart)radarChart.resize();return}
        if(chartRetry++<10)setTimeout(tryChart,500);
        else _drawChartEmpty();
      })();
    }else if(!hasData){_drawChartEmpty()}
  }).catch(function(e){
    // P0 首刷兜底: API 失败时不能整页空白 — 显示 hero + 空图表, 让用户至少看到引导
    console.error('Dashboard summary failed',e);
    var hero=_el('dashboardHero');if(hero)hero.style.display='';
    var sg=_el('statGrid');if(sg)sg.style.display='none';
    _drawChartEmpty();
  });

  updateSchemaBadge();

  get('/api/dashboard/sessions?page_size=5').then(function(r){
    var el=document.getElementById('recentReports');if(!el)return;
    if(r&&r.items&&r.items.length)el.innerHTML=r.items.map(function(x){return'<span class="badge badge-blue" style="margin:2px;animation:fadeIn .3s var(--transition) both">'+escHtml(x.agent_id)+' &middot; '+(x.status||'?')+'</span>'}).join(' ');
    else el.innerHTML='<div class="empty-state">'+t('reports_no_data')+'</div>';
  }).catch(function(e){console.error('Dashboard sessions failed',e)});
}

	function _drawChartEmpty(){
	  var tc=_el('trendChart'),rc=_el('radarChart');
	  if(tc){var ctx=tc.getContext('2d');ctx.clearRect(0,0,tc.width,tc.height);ctx.font='13px system-ui';ctx.fillStyle=getComputedStyle(document.documentElement).getPropertyValue('--text3');ctx.textAlign='center';ctx.fillText(t('home_chart_empty'),tc.width/2,tc.height/2)}
	  if(rc){var ctx2=rc.getContext('2d');ctx2.clearRect(0,0,rc.width,rc.height);ctx2.font='13px system-ui';ctx2.fillStyle=getComputedStyle(document.documentElement).getPropertyValue('--text3');ctx2.textAlign='center';ctx2.fillText(t('home_chart_empty'),rc.width/2,rc.height/2)}
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
  var ep=document.getElementById('evalProfile');if(!ep)return;
  var v=ep.value;
  var co=document.getElementById('customOpts');if(!co)return;
  co.style.display=v==='custom'?'flex':'none';
}

function startEval(){
  // Redirect to Test Runner — evaluation starts there now
  showPage('test-runner');
}

// ═══════════════════ Platform Health ═══════════════════
function phLoad(){
  var targetEl=document.getElementById('phTarget'),sysEl=document.getElementById('phSystem');
  if(targetEl)targetEl.innerHTML='<div class="skeleton" style="height:80px"></div>';
  if(sysEl)sysEl.innerHTML='<div class="skeleton" style="height:80px"></div>';

  // Target Platform: simple reachability check
  get('/api/dashboard/interaction').then(function(d){
    var s=document.getElementById('phStatus');if(!s)return;
    var sum=d&&d.summary||{};
    if(!sum.total){
      s.innerHTML='<span class="badge badge-amber">'+t('health_no_data_short')+'</span>';
      if(targetEl)targetEl.innerHTML='<div class="empty-state">'+t('health_no_data')+'</div>';
      return;
    }
    var score=sum.health_score||0, pct=Math.round(score*100);
    var cls=score>=0.8?'badge-green':score>=0.5?'badge-amber':'badge-red';
    var html='<span class="badge '+cls+'" style="font-size:13px">'+t('health_reachable')+': '+pct+'%</span>';
    if(d.stale){
      var mins=Math.round((d.stale_seconds||0)/60);
      var ago=mins>1440?Math.round(mins/1440)+'d':mins>60?Math.round(mins/60)+'h':mins+'m';
      html+=' <span class="badge badge-amber" style="cursor:pointer" onclick="App.phTriggerFull()">'+t('health_stale')+' ('+ago+')</span>';
    }
    s.innerHTML=html;
    if(targetEl){
      var feats=d&&d.features||{};
      var rows=[];
      ['auth_login','agent_chat','quiz_start'].forEach(function(k){
        var f=feats[k];if(!f)return;
        var fc=f.status==='working'?'badge-green':f.status==='degraded'?'badge-amber':'badge-red';
        rows.push('<div class="kv-row"><span>'+escHtml(f.name||k)+'</span><span class="badge '+fc+'">'+f.status+'</span></div>');
      });
      rows.push('<div class="kv-row"><span>'+t('health_platform_url')+'</span><span style="font-size:11px;color:var(--text3)">'+escHtml(d.platform_url||_targetUrl)+'</span></div>');
      targetEl.innerHTML=rows.join('');
    }
  }).catch(function(){});

  // Evaluation System: our own health
  get('/api/dashboard/summary').then(function(d){
    if(!sysEl)return;
    var wsConnected=_ws&&_ws.readyState===1;
    var wsLabel=wsConnected?t('sys_ws_connected'):t('sys_ws_disconnected');
    var wsCls=wsConnected?'badge-green':'badge-red';
    sysEl.innerHTML=[
      [t('health_total_tests'),d.total_tests||0],
      [t('health_ws_status'),'<span class="badge '+wsCls+'">'+wsLabel+'</span>'],
    ].map(function(x,i){return'<div class="kv-row" style="animation:fadeIn .3s '+(.1*i).toFixed(2)+'s both"><span>'+x[0]+'</span><span class="kv-val">'+x[1]+'</span></div>'}).join('');
  }).catch(function(){if(sysEl)sysEl.innerHTML='<div class="empty-state">'+t('health_load_failed')+'</div>'});

  document.getElementById('phRefreshBtn').onclick=phLoad;
  document.getElementById('phFullRefreshBtn').onclick=function(){
    var btn=_el('phFullRefreshBtn');if(btn){btn.disabled=true;btn.textContent=t('health_refreshing')}
    var s=document.getElementById('phStatus');
    if(s)s.innerHTML='<span class="badge badge-blue" style="animation:pulse 2s infinite">'+t('health_refreshing')+'</span>';
    post('/api/dashboard/interaction/refresh',{target_url:_targetUrl}).then(function(){
      toast(t('health_refresh_triggered'),'success');
      setTimeout(phLoad,8000);
    }).catch(function(){
      toast(t('health_load_failed'),'error');
      if(btn){btn.disabled=false;btn.textContent=t('health_full_check')}
    });
  };
}
function phTriggerFull(){document.getElementById('phFullRefreshBtn').onclick()}

// ═══════════════════ Test Runner ═══════════════════
var _trRunning=false,_trSid=null;
var _trTimerInterval=null;
function trLoad(){
  trSessions();
  var hint=_el('trSchemaHint');
  if(hint){hint.style.display=localStorage.getItem('schemaDriven')==='true'?'none':''}
  document.getElementById('trStartBtn').onclick=trStart;
  document.getElementById('trStopBtn').onclick=trStop;
  // Reset Multi-Agent panel on page entry (unless session running)
  if(!_trRunning){var maPanel=_el('maPanel');if(maPanel)maPanel.style.display='none'}
  // 自动加载profile
  if(!_platformProfile||!_platformProfile.available){loadProfile()}
}
var _trPendingParams=null;
function trStart(){
  var mode=document.getElementById('trMode').value;
  var targetUrl=(_platformProfile&&_platformProfile.target_url)||_targetUrl||localStorage.getItem('targetUrl')||'';
  if(!targetUrl){toast('Please explore a platform first or set a target URL','error');return}

  // 读schema路径: profile > localStorage
  var schemaPath='';
  if(_platformProfile&&_platformProfile.schema_path)schemaPath=_platformProfile.schema_path;
  else schemaPath=localStorage.getItem('schemaPath')||'';
  var schemaDriven=!!schemaPath;

  var params={
    mode:'guided', include_quiz:true,
    target_url:targetUrl,
    schema_driven:schemaDriven, platform_schema_path:schemaPath
  };

  // Show pre-flight confirmation
  _trPendingParams=params;
  var html='<div style="padding:8px 0">';
  html+='<div class="kv-row"><span>'+t('tr_preflight_url')+'</span><span style="font-size:11px">'+escHtml(targetUrl)+'</span></div>';
  html+='<div class="kv-row"><span>Mode</span><span style="font-size:11px">'+(mode==='multi_agent'?'Multi-Agent':'Browser Eval')+'</span></div>';
  html+='<div class="kv-row"><span>Schema</span><span class="badge '+(schemaDriven?'badge-green':'badge-amber')+'">'+(schemaDriven?t('tr_preflight_profile'):t('tr_preflight_no_profile'))+'</span></div>';
  html+='<div class="flex" style="margin-top:12px;gap:8px"><button class="btn btn-primary btn-sm" onclick="App.trConfirmStart()">'+t('tr_preflight_confirm')+'</button><button class="btn btn-outline btn-sm" onclick="App.trCancelPreflight()">'+t('tr_preflight_cancel')+'</button></div></div>';
  var el=_el('trPreflight');if(el){el.innerHTML=html;el.style.display=''}
}
function trConfirmStart(){
  var el=_el('trPreflight');if(el)el.style.display='none';
  if(!_trPendingParams)return;
  var params=_trPendingParams;_trPendingParams=null;
  var mode=document.getElementById('trMode').value;
  var endpoint=mode==='multi_agent'?'/api/tests/run-multi-agent':'/api/tests/run-browser';
  // Multi-Agent: 清空 phases = 全部 (Schema 中 ID 是真实名称如 ai-cad, 不是 phase_N)
  if(mode==='multi_agent'){
    delete params.phases;  // 空=全部, Planner 自己从 Schema 读
  }
  post(endpoint,params).then(function(data){
    if(data.status==='started'){
      _trRunning=true;_trSid=data.session_id;
      document.getElementById('trStartBtn').style.display='none';
      document.getElementById('trStopBtn').style.display='';
      var prog=_el('trProgress');if(prog)prog.style.display='';
      // Multi-Agent 模式下显示专用面板
      if(mode==='multi_agent'){
        _maState={active:false,plan:null,currentStep:null,verifications:[],diagnoses:[],startedAt:0};
        var wsStatus=_ws&&_ws.readyState===WebSocket.OPEN?'WS: Connected':'WS: '+(['CONNECTING','OPEN','CLOSING','CLOSED'][_ws?_ws.readyState:3]||'no WS');
        var maPanel=_el('maPanel');if(maPanel){maPanel.style.display='';maPanel.innerHTML='<div style="font-size:11px;color:var(--text3)">'+wsStatus+' | Waiting for events...</div>'}
        document.getElementById('trStatus').innerHTML='<span class="badge badge-green" style="animation:pulse 2s infinite">Multi-Agent: '+data.session_id+'</span>';
      }else{
        _evalProgress={phase:0,totalPhases:5,day:0,totalDays:0,action:t('eval_starting'),startedAt:Date.now()};
        trRenderProgress();
        document.getElementById('trStatus').innerHTML='<span class="badge badge-green" style="animation:pulse 2s infinite">Running: '+data.session_id+'</span>';
        trPoll();
      }
      document.getElementById('trEventLog').innerHTML='';
    }else toast('Start failed: '+JSON.stringify(data),'error');
  }).catch(function(e){toast('Error: '+e.message,'error')});
}
function trCancelPreflight(){var el=_el('trPreflight');if(el)el.style.display='none';_trPendingParams=null}
function trStop(){
  if(!_trSid)return;
  post('/api/tests/cancel',{session_id:_trSid}).then(function(){
    _trRunning=false;_trSid=null;
    if(_trTimerInterval){clearInterval(_trTimerInterval);_trTimerInterval=null}
    document.getElementById('trStartBtn').style.display='';document.getElementById('trStopBtn').style.display='none';
    var prog=_el('trProgress');if(prog)prog.style.display='none';
    var maPanel=_el('maPanel');if(maPanel)maPanel.style.display='none';
    _maState={active:false,plan:null,currentStep:null,verifications:[],diagnoses:[],startedAt:0};
    document.getElementById('trStatus').innerHTML='<span class="badge badge-amber">Stopped</span>';
    trSessions();
  }).catch(function(){});
}
function trRenderProgress(){
  var p=_evalProgress;
  var act=_el('trCurrentAction');if(act)act.textContent=p.action;
  var timer=_el('trTimer');if(timer&&p.startedAt)timer.textContent=_fmtDur((Date.now()-p.startedAt)/1000);
  if(p.startedAt&&!_trTimerInterval){_trTimerInterval=setInterval(function(){var t=_el('trTimer');if(t&&_evalProgress.startedAt)t.textContent=_fmtDur((Date.now()-_evalProgress.startedAt)/1000)},1000)}
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
// ── Multi-Agent 事件处理 (Agent C) ──
var _maState={active:false,plan:null,currentStep:null,verifications:[],diagnoses:[],startedAt:0};
function _onMultiAgentEvent(m){
  var d=m.data||{},t=m.type;
  // 确保面板可见
  var panel=_el('maPanel');
  if(!_maState.active){_maState.active=true;_maState.startedAt=Date.now();if(panel)panel.style.display=''}
  if(t==='multi_agent:plan_ready'){
    _maState.plan=d;
    _maRenderPanel();
  }
  if(t==='multi_agent:step_start'){
    _maState.currentStep=d;
    _maRenderPanel();
  }
  if(t==='multi_agent:verify_done'){
    _maState.verifications.push(d);
    _maRenderPanel();
  }
  if(t==='multi_agent:diagnosis'){
    _maState.diagnoses.push(d);
    _maRenderPanel();
  }
  if(t==='multi_agent:done'){
    _maState.active=false;
    _maRenderPanel();
    // 完成后刷新 dashboard 和 sessions
    setTimeout(loadDashboard,2000);
    setTimeout(trSessions,3000);
  }
}
function _maRenderPanel(){
  var panel=_el('maPanel');if(!panel)return;
  var s=_maState;
  var h='';
  // Header: strategy + timer
  var strat=s.plan?s.plan.strategy||'?':'?';
  h+='<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;font-size:12px">';
  h+='<b>'+t('ma_mode_multi')+'</b>';
  h+='<span style="color:var(--text3)">'+t('ma_strategy')+': '+strat+'</span>';
  if(s.startedAt)h+='<span style="color:var(--text2);font-family:monospace">'+_fmtDur((Date.now()-s.startedAt)/1000)+'</span>';
  h+='</div>';
  // Plan summary
  if(s.plan&&s.plan.phases){
    h+='<div style="font-size:11px;color:var(--text2);margin-bottom:8px">'+t('ma_planner')+' ✓: '+s.plan.phases.length+' phases';
    if(s.plan.estimated_minutes)h+=', '+t('ma_estimated')+' '+s.plan.estimated_minutes+'min';
    h+='</div>';
  }
  // Current step
  if(s.currentStep){
    var cs=s.currentStep;
    h+='<div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;margin-bottom:6px;font-size:12px">';
    h+='<span style="color:var(--accent);font-weight:600">'+escHtml(cs.phase||'')+'</span>';
    if(cs.lesson)h+=' → <span>'+escHtml(cs.lesson)+'</span>';
    if(cs.step)h+=' → <span>'+escHtml(cs.step)+'</span>';
    if(cs.step_index&&cs.total_steps)h+=' <span style="color:var(--text3)">('+cs.step_index+'/'+cs.total_steps+')</span>';
    h+='</div>';
  }
  // Recent verifications (last 5)
  var recents=s.verifications.slice(-5);
  for(var i=0;i<recents.length;i++){
    var v=recents[i];
    var vc=v.verdict==='pass'?'var(--green)':'var(--red)';
    h+='<div style="display:flex;align-items:center;gap:8px;font-size:11px;padding:3px 0;border-bottom:1px solid var(--border)">';
    h+='<span style="color:'+vc+';font-weight:700">'+(v.verdict==='pass'?t('ma_verdict_pass'):t('ma_verdict_fail'))+'</span>';
    h+='<span>'+t('ma_text')+':'+(v.text_pass?'✓':'✗')+'</span>';
    h+='<span>'+t('ma_visual')+':'+(v.visual_pass?'✓':'✗')+'</span>';
    h+='<span>'+t('ma_api')+':'+(v.api_pass?'✓':v.api_skipped?'-':'✗')+'</span>';
    if(v.text_score!=null)h+='<span style="color:var(--text3)">'+v.text_score.toFixed(1)+'</span>';
    h+='</div>';
  }
  // Done message
  if(!s.active&&(s.plan||s.verifications.length>0)){
    var total=s.verifications.length,passed=s.verifications.filter(function(x){return x.verdict==='pass'}).length;
    h+='<div style="margin-top:8px;font-size:13px;font-weight:700;color:var(--green)">'+t('ma_done')+' ('+passed+'/'+total+')</div>';
  }
  panel.innerHTML=h;
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
    var overall=(r.overall||r.overall_score||0);
    var html='<h3 style="margin-bottom:4px">'+escHtml(r.agent_id||'Report #'+r.id)+'</h3>';
    html+='<div style="font-size:11px;color:var(--text3);margin-bottom:12px">'+(r.created_at||'')+'</div>';
    // Score summary
    var scoreColor=overall>=4?'var(--green)':overall>=3?'var(--amber)':'var(--red)';
    html+='<div style="text-align:center;margin:16px 0"><div style="font-size:48px;font-weight:800;color:'+scoreColor+'">'+overall.toFixed(1)+'</div><div style="font-size:12px;color:var(--text2)">/ 5.0</div></div>';
    // Dimension analysis
    if(r.scores){
      var dims=DIMS.map(function(d){return{key:d,val:r.scores[d]||0}}).filter(function(d){return d.val>0});
      dims.sort(function(a,b){return b.val-a.val});
      if(dims.length>0){
        var top=dims.slice(0,2),bottom=dims.slice(-2).reverse();
        html+='<div style="margin-bottom:16px">';
        html+='<div class="kv-row"><span>'+t('rp_strength')+'</span><span class="kv-val" style="color:var(--green)">'+top.map(function(d){return t('dim_'+d.key)+' '+d.val.toFixed(1)}).join(', ')+'</span></div>';
        html+='<div class="kv-row"><span>'+t('rp_weakness')+'</span><span class="kv-val" style="color:var(--red)">'+bottom.map(function(d){return t('dim_'+d.key)+' '+d.val.toFixed(1)}).join(', ')+'</span></div>';
        html+='</div>';
      }
      // Dimension bars
      html+='<table style="margin-top:12px"><thead><tr><th>'+t('rp_dimension')+'</th><th>'+t('rp_score')+'</th><th></th></tr></thead><tbody>';
      DIMS.forEach(function(d){var v=r.scores[d];if(v!=null){var cls=v>=4?'high':v>=3?'mid':'low';html+='<tr><td>'+t('dim_'+d)+'</td><td><strong>'+Number(v).toFixed(1)+'</strong></td><td style="width:120px"><div class="score-bar"><div class="score-bar-fill '+cls+'" style="width:'+(v*20)+'%"></div></div></td></tr>'}});
      html+='</tbody></table>';
    }
    html+='<div style="margin-top:12px"><button class="btn btn-outline btn-sm" onclick="App.rpDownload(\''+id+'\')">'+t('rp_download')+'</button></div>';
    if(r.html_content)html+='<div style="margin-top:16px">'+r.html_content+'</div>';
    else if(r.markdown_content)html+='<pre style="white-space:pre-wrap;font-size:12px;margin-top:12px;background:var(--bg);padding:12px;border-radius:8px;max-height:400px;overflow-y:auto">'+escHtml(r.markdown_content.substring(0,5000))+'</pre>';
    el.innerHTML=html;
  }).catch(function(){document.getElementById('rpDetail').innerHTML='<div class="empty-state"><span style="color:var(--red)">'+t('health_load_failed')+'</span></div>'});
}
function reportsCompare(){_rpCmpIds=[];document.getElementById('rpCompareBtn').style.display='none';document.getElementById('rpExitCompareBtn').style.display='';reportsLoad()}
function reportsExitCompare(){_rpCmpIds=[];document.getElementById('rpCompareBtn').style.display='';document.getElementById('rpExitCompareBtn').style.display='none';document.getElementById('rpDetail').innerHTML='<div class="empty-state">Select a report to view details</div>';reportsLoad()}
function rpDownload(id){
  get('/api/reports/'+id).then(function(r){
    var md='# Evaluation Report\n\n';
    md+='**Score**: '+((r.overall||r.overall_score||0)).toFixed(2)+' / 5.0\n';
    md+='**Date**: '+(r.created_at||'')+'\n\n';
    md+='## Dimensions\n\n';
    if(r.scores){DIMS.forEach(function(d){var v=r.scores[d];if(v!=null)md+='- '+t('dim_'+d)+': '+Number(v).toFixed(1)+'\n'})}
    if(r.markdown_content)md+='\n---\n\n'+r.markdown_content;
    var blob=new Blob([md],{type:'text/markdown'});
    var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='report_'+id+'.md';
    document.body.appendChild(a);a.click();document.body.removeChild(a);
  }).catch(function(){toast('Download failed','error')});
}
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
  document.getElementById('calGenBtn').onclick=function(){post('/api/calibration/generate',{size:20}).then(function(){toast('Calibration set generated','success');calLoad()}).catch(function(e){toast('Generation failed: '+e.message,'error')})};
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
  post('/api/calibration/score',{qa_id:item.qa_id||item.id,human_scores:_calScores}).then(function(){toast('Score submitted','success');_calItems[_calIdx].scored=true;_calScores={};calLoad();calStats();var next=_calIdx+1;if(next<_calItems.length)calSelect(next)}).catch(function(e){toast('Submit failed: '+e.message,'error')});
}
function calSkip(){var next=_calIdx+1;if(next<_calItems.length){_calScores={};calSelect(next)}}
function calStats(){
  document.getElementById('calStats').innerHTML='<div class="skeleton" style="height:120px"></div>';
  get('/api/calibration/results').then(function(r){var el=document.getElementById('calStats');if(!el)return;var html='';var ov=r.overall||{};
    html+='<div class="kv-row"><span>Cohen\'s Kappa</span><span class="kv-val">'+((ov.cohens_kappa||0).toFixed(3))+'</span></div>';
    html+='<div class="kv-row"><span>Spearman Rho</span><span class="kv-val">'+((ov.spearman_rho||0).toFixed(3))+'</span></div>';
    html+='<div class="kv-row"><span>MAE</span><span class="kv-val">'+((ov.mae||0).toFixed(2))+'</span></div>';
    html+='<div class="kv-row"><span>Scored</span><span class="kv-val">'+(r.n_samples||0)+' samples</span></div>';
    if(r.per_dimension)Object.keys(r.per_dimension).forEach(function(d){var v=r.per_dimension[d];if(!v||v.warning)return;html+='<div class="kv-row"><span>'+t('dim_'+d)+'</span><span>κ:'+((v.cohens_kappa||0).toFixed(2))+' MAE:'+((v.mae||0).toFixed(2))+'</span></div>'});
    el.innerHTML=html;
  }).catch(function(){});
}

// ═══════════════════ WebSocket ═══════════════════
var _ws=null,_wsRc=0,_evalProgress={phase:0,totalPhases:5,day:0,totalDays:0,action:'',startedAt:0};
function connectWS(){
  try{
    var proto=location.protocol==='https:'?'wss':'ws';
    _ws=new WebSocket(proto+'://'+location.host+API+'/ws');
    _ws.onopen=function(){
      _wsRc=0;
      var el=document.getElementById('wsStatusDot');
      if(el){el.classList.remove('offline');el.classList.add('online')}
      var lb=document.getElementById('wsStatusLabel');
      if(lb)lb.textContent=t('sys_ws_connected')
    };
    _ws.onclose=function(){
      var el=document.getElementById('wsStatusDot');
      if(el){el.classList.remove('online');el.classList.add('offline')}
      var lb=document.getElementById('wsStatusLabel');
      if(lb)lb.textContent=t('sys_ws_disconnected');
      setTimeout(connectWS,Math.min(30000,1000*Math.pow(2,_wsRc++)))
    };
    _ws.onmessage=function(e){
      try{
        var m=JSON.parse(e.data);
        // ── 卡点干预: 评测线程 ask_user → 弹窗询问用户 (Agent 2 契约) ──
        if(m.type==='eval:need_input'){showIntervention(m.data,'eval');return}
        // ── 探索中途提问: QuestionBridge → 弹窗 (探索器问答) ──
        if(m.type==='explorer:need_input'){
          showIntervention({question:m.data.question,options:m.data.options,timeout_s:m.data.timeout_s},'explore');
          return;
        }
        // ── Multi-Agent 事件 (Agent C) ──
        if(m.type&&m.type.indexOf('multi_agent:')===0){
          var mp=_el('maPanel');if(mp&&mp.style.display==='none')mp.style.display='';
          try{_onMultiAgentEvent(m)}catch(ex){
            if(mp)mp.innerHTML+='<div style="background:#ffebee;padding:4px;font-size:11px">Handler error: '+escHtml(ex.message)+'</div>';
          }
          var st=_el('trStatus');if(st&&m.type==='multi_agent:plan_ready'&&m.data&&m.data.phases)st.innerHTML='<span class="badge badge-green">Plan: '+m.data.phases.length+' phases</span>';
          return;
        }
        if(m.type!=='eval_event')return;
        var ev=m.event,data=m.data||{};
        if(ev==='browser_start'){
          _evalProgress={phase:0,totalPhases:(data.phases||[1,2,3,4,5]).length,day:0,totalDays:0,action:t('eval_starting'),startedAt:Date.now()};
          trRenderProgress();
        }
        if(ev==='browser_log'){
          var msg=data.msg||'';
          if(/Phase\s*(\d)/i.test(msg)){_evalProgress.phase=parseInt(msg.match(/Phase\s*(\d)/i)[1]);_evalProgress.day=0}
          if(/Day\s*(\d)/i.test(msg)){_evalProgress.day=parseInt(msg.match(/Day\s*(\d)/i)[1])}
          if(/登录/.test(msg))_evalProgress.action=t('eval_login');
          else if(/导航/.test(msg))_evalProgress.action=t('eval_navigating');
          else if(/进入/.test(msg))_evalProgress.action=t('eval_learning');
          else if(/点击/.test(msg))_evalProgress.action=t('eval_completing_steps');
          else if(/Agent|对话|chat/i.test(msg))_evalProgress.action=t('eval_agent_chat');
          else if(/Quiz|quiz/.test(msg))_evalProgress.action=t('eval_quiz');
          _evalProgress.action=_evalProgress.action||msg.substring(0,60);
          trRenderProgress();
          var logEl=document.getElementById('trEventLog');
          if(logEl){
            logEl.innerHTML+='<div class="log-line">'+escHtml(msg)+'</div>';
            logEl.scrollTop=logEl.scrollHeight
          }
        }
        if(ev==='browser_done'){
          _evalProgress.action=t('eval_complete');
          _evalProgress.phase=_evalProgress.totalPhases;
          trRenderProgress();
          var logEl2=document.getElementById('trEventLog');
          if(logEl2)logEl2.innerHTML+='<div class="log-line" style="color:var(--green)">'+t('eval_complete')+'</div>';
          setTimeout(loadDashboard,2000);
          setTimeout(trSessions,3000)
        }
        if(ev==='browser_error'){
          _evalProgress.action=t('eval_error');
          trRenderProgress();
          var logEl3=document.getElementById('trEventLog');
          if(logEl3)logEl3.innerHTML+='<div class="log-line" style="color:var(--red)">'+t('eval_error')+': '+escHtml(data.error||'')+'</div>'
        }
      }catch(ex){console.error('WS handler error',ex)}
    }
  }catch(ex){console.error('connectWS error',ex)}
}

// ═══════════════════ Platform Explorer ═══════════════════
var _exploreTimer=null,_explorePoll=null,_exploreStartTs=0,_exploreSessionId='',_exploreSchemaPath='';

function _fmtDur(s){s=Math.round(s||0);var m=Math.floor(s/60),sec=s%60;return m>0?m+'m '+sec+'s':sec+'s'}
function _el(id){return document.getElementById(id)}

function exploreInit(){
  var eu=_el('exploreUrl');if(eu&&!_exploreSessionId)eu.value=_targetUrl;
  exploreLoadHistory();
  // 对话式探索: 进入页面即开启对话 (LLM 对话为主, 固定填写为辅)
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
      localStorage.setItem('lastExploreSid', r.session_id);
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
    if(r.schema_path) localStorage.setItem('lastSchemaPath', r.schema_path);
    if(sid) localStorage.setItem('lastExploreSid', sid);

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
  updateSchemaBadge();
  var hint=_el('trSchemaHint');if(hint)hint.style.display='none';
  toast(t('explorer_schema_active'),'success');
  setTimeout(function(){showPage('test-runner')},1000);
}

function exploreViewSchema(sid){
  var id = sid || _exploreSessionId || localStorage.getItem('lastExploreSid') || '';
  if(!id){toast('No exploration session. Select one from history below.','error');return}
  // 在当前页嵌入显示
  var el = document.getElementById('exploreSchemaView');
  if(!el){
    el = document.createElement('pre');
    el.id = 'exploreSchemaView';
    el.style.cssText = 'max-height:500px;overflow:auto;background:var(--bg);padding:16px;border-radius:8px;font-size:11px;margin:8px 0;white-space:pre-wrap;border:1px solid var(--border)';
    var results = _el('exploreResults');
    if(results) results.appendChild(el);
  }
  el.textContent = 'Loading...';
  fetch(API+'/api/explorer/schema/'+id).then(function(r){return r.text()}).then(function(text){
    el.textContent = text;
    el.scrollTop = 0;
  }).catch(function(e){el.textContent = 'Failed: '+e.message});
  toast('Schema loaded');
}

function exploreDownloadSchema(sid){
  var id = sid || _exploreSessionId || localStorage.getItem('lastExploreSid') || '';
  if(!id){toast('No exploration session. Select one from history below.','error');return}
  fetch(API+'/api/explorer/schema/'+id).then(function(r){return r.blob()}).then(function(blob){
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = 'platform_schema.yaml';
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
    toast('Downloaded');
  }).catch(function(e){toast('Download failed: '+e.message,'error')});
}

function exploreLoadHistory(){
  get('/api/explorer/sessions?page=1&page_size=20').then(function(r){
    var el=_el('exploreHistory');if(!el)return;
    var sessions=r.sessions||[];
    if(sessions.length===0){el.innerHTML='<div class="empty-state">'+t('explorer_no_history')+'</div>';return}
    el.innerHTML=sessions.map(function(s){
      var badge=s.status==='completed'?'<span class="badge badge-green">Done</span>':
        s.status==='running'?'<span class="badge badge-blue">Running</span>':
        s.status==='failed'?'<span class="badge badge-red">Failed</span>':
        '<span class="badge badge-amber">'+escHtml(s.status)+'</span>';
      var actions = s.status==='completed' ? ' <a href=\"#\" onclick=\"App.exploreViewSchema(\''+escHtml(s.session_id)+'\');return false\" style=\"font-size:10px;color:var(--accent)\">View</a> <a href=\"#\" onclick=\"App.exploreDownloadSchema(\''+escHtml(s.session_id)+'\');return false\" style=\"font-size:10px;color:var(--accent)\">DL</a>' : '';
      return '<div style="padding:8px 0;border-bottom:1px solid var(--border);cursor:pointer;font-size:12px" onclick="App.exploreLoadResult(\''+escHtml(s.session_id)+'\')">'+
        badge+' <b>'+escHtml(s.target_url)+'</b>'+actions+'<br>'+
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

// 探索计划确认卡 — 字段列表 + [开始探索] / [先调整]
function exploreChatPlanCard(plan){
  var msgs=_el('exploreChatMsgs');if(!msgs||!plan||!plan.steps)return;
  var d=document.createElement('div');
  d.className='chat-msg assistant plan-card';
  var rows=(plan.steps||[]).map(function(s){
    return '<div class="plan-row"><span class="plan-label">'+escHtml(s.label)+'</span>'+
      '<span class="plan-value">'+escHtml(String(s.value==null?'':s.value))+'</span>'+
      (s.editable?'<span class="plan-edit-hint">可修改</span>':'')+'</div>';
  }).join('');
  d.innerHTML='<div class="plan-box">'+rows+
    '<div class="plan-actions">'+
    '<button class="btn btn-primary btn-sm" onclick="App.exploreChatQuickStart()" data-i18n="explorer_chat_start">开始探索</button>'+
    '<button class="btn btn-outline btn-sm" onclick="App.exploreChatFocusInput()" data-i18n="explorer_chat_adjust">先调整</button>'+
    '</div></div>';
  msgs.appendChild(d);
  msgs.scrollTop=msgs.scrollHeight;
}

function exploreChatQuickStart(){
  var inp=_el('exploreChatInput');if(!inp)return;
  inp.value='开始';
  exploreChatSend();
}

function exploreChatFocusInput(){
  var inp=_el('exploreChatInput');if(!inp)return;
  inp.focus();
  toast('告诉我哪里要改，例如「把深度改 5」或「无需登录」','info');
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
    if(r&&r.chat_id){_exploreChatId=r.chat_id;exploreChatBubble('assistant',r.reply||t('explorer_chat_title'));if(r.plan)exploreChatPlanCard(r.plan)}
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
    if(r.plan)exploreChatPlanCard(r.plan);
    if(r.action==='started'&&r.explore_session_id){
      _exploreSessionId=r.explore_session_id;
      localStorage.setItem('lastExploreSid',r.explore_session_id);
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
var _intvSessionId='',_intvTimeoutTs=0,_intvTimeoutS=0,_intvTimer=null,_intvSelOpt='',_intvMode='eval';

// mode: 'eval' (评测卡点) | 'explore' (探索中途提问) — 共用同一弹窗
function showIntervention(data,mode){
  if(!data||!data.question)return;
  var ov=_el('interventionOverlay');if(!ov)return;
  _intvMode=mode||'eval';
  _intvSessionId=data.session_id||'';
  _intvTimeoutS=data.timeout_s||0;
  _intvTimeoutTs=Date.now()+_intvTimeoutS*1000;
  _intvSelOpt='';
  _el('intvQuestion').textContent=data.question;
  // 六要素求助卡: 为什么(原因) / 怎么办(恢复建议) / 证据摘要
  var cd=_el('intvCard');
  if(cd){
    var c=data.card||{},ch='';
    if(c.reason)ch+='<div class="intv-row"><b>'+(t('intv_reason')||'为什么')+'</b> '+escHtml(c.reason)+'</div>';
    if(c.recovery)ch+='<div class="intv-row"><b>'+(t('intv_recovery')||'怎么办')+'</b> '+escHtml(c.recovery)+'</div>';
    if(c.evidence)ch+='<div class="intv-evidence">'+escHtml(String(c.evidence).slice(0,200))+'</div>';
    cd.innerHTML=ch;cd.style.display=ch?'':'none';
  }
  var opts=_el('intvOptions');opts.innerHTML='';
  (data.options||[]).forEach(function(o){
    var b=document.createElement('button');
    b.className='btn btn-outline btn-sm intv-opt';
    b.textContent=o;
    b.onclick=function(){_intvSelOpt=o;opts.querySelectorAll('.sel').forEach(function(x){x.classList.remove('sel')});b.classList.add('sel')};
    opts.appendChild(b);
  });
  var tx=_el('intvText');if(tx)tx.value='';
  var hint=_el('intvTimeoutHint');if(hint)hint.textContent='';
  ov.classList.add('show');
  if(_intvTimer){clearInterval(_intvTimer);_intvTimer=null}
  if(_intvTimeoutS>0){
    _intvTimer=setInterval(function(){
      var left=Math.max(0,Math.round((_intvTimeoutTs-Date.now())/1000));
      var h=_el('intvTimeoutHint');if(h)h.textContent=left+' '+(t('intv_timeout')||'seconds before default action');
    },1000);
  }
}

function intvSubmit(){
  var opt=_intvSelOpt||'';
  var text=_el('intvText')?_el('intvText').value.trim():'';
  // 提交格式: "选项: 文本" (或纯选项 / 纯文本)
  var answer=text?(opt?opt+': '+text:text):opt;
  if(!answer){toast('请选择一个选项或输入信息','error');return}
  var ov=_el('interventionOverlay');if(ov)ov.classList.remove('show');
  if(_intvTimer){clearInterval(_intvTimer);_intvTimer=null}
  var sid=_intvSessionId,_mode=_intvMode;_intvSessionId='';_intvSelOpt='';_intvMode='eval';
  if(_mode==='explore'){
    post('/api/explorer/questions/answer',{answer:answer,skipped:false}).then(function(r){
      if(r&&r.status==='ok')toast('已提交 — 探索继续');else toast('问题已超时, 探索按默认动作继续','error');
    }).catch(function(){toast('提交失败','error')});
    return;
  }
  post('/api/tests/intervention/respond',{session_id:sid,answer:answer}).then(function(r){
    if(r&&r.status==='ok')toast('已提交 — 评测继续');else toast('卡点已超时, 评测按默认动作继续','error');
  }).catch(function(){toast('提交失败','error')});
}

// 轮询兜底: 仅 WS 断开(或未连上)时轮询 intervention/pending (10s); WS 在线时走实时通道
setInterval(function(){
  var ov=_el('interventionOverlay');if(ov&&ov.classList.contains('show'))return;
  if(_ws&&_ws.readyState===1)return; // WS 已连接 → 实时事件足够
  get('/api/tests/intervention/pending').then(function(r){
    if(r&&r.pending)showIntervention({session_id:r.session_id,question:r.question,options:r.options,timeout_s:r.timeout_s},'eval');
  }).catch(function(){});
  // 探索中途提问轮询兜底 (探索运行时)
  if(_exploreSessionId){
    get('/api/explorer/questions/current').then(function(r){
      if(r&&r.pending&&r.text)showIntervention({question:r.text,options:r.options,timeout_s:r.timeout_s},'explore');
    }).catch(function(){});
  }
},10000);

// ═══════════════════ Export ═══════════════════
window.App={showPage:showPage,loadDashboard:loadDashboard,startEval:startEval,onProfileChange:onProfileChange,toggleTheme:toggleTheme,toggleLang:toggleLang,setTargetUrl:setTargetUrl,phLoad:phLoad,phTriggerFull:phTriggerFull,trLoad:trLoad,trStart:trStart,trStop:trStop,trConfirmStart:trConfirmStart,trCancelPreflight:trCancelPreflight,reportsLoad:reportsLoad,reportsCompare:reportsCompare,reportsExitCompare:reportsExitCompare,rpSelect:rpSelect,rpDownload:rpDownload,calInit:calInit,calSelect:calSelect,calScore:calScore,calSubmit:calSubmit,calSkip:calSkip,testStart:trStart,testStop:trStop,exploreStart:exploreStart,exploreCancel:exploreCancel,exploreUseSchema:exploreUseSchema,exploreViewSchema:exploreViewSchema,exploreDownloadSchema:exploreDownloadSchema,exploreLoadHistory:exploreLoadHistory,exploreLoadResult:exploreLoadResult,exploreChatStart:exploreChatStart,exploreChatSend:exploreChatSend,exploreChatQuickStart:exploreChatQuickStart,exploreChatFocusInput:exploreChatFocusInput,intvSubmit:intvSubmit,showIntervention:showIntervention};

document.addEventListener('DOMContentLoaded',function(){
  // ── 页面可见: DOMContentLoaded 已触发 ──
  try{applyI18n()}catch(e){console.error('applyI18n',e)}
  try{if(window.I18n&&window.I18n.onDictUpdate){window.I18n.onDictUpdate(function(){applyI18n()})}}catch(e){console.error('i18n hook',e)}
  try{var lt=document.getElementById('langToggle');if(lt)lt.textContent=_lang=='zh'?'EN':'CN'}catch(e){console.error('langToggle',e)}
  try{loadProfile()}catch(e){console.error('loadProfile',e)}
  try{updateSchemaBadge()}catch(e){console.error('updateSchemaBadge',e)}
  try{loadDashboard()}catch(e){console.error('loadDashboard init',e)}
  try{onProfileChange()}catch(e){console.error('onProfileChange',e)}
  try{connectWS()}catch(e){console.error('connectWS',e)}
  setInterval(function(){_profilePolling=false;loadProfile()},30000);
});
})();
