"""
AI Agent 评测监控 Dashboard v3.1

FastAPI + WebSocket 实时推送 + 内嵌 HTML
功能: 首页总览 / QA审核 / 网页评测 / 实时测评面板

启动: .venv_wsl/bin/python -m uvicorn dashboard.app:app --host 0.0.0.0 --port 8000
"""

import asyncio
import json, os, sys, time, threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.agent_registry import AgentRegistry, AGENT_CONFIGS

from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="AI Agent 评测监控面板", version="3.1.0")

# ── WebSocket 连接管理 ────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active_connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active_connections:
            self.active_connections.remove(ws)

    async def broadcast(self, data: dict):
        for conn in self.active_connections[:]:
            try:
                await conn.send_json(data)
            except Exception:
                self.active_connections.remove(conn)

manager = ConnectionManager()

_test_state = {
    "running": False, "progress": 0, "total": 0,
    "current_event": "", "events": [],
}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        await ws.send_json({"type": "state", "data": {
            "running": _test_state["running"],
            "progress": _test_state["progress"],
            "total": _test_state["total"],
            "current_event": _test_state["current_event"],
        }})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ── 进度回调 (给 TestRunner 用) ─────────────────

async def _progress_callback(event: str, data: dict):
    """TestRunner 的进度回调 -> WebSocket 广播"""
    global _test_state
    _test_state["current_event"] = event

    if event == "scenario_start":
        _test_state["progress"] = data.get("index", 0) - 1
        _test_state["total"] = data.get("total", 0)

    await manager.broadcast({
        "type": "eval_event",
        "event": event,
        "data": data,
        "running": _test_state["running"],
    })


# ── API: 首页 ────────────────────────────────────

@app.get("/api/agents")
async def list_agents():
    return AgentRegistry.list_agents()

@app.get("/api/kb/status")
async def kb_status():
    syllabus_path = "data/course_syllabus.txt"
    ok = os.path.exists(syllabus_path)
    return {"ok": ok, "message": f"本地大纲{'已加载' if ok else '缺失'}"}

@app.get("/api/dashboard/summary")
async def dashboard_summary():
    reports_dir = Path("reports")
    if not reports_dir.exists():
        return {"total_tests": 0, "avg_overall": 0, "trend": []}
    reports = []
    for f in sorted(reports_dir.glob("report_*.json"), reverse=True)[:10]:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                reports.append(json.load(fp))
        except Exception:
            pass
    if not reports:
        return {"total_tests": 0, "avg_overall": 0, "trend": []}
    overalls = [r.get("summary", {}).get("avg_scores", {}).get("overall", 0) for r in reports]
    return {
        "total_tests": len(reports),
        "avg_overall": round(sum(overalls) / len(overalls), 2) if overalls else 0,
        "latest": reports[0] if reports else None,
        "trend": [{"ts": r.get("timestamp", ""),
                    "score": r.get("summary", {}).get("avg_scores", {}).get("overall", 0)}
                  for r in reports[:10] if r.get("summary")],
    }

@app.get("/api/tests/{filename}")
async def get_test_detail(filename: str):
    filepath = Path("reports") / filename
    if not filepath.exists():
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/api/tests/progress")
async def test_progress():
    return {"running": _test_state["running"], "progress": _test_state["progress"],
            "total": _test_state["total"], "current_event": _test_state["current_event"]}

@app.get("/api/reports/list")
async def list_reports():
    reports_dir = Path("reports")
    if not reports_dir.exists():
        return []
    files = []
    for f in sorted(reports_dir.glob("report_*.json"), reverse=True):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                files.append({
                    "filename": f.name,
                    "timestamp": data.get("timestamp", ""),
                    "overall": data.get("summary", {}).get("avg_scores", {}).get("overall", 0),
                    "total": data.get("summary", {}).get("total", 0),
                })
        except Exception:
            pass
    return files[:20]

# ── API: 运行测试 ─────────────────────────────────

@app.post("/api/tests/run")
async def trigger_test(agent_id: str = "platform", num_questions: int = 1):
    global _test_state
    if _test_state["running"]:
        return {"error": "已有测试在运行中", "status": "busy"}

    _test_state = {
        "running": True, "progress": 0, "total": num_questions,
        "current_event": "启动中", "events": [],
    }

    # 捕获 FastAPI 主线程的 event loop（WebSocket 连接在此管理）
    main_loop = asyncio.get_running_loop()
    # 项目根目录（确保后续的相对路径正确）
    project_root = Path(__file__).parent.parent

    def run_bg():
        global _test_state
        try:
            # 切换到项目根目录，确保 config/test_config.yaml 等相对路径正确
            os.chdir(str(project_root))
            _test_state["current_event"] = "初始化中..."

            from src.test_runner import TestRunner

            # 线程安全的进度回调：将 broadcast 调度到主 event loop
            def on_progress(event: str, data: dict):
                _test_state["current_event"] = event
                if event == "scenario_start":
                    _test_state["progress"] = data.get("index", 0) - 1
                    _test_state["total"] = data.get("total", 0)
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast({
                        "type": "eval_event",
                        "event": event,
                        "data": data,
                        "running": _test_state["running"],
                    }),
                    main_loop,
                )

            # 用绝对路径加载配置
            config_path = str(project_root / "config" / "test_config.yaml")
            runner = TestRunner(config_path=config_path, progress_callback=on_progress)

            # 强制覆盖：确保浏览器可见 + 使用正确的 Agent
            runner.config["num_questions"] = num_questions
            runner.config["agent_id"] = agent_id
            runner.config["headless"] = False
            runner.config["debug"] = True
            runner.agent_id = agent_id

            _test_state["current_event"] = "启动评测..."
            results = runner.run_all()
            _test_state["results"] = results
        except Exception as e:
            import traceback
            err_msg = f"{e}\n{traceback.format_exc()}"
            print(f"[Dashboard] 评测异常:\n{err_msg}")
            _test_state["current_event"] = f"错误: {e}"
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({
                    "type": "eval_event",
                    "event": "error",
                    "data": {"message": str(e)},
                    "running": False,
                }),
                main_loop,
            )
        finally:
            _test_state["running"] = False
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({
                    "type": "state",
                    "data": {
                        "running": False,
                        "progress": _test_state["progress"],
                        "total": _test_state["total"],
                        "current_event": _test_state["current_event"],
                    },
                }),
                main_loop,
            )

    threading.Thread(target=run_bg, daemon=True).start()
    return {"status": "started", "num_questions": num_questions, "agent_id": agent_id}


