"""FastAPI 应用入口"""

import asyncio
import logging
import sys
import threading
from pathlib import Path

# 确保项目根目录在 sys.path 中，使 src/ 可导入
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from starlette.middleware.gzip import GZipMiddleware

logger = logging.getLogger(__name__)

# 前端 HTML 不缓存 — 保证 UI 更新部署后用户刷新即见, 不被浏览器旧缓存挡住
_NO_CACHE = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}

from .middleware import setup_cors, setup_auth, setup_error_handlers
from .middleware.rate_limit import setup_rate_limit
from .middleware.metrics import setup_metrics
from .api import api_router

app = FastAPI(
    title="AI Agent 评测平台",
    version="3.6.0",
    description="AI Agent 全自动化测评系统 — 10维度评分 / 多Judge投票 / 火山引擎知识库 / Token成本追踪 / 速率限制 / Prometheus指标",
)

# ── 中间件 ──
app.add_middleware(GZipMiddleware, minimum_size=500)  # 压缩 >500B 的响应
setup_cors(app)
setup_auth(app)       # Basic Auth (API保护, 未配置凭据时自动放行)
setup_error_handlers(app)
setup_metrics(app)
setup_rate_limit(app)

# ── 后台平台健康度刷新 (每30分钟) ──
_health_refresh_stop = threading.Event()

def _health_refresh_loop():
    """后台线程: 双频监控
    - 每 5 分钟: 快速心跳 (login + 1 API)
    - 每 30 分钟: 全量健康检查
    """
    import json, os, time as _time
    cache_file = Path(__file__).parent.parent / "data" / "platform_health_cache.json"
    heartbeat_file = Path(__file__).parent.parent / "data" / "heartbeat_log.json"

    _full_check_interval = 1800  # 30分钟
    _heartbeat_interval = 300    # 5分钟
    _last_full_check = 0

    while not _health_refresh_stop.is_set():
        try:
            now = _time.time()
            do_full = (now - _last_full_check) >= _full_check_interval

            if do_full:
                # ── 全量检查 ──
                _sys = __import__("sys")
                _sys.path.insert(0, str(Path(__file__).parent.parent))
                from src.platform_interaction_evaluator import PlatformInteractionEvaluator
                evaluator = PlatformInteractionEvaluator(verbose=False)
                evaluator.client.login()
                report = evaluator.run_all()
                report["_ts"] = now
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(report, f, ensure_ascii=False, default=str)
                logger.info("平台全量健康度已刷新: health_score=%.0f%%",
                            report.get("summary", {}).get("health_score", 0) * 100)
                _last_full_check = now

                # 记录到指标历史
                try:
                    from backend.services.metrics_history import record_snapshot
                    record_snapshot(report)
                except Exception:
                    pass
            else:
                # ── 快速心跳 ──
                heartbeat = {"ts": now, "status": "unknown"}
                try:
                    import requests
                    s = requests.Session()
                    s.trust_env = False
                    s.proxies = {"http": None, "https": None}
                    t0 = _time.time()
                    r = s.post("http://124.174.108.70/phase3-api/auth/login",
                              json={"username": "student001", "password": "123456"},
                              timeout=10)
                    latency = (_time.time() - t0) * 1000
                    heartbeat["status"] = "ok" if r.status_code == 200 else f"HTTP_{r.status_code}"
                    heartbeat["latency_ms"] = round(latency)
                except Exception as e:
                    heartbeat["status"] = "unreachable"
                    heartbeat["error"] = str(e)[:100]

                heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
                heartbeat_file.write_text(json.dumps(heartbeat, ensure_ascii=False))
                logger.debug("心跳: %s (%.0fms)", heartbeat["status"],
                            heartbeat.get("latency_ms", 0))

        except Exception as e:
            logger.warning("健康度刷新失败: %s", e)

        _health_refresh_stop.wait(_heartbeat_interval)  # 每5分钟循环一次

