"""
Prometheus 指标导出中间件

无外部依赖, 纯 Python 实现:
- 请求计数 (按 method + path + status)
- 请求延迟 (histogram buckets)
- 活跃评测数
- 评测完成数
- 数据库连接状态
"""

import time
import threading
from collections import defaultdict
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse


class MetricsRegistry:
    """Prometheus 格式的指标注册表 (线程安全)"""

    def __init__(self):
        self._lock = threading.Lock()

        # Counter: http_requests_total{method, path, status}
        self.http_requests: dict[tuple, int] = defaultdict(int)

        # Histogram: http_request_duration_seconds{method, path}
        # buckets: 0.01, 0.05, 0.1, 0.5, 1, 5, 10
        self._latency_buckets = [0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0]
        self.http_latency: dict[tuple, list[int]] = defaultdict(
            lambda: [0] * len(self._latency_buckets)
        )
        self.http_latency_sum: dict[tuple, float] = defaultdict(float)
        self.http_latency_count: dict[tuple, int] = defaultdict(int)

        # Gauge: active_evaluations
        self.active_evaluations: int = 0

        # Counter: evaluations_total{status}
        self.evaluations_total: dict[str, int] = defaultdict(int)

        # Gauge: db_connected (0/1)
        self.db_connected: int = 1

        # Counter: eval_scores_total{dimension}
        self.eval_scores: dict[str, int] = defaultdict(int)

        # App info
        self.app_version: str = "3.4.0"
        self._start_time: float = time.time()

    def record_request(self, method: str, path: str, status: int, duration: float):
        with self._lock:
            # 路径归一化 (去掉动态 ID)
            normalized = self._normalize_path(path)
            key = (method, normalized, str(status))
            self.http_requests[key] += 1

            # 延迟
            lat_key = (method, normalized)
            for i, bound in enumerate(self._latency_buckets):
                if duration <= bound:
                    self.http_latency[lat_key][i] += 1
            self.http_latency_sum[lat_key] += duration
            self.http_latency_count[lat_key] += 1

    def set_active_evaluations(self, count: int):
        with self._lock:
            self.active_evaluations = count

    def inc_evaluation(self, status: str):
        with self._lock:
            self.evaluations_total[status] += 1
            if status == "started":
                self.active_evaluations += 1
            elif status in ("success", "error"):
                self.active_evaluations = max(0, self.active_evaluations - 1)

    def set_db_connected(self, connected: bool):
        with self._lock:
            self.db_connected = 1 if connected else 0

    def inc_eval_score(self, dimension: str):
        with self._lock:
            self.eval_scores[dimension] += 1

    @staticmethod
    def _normalize_path(path: str) -> str:
        """将路径中的动态 ID 替换为 {id}"""
        import re
        # UUIDs
        path = re.sub(
            r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            '/{id}', path
        )
        # Phase identifiers like PHASE 01
        path = re.sub(r'/PHASE\s*\d{2}', '/{phase}', path)
        # kb-xxxxx patterns
        path = re.sub(r'/kb-[a-z0-9-]+', '/{kb_id}', path)
        # Numeric IDs
        path = re.sub(r'/\d{4,}', '/{num}', path)
        return path

    def render(self) -> str:
        """生成 Prometheus 文本格式"""
        lines = []

        # HELP/TYPE headers
        lines.append("# HELP http_requests_total Total HTTP requests")
        lines.append("# TYPE http_requests_total counter")
        for (method, path, status), count in sorted(self.http_requests.items()):
            lines.append(
                f'http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}'
            )

        lines.append("# HELP http_request_duration_seconds HTTP request duration")
        lines.append("# TYPE http_request_duration_seconds histogram")
        for (method, path), buckets in sorted(self.http_latency.items()):
            for i, bound in enumerate(self._latency_buckets):
                lines.append(
                    f'http_request_duration_seconds_bucket{{method="{method}",path="{path}",le="{bound}"}} {buckets[i]}'
                )
            lines.append(
                f'http_request_duration_seconds_bucket{{method="{method}",path="{path}",le="+Inf"}} {self.http_latency_count[(method, path)]}'
            )
            lines.append(
                f'http_request_duration_seconds_sum{{method="{method}",path="{path}"}} {self.http_latency_sum[(method, path)]:.6f}'
            )
            lines.append(
                f'http_request_duration_seconds_count{{method="{method}",path="{path}"}} {self.http_latency_count[(method, path)]}'
            )

        lines.append("# HELP active_evaluations Currently running evaluations")
        lines.append("# TYPE active_evaluations gauge")
        lines.append(f"active_evaluations {self.active_evaluations}")

        lines.append("# HELP evaluations_total Total evaluations by status")
        lines.append("# TYPE evaluations_total counter")
        for status, count in sorted(self.evaluations_total.items()):
            lines.append(f'evaluations_total{{status="{status}"}} {count}')

        lines.append("# HELP db_connected Database connection status (1=ok)")
        lines.append("# TYPE db_connected gauge")
        lines.append(f"db_connected {self.db_connected}")

        lines.append("# HELP eval_scores_total Evaluation scores by dimension")
        lines.append("# TYPE eval_scores_total counter")
        for dim, count in sorted(self.eval_scores.items()):
            lines.append(f'eval_scores_total{{dimension="{dim}"}} {count}')

        # App uptime
        uptime = time.time() - self._start_time
        lines.append("# HELP app_uptime_seconds Application uptime")
        lines.append("# TYPE app_uptime_seconds gauge")
        lines.append(f"app_uptime_seconds {uptime:.0f}")

        lines.append("# HELP app_info Application version info")
        lines.append("# TYPE app_info gauge")
        lines.append(f'app_info{{version="{self.app_version}"}} 1')

        return "\n".join(lines) + "\n"


# ── 全局单例 ──
metrics = MetricsRegistry()


class MetricsMiddleware(BaseHTTPMiddleware):
    """自动记录 HTTP 请求指标的中间件"""

    async def dispatch(self, request: Request, call_next: Callable):
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        metrics.record_request(request.method, request.url.path, response.status_code, duration)
        return response


def setup_metrics(app):
    """安装指标中间件 + 注册 /metrics 端点"""
    app.add_middleware(MetricsMiddleware)

    @app.get("/metrics")
    async def metrics_endpoint():
        return PlainTextResponse(metrics.render(), media_type="text/plain; charset=utf-8")
