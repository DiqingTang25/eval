"""
API 速率限制中间件 (滑动窗口算法)

无外部依赖 (不需要 Redis)，基于内存 + 时间戳实现：
- 全局默认: 300 req/min per IP per path group
- 每个路径前缀独立计数器 — 避免 dashboard 请求挤占 test/run 配额
- 评测启动: 30 req/min (防止并发触发)
- QA 生成: 5 req/2min (LLM 调用成本控制)

P0-fix (2026-07-22): 修复共享计数器 bug — 原来所有 API 路径共用一个计数器,
    导致 dashboard 页面加载的 3-5 个正常请求就占满 /api/tests/run 的 10/min 配额。
    现在按路径前缀独立计数 (ip + prefix → hits)。
"""

import time
import threading
from collections import defaultdict
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimiter:
    """
    滑动窗口速率限制器 (线程安全) — 按路径前缀独立计数

    使用示例:
        limiter = RateLimiter(max_requests=300, window_seconds=60)
        limiter.add_rule("/api/tests/run", max_requests=30, window_seconds=60)
    """

    def __init__(self, max_requests: int = 300, window_seconds: int = 60, cleanup_interval: int = 300):
        self.default_max = max_requests
        self.window = window_seconds
        self._rules: dict[str, tuple[int, int]] = {}  # path_prefix → (max, window)
        # P0-fix: 按 (ip, prefix) 独立计数，而非全局共享
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self._start_cleanup(cleanup_interval)

    def _cleanup_expired(self):
        """移除过期 key 以防止内存泄漏"""
        now = time.time()
        max_window = max(
            [w for _, (_, w) in self._rules.items()] + [self.window]
        )
        cutoff = now - max_window
        with self._lock:
            stale_keys = [
                k for k, times in self._hits.items()
                if not times or max(times) < cutoff
            ]
            for k in stale_keys:
                del self._hits[k]

    def _start_cleanup(self, interval: int):
        """启动后台守护线程定期清理过期 key"""
        def _run():
            while True:
                time.sleep(interval)
                self._cleanup_expired()
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def add_rule(self, path_prefix: str, max_requests: int, window_seconds: int = 60):
        """为特定路径前缀设置限制规则"""
        self._rules[path_prefix] = (max_requests, window_seconds)

    def _get_rule(self, path: str) -> tuple[str, int, int]:
        """匹配路径对应的限制规则, 返回 (prefix, max, window)"""
        for prefix, rule in sorted(self._rules.items(), key=lambda x: -len(x[0])):
            if path.startswith(prefix):
                return (prefix, rule[0], rule[1])
        return ("__default__", self.default_max, self.window)

    def is_allowed(self, key: str, path: str = "/") -> tuple[bool, int, int]:
        """
        检查请求是否允许通过

        P0-fix: 按 (ip, prefix) 独立计数 — 不同路径前缀不共享计数器

        Returns:
            (allowed: bool, remaining: int, reset_seconds: int)
        """
        prefix, max_req, window = self._get_rule(path)
        # P0-fix: 复合 key = ip + matched_prefix, 各路径前缀独立计数
        composite_key = f"{key}|{prefix}"
        now = time.time()
        cutoff = now - window

        with self._lock:
            # 清理过期记录
            self._hits[composite_key] = [t for t in self._hits.get(composite_key, []) if t > cutoff]

            count = len(self._hits[composite_key])
            if count >= max_req:
                # 计算重置时间
                oldest = min(self._hits[composite_key])
                reset_seconds = int(oldest + window - now) + 1
                return (False, 0, max(1, reset_seconds))

            self._hits[composite_key].append(now)
            remaining = max_req - count - 1
            reset_seconds = window
            return (True, remaining, reset_seconds)

    def get_client_key(self, request: Request) -> str:
        """从请求提取限流 key (IP + 可选用户)"""
        # X-Forwarded-For 处理 (Nginx 反向代理)
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"
        return f"ip:{ip}"


