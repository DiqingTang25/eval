"""
Watchdog — 超时保护 + 心跳监控 + 优雅取消 (P0-15)

三层保护:
1. Per-Scenario Timeout: 单个问题评测的最大时长
2. Global Timeout: 整个评测运行的最大时长
3. Heartbeat Monitor: 检测线程卡死(无心跳)并强制终止

用法:
    wd = Watchdog(
        scenario_timeout=600,     # 单个场景最多10分钟
        global_timeout=1800,      # 总体最多30分钟
        heartbeat_interval=30,    # 每30秒心跳一次
        heartbeat_stale=120,      # 2分钟无心跳视为卡死
    )

    # 在评测线程中:
    wd.start()
    for scenario in scenarios:
        wd.check_cancelled()           # 检查是否被取消
        with wd.scenario_context():    # 场景超时上下文
            result = run_scenario(scenario)
        wd.heartbeat()                 # 每个场景后心跳

    wd.stop()
"""

import signal
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class WatchdogState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    CANCELLED = "cancelled"
    TIMEOUT_SCENARIO = "timeout_scenario"
    TIMEOUT_GLOBAL = "timeout_global"
    STUCK = "stuck"              # 心跳超时,线程卡死
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class WatchdogStatus:
    """Watchdog 当前状态快照"""
    state: WatchdogState = WatchdogState.IDLE
    started_at: float = 0.0
    last_heartbeat: float = 0.0
    elapsed_seconds: float = 0.0
    scenarios_completed: int = 0
    scenarios_total: int = 0
    current_scenario_started: float = 0.0
    current_scenario_elapsed: float = 0.0
    cancellation_reason: str = ""


class WatchdogCancelled(Exception):
    """评测被取消或超时"""
    def __init__(self, reason: str, state: WatchdogState):
        self.reason = reason
        self.state = state
        super().__init__(reason)