@app.on_event("startup")
async def startup_health_refresh():
    threading.Thread(target=_health_refresh_loop, daemon=True, name="health-refresh").start()
    # i18n 自适应: 启动时扫描前端代码, 自动补齐缺失的翻译键
    try:
        from backend.api.i18n import startup_scan
        startup_scan()
    except Exception as e:
        logger.warning("i18n startup scan skipped: %s", e)

@app.on_event("shutdown")
async def shutdown_health_refresh():
    _health_refresh_stop.set()

# ── API 路由 (必须在静态文件和SPA fallback之前注册) ──
app.include_router(api_router)

# ── WebSocket ──
from fastapi import WebSocket
from .ws import ws_manager

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
    except Exception:
        pass
    finally:
        await ws_manager.disconnect(ws)

# ── 静态文件缓存中间件 ──
@app.middleware("http")
async def add_cache_headers(request, call_next):
    resp = await call_next(request)
    path = request.url.path
    # JS/CSS/Fonts/Images: cache 24h (immutable — deploy restarts service = new URL)
    if any(path.endswith(ext) for ext in ('.js', '.css', '.woff2', '.png', '.svg', '.ico', '.jpg', '.webp')):
        resp.headers["Cache-Control"] = "public, max-age=86400, immutable"
    elif path.startswith('/reports/'):
        resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp

# ── 静态文件 (前端) ──
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    for sub in ["js", "css", "assets", "images"]:
        sub_dir = frontend_dir / sub
        if sub_dir.exists():
            app.mount(f"/{sub}", StaticFiles(directory=str(sub_dir)), name=f"static-{sub}")
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

# ── 报告文件 (persona_tester 生成的可视化 HTML/JSON/MD) ──
reports_dir = Path(__file__).parent.parent / "reports"
reports_dir.mkdir(exist_ok=True)
app.mount("/reports", StaticFiles(directory=str(reports_dir)), name="reports")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "3.6.0"}


# ── 首页: 直接从Python返回, 绕过前端文件系统 ──
from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
async def root_page():
    """直接返回Dashboard HTML, 不受文件系统linter干扰."""
    css_path = frontend_dir / "css" / "style.css"
    css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AI Agent 评测平台</title>
<script>try{{document.documentElement.setAttribute('data-theme',localStorage.getItem('theme')||'light')}}catch(e){{}}</script>
<style>{css}</style>
</head>
<body>
<div class="header"><h1>🤖 AI Agent 评测平台 v3.6</h1><div class="header-right">
<button class="lang-toggle" onclick="toggleTheme()">🌙</button>
<button class="lang-toggle" onclick="toggleLang()">EN</button>
<span id="sysStatus"><span class="live-dot"></span>在线</span></div></div>

<nav class="nav">
<a class="active" data-page="dashboard" href="#" onclick="showPage('dashboard');return false">📊 首页</a>
<a data-page="platform-health" href="#" onclick="showPage('platform-health');return false">🔌 平台监控</a>
<a data-page="test-runner" href="#" onclick="showPage('test-runner');return false">🧪 测试运行</a>
<a data-page="reports" href="#" onclick="showPage('reports');return false">📋 报告</a>
<a data-page="calibration" href="#" onclick="showPage('calibration');return false">🎯 校准</a>
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
<option value="patrol">🔍 巡检 ~5min</option>
<option value="full" selected>📋 全平台 ~18min</option>
<option value="deep">🔬 深度 ~30min</option>
<option value="custom">⚙️ 自定义</option>
</select>
<span id="customOpts" style="display:none;gap:4px">
<input id="numQuestions" type="number" value="3" min="1" max="20" style="width:55px">
<span>题×</span><input id="maxTurns" type="number" value="3" min="1" max="10" style="width:55px"><span>轮</span>
</span>
<button class="btn btn-primary" onclick="startEval()">▶ 开始测评</button>
<button class="btn btn-outline btn-sm" onclick="loadDashboard()">🔄 刷新</button>
</div>
<div id="evalModeHint" style="font-size:11px;color:var(--dim);margin:4px 0"></div>
<div id="evalStatusBar" style="display:none;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin:8px 0;font-size:12px">
<span id="wsIndicator" style="color:#dc2626">🔌 WS断开</span> |
<span>⏱️ <b id="evalElapsed">00:00</b></span> |
<span>📍 <span id="evalStep">就绪</span></span>
</div>
<div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
<div id="liveEvalPanel" style="display:none">
<div class="live-eval-header"><h3>🔍 实时评测</h3><button class="btn btn-outline btn-sm" onclick="document.getElementById('liveEvalBody').innerHTML=''">清空</button></div>
<div class="live-eval-body" id="liveEvalBody"><div class="qa-empty">点击"开始测评"查看完整过程</div></div>
</div>
<div class="score-mini-grid" id="scoreMiniGrid"></div>
<div class="two-col">
<div class="card"><h3>📈 得分趋势</h3><div style="position:relative;height:200px"><canvas id="trendChart" style="width:100%;height:100%"></canvas></div></div>
<div class="card"><h3>🎯 维度分布</h3><div style="position:relative;height:200px"><canvas id="radarChart" style="width:100%;height:100%"></canvas></div></div>
</div>
<div class="card"><h3>📋 最近报告</h3><div id="recentReports">加载中...</div></div>
</div>