# ── 全局限流器实例 ──
# P0-fix: 默认 300 req/min per IP per path group (原来 3000 但共享计数器有 bug)
# 现在按 prefix 独立计数, 300/min 对 dashboard 浏览足够
limiter = RateLimiter(max_requests=300, window_seconds=60)

# 注册敏感路径限制 — 各路径前缀独立计数, 互不影响
limiter.add_rule("/api/tests/run", max_requests=30, window_seconds=60)       # 启动评测 (原10→30)
limiter.add_rule("/api/qa/generate", max_requests=10, window_seconds=120)     # QA 生成 (原5→10)
limiter.add_rule("/api/web-eval/run", max_requests=30, window_seconds=60)     # Web 评测 (原15→30)
limiter.add_rule("/api/kb/search", max_requests=120, window_seconds=60)       # KB 搜索 (原60→120)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI 速率限制中间件 — P0-fix: 按路径前缀独立计数"""

    def __init__(self, app, limiter_instance: RateLimiter = None):
        super().__init__(app)
        self.limiter = limiter_instance or limiter

    async def dispatch(self, request: Request, call_next: Callable):
        # 跳过非 API 路径 (health, WebSocket, 静态文件等)
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        client_key = self.limiter.get_client_key(request)
        allowed, remaining, reset_sec = self.limiter.is_allowed(client_key, path)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded. Please slow down.",
                    "retry_after_seconds": reset_sec,
                    "status_code": 429,
                    "path": path,
                },
                headers={
                    "Retry-After": str(reset_sec),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_sec),
                },
            )

        response = await call_next(request)

        # 响应头中暴露剩余限流信息
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_sec)
        return response


def setup_rate_limit(app):
    """安装速率限制中间件"""
    app.add_middleware(RateLimitMiddleware, limiter_instance=limiter)


# ── 客户端工具: 带重试的 HTTP 请求 (供脚本使用) ──

def fetch_with_retry(url: str, method: str = "GET", json_body: dict = None,
                     max_retries: int = 3, base_delay: float = 1.0,
                     timeout: int = 30, **kwargs) -> "requests.Response":
    """
    发送 HTTP 请求, 遇到 429 自动指数退避重试.

    用法:
        from backend.middleware.rate_limit import fetch_with_retry
        resp = fetch_with_retry("http://127.0.0.1:8000/api/tests/run",
                                method="POST", json_body={"agent_id": "mock"})
    """
    import requests as _requests

    last_resp = None
    for attempt in range(max_retries + 1):
        try:
            if method.upper() == "GET":
                resp = _requests.get(url, timeout=timeout, **kwargs)
            elif method.upper() == "POST":
                resp = _requests.post(url, json=json_body, timeout=timeout, **kwargs)
            elif method.upper() == "PUT":
                resp = _requests.put(url, json=json_body, timeout=timeout, **kwargs)
            elif method.upper() == "DELETE":
                resp = _requests.delete(url, timeout=timeout, **kwargs)
            else:
                resp = _requests.request(method, url, json=json_body, timeout=timeout, **kwargs)

            if resp.status_code != 429:
                return resp

            # 429 → 解析 retry_after 并重试
            retry_after = 1.0
            try:
                body = resp.json()
                retry_after = float(body.get("retry_after_seconds", 1))
            except Exception:
                pass

            delay = max(retry_after, base_delay * (2 ** attempt))
            if attempt < max_retries:
                import logging
                logging.getLogger(__name__).warning(
                    "429 rate limited on %s, retrying in %.1fs (attempt %d/%d)",
                    url, delay, attempt + 1, max_retries,
                )
                import time as _time
                _time.sleep(delay)
            last_resp = resp

        except _requests.exceptions.ConnectionError as e:
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                import logging
                logging.getLogger(__name__).warning(
                    "Connection error on %s: %s, retrying in %.1fs",
                    url, e, delay,
                )
                import time as _time
                _time.sleep(delay)
            else:
                raise

    return last_resp