# ── API: QA 审核 ─────────────────────────────────

QA_PENDING_PATH = "data/qa_pending.json"
QA_BANK_PATH = "data/golden_qa_bank.json"

def _read_qa(filepath: str) -> list:
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def _write_qa(filepath: str, data: list):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.get("/api/qa/list")
async def qa_list(status: str = "all", phase: str = "all"):
    qa_all = _read_qa(QA_PENDING_PATH)
    if status != "all":
        qa_all = [q for q in qa_all if q.get("status") == status]
    if phase != "all":
        qa_all = [q for q in qa_all if q.get("phase") == phase]
    return {"total": len(qa_all), "items": qa_all}

@app.get("/api/qa/stats")
async def qa_stats():
    qa_all = _read_qa(QA_PENDING_PATH)
    approved = _read_qa(QA_BANK_PATH)
    phases = ["PHASE 01", "PHASE 02", "PHASE 03", "PHASE 04", "PHASE 05"]
    return {
        "pending": sum(1 for q in qa_all if q.get("status") == "pending"),
        "approved": len(approved),
        "rejected": sum(1 for q in qa_all if q.get("status") == "rejected"),
        "total": len(qa_all),
        "by_phase": {p: sum(1 for q in qa_all if q.get("phase") == p) for p in phases},
    }

@app.post("/api/qa/{qa_id}/approve")
async def qa_approve(qa_id: str):
    qa_all = _read_qa(QA_PENDING_PATH)
    approved = _read_qa(QA_BANK_PATH)
    for q in qa_all:
        if q["qa_id"] == qa_id:
            q["status"] = "approved"
            q["reviewer_notes"] = "人工审核通过"
            approved.append(q)
            break
    _write_qa(QA_PENDING_PATH, qa_all)
    _write_qa(QA_BANK_PATH, approved)
    return {"ok": True, "qa_id": qa_id, "status": "approved"}

@app.post("/api/qa/{qa_id}/reject")
async def qa_reject(qa_id: str, reason: str = ""):
    qa_all = _read_qa(QA_PENDING_PATH)
    for q in qa_all:
        if q["qa_id"] == qa_id:
            q["status"] = "rejected"
            q["reviewer_notes"] = reason or "人工审核拒绝"
            break
    _write_qa(QA_PENDING_PATH, qa_all)
    return {"ok": True, "qa_id": qa_id, "status": "rejected"}

@app.post("/api/qa/{qa_id}/edit")
async def qa_edit(qa_id: str, body: dict):
    qa_all = _read_qa(QA_PENDING_PATH)
    for q in qa_all:
        if q["qa_id"] == qa_id:
            q.update({k: v for k, v in body.items() if k in
                      ["question", "golden_answer", "knowledge_points", "difficulty"]})
            q["status"] = "pending"
            break
    _write_qa(QA_PENDING_PATH, qa_all)
    return {"ok": True, "qa_id": qa_id}

@app.post("/api/qa/generate")
async def qa_generate():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"error": "未设置 OPENAI_API_KEY"}
    from src.qa_generator import QAGenerator
    gen = QAGenerator(api_key)
    qa_pairs = gen.generate_from_excel()
    gen.save_pending(qa_pairs)
    return {"ok": True, "total": len(qa_pairs)}

# ── API: 网页评测 ─────────────────────────────────

_web_eval_result = None

@app.post("/api/web-eval/run")
async def web_eval_run(url: str = "http://124.174.108.70"):
    global _web_eval_result
    api_key = os.getenv("OPENAI_API_KEY", "")
    from src.web_evaluator import WebEvaluator
    evaluator = WebEvaluator(api_key=api_key)
    _web_eval_result = evaluator.evaluate(url, test_questions=[
        {"question": "请介绍一下这个AI硬件课程包含哪些内容", "golden_answer": ""},
        {"question": "ESP32-S3的ADC分辨率是多少", "golden_answer": ""},
    ])
    return {"ok": True, "overall_score": _web_eval_result.overall_score}

@app.get("/api/web-eval/results")
async def web_eval_results():
    if _web_eval_result is None:
        return {"error": "尚未执行网页评测"}
    return _web_eval_result.to_dict()