<div id="page-platform-health" class="page"><div style="text-align:center;padding:60px">📊 加载中...</div></div>
<div id="page-test-runner" class="page"><div style="text-align:center;padding:60px">📊 加载中...</div></div>
<div id="page-reports" class="page"><div style="text-align:center;padding:60px">📊 加载中...</div></div>
<div id="page-calibration" class="page"><div style="text-align:center;padding:60px">📊 加载中...</div></div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="/js/i18n.js"></script>
<script>
var API=(function(){{try{{var p=location.pathname;return(p.startsWith('/test/')||p==='/test')?'/test':''}}catch(e){{return''}}}})();
function escHtml(s){{return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}}
async function get(p){{var r=await fetch(API+p);return r.json()}}
async function post(p,b){{var r=await fetch(API+p,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(b)}});return r.json()}}
function toggleTheme(){{var e=document.documentElement,t=e.getAttribute('data-theme')==='dark'?'light':'dark';e.setAttribute('data-theme',t);localStorage.setItem('theme',t)}}
function toggleLang(){{var c=localStorage.getItem('lang')||'zh',n=c==='zh'?'en':'zh';localStorage.setItem('lang',n);if(window.setLang)window.setLang(n)}}
function onProfileChange(){{var v=document.getElementById('evalProfile').value;var co=document.getElementById('customOpts');co.style.display=v==='custom'?'inline-flex':'none';var hints={{patrol:'巡检: 每Phase抽1Day, ~5min',full:'全平台: 22Days+Quiz验证, ~18min',deep:'深度: 双模式+逐Step, ~30min',custom:'自定义: 自由设置题目数x轮数'}};document.getElementById('evalModeHint').textContent=hints[v]||''}}

async function loadDashboard(){{
try{{
var d=await get('/api/dashboard/summary');
var el=function(id){{return document.getElementById(id)}};
if(el('totalTests'))el('totalTests').textContent=d.total_tests||0;
if(el('avgScore'))el('avgScore').textContent=(d.avg_overall||0).toFixed(2);
if(el('qaApproved'))el('qaApproved').textContent=d.qa_approved||0;
if(el('qaPending'))el('qaPending').textContent=d.qa_pending||0;
var reps=await get('/api/dashboard/sessions?page_size=5'),rl=el('recentReports');
if(rl&&reps.items&&reps.items.length)rl.innerHTML=reps.items.map(function(r){{return'<span class="badge badge-blue" style="margin:2px">'+escHtml(r.agent_id)+' - '+(r.status||'?')+'</span>'}}).join(' ');
else if(rl)rl.innerHTML='<span style="color:var(--dim)">暂无报告</span>';
renderCharts(d)
}}catch(e){{console.error(e)}}
}}

