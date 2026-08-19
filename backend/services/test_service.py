"""测试服务 — 后台线程运行 TestRunner + 进度回调桥接 + 结果持久化 + Watchdog 超时保护 (P0-15)"""

import asyncio
import collections
import json
import os
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from backend.dependencies import get_sync_db
from backend.models import (
    TestSession, TestScenario, ConversationTurn, EvalScore, Report, QAPair,
)
from backend.ws import ws_manager

# ── 事件日志缓冲区 (最近 2000 条, 用于前端拉取历史) ──
_event_log_buffer: dict[str, collections.deque] = {}
_EVENT_LOG_MAX = 2000


class TestService:
    """测试编排服务 — 管理后台评测线程, 带 Watchdog 超时保护"""

    # ── P0-15: 超时配置 ──
    DEFAULT_SCENARIO_TIMEOUT = 600     # 单场景超时 10 分钟
    DEFAULT_GLOBAL_TIMEOUT = 1800      # 全局超时 30 分钟
    DEFAULT_HEARTBEAT_INTERVAL = 30    # 心跳间隔 30 秒
    DEFAULT_HEARTBEAT_STALE = 120      # 2 分钟无心跳视为卡死

    def __init__(self):
        self._running = False
        self._current_session_id: Optional[str] = None
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

        # P0-15: Watchdog 相关
        self._watchdog = None           # src.watchdog.Watchdog 实例
        self._eval_thread: Optional[threading.Thread] = None
        self._cancel_requested = threading.Event()

        # P0-15: 超时配置(可从环境变量覆盖)
        self.scenario_timeout = int(
            os.getenv("EVAL_SCENARIO_TIMEOUT", str(self.DEFAULT_SCENARIO_TIMEOUT))
        )
        self.global_timeout = int(
            os.getenv("EVAL_GLOBAL_TIMEOUT", str(self.DEFAULT_GLOBAL_TIMEOUT))
        )
        self.heartbeat_interval = int(
            os.getenv("EVAL_HEARTBEAT_INTERVAL", str(self.DEFAULT_HEARTBEAT_INTERVAL))
        )
        self.heartbeat_stale = int(
            os.getenv("EVAL_HEARTBEAT_STALE", str(self.DEFAULT_HEARTBEAT_STALE))
        )

        # 卡点干预: 评测线程遇到卡点时阻塞询问用户
        self._interventions: dict = {}          # session_id -> {event, question, options, timeout_s, default, answer, asked_at}
        self._interventions_lock = threading.Lock()
        self._audit_lock = threading.Lock()     # 干预审计日志写锁 (data/intervention_log.json)
        self._human_sessions: set = set()       # 本轮得到过人工回答的 session (退出类型 needs_human 判定)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_session_id(self) -> Optional[str]:
        return self._current_session_id

    async def start_run(
        self,
        agent_id: str = "hiagent",
        num_questions: int = 1,
        max_turns: int = 3,
        profile: str = "standard",
        target_url: str = "",
        schema_driven: bool = False,
        platform_schema_path: str = "",
    ) -> dict:
        """启动一次评测"""
        if self._running:
            return {"status": "busy", "error": "已有测试在运行中"}

        # 捕获主事件循环
        self._main_loop = asyncio.get_running_loop()
        project_root = Path(__file__).parent.parent.parent

        # 先在数据库中创建 TestSession
        db = get_sync_db()
        try:
            session_id = f"session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
            ts = TestSession(
                session_id=session_id,
                agent_id=agent_id,
                profile=profile,
                status="running",
                total_scenarios=num_questions,
                started_at=datetime.now(timezone.utc),
                config_snapshot={
                    "agent_id": agent_id,
                    "num_questions": num_questions,
                    "max_turns": max_turns,
                    "profile": profile,
                    "target_url": target_url,
                    "schema_driven": schema_driven,
                    "platform_schema_path": platform_schema_path,
                    "watchdog": {
                        "scenario_timeout": self.scenario_timeout,
                        "global_timeout": self.global_timeout,
                        "heartbeat_interval": self.heartbeat_interval,
                        "heartbeat_stale": self.heartbeat_stale,
                    },
                },
            )
            db.add(ts)
            db.commit()
            self._current_session_id = session_id
        finally:
            db.close()

        # P0-15: 初始化 Watchdog
        from src.watchdog import Watchdog
        self._watchdog = Watchdog(
            scenario_timeout=self.scenario_timeout,
            global_timeout=self.global_timeout,
            heartbeat_interval=self.heartbeat_interval,
            heartbeat_stale=self.heartbeat_stale,
            on_cancel=lambda reason: self._on_watchdog_cancel(reason),
        )
        self._watchdog.start(scenarios_total=num_questions)
        self._cancel_requested.clear()
        self._running = True

        # 后台线程
        self._eval_thread = threading.Thread(
            target=self._run_in_thread,
            args=(agent_id, num_questions, max_turns, profile, session_id, project_root, target_url),
            daemon=True,
        )
        self._eval_thread.start()

        # P0-15: 启动看门狗状态推送线程
        watchdog_reporter = threading.Thread(
            target=self._watchdog_status_reporter,
            daemon=True,
            name="watchdog-reporter",
        )
        watchdog_reporter.start()

        return {
            "status": "started",
            "session_id": session_id,
            "agent_id": agent_id,
            "num_questions": num_questions,
            # P0-15: 返回超时配置给前端
            "timeout_config": {
                "scenario_timeout": self.scenario_timeout,
                "global_timeout": self.global_timeout,
                "heartbeat_interval": self.heartbeat_interval,
            },
        }

    async def start_multi_agent(
        self, strategy: str = "spot_check",
        phases: list[str] = None, mode: str = "guided",
        headless: bool = True, target_url: str = "",
    ) -> dict:
        """启动 Multi-Agent 测试编排 (Agent C)

        Planner → Executor → Verifier → Reporter
        Schema 驱动, 零硬编码, 三通道验证
        """
        if self._running:
            return {"status": "busy", "error": "已有测试在运行中"}

        self._main_loop = asyncio.get_running_loop()
        project_root = Path(__file__).parent.parent.parent
        self._running = True
        self._cancel_requested.clear()

        session_id = f"multi_agent_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self._current_session_id = session_id

        thread = threading.Thread(
            target=self._run_multi_agent,
            args=(strategy, phases, mode, headless, session_id, project_root, target_url),
            daemon=True,
            name=f"multi-agent-{session_id[:8]}",
        )
        thread.start()

        return {
            "status": "started",
            "session_id": session_id,
            "evaluator_type": "multi_agent",
            "strategy": strategy,
            "phases": phases or "all (from schema)",
        }

    async def start_browser_eval(
        self, phases: list = None, mode: str = "guided",
        headless: bool = True, include_quiz: bool = True,
        target_url: str = "",
    ) -> dict:
        """启动全平台浏览器遍历测评"""
        if self._running:
            return {"status": "busy", "error": "已有测试在运行中"}

        if phases is None:
            phases = [1, 2, 3, 4, 5]

        self._main_loop = asyncio.get_running_loop()
        project_root = Path(__file__).parent.parent.parent
        self._running = True
        self._cancel_requested.clear()

        session_id = f"browser_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self._current_session_id = session_id

        thread = threading.Thread(
            target=self._run_browser_eval,
            args=(phases, mode, headless, include_quiz, session_id, project_root, target_url),
            daemon=True,
            name=f"browser-eval-{session_id[:8]}",
        )
        thread.start()

        total_days = sum({1:4,2:5,3:6,4:7,5:1}.get(p, 0) for p in phases)
        return {
            "status": "started",
            "session_id": session_id,
            "evaluator_type": "browser",
            "phases": phases,
            "mode": mode,
            "total_days": total_days,
            "include_quiz": include_quiz,
            "est_duration_minutes": round(total_days * 0.8),
        }

    def _run_multi_agent(
        self, strategy: str, phases: list[str], mode: str,
        headless: bool, session_id: str, project_root: Path, target_url: str = "",
    ) -> None:
        """后台线程执行 Multi-Agent 流水线 (Agent C)"""
        import os as _os
        _os.chdir(str(project_root))

        try:
            print(f"[MultiAgent] Starting: strategy={strategy} phases={phases} "
                  f"mode={mode} target_url={target_url} project_root={project_root}", flush=True)
            from src.multi_agent import MultiAgentOrchestrator

            def ws_cb(event_type: str, data: dict):
                if self._main_loop:
                    asyncio.run_coroutine_threadsafe(
                        ws_manager.broadcast({
                            "type": event_type,
                            "data": data,
                            "running": self._running,
                        }),
                        self._main_loop,
                    )

            orch = MultiAgentOrchestrator(
                ws_callback=ws_cb,
                strategy=strategy,
                phases_filter=phases,
                headless=headless,
                mode=mode,
                target_url=target_url,
                # 卡点干预: Schema 缺失等卡点阻塞询问用户
                ask_user=lambda q, opts=None, timeout_s=300, default=None: self.ask_user(
                    session_id, q, opts, timeout_s, default),
            )
            report = orch.run()

            # DIAG: 写入文件以便排查
            try:
                import json as _json
                _diag = {
                    "strategy": strategy, "phases_filter": phases,
                    "report_phases": len(report.verification_results) if report else 0,
                    "report_pass_rate": report.pass_rate if report else 0,
                }
                (project_root / "output" / "ma_diag.json").write_text(_json.dumps(_diag, indent=2, default=str))
            except Exception:
                pass

            # 广播完成
            if self._main_loop:
                asyncio.run_coroutine_threadsafe(
                    ws_manager.broadcast({
                        "type": "multi_agent:done",
                        "data": {
                            "report_path": "",
                            "pass_rate": report.pass_rate,
                            "total_steps": report.total_steps,
                            "failures": report.failures,
                        },
                        "running": False,
                    }),
                    self._main_loop,
                )
            # 退出类型指标
            from src.run_metrics import EXIT_COMPLETED, EXIT_COMPLETED_DEGRADED
            exit_type = EXIT_COMPLETED_DEGRADED if report.failures else EXIT_COMPLETED
            self._record_run_metrics("multi_agent", exit_type, session_id,
                                     errors_n=report.failures)
            # 报告持久化 → Reports 页面可见
            self._persist_multi_agent_report(session_id, project_root, report, "")
        except Exception as e:
            import traceback as _tb2
            print(f"[MultiAgent] FAILED: {e}\n{_tb2.format_exc()}", flush=True)
            self._record_run_metrics("multi_agent", "failed_permanently",
                                     session_id, note=str(e)[:200])
            if self._main_loop:
                asyncio.run_coroutine_threadsafe(
                    ws_manager.broadcast({
                        "type": "multi_agent:done",
                        "data": {"error": str(e), "pass_rate": 0, "total_steps": 0, "failures": 0},
                        "running": False,
                    }),
                    self._main_loop,
                )
        finally:
            self._running = False

    def _run_browser_eval(
        self, phases: list, mode: str, headless: bool,
        include_quiz: bool, session_id: str, project_root: Path,
    ) -> None:
        """后台线程执行浏览器遍历测评"""
        import os as _os
        _os.chdir(str(project_root))

        # 广播: 开始
        if self._main_loop:
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast({
                    "type": "eval_event",
                    "event": "browser_start",
                    "data": {"phases": phases, "mode": mode, "session_id": session_id},
                }), self._main_loop)

        try:
            from src.browser_evaluator import BrowserEvaluator
            evaluator = BrowserEvaluator(
                headless=headless,
                mode=mode,
                phase_filter=None,  # 全Phase, 由phases列表控制
            )
            # Agent C: Self-Healing 定位器自动恢复 (四层级联: L0原始→L1语义→L2结构→L3 AI)
            from src.self_healing import apply_self_healing
            apply_self_healing(evaluator)
            # 卡点干预: 登录失败/Day出错时阻塞询问用户
            evaluator._ask_cb = lambda q, opts=None, timeout_s=300, default=None: self.ask_user(
                session_id, q, opts, timeout_s, default)
            # 注入 WebSocket 进度回调
            orig_log = evaluator._log
            def _ws_log(msg, level="info"):
                orig_log(msg, level)
                if self._main_loop:
                    asyncio.run_coroutine_threadsafe(
                        ws_manager.broadcast({
                            "type": "eval_event",
                            "event": "browser_log",
                            "data": {"msg": msg, "level": level, "session_id": session_id},
                        }), self._main_loop)

            evaluator._log = _ws_log
            result = evaluator.run()

            # Agent C: Coverage Tracker — 计算测试覆盖率 (不阻塞主流程)
            coverage_report = None
            try:
                from src.coverage_tracker import compute_coverage_after_eval
                coverage_report = compute_coverage_after_eval()
                if coverage_report.get("schema_available"):
                    orig_log(f"Coverage: {coverage_report['overall']['coverage_pct']}% overall, "
                             f"{len(coverage_report.get('risk_areas',[]))} risk areas", "info")
            except Exception as coverage_err:
                orig_log(f"Coverage tracker unavailable: {coverage_err}", "warn")

            # 广播: 完成
            summary = result.get("summary", {})
            if self._main_loop:
                asyncio.run_coroutine_threadsafe(
                    ws_manager.broadcast({
                        "type": "eval_event",
                        "event": "browser_done",
                        "data": {
                            "session_id": session_id,
                            "summary": summary,
                            "phases_tested": summary.get("phases_tested", []),
                            "days_completed": summary.get("days_completed", 0),
                            "days_total": summary.get("days_total", 0),
                            "phase5_ok": summary.get("phase5_agent_ok", False),
                            # Agent C: 覆盖率摘要 (若可用)
                            "coverage": coverage_report.get("overall") if coverage_report else None,
                        },
                    }), self._main_loop)

            # 退出类型指标: 完成 (带错误=降级完成) / 人工介入过=needs_human
            from src.run_metrics import (
                EXIT_COMPLETED, EXIT_COMPLETED_DEGRADED)
            errors_n = len(result.get("errors") or [])
            exit_type = EXIT_COMPLETED_DEGRADED if errors_n else EXIT_COMPLETED
            self._record_run_metrics("browser_eval", exit_type, session_id,
                                     errors_n=errors_n)
        except Exception as e:
            import traceback
            self._record_run_metrics("browser_eval", "failed_permanently",
                                     session_id, note=str(e)[:200])
            if self._main_loop:
                asyncio.run_coroutine_threadsafe(
                    ws_manager.broadcast({
                        "type": "eval_event",
                        "event": "browser_error",
                        "data": {"session_id": session_id, "error": str(e)},
                    }), self._main_loop)
        finally:
            self._running = False

    # ═══════════════════════════════════════════════════════════
    # 卡点干预 (自动化为主, 卡点暴露询问用户)
    # ═══════════════════════════════════════════════════════════

    def ask_user(
        self, session_id: str, question: str, options: list | None = None,
        timeout_s: int = 300, default: str | None = None,
        card: dict | None = None,
    ) -> str:
        """阻塞询问用户 — 评测线程在卡点处调用。

        1. 记录待回答状态并广播 WS 事件 eval:need_input
        2. 阻塞等待用户 POST /api/tests/intervention/respond
        3. 超时 → 返回 default (自动化优先, 不无限等待)

        card: 六要素求助卡 (error_interpreter.interpret 的产物),
              随 WS 事件带给前端展示 reason/evidence/recovery/risk。
        """
        if card:
            # 求助卡优先: 六要素 + 风险分级超时
            question = card.get("question") or question
            options = list(card.get("options") or options or [])
            default = card.get("default") or default
            timeout_s = int(card.get("timeout_s") or timeout_s)
        entry = {
            "event": threading.Event(),
            "question": question,
            "options": list(options or []),
            "timeout_s": timeout_s,
            "default": default,
            "answer": None,
            "asked_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._interventions_lock:
            self._interventions[session_id] = entry

        # 审计: 记录一次 ask
        self._append_intervention_log(
            "ask", session_id,
            question=question, options=entry["options"],
            timeout_s=timeout_s, default=default,
            card=card or {},
        )

        # 广播: 前端弹窗询问
        if self._main_loop:
            try:
                asyncio.run_coroutine_threadsafe(
                    ws_manager.broadcast({
                        "type": "eval:need_input",
                        "data": {
                            "session_id": session_id,
                            "question": question,
                            "options": entry["options"],
                            "timeout_s": timeout_s,
                            "default": default,
                            "card": card or {},
                        },
                        "running": self._running,
                    }),
                    self._main_loop,
                )
            except Exception:
                pass  # WS 不可用不影响询问流程 (HTTP 轮询兜底)

        answered = entry["event"].wait(timeout_s)
        with self._interventions_lock:
            stored = self._interventions.pop(session_id, None)

        answer = (stored or entry).get("answer")
        if answered and answer not in (None, ""):
            # 标记: 本次运行得到过人工介入 → 退出类型判定用
            with self._interventions_lock:
                self._human_sessions.add(session_id)
            # 经验库: 失败+人工修复 → 下次同类任务先查这条经验 (自演化)
            try:
                from src.experience_store import record_experience, TASK_EVALUATION, EXIT_NEEDS_HUMAN
                record_experience(
                    task_type=TASK_EVALUATION,
                    trigger=question[:200],
                    action=str(answer)[:200],
                    outcome="已按用户回答继续",
                    exit_type=EXIT_NEEDS_HUMAN,
                    note="评测卡点人工干预",
                )
            except Exception:
                pass
            self._append_intervention_log("answer", session_id, answer=answer)
            return str(answer)
        # 审计: 超时走默认动作
        self._append_intervention_log("timeout", session_id, answer=default)
        return default if default is not None else "skip"

    def respond_intervention(self, session_id: str, answer: str) -> bool:
        """用户应答 (由 API 端点调用, 非阻塞)"""
        with self._interventions_lock:
            entry = self._interventions.get(session_id)
        if not entry:
            return False  # 已超时或不存在
        entry["answer"] = answer
        entry["event"].set()
        # 审计: 记录一次 answer
        self._append_intervention_log("answer", session_id, answer=answer)
        return True

    def pending_intervention(self) -> dict | None:
        """当前待回答的干预问题 (前端轮询兜底)"""
        with self._interventions_lock:
            for sid, entry in self._interventions.items():
                return {
                    "session_id": sid,
                    "question": entry["question"],
                    "options": entry["options"],
                    "timeout_s": entry["timeout_s"],
                    "default": entry["default"],
                    "asked_at": entry["asked_at"],
                    "card": entry.get("card") or {},
                }
        return None

    def _persist_multi_agent_report(self, session_id: str, project_root: Path,
                                    report, report_path: str):
        """Multi-Agent 结果持久化到 reports 表 — Reports 页面立即可见

        (此前 multi_agent 结果只写 eval_output 文件, 前端 Reports 页读不到 —
         用户跑完评测却找不到结果, 这是交付缺口)
        """
        try:
            from backend.models import Report as ReportModel, TestSession as TestSessionModel
            import glob as _glob
            # 找到本次运行的报告文件 (Reporter 写入 eval_output/multi_agent/)
            if not report_path:
                cands = sorted(
                    _glob.glob(str(project_root / "eval_output" / "multi_agent" / "multi_agent_report_*.json")),
                    reverse=True)
                report_path = cands[0] if cands else ""
            markdown = ""
            try:
                if report_path and Path(report_path).exists():
                    import json as _json
                    data = _json.loads(Path(report_path).read_text(encoding="utf-8"))
                    diag = data.get("diagnosis") or {}
                    findings = diag.get("findings") or []
                    lines = [
                        f"# Multi-Agent 评测报告",
                        f"",
                        f"- 会话: {session_id}",
                        f"- 策略: {data.get('strategy', '')}",
                        f"- 通过率: {data.get('pass_rate', 0):.0%}",
                        f"- 验证步骤: {data.get('total_steps', 0)} | 失败: {data.get('failures', 0)}",
                        f"- 致命失败: {data.get('critical_failures', 0)}",
                        f"",
                        f"## 关键发现",
                    ]
                    for f in findings[:10]:
                        lines.append(f"- [{f.get('severity', '')}] {str(f.get('step', ''))[:80]}: "
                                     f"{str(f.get('reason', ''))[:150]}")
                    markdown = "\n".join(lines)
            except Exception:
                pass

            db = get_sync_db()
            try:
                # TestSession (report 外键依赖)
                ts = db.query(TestSessionModel).filter_by(session_id=session_id).first()
                if not ts:
                    ts = TestSessionModel(
                        session_id=session_id, agent_id="multi_agent",
                        profile="standard", status="success",
                        total_scenarios=getattr(report, "total_steps", 0) or 0,
                        started_at=datetime.now(timezone.utc),
                        finished_at=datetime.now(timezone.utc),
                    )
                    db.add(ts)
                    db.flush()
                # Report
                existing = db.query(ReportModel).filter_by(session_id=ts.id).first()
                summary = {
                    "agent_id": "multi_agent",
                    "total": getattr(report, "total_steps", 0) or 0,
                    "avg_scores": {"overall": round((getattr(report, "pass_rate", 0) or 0) * 100, 1)},
                    "pass_rate": getattr(report, "pass_rate", 0),
                    "failures": getattr(report, "failures", 0),
                    "critical_failures": getattr(report, "critical_failures", 0),
                    "strategy": getattr(report, "strategy", ""),
                    "diagnosis": getattr(report, "diagnosis", None) if hasattr(report, "diagnosis") else None,
                }
                if existing:
                    existing.summary_json = summary
                    existing.markdown_content = markdown
                    existing.json_path = report_path or existing.json_path
                else:
                    db.add(ReportModel(
                        session_id=ts.id,
                        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                        summary_json=summary,
                        markdown_content=markdown,
                        json_path=report_path,
                    ))
                db.commit()
            finally:
                db.close()
        except Exception:
            try:
                db.rollback()
                db.close()
            except Exception:
                pass

    def _record_run_metrics(self, run_type: str, exit_type: str, session_id: str,
                            errors_n: int = 0, note: str = ""):
        """退出类型指标落盘 (output/metrics/runs.jsonl) — 失败静默"""
        try:
            from src.run_metrics import record_run
            with self._interventions_lock:
                had_human = session_id in self._human_sessions
            record_run(
                run_type=run_type, exit_type=exit_type, session_id=session_id,
                had_human=had_human, errors_n=errors_n, note=note,
            )
        except Exception:
            pass

    def intervention_history(self, session_id: str, last_n: int = 50) -> list:
        """读取某次评测会话的干预审计记录 (ask/answer/timeout)"""
        try:
            from pathlib import Path as _P
            log_path = _P(__file__).resolve().parents[2] / "data" / "intervention_log.json"
            if not log_path.exists():
                return []
            rows = json.loads(log_path.read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                return []
            return [r for r in rows if r.get("session_id") == session_id][-last_n:]
        except Exception:
            return []

    def _append_intervention_log(self, kind: str, session_id: str, **fields) -> None:
        """干预审计 — 每次 ask/answer/timeout 追加一条 JSON 到 data/intervention_log.json

        v2 加分项: 线程安全 (audit_lock 串行化读改写); 失败静默, 绝不影响评测主流程。
        """
        try:
            record = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "kind": kind,        # ask | answer | timeout
                "session_id": session_id,
            }
            record.update(fields)
            log_path = Path(__file__).resolve().parents[2] / "data" / "intervention_log.json"
            with self._audit_lock:
                entries = []
                if log_path.exists():
                    try:
                        entries = json.loads(log_path.read_text(encoding="utf-8") or "[]")
                        if not isinstance(entries, list):
                            entries = []
                    except Exception:
                        entries = []   # 文件损坏时从头开始, 不阻塞
                entries.append(record)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(
                    json.dumps(entries, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except Exception:
            pass

    async def cancel_run(self) -> dict:
        """P0-15: 取消当前评测"""
        if not self._running:
            return {"status": "idle", "message": "没有正在运行的评测"}

        self._cancel_requested.set()
        if self._watchdog:
            self._watchdog.cancel("用户手动取消")

        return {
            "status": "cancelling",
            "session_id": self._current_session_id,
            "message": "正在取消评测...",
        }

    async def get_health(self) -> dict:
        """P0-15: 获取评测健康状态(Watchdog状态)"""
        if not self._watchdog:
            return {
                "running": self._running,
                "watchdog_active": False,
                "state": "idle",
            }

        status = self._watchdog.get_status()
        return {
            "running": self._running,
            "watchdog_active": True,
            "state": status.state.value,
            "elapsed_seconds": round(status.elapsed_seconds, 1),
            "scenarios_completed": status.scenarios_completed,
            "scenarios_total": status.scenarios_total,
            "seconds_since_heartbeat": round(
                time.monotonic() - status.last_heartbeat, 1
            ) if status.last_heartbeat > 0 else None,
            "current_scenario_elapsed": round(status.current_scenario_elapsed, 1),
            "cancellation_reason": status.cancellation_reason,
        }

    @staticmethod
    def get_logs(session_id: str, last_n: int = 500) -> dict:
        """获取指定 session 的事件日志 (用于前端拉取历史)"""
        buf = _event_log_buffer.get(session_id, collections.deque())
        items = list(buf)[-last_n:]
        return {
            "session_id": session_id,
            "total_events": len(buf),
            "returned": len(items),
            "events": list(items),
        }

    # ── 内部方法 ──────────────────────────────────────────

    def _on_watchdog_cancel(self, reason: str):
        """Watchdog 取消回调 — 广播取消事件"""
        if self._main_loop:
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast({
                    "type": "eval_event",
                    "event": "cancelled",
                    "data": {
                        "reason": reason,
                        "session_id": self._current_session_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    "running": False,
                }),
                self._main_loop,
            )

    def _watchdog_status_reporter(self):
        """P0-15: 定期推送看门狗状态到 WebSocket"""
        while self._running and self._watchdog and self._watchdog.is_running:
            time.sleep(self.heartbeat_interval)
            if not self._running:
                break
            try:
                status = self._watchdog.get_status()
                if self._main_loop:
                    asyncio.run_coroutine_threadsafe(
                        ws_manager.broadcast({
                            "type": "watchdog_health",
                            "data": {
                                "state": status.state.value,
                                "elapsed_seconds": round(status.elapsed_seconds, 1),
                                "scenarios_completed": status.scenarios_completed,
                                "scenarios_total": status.scenarios_total,
                                "seconds_since_heartbeat": round(
                                    time.monotonic() - status.last_heartbeat, 1
                                ) if status.last_heartbeat > 0 else None,
                                "current_scenario_elapsed": round(
                                    status.current_scenario_elapsed, 1
                                ),
                            },
                        }),
                        self._main_loop,
                    )
            except Exception:
                pass  # 静默失败,不影响主流程

    def _run_in_thread(
        self, agent_id: str, num_questions: int, max_turns: int,
        profile: str, session_id: str, project_root: Path,
    ) -> None:
        """后台线程执行评测 — P0-15: 带 Watchdog 保护"""
        db = get_sync_db()
        watchdog = self._watchdog  # 本地引用,线程安全
        try:
            os.chdir(str(project_root))

            from src.test_runner import TestRunner
            from src.watchdog import WatchdogCancelled

            def on_progress(event: str, data: dict):
                """线程安全的进度回调 → WebSocket 广播 + 事件日志缓冲"""
                # P0-15: 每次进度回调同时更新心跳
                if watchdog:
                    watchdog._touch()

                # 写入事件日志缓冲区
                ts_now = datetime.now(timezone.utc).isoformat()
                log_entry = {"ts": ts_now, "event": event, "data": data}
                if session_id not in _event_log_buffer:
                    _event_log_buffer[session_id] = collections.deque(maxlen=_EVENT_LOG_MAX)
                _event_log_buffer[session_id].append(log_entry)

                if self._main_loop:
                    asyncio.run_coroutine_threadsafe(
                        ws_manager.broadcast({
                            "type": "eval_event",
                            "event": event,
                            "data": data,
                            "running": self._running,
                        }),
                        self._main_loop,
                    )

            # 创建 TestRunner — P0-15: 传入 watchdog 引用
            config_path = project_root / "config" / "test_config.yaml"
            runner = TestRunner(
                config_path=str(config_path),
                progress_callback=on_progress,
                watchdog=watchdog,  # P0-15: 注入看门狗
            )

            # 覆盖配置
            runner.config["num_questions"] = num_questions
            runner.config["max_turns"] = max_turns
            runner.config["agent_id"] = agent_id
            runner.config["headless"] = True
            runner.config["debug"] = False
            runner.agent_id = agent_id

            # P0-15: 注入超时配置
            runner.config["scenario_timeout"] = self.scenario_timeout
            runner.config["global_timeout"] = self.global_timeout

            # 运行评测(带取消检查)
            results = runner.run_all()

            # 持久化结果到数据库
            self._persist_results(db, session_id, results, agent_id)

            # 更新 session 状态
            ts = db.query(TestSession).filter_by(session_id=session_id).first()
            if ts:
                # P0-15: 检查看门狗状态决定最终状态
                if watchdog and watchdog.get_status().state.value in (
                    "cancelled", "timeout_global", "timeout_scenario", "stuck"
                ):
                    ts.status = "cancelled"
                else:
                    ts.status = "success"
                ts.finished_at = datetime.now(timezone.utc)
                db.commit()

            # 退出类型指标 (取消的 run 不记)
            if ts and ts.status == "success":
                from src.run_metrics import EXIT_COMPLETED
                self._record_run_metrics("test_runner", EXIT_COMPLETED, session_id)

        except WatchdogCancelled as e:
            # P0-15: 看门狗触发的取消
            print(f"[TestService] 评测被取消: {e.reason}")
            try:
                ts = db.query(TestSession).filter_by(session_id=session_id).first()
                if ts:
                    ts.status = "cancelled"
                    ts.finished_at = datetime.now(timezone.utc)
                    db.commit()
            except Exception:
                db.rollback()

        except Exception as e:
            err_detail = f"{e}\n{traceback.format_exc()}"
            print(f"[TestService] 评测异常:\n{err_detail}")

            # 卡点暴露: 意外错误 → LLM 转译成自然语言告知用户 (超时默认终止)
            try:
                from backend.services.error_interpreter import interpret
                card = interpret("eval_exception", str(e), {"agent_id": agent_id})
                self.ask_user(session_id, card["question"], card["options"],
                              timeout_s=card["timeout_s"], default=card["default"],
                              card=card)
            except Exception:
                pass

            # 退出类型指标 + 经验库
            self._record_run_metrics("test_runner", "failed_permanently",
                                     session_id, note=str(e)[:200])
            try:
                from src.experience_store import (
                    record_experience, TASK_EVALUATION, EXIT_FAILED_PERMANENT)
                record_experience(
                    task_type=TASK_EVALUATION,
                    trigger=str(e)[:200],
                    action="评测终止",
                    outcome="评测失败",
                    exit_type=EXIT_FAILED_PERMANENT,
                    note="TestRunner 异常",
                )
            except Exception:
                pass

            # 更新 session 为错误状态
            try:
                ts = db.query(TestSession).filter_by(session_id=session_id).first()
                if ts:
                    ts.status = "error"
                    ts.finished_at = datetime.now(timezone.utc)
                    db.commit()
            except Exception:
                db.rollback()

            if self._main_loop:
                asyncio.run_coroutine_threadsafe(
                    ws_manager.broadcast({
                        "type": "eval_event",
                        "event": "error",
                        "data": {
                            "message": str(e),
                            "traceback": traceback.format_exc(),
                            "stage": "test_service_crash",
                        },
                        "running": False,
                    }),
                    self._main_loop,
                )
        finally:
            self._running = False
            self._current_session_id = None
            if watchdog:
                watchdog.stop()
            self._watchdog = None
            self._eval_thread = None
            db.close()

            # 通知完成
            if self._main_loop:
                asyncio.run_coroutine_threadsafe(
                    ws_manager.broadcast({
                        "type": "state",
                        "data": {
                            "running": False,
                            "progress": num_questions,
                            "total": num_questions,
                            "current_event": "done",
                        },
                    }),
                    self._main_loop,
                )

    def _persist_results(self, db: Session, session_id: str, results: list, agent_id: str) -> None:
        """将 TestRunner 返回的结果持久化到 MySQL"""
        ts = db.query(TestSession).filter_by(session_id=session_id).first()
        if not ts:
            return

        # project root for config loading
        _project_root = Path(__file__).resolve().parent.parent.parent

        all_scores = []
        boundary_summary = {"in_scope": 0, "partial_match": 0, "out_of_scope": 0, "error": 0}

        for i, r in enumerate(results):
            qd = r.get("question_data", {})

            # 创建 TestScenario
            scenario = TestScenario(
                session_id=ts.id,
                scenario_index=i + 1,
                status="success" if not r.get("error") else "error",
                error=r.get("error", ""),
                full_conversation=r.get("full_conversation", ""),
            )
            db.add(scenario)
            db.flush()  # 获取 scenario.id

            # 对话轮次
            for t in r.get("conversation_turns", []):
                resp = t.get("response", {})
                turn = ConversationTurn(
                    scenario_id=scenario.id,
                    turn=t.get("turn", 0),
                    question=t.get("question", ""),
                    response_status=resp.get("status", ""),
                    response_text=resp.get("response", ""),
                    response_duration=resp.get("duration", 0.0),
                    turn_index=t.get("turn", 0),
                )
                db.add(turn)

            # 评分
            score_data = r.get("score", {})
            if score_data:
                score = EvalScore(
                    scenario_id=scenario.id,
                    correctness=score_data.get("correctness", 0.0),
                    relevancy=score_data.get("relevancy", 0.0),
                    completeness=score_data.get("completeness", 0.0),
                    guidance=score_data.get("guidance", 0.0),
                    followup_quality=score_data.get("followup_quality", 0.0),
                    boundary_compliance=score_data.get("boundary_compliance", 0.0),
                    turn_consistency=score_data.get("turn_consistency", 0.0),
                    knowledge_scaffolding=score_data.get("knowledge_scaffolding", 0.0),
                    overall=score_data.get("overall", 0.0),
                    boundary_status=score_data.get("boundary_status", ""),
                    n_judges=score_data.get("n_judges", 1),
                    judge_variance=score_data.get("judge_variance", 0.0),
                    flags=score_data.get("flags", []),
                    needs_human_review=score_data.get("needs_human_review", False),
                    confidences=score_data.get("confidences", {}),
                )
                db.add(score)
                all_scores.append(score_data)

            # 边界统计
            boundary = r.get("boundary", {})
            if boundary:
                status = boundary.get("status", "")
                if status in boundary_summary:
                    boundary_summary[status] += 1

        db.flush()

        # 计算汇总
        dims = [
            "correctness", "relevancy", "completeness", "guidance",
            "followup_quality", "boundary_compliance",
            "turn_consistency", "knowledge_scaffolding",
        ]
        avg_scores = {dim: 0.0 for dim in dims}
        avg_scores["overall"] = 0.0
        if all_scores:
            for dim in dims:
                avg_scores[dim] = round(
                    sum(s.get(dim, 0) for s in all_scores) / len(all_scores), 2
                )
            avg_scores["overall"] = round(
                sum(s.get("overall", 0) for s in all_scores) / len(all_scores), 2
            )

        # 创建 Report
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # 加载重要性权重 (与 evaluator 的 YAML 配置保持一致)
        importance_weights = {}
        try:
            import yaml
            weights_path = _project_root / "config" / "dimension_weights.yaml"
            if weights_path.exists():
                with open(weights_path, "r", encoding="utf-8") as f:
                    yaml_data = yaml.safe_load(f)
                imp = (yaml_data or {}).get("importance", {})
                importance_weights = {k: float(v) for k, v in imp.items()
                                      if isinstance(v, (int, float)) and not k.startswith("_")}
        except Exception:
            pass  # YAML 不可用时跳过

        summary_data = {
            "total": len(results),
            "avg_scores": avg_scores,
            "boundary": boundary_summary,
            "agent_id": agent_id,
            "importance_weights": importance_weights,
        }
        # v3.6: 读取 Reporter 生成的真实报告文件(.md/.html)写入MySQL
        # Reporter.generate_report() 已在 run_all() 中调用, 文件在 reports/ 目录
        md_content, html_content, md_path, json_path = self._read_latest_report_files()

        report = Report(
            session_id=ts.id,
            timestamp=timestamp,
            summary_json=summary_data,
            markdown_path=md_path,
            json_path=json_path,
            markdown_content=md_content,
            html_content=html_content,
        )
        db.add(report)
        db.commit()

    # ── v3.6: 读取 Reporter 刚生成的真实报告文件 ──

    @staticmethod
    def _read_latest_report_files() -> tuple[str | None, str | None, str | None, str | None]:
        """从 reports/ 目录读取最新生成的报告文件内容

        Reporter.generate_report() 在 test_runner.run_all() 返回前调用,
        所以 _persist_results 执行时最新文件就是本次评测的报告。

        Returns: (md_content, html_content, md_path, json_path)
        """
        from pathlib import Path

        reports_dir = Path(__file__).resolve().parents[2] / "reports"
        if not reports_dir.exists():
            return None, None, None, None

        # 按修改时间排序, 取最新的
        md_files = sorted(
            reports_dir.glob("report_*.md"),
            key=lambda f: f.stat().st_mtime, reverse=True,
        )
        html_files = sorted(
            reports_dir.glob("report_*.html"),
            key=lambda f: f.stat().st_mtime, reverse=True,
        )
        json_files = sorted(
            reports_dir.glob("report_*.json"),
            key=lambda f: f.stat().st_mtime, reverse=True,
        )

        project_root = Path(__file__).resolve().parents[2]
        md_content = None
        html_content = None
        md_path = None
        json_path = None

        if md_files:
            try:
                p = md_files[0]
                md_content = p.read_text(encoding="utf-8")
                md_path = str(p.relative_to(project_root))
            except Exception:
                pass

        if html_files:
            try:
                html_content = html_files[0].read_text(encoding="utf-8")
            except Exception:
                pass

        if json_files:
            try:
                json_path = str(json_files[0].relative_to(project_root))
            except Exception:
                pass

        return md_content, html_content, md_path, json_path