# ── HTML 面板 ────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    tab = request.query_params.get("tab", "home")
    return DASHBOARD_HTML.replace("__ACTIVE_TAB__", tab)


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AI Agent 评测面板 v3.1</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}
.header{background:#1e293b;padding:12px 24px;border-bottom:1px solid #334155;display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:18px;color:#38bdf8}
.nav{display:flex;gap:4px;background:#1e293b;padding:0 24px;border-bottom:1px solid #334155}
.nav a{padding:12px 20px;text-decoration:none;color:#94a3b8;font-size:14px;border-bottom:2px solid transparent;transition:.2s}
.nav a:hover,.nav a.active{color:#38bdf8;border-bottom-color:#38bdf8}
.tab{display:none}
.tab.active{display:block}
.status-dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:8px}
.status-dot.online{background:#22c55e}.status-dot.offline{background:#ef4444}
.status-dot.busy{background:#f59e0b;animation:pulse 1s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;padding:20px}
.card{background:#1e293b;border-radius:10px;padding:16px;border:1px solid #334155}
.card h3{font-size:13px;color:#94a3b8;margin-bottom:6px}
.card .value{font-size:28px;font-weight:bold;color:#38bdf8}
.card .unit{font-size:13px;color:#64748b}
.controls{padding:0 20px 16px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.btn{padding:8px 16px;border:none;border-radius:6px;font-size:13px;cursor:pointer;font-weight:600;transition:.2s}
.btn-primary{background:#2563eb;color:#fff}.btn-primary:hover{background:#1d4ed8}
.btn-success{background:#16a34a;color:#fff}.btn-success:hover{background:#15803d}
.btn-danger{background:#dc2626;color:#fff}.btn-danger:hover{background:#b91c1c}
.btn-warning{background:#d97706;color:#fff}.btn-warning:hover{background:#b45309}
.btn-outline{background:transparent;border:1px solid #475569;color:#e2e8f0}
.btn-outline:hover{background:#334155}
.btn-sm{padding:4px 10px;font-size:12px}
.btn:disabled{opacity:0.5;cursor:not-allowed}
select,input,textarea{padding:7px 10px;border-radius:6px;border:1px solid #475569;background:#0f172a;color:#e2e8f0;font-size:13px}
.progress-bar{width:100%;height:6px;background:#334155;border-radius:3px;overflow:hidden;margin-top:8px}
.progress-fill{height:100%;background:linear-gradient(90deg,#38bdf8,#2563eb);transition:width .3s}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:14px}

/* ── Live Eval Panel ── */
.live-eval{background:#1e293b;border-radius:10px;border:1px solid #334155;margin:0 20px 20px;overflow:hidden}
.live-eval-header{background:#1e3a5f;padding:12px 16px;display:flex;justify-content:space-between;align-items:center}
.live-eval-header h3{font-size:14px;color:#38bdf8}
.live-eval-body{padding:16px;max-height:500px;overflow-y:auto}
.eval-step{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid #1e293b;align-items:flex-start}
.eval-step .step-icon{width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0;background:#334155}
.eval-step .step-icon.send{background:#1e3a5f}.eval-step .step-icon.response{background:#1a3a2a}
.eval-step .step-icon.score{background:#3a2a1a}.eval-step .step-icon.boundary{background:#2a1a3a}
.eval-step .step-icon.error{background:#3a1a1a}
.eval-step .step-content{flex:1;min-width:0}
.eval-step .step-label{font-size:11px;color:#64748b;margin-bottom:2px}
.eval-step .step-text{font-size:13px;color:#e2e8f0;word-break:break-word}
.eval-step .step-text.user{color:#94a3b8}
.eval-step .step-text.ai{color:#22c55e}
.eval-step .step-text.error{color:#ef4444}
.eval-step .step-meta{font-size:11px;color:#64748b;margin-top:2px}

/* ── Score Mini Cards ── */
.score-mini-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px;padding:12px 0}
.score-mini{background:#0f172a;border-radius:8px;padding:10px;text-align:center}
.score-mini .sm-val{font-size:24px;font-weight:bold}
.score-mini .sm-label{font-size:11px;color:#94a3b8;margin-top:2px}
.score-mini .sm-explanation{font-size:10px;color:#64748b;margin-top:4px;line-height:1.4}
.sm-high{color:#22c55e}.sm-mid{color:#f59e0b}.sm-low{color:#ef4444}

/* ── QA Review ── */
.qa-layout{display:grid;grid-template-columns:380px 1fr;gap:16px;padding:20px;height:calc(100vh - 140px)}
.qa-list{overflow-y:auto;border:1px solid #334155;border-radius:10px;background:#1e293b}
.qa-item{padding:10px 14px;border-bottom:1px solid #334155;cursor:pointer;transition:.15s}
.qa-item:hover{background:#334155}
.qa-item.selected{background:#1e3a5f;border-left:3px solid #38bdf8}
.qa-item .qa-q{font-size:13px;color:#e2e8f0;margin-bottom:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.qa-item .qa-meta{font-size:11px;color:#64748b}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}
.badge-pending{background:#f59e0b33;color:#f59e0b}
.badge-approved{background:#22c55e33;color:#22c55e}
.badge-rejected{background:#ef444433;color:#ef4444}
.qa-detail{padding:16px;border:1px solid #334155;border-radius:10px;background:#1e293b;overflow-y:auto}
.qa-detail h3{color:#38bdf8;margin-bottom:12px}
.qa-detail label{display:block;font-size:12px;color:#94a3b8;margin:10px 0 4px}
.qa-detail textarea{width:100%;min-height:80px;resize:vertical}

/* ── Web Eval ── */
.lh-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;padding:20px}
.lh-card{background:#1e293b;border-radius:50%;width:120px;height:120px;display:flex;flex-direction:column;align-items:center;justify-content:center;margin:0 auto;border:4px solid #334155}
.lh-card .ring{font-size:32px;font-weight:bold}
.lh-card .label{font-size:11px;color:#94a3b8;text-align:center;margin-top:4px}
.lh-ring-green{border-color:#22c55e}.lh-ring-green .ring{color:#22c55e}
.lh-ring-yellow{border-color:#f59e0b}.lh-ring-yellow .ring{color:#f59e0b}
.lh-ring-red{border-color:#ef4444}.lh-ring-red .ring{color:#ef4444}
.web-eval-detail{padding:20px}
.web-eval-detail table{width:100%;border-collapse:collapse}
.web-eval-detail th,.web-eval-detail td{padding:10px;border-bottom:1px solid #334155;text-align:left;font-size:13px}
.web-eval-detail th{color:#94a3b8}

/* ── Report Viewer ── */
.report-viewer{background:#1e293b;border-radius:10px;border:1px solid #334155;margin:20px}
.report-viewer h3{color:#38bdf8;padding:16px 16px 0}
.report-table{width:100%;border-collapse:collapse;margin:16px 0}
.report-table th,.report-table td{padding:10px 16px;border-bottom:1px solid #334155;font-size:13px}
.report-table th{color:#94a3b8;text-align:left}
.report-conversation{background:#0f172a;border-radius:8px;padding:12px;margin:8px 0;font-size:12px}
.report-conversation .rc-user{color:#94a3b8;margin-bottom:4px}
.report-conversation .rc-ai{color:#22c55e;margin-bottom:8px;padding-left:16px;border-left:2px solid #334155}

.filter-bar{display:flex;gap:8px;padding:0 0 12px;flex-wrap:wrap}
@media(max-width:768px){.two-col,.qa-layout{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="header">
  <h1>🤖 AI Agent 评测面板 v3.1</h1>
  <div>
    <span id="testStatus" class="status-dot offline"></span>
    <span id="testStatusText" style="font-size:13px">就绪</span>
  </div>
</div>
<div class="nav">
  <a href="?tab=home" class="__TAB_HOME__" onclick="switchTab('home')">📊 首页</a>
  <a href="?tab=qareview" class="__TAB_QAREVIEW__" onclick="switchTab('qareview')">✅ QA审核</a>
  <a href="?tab=webeval" class="__TAB_WEBEVAL__" onclick="switchTab('webeval')">🌐 网页评测</a>
</div>

<!-- HOME TAB -->
<div id="tab-home" class="tab __HOME_VISIBLE__">
  <div class="grid" id="summaryCards">
    <div class="card"><h3>📊 历史测试</h3><div class="value" id="totalTests">-</div></div>
    <div class="card"><h3>⭐ 平均综合分</h3><div class="value" id="avgScore">-</div></div>
    <div class="card"><h3>✅ 黄金QA库</h3><div class="value" id="qaApproved">-</div></div>
    <div class="card"><h3>⚡ 状态</h3><div class="value" id="currentPhase" style="font-size:16px">待命</div></div>
  </div>

  <!-- 🟢 测评控制区 -->
  <div class="controls">
    <select id="agentSelect"><option value="platform">HiAgent API测试</option><option value="web_test">网站测试 (Playwright)</option></select>
    <input id="numQuestions" type="number" value="1" min="1" max="10" style="width:70px" title="测试场景数">
    <button class="btn btn-primary" id="startTestBtn" onclick="startTest()">▶ 开始测评</button>
    <button class="btn btn-outline" onclick="refreshHome()">🔄 刷新</button>
    <span style="font-size:12px;color:#64748b" id="evalHint">选择Agent和场景数，点击"开始测评"即可在下方查看完整过程</span>
  </div>

  <div class="progress-bar" style="margin:0 20px 0"><div class="progress-fill" id="progressFill" style="width:0%"></div></div>
  <div style="padding:0 20px 8px;font-size:11px;color:#64748b" id="progressLabel"></div>

  <!-- 🟢 实时评测面板 -->
  <div class="live-eval" id="liveEvalPanel" style="display:none">
    <div class="live-eval-header">
      <h3 id="liveEvalTitle">🔍 实时评测过程</h3>
      <button class="btn btn-outline btn-sm" onclick="document.getElementById('liveEvalBody').innerHTML='<div style=color:#64748b;text-align:center;padding:20px>等待新评测...</div>'">清空</button>
    </div>
    <div class="live-eval-body" id="liveEvalBody">
      <div style="color:#64748b;text-align:center;padding:20px">点击"开始测评"查看完整过程</div>
    </div>
  </div>

  <!-- 得分卡片区 -->
  <div class="score-mini-grid" id="scoreMiniGrid" style="padding:0 20px"></div>

  <!-- 图表区 -->
  <div class="two-col" style="padding:0 20px 20px">
    <div class="card"><h3>📈 得分趋势</h3><canvas id="trendChart" height="180"></canvas></div>
    <div class="card"><h3>🎯 维度分布</h3><canvas id="radarChart" height="180"></canvas></div>
  </div>

  <!-- 历史报告 -->
  <div class="report-viewer" id="reportViewer">
    <h3>📋 历史报告</h3>
    <div style="padding:16px" id="reportList">加载中...</div>
    <div id="reportDetail" style="padding:0 16px 16px"></div>
  </div>
</div>

<!-- QA REVIEW TAB -->
<div id="tab-qareview" class="tab __QAREVIEW_VISIBLE__">
  <div class="controls" style="padding-top:16px">
    <select id="qaFilterStatus" onchange="loadQAList()"><option value="all">全部</option><option value="pending" selected>待审核</option><option value="approved">已通过</option><option value="rejected">已拒绝</option></select>
    <select id="qaFilterPhase" onchange="loadQAList()"><option value="all">全部阶段</option><option>PHASE 01</option><option>PHASE 02</option><option>PHASE 03</option><option>PHASE 04</option><option>PHASE 05</option></select>
    <button class="btn btn-primary btn-sm" onclick="generateQA()">🔄 从Excel生成QA</button>
    <span id="qaStats" style="font-size:12px;color:#94a3b8"></span>
  </div>
  <div class="qa-layout">
    <div class="qa-list" id="qaList"><div style="padding:40px;text-align:center;color:#64748b">加载中...</div></div>
    <div class="qa-detail" id="qaDetail"><div style="padding:40px;text-align:center;color:#64748b">← 选择一条QA查看详情</div></div>
  </div>
</div>

<!-- WEB EVAL TAB -->
<div id="tab-webeval" class="tab __WEBEVAL_VISIBLE__">
  <div class="controls" style="padding-top:16px">
    <input id="webEvalUrl" value="http://124.174.108.70" style="width:400px">
    <button class="btn btn-primary" onclick="runWebEval()">🔍 开始评测</button>
    <button class="btn btn-outline" onclick="loadWebEvalResults()">🔄 刷新结果</button>
  </div>
  <div class="lh-cards" id="lhScoreCards"><div style="grid-column:1/-1;text-align:center;color:#64748b;padding:40px">点击"开始评测"对网页进行全维度检测</div></div>
  <div class="web-eval-detail" id="webEvalDetail"></div>
</div>

<script>
// ── Tab ─────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-'+tab).classList.add('active');
  document.querySelectorAll('.nav a').forEach(a => a.classList.remove('active'));
  document.querySelectorAll('.nav a').forEach(a => {if(a.href.includes('tab='+tab))a.classList.add('active')});
  if(tab==='qareview')loadQAList();
  if(tab==='webeval')loadWebEvalResults();
  if(tab==='home')refreshHome();
}
const urlParams=new URLSearchParams(window.location.search);
switchTab(urlParams.get('tab')||'home');

// ── WebSocket ───────────────────────────────────────
const ws=new WebSocket(`ws://${location.host}/ws`);
let evalEvents=[];
ws.onmessage=(e)=>{
  const msg=JSON.parse(e.data);
  if(msg.type==='eval_event'){
    evalEvents.push(msg);
    handleEvalEvent(msg.event,msg.data);
    updateProgress(msg);
    if(msg.event==='done'){onTestComplete();}
  }
};

function updateProgress(msg){
  if(msg.event==='scenario_start'){
    document.getElementById('progressFill').style.width=(msg.data.index-1)/msg.data.total*100+'%';
    document.getElementById('progressLabel').textContent=`场景 ${msg.data.index}/${msg.data.total}`;
  }
  if(msg.event==='scenario_done'){
    document.getElementById('progressFill').style.width=msg.data.index/msg.data.total*100+'%';
  }
  if(msg.event==='done'){
    document.getElementById('progressFill').style.width='100%';
    document.getElementById('progressLabel').textContent='✅ 评测完成';
    document.getElementById('testStatus').classList.remove('busy');document.getElementById('testStatus').classList.add('online');
    document.getElementById('testStatusText').textContent='就绪';
  }
}

function handleEvalEvent(event,data){
  const panel=document.getElementById('liveEvalPanel');
  const body=document.getElementById('liveEvalBody');
  panel.style.display='block';

  let icon='📌',label='',text='',cls='';
  switch(event){
    case 'test_start':
      icon='🚀';label='评测启动';text=`Agent: ${data.agent} | 场景数: ${data.total}`;
      body.innerHTML='<div style="color:#64748b;text-align:center;padding:20px">评测进行中...</div>';
      document.getElementById('liveEvalTitle').textContent=`🔍 实时评测 · ${data.agent} · ${data.total}个场景`;
      document.getElementById('scoreMiniGrid').innerHTML='';
      document.getElementById('testStatus').classList.remove('offline','online');document.getElementById('testStatus').classList.add('busy');
      document.getElementById('testStatusText').textContent='评测中';
      document.getElementById('startTestBtn').disabled=true;
      break;
    case 'scenario_start':
      icon='🎯';label=`场景 ${data.index}/${data.total}`;text=``;
      body.innerHTML+=`<div style="color:#38bdf8;font-weight:600;padding:12px 0 4px;font-size:14px;border-top:2px solid #334155;margin-top:8px">📝 场景 ${data.index}/${data.total} · ${data.qa_id||''}</div>`;
      break;
    case 'agent_start':icon='🔌';label='连接Agent';text=`正在连接 ${data.agent}`;break;
    case 'agent_ready':icon='✅';label='Agent就绪';text='浏览器已启动，页面加载完成';break;
    case 'prologue':icon='💬';label='开场白';text=data.text;cls='ai';break;
    case 'send':icon='📤';label=`第${data.turn}轮提问 (${data.max_turns}轮)`;text=data.question;cls='user';break;
    case 'response':icon='📥';label=`第${data.turn}轮回复 (${data.status}, ${data.duration}s)`;text=data.text;cls='ai';break;
    case 'generating_followup':icon='🧠';label='生成追问';text='LLM正在根据上下文生成追问...';break;
    case 'followup':icon='🔄';label='追问';text=data.question;cls='user';break;
    case 'followup_end':icon='⏹️';label='追问结束';text='无需继续追问';break;
    case 'conversation_end':icon='🏁';label='对话结束';text=data.reason;break;
    case 'turns_done':icon='📋';label='对话完成';text=`共 ${data.total_turns} 轮对话`;break;
    case 'boundary_start':icon='🛡️';label='边界检测';text='开始检测回答是否在课程范围内...';break;
    case 'boundary_done':icon='🛡️';label='边界检测完成';text=`状态: ${data.status} | 关键词命中率: ${data.hit_rate}% | ${data.recommendation}`;cls='ai';break;
    case 'scoring':icon='📊';label='6维度评分';text='LLM正在综合评估...';break;
    case 'score_done':
      icon='📊';label='评分完成';
      const jinfo=data.n_judges?`${data.n_judges}Judge σ=${data.judge_variance||0}`:'';
      const warn=data.needs_human_review?' ⚠️需复核':'';
      text=`综合: ${data.overall}/5.0 | 正确性:${data.correctness} 相关性:${data.relevancy} 完整性:${data.completeness} 引导力:${data.guidance} 追问:${data.followup_quality} 边界:${data.boundary_compliance} 一致性:${data.turn_consistency} 递进性:${data.knowledge_scaffolding} | ${jinfo}${warn}`;
      showScoreCards(data);
      break;
    case 'scenario_done':icon='✅';label='场景完成';text=`综合得分: ${data.overall}/5.0`;break;
    case 'done':icon='🏁';label='评测全部完成';text='报告已生成, 详情见下方';document.getElementById('startTestBtn').disabled=false;break;
    case 'error':icon='❌';label='错误';text=data.message;cls='error';document.getElementById('startTestBtn').disabled=false;break;
    default:return;
  }

  if(text){
    const div=document.createElement('div');
    div.className='eval-step';
    div.innerHTML=`<div class="step-icon ${event}">${icon}</div><div class="step-content"><div class="step-label">${label}</div><div class="step-text ${cls}">${text}</div></div>`;
    body.appendChild(div);
    body.scrollTop=body.scrollHeight;
  }
}

function showScoreCards(scores){
  const dims=[
    {key:'correctness',label:'事实正确性'},
    {key:'relevancy',label:'答案相关性'},
    {key:'completeness',label:'内容完整性'},
    {key:'guidance',label:'教学引导力'},
    {key:'followup_quality',label:'追问质量'},
    {key:'boundary_compliance',label:'边界合规'},
    {key:'turn_consistency',label:'跨轮一致性',isNew:true},
    {key:'knowledge_scaffolding',label:'知识递进',isNew:true},
    {key:'overall',label:'综合得分',isOverall:true},
  ];
  const grid=document.getElementById('scoreMiniGrid');
  const confidence=scores.confidences||{};
  const flags=scores.flags||[];
  grid.innerHTML=dims.map(d=>{
    const v=scores[d.key]||0;
    const cls=v>=4?'sm-high':v>=3?'sm-mid':'sm-low';
    const conf=confidence[d.key];
    const confHtml=conf!==undefined?`<span style="font-size:9px;color:${conf>1.0?'#ef4444':'#64748b'}">σ=${conf.toFixed(1)}</span>`:'';
    const newTag=d.isNew?'<span style="font-size:8px;background:#a855f7;color:#fff;padding:0 4px;border-radius:2px;margin-left:2px">NEW</span>':'';
    const explanations={
      correctness:['严重错误','多处错误','部分准确','基本准确','完全准确'],
      relevancy:['答非所问','多次偏离','部分切题','整体切题','完全切题'],
      completeness:['几乎未覆盖','少数覆盖','覆盖一半','覆盖大部分','全部覆盖'],
      guidance:['无引导','引导混乱','基本引导','较清晰','层层递进'],
      followup_quality:['完全混乱','重复答非所问','质量下降','回答良好','高质量'],
      boundary_compliance:['完全脱离','大部分通用','部分课程','主要课程','严格基于课程'],
      turn_consistency:['完全不一致','多次矛盾','存在跳跃','基本一致','完全一致'],
      knowledge_scaffolding:['无递进','退步/重复','独立缺少递进','有递进','层层深化'],
      overall:['不合格','需改进','良好','优秀','卓越'],
    };
    const expText=explanations[d.key]?explanations[d.key][Math.min(4,Math.floor(v))]:'';
    return `<div class="score-mini"><div class="sm-val ${cls}">${v.toFixed(1)}${newTag}</div><div class="sm-label">${d.label} ${confHtml}</div><div class="sm-explanation">${expText}</div></div>`;
  }).join('');
  // 置信度告警
  if(flags.length>0){
    const alertBox=document.createElement('div');
    alertBox.style.cssText='margin:8px 20px;padding:8px 12px;background:#3a1a1a;border:1px solid #ef4444;border-radius:6px;font-size:12px;color:#ef4444';
    alertBox.innerHTML='⚠️ 评分置信度低: '+flags.join('; ')+' (多Judge投票不一致)';
    grid.appendChild(alertBox);
  }
}

function onTestComplete(){
  setTimeout(refreshHome,2000);
  setTimeout(loadReportList,3000);
}

// ── Home ────────────────────────────────────────────
async function refreshHome(){
  try{
    const resp=await fetch('/api/dashboard/summary');
    const data=await resp.json();
    document.getElementById('totalTests').textContent=data.total_tests;
    document.getElementById('avgScore').textContent=(data.avg_overall||0).toFixed(2);
    const qaResp=await fetch('/api/qa/stats');
    const qaData=await qaResp.json();
    document.getElementById('qaApproved').textContent=qaData.approved;
    if(data.trend&&data.trend.length>0)drawTrend(data.trend);
    if(data.latest)drawRadar(data.latest);
    loadReportList();
  }catch(e){console.error(e);}
}

let trendChart=null,radarChart=null;
function drawTrend(trend){
  const ctx=document.getElementById('trendChart').getContext('2d');
  if(trendChart)trendChart.destroy();
  trendChart=new Chart(ctx,{type:'line',data:{labels:trend.map(t=>t.ts.slice(9,17)).reverse(),
    datasets:[{label:'综合得分',data:trend.map(t=>t.score).reverse(),borderColor:'#38bdf8',backgroundColor:'rgba(56,189,248,0.1)',fill:true,tension:.3}]},
    options:{responsive:true,plugins:{legend:{labels:{color:'#94a3b8'}}},scales:{x:{ticks:{color:'#64748b'},grid:{color:'#1e293b'}},y:{min:0,max:5,ticks:{color:'#64748b'},grid:{color:'#1e293b'}}}}});
}
function drawRadar(data){
  const ctx=document.getElementById('radarChart').getContext('2d');
  if(radarChart)radarChart.destroy();
  const ss=data.summary.avg_scores;
  const labs=['正确性','相关性','完整性','引导力','追问','边界'];
  const vals=[ss.correctness||0,ss.relevancy||0,ss.completeness||0,ss.guidance||0,ss.followup_quality||0,ss.boundary_compliance||0];
  radarChart=new Chart(ctx,{type:'radar',data:{labels:labs,datasets:[{label:data.timestamp,data:vals,borderColor:'#38bdf8',backgroundColor:'rgba(56,189,248,0.15)'}]},
    options:{responsive:true,scales:{r:{min:0,max:5,grid:{color:'#334155'},pointLabels:{color:'#94a3b8'}}},plugins:{legend:{labels:{color:'#94a3b8'}}}}});
}

async function startTest(){
  if(document.getElementById('startTestBtn').disabled)return;
  const agent=document.getElementById('agentSelect').value;
  const num=document.getElementById('numQuestions').value;
  document.getElementById('liveEvalPanel').style.display='block';
  document.getElementById('liveEvalBody').innerHTML='<div style="color:#f59e0b;text-align:center;padding:20px">⏳ 正在启动评测...</div>';
  document.getElementById('liveEvalTitle').textContent='🔍 实时评测过程';
  document.getElementById('scoreMiniGrid').innerHTML='';
  document.getElementById('progressFill').style.width='0%';
  document.getElementById('progressLabel').textContent='启动中...';
  document.getElementById('evalHint').textContent='评测进行中，下方展示每一步详细信息...';
  evalEvents=[];
  try{
    const resp=await fetch(`/api/tests/run?agent_id=${agent}&num_questions=${num}`,{method:'POST'});
    const data=await resp.json();
    if(data.status!=='started')alert(JSON.stringify(data));
  }catch(e){alert(e.message);document.getElementById('startTestBtn').disabled=false;}
}

// ── Report List ─────────────────────────────────────
async function loadReportList(){
  try{
    const resp=await fetch('/api/reports/list');
    const reports=await resp.json();
    const el=document.getElementById('reportList');
    if(!reports.length){el.innerHTML='<span style="color:#64748b">暂无报告</span>';return;}
    el.innerHTML=reports.map((r,i)=>`<button class="btn btn-outline btn-sm" onclick="loadReportDetail('${r.filename}')" style="margin:0 6px 6px 0">📄 ${r.timestamp.slice(9)} · ${r.overall?.toFixed(1)||'?'}/5 · ${r.total}场景</button>`).join('');
    if(reports.length>0)loadReportDetail(reports[0].filename);
  }catch(e){console.error(e);}
}

async function loadReportDetail(filename){
  try{
    const resp=await fetch('/api/tests/'+filename);
    const data=await resp.json();
    const s=data.summary||{};
    const avg=s.avg_scores||{};
    const explanations=s.explanations||{};
    const dims=[{k:'correctness',l:'事实正确性'},{k:'relevancy',l:'答案相关性'},{k:'completeness',l:'内容完整性'},{k:'guidance',l:'教学引导力'},{k:'followup_quality',l:'追问质量'},{k:'boundary_compliance',l:'边界合规性'},{k:'turn_consistency',l:'跨轮一致性'},{k:'knowledge_scaffolding',l:'知识递进性'}];

    let html=`<div style="padding-top:16px"><h4 style="color:#38bdf8">📊 ${data.timestamp} · 综合 ${avg.overall?.toFixed(2)||'?'}/5.00</h4></div>`;

    // 评分表
    html+=`<table class="report-table"><tr><th>维度</th><th>得分</th><th>解释</th></tr>`;
    dims.forEach(d=>{
      const v=avg[d.k]||0;
      const exp=explanations[d.k]||'';
      const cls=v>=4?'color:#22c55e':v>=3?'color:#f59e0b':'color:#ef4444';
      html+=`<tr><td>${d.l}</td><td style="${cls};font-weight:bold">${v.toFixed(2)}</td><td style="font-size:12px;color:#94a3b8">${exp}</td></tr>`;
    });
    html+=`</table>`;

    // 边界
    if(s.boundary){
      const b=s.boundary;
      html+=`<div style="margin:16px 0;padding:12px;background:#0f172a;border-radius:8px;font-size:13px"><b>🛡️ 边界检测</b>: 在范围${b.in_scope} · 部分匹配${b.partial_match} · 超出${b.out_of_scope}</div>`;
    }

    // 场景详情
    (data.details||[]).forEach((r,i)=>{
      const qd=r.question_data||{};
      const sc=r.score||{};
      html+=`<div style="margin-top:16px;padding:12px;background:#0f172a;border-radius:8px"><b>场景${i+1}</b>: ${(qd.question||'').substring(0,80)}...<br><span style="font-size:11px;color:#64748b">${qd.phase||''} · ${qd.type||''}</span>`;

      if(sc.overall){
        html+=`<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:8px">`;
        dims.forEach(d=>{
          if(d.k==='boundary_compliance')return;
          const v=sc[d.k]||0;
          if(v>0){
            const cls=v>=4?'#22c55e':v>=3?'#f59e0b':'#ef4444';
            html+=`<span style="font-size:11px;background:#1e293b;padding:4px 8px;border-radius:4px">${d.l}: <b style="color:${cls}">${v}</b></span>`;
          }
        });
        html+=`</div>`;
      }

      // 对话记录
      (r.conversation_turns||[]).forEach(t=>{
        const resp=t.response||{};
        html+=`<div class="report-conversation"><div class="rc-user">👤 <b>第${t.turn}轮</b>: ${t.question}</div><div class="rc-ai">🤖 (${resp.status}, ${(resp.duration||0).toFixed(1)}s): ${(resp.response||'').substring(0,300)}</div></div>`;
      });
      html+=`</div>`;
    });

    document.getElementById('reportDetail').innerHTML=html;
  }catch(e){console.error(e);}
}

// ── QA Review ───────────────────────────────────────
let selectedQA=null;
async function loadQAList(){
  const status=document.getElementById('qaFilterStatus').value;
  const phase=document.getElementById('qaFilterPhase').value;
  try{
    const resp=await fetch(`/api/qa/list?status=${status}&phase=${phase}`);
    const data=await resp.json();
    const statsResp=await fetch('/api/qa/stats');
    const stats=await statsResp.json();
    document.getElementById('qaStats').textContent=`待审:${stats.pending} | 通过:${stats.approved} | 拒绝:${stats.rejected}`;
    const listEl=document.getElementById('qaList');
    if(!data.items.length){listEl.innerHTML='<div style="padding:40px;text-align:center;color:#64748b">暂无QA数据</div>';return;}
    listEl.innerHTML=data.items.map((q,i)=>`<div class="qa-item ${selectedQA===q.qa_id?'selected':''}" onclick="selectQA('${q.qa_id}')"><div class="qa-q">${q.question.substring(0,60)}...</div><div class="qa-meta">${q.phase} | ${q.type} | <span class="badge badge-${q.status}">${q.status}</span></div></div>`).join('');
  }catch(e){console.error(e);}
}
async function selectQA(qaId){
  selectedQA=qaId;
  const resp=await fetch(`/api/qa/list?status=all&phase=all`);
  const data=await resp.json();
  const q=data.items.find(i=>i.qa_id===qaId);
  if(!q)return;
  document.getElementById('qaDetail').innerHTML=`<h3>📝 ${q.qa_id}</h3>
    <label>阶段</label><div>${q.phase} | ${q.type} | ${q.difficulty}</div>
    <label>问题</label><textarea>${q.question}</textarea>
    <label>黄金答案</label><textarea style="min-height:120px">${q.golden_answer}</textarea>
    <label>知识点</label><div>${(q.knowledge_points||[]).join(', ')}</div>
    <label>来源</label><div style="font-size:12px;color:#94a3b8">${q.source?.document} / ${q.source?.sheet}</div>
    <label>原文依据</label><div style="font-size:12px;color:#64748b;background:#0f172a;padding:8px;border-radius:4px">${q.source?.excerpt||'N/A'}</div>
    <label>状态</label><span class="badge badge-${q.status}">${q.status}</span>
    <div style="margin-top:14px;display:flex;gap:8px">
      ${q.status==='pending'?`<button class="btn btn-success btn-sm" onclick="approveQA('${q.qa_id}')">✅ 通过</button><button class="btn btn-danger btn-sm" onclick="rejectQA('${q.qa_id}')">❌ 拒绝</button><button class="btn btn-warning btn-sm" onclick="editQA('${q.qa_id}')">✏️ 编辑</button>`:'<span style="color:#94a3b8">已处理</span>'}
    </div>`;
  loadQAList();
}
async function approveQA(qaId){await fetch(`/api/qa/${qaId}/approve`,{method:'POST'});loadQAList();selectQA(qaId);}
async function rejectQA(qaId){const reason=prompt('拒绝原因（可选）:');await fetch(`/api/qa/${qaId}/reject?reason=${encodeURIComponent(reason||'')}`,{method:'POST'});loadQAList();selectQA(qaId);}
async function editQA(qaId){alert('编辑功能：修改上方文本后点击保存（Demo阶段简化实现）');}
async function generateQA(){document.getElementById('qaList').innerHTML='<div style="padding:40px;text-align:center;color:#f59e0b">⏳ 正在从Excel生成QA...</div>';try{const resp=await fetch('/api/qa/generate',{method:'POST'});const data=await resp.json();loadQAList();}catch(e){loadQAList();}}
setInterval(loadQAList,15000);

// ── Web Eval ────────────────────────────────────────
async function runWebEval(){
  const url=document.getElementById('webEvalUrl').value;
  document.getElementById('lhScoreCards').innerHTML='<div style="grid-column:1/-1;text-align:center;color:#f59e0b;padding:40px">⏳ 正在评测网页...</div>';
  try{const resp=await fetch(`/api/web-eval/run?url=${encodeURIComponent(url)}`,{method:'POST'});const data=await resp.json();if(data.ok)loadWebEvalResults();}catch(e){console.error(e);}
}
async function loadWebEvalResults(){
  try{
    const resp=await fetch('/api/web-eval/results');
    const data=await resp.json();
    if(data.error){document.getElementById('lhScoreCards').innerHTML=`<div style="grid-column:1/-1;text-align:center;color:#64748b;padding:40px">${data.error}</div>`;return;}
    renderWebEval(data);
  }catch(e){document.getElementById('lhScoreCards').innerHTML='<div style="grid-column:1/-1;text-align:center;color:#64748b;padding:40px">暂无结果</div>';}
}
function renderWebEval(data){
  const p=data.performance||{},a=data.accessibility||{},bp=data.best_practices||{},ai=data.ai_function||{},ux=data.ui_ux||{},ct=data.content||{};
  const cards=[
    {label:'综合',score:data.overall_score},{label:'性能',score:p.score||0,detail:`LCP:${p.lcp||0}ms`},
    {label:'可访问性',score:a.score||0,detail:`违规:${(a.violations||[]).length}项`},{label:'最佳实践',score:bp.score||0,detail:`HTTPS:${bp.https?'✓':'✗'}`},
    {label:'AI对话',score:ai.score||0,detail:`延迟:${ai.response_latency_ms||0}ms`},{label:'UI/UX',score:ux.score||0},{label:'内容',score:ct.score||0}
  ];
  document.getElementById('lhScoreCards').innerHTML=cards.map(c=>{
    const cls=c.score>=80?'lh-ring-green':c.score>=50?'lh-ring-yellow':'lh-ring-red';
    return `<div style="text-align:center"><div class="lh-card ${cls}"><span class="ring">${c.score}</span><span class="label">${c.label}</span></div><div style="font-size:11px;color:#64748b;margin-top:4px">${c.detail||''}</div></div>`;
  }).join('');
  const violations=a.violations||[],layoutIssues=ux.layout_issues||[];
  document.getElementById('webEvalDetail').innerHTML=`<table><tr><th>指标</th><th>值</th><th>评估</th></tr>
    <tr><td>LCP</td><td>${p.lcp||0}ms</td><td>${p.lcp<2500?'✅':p.lcp<4000?'⚠️':'❌'}</td></tr>
    <tr><td>TTFB</td><td>${p.ttfb||0}ms</td><td>${p.ttfb<800?'✅':p.ttfb<1800?'⚠️':'❌'}</td></tr>
    <tr><td>FCP</td><td>${p.fcp||0}ms</td><td>${p.fcp<1800?'✅':p.fcp<3000?'⚠️':'❌'}</td></tr>
    <tr><td>HTTPS</td><td>${bp.https?'✅':'❌'}</td><td>-</td></tr>
    <tr><td>可访问性违规</td><td>${violations.length}项</td><td>${violations.length===0?'✅':'⚠️'}</td></tr>
    <tr><td>AI延迟</td><td>${ai.response_latency_ms||0}ms</td><td>${(ai.response_latency_ms||0)<3000?'✅':'⚠️'}</td></tr></table>
    ${violations.length>0?`<h4 style="color:#ef4444;margin-top:16px">⚠️ 可访问性违规:</h4>${violations.map(v=>`<div style="font-size:12px;color:#94a3b8">• <b>${v.id}</b> (${v.impact}): ${v.help}</div>`).join('')}`:''}`;
}

refreshHome();
</script>
</body>
</html>"""

# Replace tab visibility
_active_tab = "home"
DASHBOARD_HTML = DASHBOARD_HTML.replace("__TAB_HOME__", "active")
DASHBOARD_HTML = DASHBOARD_HTML.replace("__TAB_QAREVIEW__", "")
DASHBOARD_HTML = DASHBOARD_HTML.replace("__TAB_WEBEVAL__", "")
DASHBOARD_HTML = DASHBOARD_HTML.replace("__HOME_VISIBLE__", "active")
DASHBOARD_HTML = DASHBOARD_HTML.replace("__QAREVIEW_VISIBLE__", "")
DASHBOARD_HTML = DASHBOARD_HTML.replace("__WEBEVAL_VISIBLE__", "")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
