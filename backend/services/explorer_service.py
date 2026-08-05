"""
Platform Explorer 服务 — 后台线程运行探索器 + 轮询状态

设计: 探索器在后台线程运行, 前端通过 GET /api/explorer/status 每2秒轮询。
      WebSocket 推送是可选的 (Phase 2)。
"""

import json
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


class ExplorerService:
    """平台探索编排服务"""

    def __init__(self):
        self._running = False
        self._current_session_id: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._cancel = threading.Event()
        self._progress_msg = ""  # 当前进度消息, 前端轮询读取

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
                verbose=False,
            )

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

            # ── 运行完整探索 ──
            schema, report, yaml_path = explorer.explore(
                target_url=target_url,
                username=username,
                password=password,
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
