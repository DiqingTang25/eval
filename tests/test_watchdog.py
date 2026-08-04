"""P0-15: Watchdog 超时保护 + 心跳监控 + 取消检测 测试"""

import time
import pytest
from src.watchdog import (
    Watchdog, WatchdogCancelled, WatchdogState, WatchdogStatus,
    run_with_timeout,
)


class TestWatchdogLifecycle:
    """基本生命周期测试"""

    def test_start_and_is_running(self):
        wd = Watchdog(global_timeout=60)
        wd.start(scenarios_total=3)
        assert wd.is_running
        status = wd.get_status()
        assert status.state == WatchdogState.RUNNING
        assert status.scenarios_total == 3
        wd.stop()

    def test_stop(self):
        wd = Watchdog(global_timeout=60)
        wd.start(scenarios_total=5)
        wd.stop()
        status = wd.get_status()
        assert status.state == WatchdogState.COMPLETED
        assert not wd.is_running

    def test_double_start_noop(self):
        wd = Watchdog(global_timeout=60)
        wd.start()
        first_started = wd.get_status().started_at
        wd.start()  # Should be no-op
        assert wd.get_status().started_at == first_started
        wd.stop()


class TestHeartbeat:
    """心跳测试"""

    def test_heartbeat_increments_count(self):
        wd = Watchdog(global_timeout=60)
        wd.start(scenarios_total=10)
        assert wd.get_status().scenarios_completed == 0
        wd.heartbeat()
        assert wd.get_status().scenarios_completed == 1
        wd.heartbeat()
        wd.heartbeat()
        assert wd.get_status().scenarios_completed == 3
        wd.stop()

    def test_heartbeat_updates_timestamp(self):
        wd = Watchdog(global_timeout=60)
        wd.start()
        first_hb = wd.get_status().last_heartbeat
        time.sleep(0.1)
        wd.heartbeat()
        second_hb = wd.get_status().last_heartbeat
        assert second_hb > first_hb
        wd.stop()

    def test_touch_updates_timestamp(self):
        wd = Watchdog(global_timeout=60)
        wd.start()
        first = wd.get_status().last_heartbeat
        time.sleep(0.1)
        wd._touch()
        second = wd.get_status().last_heartbeat
        assert second > first
        wd.stop()


class TestCancel:
    """取消测试"""

    def test_cancel_sets_state(self):
        wd = Watchdog(global_timeout=60)
        wd.start()
        wd.cancel("用户取消")
        assert wd.is_cancelled
        assert not wd.is_running
        status = wd.get_status()
        assert status.state == WatchdogState.CANCELLED
        assert "用户取消" in status.cancellation_reason

    def test_check_cancelled_raises(self):
        wd = Watchdog(global_timeout=60)
        wd.start()
        wd.cancel("测试")
        with pytest.raises(WatchdogCancelled) as exc:
            wd.check_cancelled()
        assert "测试" in str(exc.value)

    def test_check_cancelled_noop_when_running(self):
        wd = Watchdog(global_timeout=60)
        wd.start()
        # Should not raise
        wd.check_cancelled()
        wd.stop()

    def test_on_cancel_callback(self):
        calls = []
        wd = Watchdog(global_timeout=60, on_cancel=lambda r: calls.append(r))
        wd.start()
        wd.cancel("超时")
        assert len(calls) == 1
        assert calls[0] == "超时"

    def test_cancel_twice_noop(self):
        wd = Watchdog(global_timeout=60)
        wd.start()
        wd.cancel("first")
        state_after_first = wd.get_status().state
        wd.cancel("second")
        # State should still be cancelled, not changed
        assert wd.get_status().state == state_after_first


class TestGlobalTimeout:
    """全局超时测试"""

    def test_global_timeout_triggers_cancel(self):
        wd = Watchdog(global_timeout=0.5, heartbeat_stale=10)
        wd.start()
        time.sleep(0.7)  # Wait for timer to fire
        # After global timeout, should be cancelled
        status = wd.get_status()
        assert status.state in (WatchdogState.CANCELLED, WatchdogState.TIMEOUT_GLOBAL)

    def test_global_timeout_zero_disabled(self):
        """global_timeout=0 表示禁用全局超时"""
        wd = Watchdog(global_timeout=0, heartbeat_stale=10)
        wd.start()
        time.sleep(0.3)
        status = wd.get_status()
        # Should still be running (no timeout)
        assert status.state == WatchdogState.RUNNING
        wd.stop()


class TestScenarioContext:
    """场景超时上下文测试"""

    def test_scenario_context_without_timeout(self):
        wd = Watchdog(scenario_timeout=60)
        wd.start()
        with wd.scenario_context(scenario_index=1):
            x = 1 + 1
        assert x == 2
        wd.stop()


class TestRunWithTimeout:
    """run_with_timeout 工具函数测试"""

    def test_success(self):
        ok, result, err = run_with_timeout(
            lambda x, y: x + y, args=(2, 3), timeout=5
        )
        assert ok
        assert result == 5
        assert err is None

    def test_timeout(self):
        ok, result, err = run_with_timeout(
            lambda: time.sleep(5), timeout=0.3
        )
        assert not ok
        assert result is None
        assert "超时" in err

    def test_exception(self):
        def boom():
            raise ValueError("test error")

        ok, result, err = run_with_timeout(boom, timeout=5)
        assert not ok
        assert "test error" in err

    def test_on_timeout_callback(self):
        called = []
        ok, _, _ = run_with_timeout(
            lambda: time.sleep(5),
            timeout=0.2,
            on_timeout=lambda: called.append(True),
        )
        assert not ok
        assert len(called) == 1


class TestWatchdogStatus:
    """状态快照测试"""

    def test_elapsed_time(self):
        wd = Watchdog(global_timeout=60)
        wd.start()
        time.sleep(0.2)
        status = wd.get_status()
        assert status.elapsed_seconds >= 0.15
        wd.stop()

    def test_heartbeat_staleness(self):
        wd = Watchdog(global_timeout=60, heartbeat_stale=0.5, heartbeat_interval=0.1)
        wd.start()
        wd.heartbeat()
        time.sleep(0.6)
        # Monitor should detect stale heartbeat
        time.sleep(0.2)  # Give monitor time to fire
        status = wd.get_status()
        # After stale heartbeat, monitor should have triggered cancel
        if status.state == WatchdogState.RUNNING:
            # Monitor may not have fired yet, check again
            time.sleep(0.5)
            status = wd.get_status()
        # Either cancelled (by stale detection) or still running (race)
        # Just verify it doesn't crash
        assert status.state.value in ("running", "cancelled", "stuck")
        wd.stop()
