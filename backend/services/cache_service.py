"""
评估结果缓存服务

架构: Redis 优先 (如有), 否则回退到内存 LRU 缓存
使用场景:
  - 相同 (question, golden_answer, model) 的评估结果缓存, 避免重复 LLM Judge 调用
  - Dashboard 统计数据缓存 (TTL 30s)
"""

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Optional


class MemoryCache:
    """线程安全的内存 LRU 缓存 (无 Redis 时的回退方案)"""

    def __init__(self, max_size: int = 256, ttl_seconds: int = 3600):
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                return None
            expires_at, value = self._cache[key]
            if time.time() > expires_at:
                del self._cache[key]
                return None
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl: int = None):
        ttl = ttl or self._ttl
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)  # evict oldest
            self._cache[key] = (time.time() + ttl, value)

    def delete(self, key: str):
        with self._lock:
            self._cache.pop(key, None)

    def clear(self):
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)


# ── 缓存 Key 构造 ──

def _make_eval_cache_key(question: str, golden_answer: str, model: str = "",
                         dimensions: list[str] = None) -> str:
    """为评估结果构造缓存 key (SHA256)"""
    payload = {
        "q": question,
        "a": golden_answer,
        "m": model or "deepseek-chat",
        "d": sorted(dimensions) if dimensions else [],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return "eval:" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _make_dashboard_cache_key(endpoint: str, params: dict = None) -> str:
    """为 Dashboard 数据构造缓存 key"""
    p = params or {}
    raw = endpoint + ":" + json.dumps(p, sort_keys=True)
    return "dash:" + hashlib.md5(raw.encode()).hexdigest()[:12]


# ── Redis 客户端 (可选) ──

_redis_client = None


def _get_redis():
    """惰性加载 Redis 连接 (如果配置了 REDIS_URL)"""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    redis_url = os.getenv("REDIS_URL", "")
    if redis_url:
        try:
            import redis
            _redis_client = redis.from_url(redis_url, decode_responses=True)
            _redis_client.ping()
            print(f"[CacheService] Redis connected: {redis_url}")
            return _redis_client
        except Exception as e:
            print(f"[CacheService] Redis unavailable ({e}), using in-memory cache")
            _redis_client = False
            return None
    else:
        _redis_client = False
        return None


# ── 统一缓存接口 ──

class CacheService:
    """评估结果缓存服务 (Redis 优先 → 内存回退)"""

    def __init__(self):
        self._memory = MemoryCache(max_size=512, ttl_seconds=3600)
        self._dashboard_cache = MemoryCache(max_size=32, ttl_seconds=30)

    # ── 评估结果缓存 ──

    def get_eval_result(self, question: str, golden_answer: str,
                        model: str = "", dimensions: list[str] = None) -> Optional[dict]:
        """获取缓存的评估结果"""
        key = _make_eval_cache_key(question, golden_answer, model, dimensions)
        redis = _get_redis()
        if redis:
            try:
                raw = redis.get(key)
                return json.loads(raw) if raw else None
            except Exception:
                pass
        return self._memory.get(key)

    def set_eval_result(self, question: str, golden_answer: str,
                        result: dict, model: str = "",
                        dimensions: list[str] = None, ttl: int = 86400):
        """缓存评估结果 (默认 24h)"""
        key = _make_eval_cache_key(question, golden_answer, model, dimensions)
        redis = _get_redis()
        if redis:
            try:
                redis.setex(key, ttl, json.dumps(result, ensure_ascii=False))
            except Exception:
                pass
        self._memory.set(key, result, ttl)

    def invalidate_eval_cache(self, question: str = None, golden_answer: str = None):
        """失效评估缓存 (传 None 表示清空全部)"""
        if question is None:
            self._memory.clear()
            redis = _get_redis()
            if redis:
                try:
                    for k in redis.scan_iter("eval:*"):
                        redis.delete(k)
                except Exception:
                    pass
        else:
            key = _make_eval_cache_key(question, golden_answer or "")
            self._memory.delete(key)
            redis = _get_redis()
            if redis:
                try:
                    redis.delete(key)
                except Exception:
                    pass

    # ── Dashboard 缓存 ──

    def get_dashboard(self, endpoint: str, params: dict = None) -> Optional[dict]:
        return self._dashboard_cache.get(_make_dashboard_cache_key(endpoint, params))

    def set_dashboard(self, endpoint: str, data: dict, params: dict = None):
        self._dashboard_cache.set(_make_dashboard_cache_key(endpoint, params), data, ttl=30)

    def invalidate_dashboard(self):
        self._dashboard_cache.clear()

    # ── 状态 ──

    def status(self) -> dict:
        redis = _get_redis()
        return {
            "backend": "redis" if redis else "memory",
            "redis_available": redis is not None,
            "memory_keys": self._memory.size,
            "dashboard_keys": self._dashboard_cache.size,
        }


# 全局单例
cache_service = CacheService()
