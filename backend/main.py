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
    # HTML: never cache
    if path == '/' or path.endswith('.html'):
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    # JS/CSS: short cache (10s), allow revalidation
    elif any(path.endswith(ext) for ext in ('.js', '.css')):
        resp.headers["Cache-Control"] = "public, max-age=10, must-revalidate"
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


# ── 首页 ──
from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
async def root_page():
    """Serve the SPA index.html"""
    index_path = frontend_dir / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"), headers=_NO_CACHE)
    return HTMLResponse("<h1>Frontend not found</h1>", status_code=404)


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
