"""
QuestionBridge — 线程安全问答桥 (交互式探索 + 测评卡点协作)

工作线程 (探索/测评) 调用 ask() 阻塞等待评测用户的回答;
HTTP/WS 线程调用 answer() 唤醒。支持超时降级 + 完整对话历史。

设计要点:
  - 一次只有一个 pending 问题 (工作线程串行提问)
  - 超时返回 timed_out=True → 调用方走降级路径
  - disabled 时 ask() 立即返回 auto_disabled → 无人值守模式保底
  - history 供前端轮询渲染对话 (问题/回答/超时/跳过)

用法:
    bridge = QuestionBridge()
    result = bridge.ask(
        text="登录页需要手机验证码, 请提供",
        options=["跳过登录"],
        context="页面快照摘要",
        timeout_s=180,
        source="explorer",
    )
    # result: {"answer": str, "skipped": bool, "timed_out": bool, "question_id": str}
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Callable, Optional


class QuestionBridge:
    """线程安全问答桥"""

    def __init__(self, enabled: bool = True):
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._question: Optional[dict] = None
        self._answer: Optional[dict] = None
        self._enabled = bool(enabled)
        self._history: list[dict] = []
        self._on_question: Optional[Callable] = None  # 新问题回调 (WS 推送用)

    # ── 配置 ──

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, v: bool):
        with self._lock:
            self._enabled = bool(v)

    def set_on_question(self, cb: Optional[Callable]):
        """新问题产生时的通知回调 (签名: cb(dict))"""
        with self._lock:
            self._on_question = cb

    # ── 工作线程侧 ──

    def ask(
        self,
        text: str,
        options: list[str] = None,
        context: str = "",
        context_type: str = "",
        timeout_s: float = 180.0,
        source: str = "",
        meta: dict = None,
    ) -> dict:
        """
        提出一个问题并阻塞等待回答。

        :returns: {"answer", "skipped", "timed_out", "question_id", "auto_disabled"}
        """
        if not self._enabled:
            return {
                "answer": "", "skipped": True, "timed_out": False,
                "question_id": "", "auto_disabled": True,
            }

        qid = uuid.uuid4().hex[:8]
        with self._lock:
            q = {
                "qid": qid,
                "text": (text or "")[:1000],
                "options": list(options or [])[:8],
                "context": (context or "")[:2000],
                "context_type": context_type,
                "source": source,
                "meta": meta or {},
                "ts": time.time(),
                "timeout_s": float(timeout_s),
                "status": "pending",
            }
            self._question = q
            self._answer = None
            self._event.clear()
            cb = self._on_question

        if cb:
            try:
                cb(dict(q))
            except Exception:
                pass

        ok = self._event.wait(timeout=timeout_s)

        with self._lock:
            ans = self._answer
            self._answer = None
            self._question = None
            if not ok or not ans:
                self._history.append({
                    "qid": qid, "text": q["text"], "options": q["options"],
                    "source": source, "status": "timed_out", "ts": time.time(),
                })
                return {
                    "answer": "", "skipped": True, "timed_out": True,
                    "question_id": qid, "auto_disabled": False,
                }
            answer_text = ans.get("answer", "") or ""
            skipped = bool(ans.get("skipped"))
            self._history.append({
                "qid": qid, "text": q["text"], "options": q["options"],
                "source": source,
                "status": "skipped" if skipped else "answered",
                "answer": answer_text[:4000],
                "ts": time.time(),
            })
            return {
                "answer": answer_text, "skipped": skipped,
                "timed_out": False, "question_id": qid, "auto_disabled": False,
            }

    # ── HTTP/WS 线程侧 ──

    def answer(self, qid: str, answer: str = "", skipped: bool = False) -> bool:
        """回答当前 pending 问题。返回是否命中。"""
        with self._lock:
            q = self._question
            if not q or q["qid"] != qid:
                return False
            self._answer = {"answer": answer or "", "skipped": bool(skipped)}
            self._event.set()
            return True

    def answer_any(self, answer: str = "", skipped: bool = False) -> bool:
        """回答当前 pending 问题 (不校验 qid)。"""
        with self._lock:
            if not self._question:
                return False
            self._answer = {"answer": answer or "", "skipped": bool(skipped)}
            self._event.set()
            return True

    # ── 状态查询 (前端轮询) ──

    def current_question(self) -> Optional[dict]:
        """当前 pending 问题 (含剩余秒数)。无则 None。"""
        with self._lock:
            if not self._question:
                return None
            q = dict(self._question)
            q["remaining_s"] = max(
                0.0, round(q["timeout_s"] - (time.time() - q["ts"]), 1)
            )
            return q

    def history(self, last_n: int = 30) -> list[dict]:
        """最近问答历史 (倒序优先由调用方决定, 这里返回时间正序尾部)。"""
        with self._lock:
            return [dict(h) for h in self._history[-last_n:]]

    def clear(self):
        with self._lock:
            self._history.clear()
            self._question = None
            self._answer = None
