"""
异步证据队列 — Phase 1 削峰填谷 (纯 MySQL 存储)

基于 Redis Streams:
  - 测试完成 → 入队 (不阻塞主流程)
  - Worker 消费 → 直接写入 MySQL evidence_trail + eval_scores
  - 失败自动重试 + Dead Letter Queue
  - Redis 不可用时 → 降级同步写入
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Redis Streams Key
STREAM_KEY = "agent_eval:evidence:stream"
GROUP_NAME = "evidence_workers"
CONSUMER_NAME = f"worker_{os.getpid()}"
# Dead Letter Queue: 超过最大重试次数的消息移到这里
DLQ_KEY = "agent_eval:evidence:dlq"
MAX_RETRIES = 3


class EvidenceQueue:
    """Redis Streams 证据队列"""

    def __init__(self, redis_url: str = None):
        self._redis = None
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._available = None  # None = 未检测

    @property
    def redis(self):
        """惰性连接 Redis"""
        if self._redis is None:
            try:
                import redis
                self._redis = redis.Redis.from_url(
                    self.redis_url, decode_responses=True, socket_timeout=5
                )
                self._redis.ping()
                self._available = True
                self._ensure_group()
            except ImportError:
                logger.warning("redis 库未安装, 证据队列不可用")
                self._available = False
            except Exception as e:
                logger.warning("Redis 连接失败 (%s), 证据队列降级为同步模式", e)
                self._available = False
        return self._redis if self._available else None

    @property
    def available(self) -> bool:
        if self._available is None:
            _ = self.redis  # 触发连接检测
        return bool(self._available)

    def _ensure_group(self):
        """确保 Consumer Group 存在"""
        try:
            self._redis.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
            logger.info("Redis Streams group '%s' created", GROUP_NAME)
        except Exception:
            # Group 已存在 → 正常
            pass

    # ── Producer API ──

    def enqueue(
        self,
        session_id: str,
        scenario_index: int,
        eval_score_id: str,
        conversation_json: dict,
        score_json: dict,
        screenshot_paths: list[str] = None,
        recording_path: str = None,
        report_path: str = None,
    ) -> Optional[str]:
        """入队一条证据处理任务

        Returns: Redis message ID, 或 None (Redis 不可用时)
        """
        msg = {
            "session_id": session_id,
            "scenario_index": scenario_index,
            "eval_score_id": eval_score_id,
            "conversation_json": json.dumps(conversation_json, ensure_ascii=False, default=str),
            "score_json": json.dumps(score_json, ensure_ascii=False, default=str),
            "screenshot_paths": json.dumps(screenshot_paths or []),
            "recording_path": recording_path or "",
            "report_path": report_path or "",
            "retry_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        r = self.redis
        if r is None:
            # Redis 不可用 → 降级为同步处理
            logger.debug("Redis 不可用, 同步处理证据: %s", session_id)
            self._process_sync(msg)
            return None

        msg_id = r.xadd(STREAM_KEY, msg, maxlen=10000)
        logger.debug("Enqueued evidence: %s (msg_id=%s)", session_id, msg_id)
        return msg_id

    # ── Consumer API ──

    def consume_one(self, block_ms: int = 5000) -> bool:
        """消费一条消息 (阻塞等待)

        Returns: True if processed a message, False if timeout
        """
        r = self.redis
        if r is None:
            return False

        try:
            streams = r.xreadgroup(
                GROUP_NAME, CONSUMER_NAME,
                {STREAM_KEY: ">"}, count=1, block=block_ms,
            )
        except Exception:
            # Group 不存在 → 重建
            self._ensure_group()
            return False

        if not streams:
            return False

        for stream_name, messages in streams:
            for msg_id, fields in messages:
                try:
                    self._process_message(fields)
                    r.xack(STREAM_KEY, GROUP_NAME, msg_id)
                    logger.debug("Evidence processed: msg_id=%s", msg_id)
                except Exception as e:
                    logger.error("Evidence processing failed: msg_id=%s — %s", msg_id, e)
                    retry_count = int(fields.get("retry_count", 0)) + 1
                    if retry_count <= MAX_RETRIES:
                        # 重试: 重新入队
                        fields["retry_count"] = retry_count
                        fields["last_error"] = str(e)[:500]
                        r.xadd(STREAM_KEY, fields)
                        r.xack(STREAM_KEY, GROUP_NAME, msg_id)
                        logger.warning("Evidence retry %d/%d: msg_id=%s",
                                       retry_count, MAX_RETRIES, msg_id)
                    else:
                        # 移到死信队列
                        r.xadd(DLQ_KEY, {**fields, "final_error": str(e)[:500]})
                        r.xack(STREAM_KEY, GROUP_NAME, msg_id)
                        logger.error("Evidence moved to DLQ after %d retries: msg_id=%s",
                                     MAX_RETRIES, msg_id)

        return True

    def consume_loop(self, idle_callback=None):
        """持续消费循环 (用于后台 worker)"""
        logger.info("Evidence worker started: stream=%s group=%s consumer=%s",
                    STREAM_KEY, GROUP_NAME, CONSUMER_NAME)
        while True:
            try:
                processed = self.consume_one(block_ms=5000)
                if not processed and idle_callback:
                    idle_callback()
            except KeyboardInterrupt:
                logger.info("Evidence worker stopped")
                break
            except Exception as e:
                logger.error("Evidence worker error: %s", e)
                time.sleep(1)

    # ── Pending 消息重处理 ──

    def reclaim_pending(self, min_idle_ms: int = 60000) -> int:
        """回收超时未ACK的 Pending 消息"""
        r = self.redis
        if r is None:
            return 0

        count = 0
        try:
            pending = r.xpending_range(STREAM_KEY, GROUP_NAME, min="-", max="+", count=100)
            for entry in pending:
                msg_id = entry["message_id"]
                idle_ms = entry.get("time_since_delivered", 0)
                if idle_ms >= min_idle_ms:
                    # 认领并重新处理
                    claimed = r.xclaim(STREAM_KEY, GROUP_NAME, CONSUMER_NAME,
                                       min_idle_time=min_idle_ms, message_ids=[msg_id])
                    for c_msg_id, c_fields in claimed:
                        try:
                            self._process_message(c_fields)
                            r.xack(STREAM_KEY, GROUP_NAME, c_msg_id)
                            count += 1
                        except Exception as e:
                            logger.error("Reclaim processing failed: %s — %s", c_msg_id, e)
        except Exception as e:
            logger.warning("Pending reclaim failed: %s", e)

        return count

    # ── 内部: 消息处理 ──

    def _process_message(self, fields: dict):
        """处理一条消息: 证据直接写入 MySQL"""
        conversation_json = json.loads(fields["conversation_json"])
        score_json = json.loads(fields["score_json"])
        session_id = fields["session_id"]
        scenario_index = int(fields["scenario_index"])
        eval_score_id = fields["eval_score_id"]
        metadata = json.loads(fields.get("metadata_json", "{}") or "{}")

        from src.evidence_hasher import EvidenceHasher
        from backend.dependencies import get_sync_db

        hasher = EvidenceHasher()
        db = get_sync_db()
        try:
            fingerprint = hasher.store_evidence(
                db=db,
                session_id=session_id,
                eval_score_id=eval_score_id,
                scenario_index=scenario_index,
                conversation_json=conversation_json,
                score_json=score_json,
                metadata=metadata,
            )
            db.commit()
            logger.info("Evidence stored: session=%s scenario=%d hash=%s",
                        session_id, scenario_index, fingerprint[:16])
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _process_sync(self, fields: dict):
        """同步降级模式: 直接写 MySQL (Redis 不可用时)"""
        try:
            self._process_message(fields)
        except Exception as e:
            logger.error("Sync evidence processing failed: %s", e)


# ── 独立 Worker 入口 ──

def run_worker():
    """启动证据队列 Worker (用于 systemd / 独立进程)"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    queue = EvidenceQueue()
    if not queue.available:
        logger.error("Redis 不可用, Worker 无法启动")
        return
    logger.info("Starting evidence worker...")
    # 先回收 Pending 消息
    reclaimed = queue.reclaim_pending(min_idle_ms=30000)
    if reclaimed:
        logger.info("Reclaimed %d pending messages", reclaimed)
    queue.consume_loop()


if __name__ == "__main__":
    run_worker()