async function loadAgents(){{
try{{var a=await get('/api/agents'),keys=Object.keys(a||{{}}).filter(function(k){{return k==='platform'}}),sel=document.getElementById('agentSelect');
if(sel)sel.innerHTML=keys.length?keys.map(function(k){{return'<option value="'+k+'">'+(a[k]&&a[k].name||k)+'</option>'}}).join(''):'<option value="platform">实训教学平台</option>'}}catch(e){{}}
}}

var trendChartObj=null,radarChartObj=null;
function renderCharts(d){{
if(typeof Chart==='undefined')return;
var dims=['correctness','relevancy','completeness','guidance','followup_quality','boundary_compliance','turn_consistency','knowledge_scaffolding'];
var labels=window.getDimLabels?window.getDimLabels():['正确性','相关性','完整性','引导力','追问','边界','一致性','递进性'];
var dark=document.documentElement.getAttribute('data-theme')==='dark',grid=dark?'rgba(148,163,184,.16)':'rgba(100,116,139,.14)',tick=dark?'#94a3b8':'#64748b',sky=dark?'#38bdf8':'#0ea5e9',fill=dark?'rgba(56,189,248,.14)':'rgba(14,165,233,.12)';
Chart.defaults.color=tick;
var tEl=document.getElementById('trendChart');
if(tEl){{var trend=(d.trend||[]).slice().reverse();if(trendChartObj)trendChartObj.destroy();
trendChartObj=new Chart(tEl,{{type:'line',data:{{labels:trend.map(function(p,i){{return p.ts?String(p.ts).replace('T',' ').substring(5,16):(i+1)}}),datasets:[{{data:trend.map(function(p){{return p.score}}),borderColor:sky,backgroundColor:fill,fill:true,tension:.35,borderWidth:2,pointRadius:3,pointBackgroundColor:sky}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{y:{{min:0,max:5,ticks:{{stepSize:1}},grid:{{color:grid}}}},x:{{grid:{{color:grid}}}}}}}}}})}}
var rEl=document.getElementById('radarChart');
if(rEl){{var latest=d.latest||{{}};if(radarChartObj)radarChartObj.destroy();
radarChartObj=new Chart(rEl,{{type:'radar',data:{{labels:labels,datasets:[{{data:dims.map(function(k){{return latest[k]||0}}),borderColor:sky,backgroundColor:fill,borderWidth:2,pointRadius:3,pointBackgroundColor:sky}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{r:{{min:0,max:5,ticks:{{stepSize:1,backdropColor:'transparent'}},grid:{{color:grid}},pointLabels:{{color:tick}}}}}}}}}})}}
}}

async function startEval(){{
var profile=document.getElementById('evalProfile').value;
var panel=document.getElementById('liveEvalPanel'),body=document.getElementById('liveEvalBody'),bar=document.getElementById('evalStatusBar');
if(panel)panel.style.display='block';if(bar)bar.style.display='flex';
if(body)body.innerHTML='<div class="qa-empty">启动中...</div>';
var presets={{patrol:{{phases:[1,2,3,4,5],mode:'guided',include_quiz:true}},full:{{phases:[1,2,3,4,5],mode:'guided',include_quiz:true}},deep:{{phases:[1,2,3,4,5],mode:'both',include_quiz:true}}}};
var params,endpoint;
if(profile==='custom'){{params={{agent_id:'platform',num_questions:parseInt(document.getElementById('numQuestions').value)||3,max_turns:parseInt(document.getElementById('maxTurns').value)||3,profile:'custom'}};endpoint='/api/tests/run'}}
else{{params=presets[profile]||presets.full;endpoint='/api/tests/run-browser'}}
try{{var data=await post(endpoint,params);if(data.status==='started'){{if(body)body.innerHTML='<div class="qa-empty" style="color:#16a34a">已启动: '+data.session_id+'</div>'}}else{{if(body)body.innerHTML='<div class="qa-empty" style="color:#dc2626">失败: '+JSON.stringify(data)+'</div>'}}}}catch(e){{if(body)body.innerHTML='<div class="qa-empty" style="color:#dc2626">错误: '+e.message+'</div>'}}
}}

var _pageMods={{}};
function showPage(name){{
document.querySelectorAll('.page').forEach(function(p){{p.classList.remove('active')}});
document.querySelectorAll('.nav a').forEach(function(a){{a.classList.remove('active')}});
var el=document.getElementById('page-'+name);if(el)el.classList.add('active');else{{console.warn('No element: page-'+name);return}}
var nv=document.querySelector('.nav a[data-page="'+name+'"]');if(nv)nv.classList.add('active');
// dashboard is hardcoded in HTML — only refresh if no active eval
if(name==='dashboard'){{
var panel=document.getElementById('liveEvalPanel');
var isRunning=panel&&panel.style.display==='block';
if(!isRunning){{loadDashboard();loadAgents()}}
return}}
var modMap={{'platform-health':'platform-health','test-runner':'test_runner',reports:'reports',calibration:'calibration'}};
var modName=modMap[name];if(!modName){{el.innerHTML='<div style=\"padding:40px;text-align:center;color:var(--red)\">未知页面: '+name+'</div>';return}}
if(_pageMods[name]){{var p=_pageMods[name];if(p.render)p.render();return}}
el.innerHTML='<div style=\"text-align:center;padding:40px;color:var(--muted)\">加载 '+modName+'.js ...</div>';
import(API+'/js/pages/'+modName+'.js').then(function(m){{var p=m.default||m;_pageMods[name]=p;if(p.init)p.init();if(p.render)p.render()}}).catch(function(e){{el.innerHTML='<div style=\"padding:40px;text-align:center;color:var(--red)\">页面加载失败: '+modName+'<br><small>'+e.message+'</small></div>';console.warn('Page fail:',name,e)}})
}}

var _ws=null,_wsReconnect=0;
function connectWS(){{
try{{var proto=location.protocol==='https:'?'wss':'ws';_ws=new WebSocket(proto+'://'+location.host+'/ws');
_ws.onopen=function(){{_wsReconnect=0;var el=document.getElementById('wsIndicator');if(el){{el.innerHTML='WS已连接';el.style.color='#16a34a'}}}};
_ws.onclose=function(){{var el=document.getElementById('wsIndicator');if(el){{el.innerHTML='WS断开';el.style.color='#dc2626'}}var d=Math.min(30000,1000*Math.pow(2,_wsReconnect++));setTimeout(connectWS,d)}};
_ws.onmessage=function(e){{try{{var m=JSON.parse(e.data);if(m.type==='eval_event'){{var event=m.event,data=m.data||{{}};if(event==='browser_log'){{var body=document.getElementById('liveEvalBody');if(body){{body.innerHTML+='<div style=\"font-size:11px;padding:2px 0;border-bottom:1px solid var(--line-soft)\">'+escHtml(data.msg||'')+'</div>';body.scrollTop=body.scrollHeight}}}}if(event==='browser_done'){{var body=document.getElementById('liveEvalBody');if(body){{body.innerHTML+='<div style=\"color:#16a34a;padding:8px;font-weight:600\">测评完成!</div>'}}setTimeout(loadDashboard,2000)}}}}}}catch(ex){{}}}}
}}catch(ex){{}}
}}

document.addEventListener('DOMContentLoaded',function(){{loadDashboard();loadAgents();onProfileChange();setTimeout(connectWS,500)}});
</script>
</body>
</html>"""


# SPA fallback: serve existing static files, otherwise return index.html
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    if full_path.startswith("api/"):
        return {"error": "API endpoint not found", "path": full_path}
    # Check if a real file exists and serve it directly
    file_path = frontend_dir / full_path
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path), headers=_NO_CACHE)
    # SPA fallback
    index_path = frontend_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), headers=_NO_CACHE)
    return {"message": "Frontend not found.", "status": "ok"}