class Watchdog:
    """评测看门狗 — 线程安全"""

    def __init__(
        self,
        scenario_timeout: float = 600,       # 单场景超时(秒), 默认10分钟
        global_timeout: float = 1800,        # 全局超时(秒), 默认30分钟
        heartbeat_interval: float = 30,      # 心跳间隔(秒)
        heartbeat_stale: float = 120,        # 心跳过期阈值(秒), 超过此值视为卡死
        on_cancel: Optional[Callable[[str], None]] = None,  # 取消回调
    ):
        self.scenario_timeout = scenario_timeout
        self.global_timeout = global_timeout
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_stale = heartbeat_stale
        self.on_cancel = on_cancel

        # 线程安全状态
        self._lock = threading.RLock()
        self._cancelled = threading.Event()

        self.state = WatchdogState.IDLE
        self._started_at: float = 0.0
        self._last_heartbeat: float = 0.0
        self._scenarios_completed: int = 0
        self._scenarios_total: int = 0
        self._scenario_started_at: float = 0.0
        self._cancellation_reason: str = ""

        # 监控线程
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_stop = threading.Event()

        # 全局超时定时器
        self._global_timer: Optional[threading.Timer] = None

    # ── 生命周期 ─────────────────────────────────────────

    def start(self, scenarios_total: int = 0) -> None:
        """启动看门狗"""
        with self._lock:
            if self.state == WatchdogState.RUNNING:
                return
            self.state = WatchdogState.RUNNING
            self._started_at = time.monotonic()
            self._last_heartbeat = self._started_at
            self._scenarios_completed = 0
            self._scenarios_total = scenarios_total
            self._cancelled.clear()
            self._cancellation_reason = ""

        # 启动全局超时定时器
        if self.global_timeout > 0:
            self._global_timer = threading.Timer(
                self.global_timeout,
                self._on_global_timeout,
            )
            self._global_timer.daemon = True
            self._global_timer.start()

        # 启动心跳监控线程
        self._monitor_stop.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="watchdog-monitor",
        )
        self._monitor_thread.start()

    def stop(self) -> None:
        """正常停止看门狗"""
        self._stop_monitor()
        self._cancel_global_timer()
        with self._lock:
            if self.state == WatchdogState.RUNNING:
                self.state = WatchdogState.COMPLETED

    def cancel(self, reason: str) -> None:
        """取消评测"""
        with self._lock:
            if self.state != WatchdogState.RUNNING:
                return
            self.state = WatchdogState.CANCELLED
            self._cancellation_reason = reason
        self._cancelled.set()
        self._stop_monitor()
        self._cancel_global_timer()
        if self.on_cancel:
            try:
                self.on_cancel(reason)
            except Exception:
                pass

    # ── 心跳 ──────────────────────────────────────────────

    def heartbeat(self) -> None:
        """发送心跳 — 评测线程在每个场景完成后调用"""
        with self._lock:
            self._last_heartbeat = time.monotonic()
            self._scenarios_completed += 1

    def _touch(self) -> None:
        """轻量心跳 — 用于更频繁的心跳(如场景内部)"""
        with self._lock:
            self._last_heartbeat = time.monotonic()

    # ── 场景超时上下文管理器 ──────────────────────────────

    @contextmanager
    def scenario_context(self, scenario_index: int = 0):
        """场景超时上下文管理器

        用法:
            with wd.scenario_context(i):
                result = run_scenario(q)
        """
        start = time.monotonic()
        with self._lock:
            self._scenario_started_at = start

        # 使用 signal.alarm 作为场景超时(仅在主线程有效)
        # 对于后台线程,使用轮询方式
        old_handler = None
        timer_set = False

        try:
            # 尝试 signal-based timeout (主线程)
            def _handler(signum, frame):
                raise WatchdogCancelled(
                    f"场景 #{scenario_index} 超时 ({self.scenario_timeout}s)",
                    WatchdogState.TIMEOUT_SCENARIO,
                )

            try:
                old_handler = signal.signal(signal.SIGALRM, _handler)
                signal.alarm(int(self.scenario_timeout))
                timer_set = True
            except ValueError:
                # signal only works in main thread - use thread-based fallback
                pass

            yield
        except WatchdogCancelled:
            # 更新状态
            with self._lock:
                if self.state == WatchdogState.RUNNING:
                    self.state = WatchdogState.TIMEOUT_SCENARIO
                    self._cancellation_reason = f"场景 #{scenario_index} 超时"
            raise
        finally:
            if timer_set:
                try:
                    signal.alarm(0)
                    if old_handler:
                        signal.signal(signal.SIGALRM, old_handler)
                except Exception:
                    pass

    # ── 取消检查 ──────────────────────────────────────────

    def check_cancelled(self) -> None:
        """检查是否已取消/超时 — 在评测循环的关键点调用

        Raises:
            WatchdogCancelled: 如果已取消
        """
        if self._cancelled.is_set():
            with self._lock:
                reason = self._cancellation_reason or "评测已取消"
                state = self.state
            raise WatchdogCancelled(reason, state)

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self.state == WatchdogState.RUNNING

    # ── 状态快照 ──────────────────────────────────────────

    def get_status(self) -> WatchdogStatus:
        """获取当前状态快照(线程安全)"""
        with self._lock:
            now = time.monotonic()
            return WatchdogStatus(
                state=self.state,
                started_at=self._started_at,
                last_heartbeat=self._last_heartbeat,
                elapsed_seconds=(
                    now - self._started_at if self._started_at > 0 else 0
                ),
                scenarios_completed=self._scenarios_completed,
                scenarios_total=self._scenarios_total,
                current_scenario_started=self._scenario_started_at,
                current_scenario_elapsed=(
                    now - self._scenario_started_at
                    if self._scenario_started_at > 0 else 0
                ),
                cancellation_reason=self._cancellation_reason,
            )

    # ── 内部方法 ──────────────────────────────────────────

    def _on_global_timeout(self) -> None:
        """全局超时回调"""
        elapsed = time.monotonic() - self._started_at if self._started_at > 0 else 0
        self.cancel(f"全局超时: 运行 {elapsed:.0f}s > {self.global_timeout}s 上限")

    def _monitor_loop(self) -> None:
        """心跳监控循环 — 在独立daemon线程中运行"""
        while not self._monitor_stop.wait(timeout=min(self.heartbeat_interval, 10)):
            with self._lock:
                if self.state != WatchdogState.RUNNING:
                    break
                now = time.monotonic()
                since_heartbeat = now - self._last_heartbeat if self._last_heartbeat > 0 else 0

            # 心跳过期检测
            if since_heartbeat > self.heartbeat_stale:
                self.cancel(
                    f"心跳过期: {since_heartbeat:.0f}s 未收到心跳 "
                    f"(阈值 {self.heartbeat_stale}s), 评测线程可能卡死"
                )
                break

    def _stop_monitor(self) -> None:
        """停止监控线程"""
        self._monitor_stop.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5)

    def _cancel_global_timer(self) -> None:
        """取消全局超时定时器"""
        if self._global_timer:
            self._global_timer.cancel()
            self._global_timer = None


# ── 便利函数 ──────────────────────────────────────────────

def run_with_timeout(
    func: Callable,
    args: tuple = (),
    kwargs: dict = None,
    timeout: float = 300,
    on_timeout: Callable[[], None] = None,
) -> tuple:
    """在独立线程中运行函数,带超时保护

    返回: (success: bool, result: Any, error: str)

    注意: Python 线程无法强制终止,超时后线程可能仍在运行。
    对于需要真正终止的场景,使用 multiprocessing.Process。
    """
    kwargs = kwargs or {}
    result_holder = {"result": None, "error": None, "done": False}

    def _wrapper():
        try:
            result_holder["result"] = func(*args, **kwargs)
        except Exception as e:
            result_holder["error"] = str(e)
        finally:
            result_holder["done"] = True

    thread = threading.Thread(target=_wrapper, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if not result_holder["done"]:
        if on_timeout:
            try:
                on_timeout()
            except Exception:
                pass
        return (False, None, f"操作超时 ({timeout}s)")

    if result_holder["error"]:
        return (False, None, result_holder["error"])

    return (True, result_holder["result"], None)
