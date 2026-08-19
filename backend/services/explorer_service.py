"""
Platform Explorer 服务 — 后台线程运行探索器 + 轮询状态

设计: 探索器在后台线程运行, 前端通过 GET /api/explorer/status 每2秒轮询。
      WebSocket 推送是可选的 (Phase 2)。
"""

import asyncio
import json
import logging
import os
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.dependencies import get_sync_db
from backend.models import ExplorationSession
from backend.ws import ws_manager
from src.question_bridge import QuestionBridge

logger = logging.getLogger(__name__)


class ExplorerService:
    """平台探索编排服务"""

    def __init__(self):
        self._running = False
        self._current_session_id: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._cancel = threading.Event()
        self._progress_msg = ""  # 当前进度消息, 前端轮询读取
        self._bridge: Optional[QuestionBridge] = None  # 交互式登录问答桥 (当前/最近一次探索)
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None  # WS 广播用

    def set_main_loop(self, loop: Optional[asyncio.AbstractEventLoop]):
        """由 API 层注入事件循环 (WS 广播用)"""
        self._main_loop = loop

    def _on_bridge_question(self, q: dict):
        """QuestionBridge 新问题回调 — WS 推送 explorer:need_input (前端弹窗)"""
        if self._main_loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast({
                    "type": "explorer:need_input",
                    "data": {
                        "qid": q.get("qid", ""),
                        "question": q.get("text", ""),
                        "options": q.get("options", []),
                        "context": q.get("context", ""),
                        "source": q.get("source", "explorer"),
                        "timeout_s": q.get("timeout_s", 180),
                    },
                    "running": self._running,
                }),
                self._main_loop,
            )
        except Exception:
            pass  # WS 不可用不影响问答流程 (HTTP 轮询兜底)

    # ── 问答桥访问器 (API 层调用) ──

    def current_question(self) -> Optional[dict]:
        """当前待回答的探索问题; 无则 None"""
        return self._bridge.current_question() if self._bridge else None

    def answer_question(self, answer: str = "", skipped: bool = False) -> bool:
        """回答当前探索问题。返回是否命中 (问题已超时/不存在则 False)"""
        return bool(self._bridge and self._bridge.answer_any(answer=answer, skipped=skipped))

    def question_history(self, last_n: int = 30) -> list:
        """最近一次探索的问答历史"""
        return self._bridge.history(last_n) if self._bridge else []

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_session_id(self) -> Optional[str]:
        return self._current_session_id

    @property
    def progress_message(self) -> str:
        return self._progress_msg

    async def start_explore(
        self,
        target_url: str,
        username: str = "",
        password: str = "",
        headless: bool = True,
        max_depth: int = 3,
        max_pages: int = 50,
        api_threshold: float = 0.50,
    ) -> dict:
        """启动一次平台探索"""
        if self._running:
            return {"status": "busy", "error": "已有探索任务在运行中"}

        self._running = True
        self._cancel.clear()

        # ── 交互式问答桥 (每次探索新建; 保留到下一次探索, 供 history 查询) ──
        self._bridge = QuestionBridge(enabled=True)
        # 探索中途向用户提问时, 通过 WS 推送到前端弹窗 (HTTP 轮询兜底在 API 层)
        self._bridge.set_on_question(self._on_bridge_question)

        session_id = (
            f"explore_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_"
            f"{uuid.uuid4().hex[:6]}"
        )
        self._current_session_id = session_id
        self._progress_msg = "Initializing..."
        project_root = Path(__file__).parent.parent.parent
        output_dir = project_root / "output" / "platform_probe" / session_id

        # ── 数据库记录 ──
        db = get_sync_db()
        try:
            session = ExplorationSession(
                session_id=session_id,
                target_url=target_url,
                status="running",
                config_snapshot={
                    "username": (username[:3] + "***") if username else "",
                    "headless": headless,
                    "max_depth": max_depth,
                    "max_pages": max_pages,
                    "api_threshold": api_threshold,
                },
                started_at=datetime.now(timezone.utc),
            )
            db.add(session)
            db.commit()
        except Exception as e:
            db.rollback()
            self._running = False
            self._current_session_id = None
            return {"status": "error", "error": f"数据库写入失败: {e}"}
        finally:
            db.close()

        # ── 后台线程 ──
        self._thread = threading.Thread(
            target=self._run_explore,
            args=(session_id, target_url, username, password,
                  headless, max_depth, max_pages, api_threshold,
                  str(output_dir), str(project_root)),
            daemon=True,
        )
        self._thread.start()

        return {
            "status": "started",
            "session_id": session_id,
            "target_url": target_url,
        }

    def _run_explore(
        self,
        session_id: str,
        target_url: str,
        username: str,
        password: str,
        headless: bool,
        max_depth: int,
        max_pages: int,
        api_threshold: float,
        output_dir: str,
        project_root: str,
    ):
        """后台线程: 运行探索器"""
        import sys
        sys.path.insert(0, project_root)

        od = Path(output_dir)
        od.mkdir(parents=True, exist_ok=True)

        try:
            # ── 检查 Playwright ──
            self._progress_msg = "L0: Checking Playwright..."
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                raise RuntimeError(
                    "Playwright not installed. Run: pip install playwright && "
                    "python -m playwright install chromium"
                )

            # ── 导入探索器 ──
            self._progress_msg = "L0: Starting browser..."
            from src.platform_probe.explorer import PlatformExplorer

            explorer = PlatformExplorer(
                headless=headless,
                output_dir=od,
                api_threshold=api_threshold,
                max_depth=max_depth,
                max_pages=max_pages,
                verbose=True,  # 启用日志输出方便调试L1.8
            )
            explorer._session_id = session_id  # 供 profile 使用

            # ── L0: 认证 ──
            self._progress_msg = "L0: Detecting auth and logging in..."
            if self._cancel.is_set():
                self._finish_session(session_id, "cancelled")
                return

            # ── L1: 捕获 ──
            self._progress_msg = "L1: Capturing traffic and exploring pages..."
            if self._cancel.is_set():
                self._finish_session(session_id, "cancelled")
                return

            # ── 交互式问答通道 (非标准登录模式 → 向用户确认) ──
            # 兼容性: src 侧 ask_callback 支持由 agent5-integration 移植,
            # 此处探测签名, 不支持时静默跳过, 保证原自动流程零变化。
            import inspect
            bridge = self._bridge
            explore_kwargs = {}

            def ask_cb(text, options=None, context="", context_type="",
                       timeout_s=180.0, source="", meta=None):
                if bridge is None:
                    return {"answer": "", "skipped": True, "timed_out": False}
                return bridge.ask(
                    text=text, options=options, context=context,
                    context_type=context_type, timeout_s=timeout_s,
                    source=source or "explorer", meta=meta,
                )

            if "ask_callback" in inspect.signature(explorer.explore).parameters:
                explore_kwargs["ask_callback"] = ask_cb
            else:
                logger.warning(
                    "PlatformExplorer.explore 不支持 ask_callback, 交互式登录问答未启用"
                )

            # ── 运行完整探索 ──
            schema, report, yaml_path = explorer.explore(
                target_url=target_url,
                username=username,
                password=password,
                **explore_kwargs,
            )

            # ── 检查取消 ──
            if self._cancel.is_set():
                self._finish_session(session_id, "cancelled")
                return

            # ── L3/L4 进度 ──
            self._progress_msg = "L3/L4: Classifying APIs and generating schema..."

            # ── 更新数据库 (成功) ──
            db = get_sync_db()
            try:
                session = db.query(ExplorationSession).filter_by(
                    session_id=session_id
                ).first()
                if session:
                    session.status = "completed"
                    session.phases_found = report.phases_found
                    session.lessons_found = report.lessons_found
                    session.steps_found = report.steps_found
                    session.api_endpoints_found = report.api_endpoints_found
                    session.hidden_endpoints_found = report.hidden_endpoints_found
                    session.overall_confidence = report.confidence.overall
                    session.structure_confidence = report.confidence.structure
                    session.api_confidence = report.confidence.apis
                    session.duration_seconds = report.duration_seconds
                    session.schema_path = yaml_path
                    session.report_path = str(od / "exploration_report.md")
                    session.warnings = {
                        "items": report.warnings,
                        "recommendations": report.recommendations,
                    }
                    session.finished_at = datetime.now(timezone.utc)
                    db.commit()
                db.close()
            except Exception:
                try:
                    db.rollback()
                    db.close()
                except Exception:
                    pass

            self._progress_msg = (
                f"Completed! {report.phases_found} phases, "
                f"{report.steps_found} steps, {report.api_endpoints_found} APIs"
            )

        except Exception as e:
            traceback_str = traceback.format_exc()
            self._progress_msg = f"Failed: {e}"

            try:
                self._finish_session(session_id, "failed", error=traceback_str)
            except Exception:
                pass

        finally:
            self._running = False
            self._current_session_id = None
            # 保留 _bridge — 供 /questions/history 查询本次探索的问答记录

    def _finish_session(self, session_id: str, status: str, error: str = ""):
        """更新数据库状态"""
        try:
            db = get_sync_db()
            session = db.query(ExplorationSession).filter_by(
                session_id=session_id
            ).first()
            if session:
                session.status = status
                if error:
                    session.error = error[:5000]
                session.finished_at = datetime.now(timezone.utc)
                db.commit()
            db.close()
        except Exception:
            pass

    async def cancel_explore(self) -> dict:
        """取消正在运行的探索"""
        if not self._running:
            return {"status": "ok", "message": "没有运行中的探索任务"}
        self._cancel.set()
        self._progress_msg = "Cancelling..."
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        if self._current_session_id:
            self._finish_session(self._current_session_id, "cancelled")
        self._running = False
        self._current_session_id = None
        return {"status": "cancelled", "message": "探索已取消"}

    async def get_status(self) -> dict:
        """获取当前状态 (前端每2秒轮询)"""
        return {
            "running": self._running,
            "session_id": self._current_session_id,
            "progress": self._progress_msg,
        }

    async def get_sessions(self, page: int = 1, page_size: int = 20) -> dict:
        """探索历史"""
        try:
            db = get_sync_db()
            from sqlalchemy import desc
            total = db.query(ExplorationSession).count()
            sessions = (
                db.query(ExplorationSession)
                .order_by(desc(ExplorationSession.created_at))
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            result = {
                "sessions": [s.to_dict() for s in sessions],
                "total": total,
                "page": page,
                "page_size": page_size,
            }
            db.close()
            return result
        except Exception as e:
            return {"sessions": [], "total": 0, "error": str(e)}

    async def get_session(self, session_id: str) -> dict | None:
        """单个探索会话"""
        try:
            db = get_sync_db()
            session = db.query(ExplorationSession).filter_by(
                session_id=session_id
            ).first()
            db.close()
            return session.to_dict() if session else None
        except Exception:
            return None

    async def get_latest_ready_schema(self) -> dict | None:
        """获取最近一次可用的 schema"""
        try:
            db = get_sync_db()
            from sqlalchemy import desc
            session = (
                db.query(ExplorationSession)
                .filter_by(status="completed")
                .filter(ExplorationSession.overall_confidence >= 0.5)
                .order_by(desc(ExplorationSession.created_at))
                .first()
            )
            db.close()
            if session:
                return {
                    "schema_path": session.schema_path,
                    "session_id": session.session_id,
                    "target_url": session.target_url,
                    "overall_confidence": session.overall_confidence,
                }
            return None
        except Exception:
            return None
