"""
EvalInteractive — 测评卡点解决器 (BlockerResolver)

Schema 自动化测评为主, 只有遇到卡点才介入。降级保底阶梯:

  L0  内置 Self-Healing 四层级联 (src/self_healing.py, 已存在)
  L1  卡点记录 → LLM 观察页面快照自主决策 (retry_hint / ask / skip)
  L2  LLM retry_hint → 执行器重试 (默认最多 2 次)
  L3  LLM 生成问题 → 向评测用户提问 (阻塞等待, 超时 120s)
      - 用户回答 → 回灌 LLM → 生成新 retry_hint (额外允许 2 次重试)
  L4  超时/跳过 → 按 LLM 建议跳过该步并标注原因, 继续后续测评
  L5  LLM 不可用 → 规则式: 直接向用户提通用问题 → 回答作为意图重试 → 否则跳过
  L6  提问预算耗尽 → 全部跳过, 测评不中断, 报告带完整卡点日志

所有卡点记录进 resolver.log → 最终报告 diagnosis (可追溯)。

用法:
    from src.eval_interactive import BlockerResolver
    resolver = BlockerResolver(ask_fn=bridge.ask)
    r = resolver.resolve(
        kind="navigation", phase_name=..., lesson_name=..., step_name=...,
        error="找不到 Phase 按钮", dom_snapshot={...})
    # r: {"action": "retry", "hint": "..."} | {"action": "skip", "reason": "..."}
"""
from __future__ import annotations

import json
import time
from typing import Callable, Optional

RESOLVER_SYSTEM_PROMPT = """你是自动化测评的卡点解决助手。一个浏览器测评机器人在测评教学平台时遇到卡点。
你的任务: 观察卡点信息和当前页面状态, 输出一个 JSON 决策 (只输出 JSON):

- {"action":"retry","hint":"..."}
    hint 是给浏览器执行器的一句话指引: 优先给"页面上具体按钮的完整文字" (执行器会先精确点击);
    如果无法确定, 给一句语义意图描述 (例如 "点击显示'完成'或'继续'含义的按钮")。
- {"action":"ask","question":"...","options":["..."],"reason":"..."}
    页面信息不足以自行解决, 需要向评测用户询问。问题用中文、具体、面向非技术用户。
    例如: "页面上没有找到'本步已完成'按钮。请问完成当前步骤需要点击哪个按钮? 请描述按钮文字或位置。"
    options 给 2-3 个快捷选项 (调用方会自动追加"跳过本步")。
- {"action":"skip","reason":"..."}
    该卡点无法或不应继续处理 (例如页面本身报错、功能不存在), 直接跳过并注明原因。

规则:
1. 优先 retry — 大多数卡点是按钮文字/位置差异, 给出新指引即可。
2. 只有当信息确实不足 (如需要用户提供验证码/账号/手动操作) 才 ask。
3. 如果错误显示平台功能本身异常 (HTTP 5xx、白屏、报错弹窗), 直接 skip。
4. 用户回答后 (历史会提供), 尽量从回答中提取可执行的 retry hint。"""


class BlockerResolver:
    """测评卡点解决器 — 降级保底阶梯"""

    def __init__(
        self,
        ask_fn: Optional[Callable] = None,
        question_timeout: float = 120.0,
        max_llm_retries: int = 2,
        max_questions: int = 10,
        max_retries_after_answer: int = 2,
        verbose: bool = True,
    ):
        self.ask_fn = ask_fn
        self.question_timeout = question_timeout
        self.max_llm_retries = max_llm_retries
        self.max_questions = max_questions
        self.max_retries_after_answer = max_retries_after_answer
        self.verbose = verbose

        self.stats = {
            "blockers": 0, "llm_retried": 0, "questions_asked": 0,
            "user_resolved": 0, "skipped": 0, "timed_out": 0,
        }
        self.log: list[dict] = []
        self._retry_counts: dict = {}
        self._questions_asked = 0

    # ── 主入口 ──

    def resolve(
        self,
        kind: str,
        phase_name: str = "",
        lesson_name: str = "",
        step_name: str = "",
        error: str = "",
        dom_snapshot: Optional[dict] = None,
    ) -> dict:
        """
        处理一个卡点。

        :param kind: 'login' | 'navigation' | 'enter_content' | 'step_action' | 'agent' | 'quiz'
        :returns: {"action": "retry", "hint": str} | {"action": "skip", "reason": str}
        """
        self.stats["blockers"] += 1
        key = f"{phase_name}|{lesson_name}|{step_name}|{kind}"
        entry = {
            "kind": kind, "phase": phase_name, "lesson": lesson_name,
            "step": step_name, "error": (error or "")[:300],
            "ts": time.time(), "resolution": "pending",
        }
        self.log.append(entry)

        if self.verbose:
            print(f"  [Blocker] {kind} @ {phase_name}/{lesson_name}/{step_name}: {error[:80]}")

        # ── 预算检查: 提问次数耗尽 → 直接跳过 ──
        if self._questions_asked >= self.max_questions:
            entry["resolution"] = "skip_budget"
            entry["reason"] = f"提问次数达到上限 ({self.max_questions})"
            self.stats["skipped"] += 1
            return {"action": "skip", "reason": entry["reason"]}

        # ── LLM 决策 ──
        decision = self._llm_decide(kind, phase_name, lesson_name, step_name, error, dom_snapshot)

        if decision is None:
            return self._rule_fallback(entry, kind, phase_name, lesson_name, step_name, error)

        action = decision.get("action", "skip")
        retry_count = self._retry_counts.get(key, 0)

        if action == "retry":
            if retry_count < self.max_llm_retries:
                self._retry_counts[key] = retry_count + 1
                self.stats["llm_retried"] += 1
                entry["resolution"] = "retry"
                entry["hint"] = decision.get("hint", "")[:300]
                return {"action": "retry", "hint": entry["hint"]}
            # 重试预算耗尽 → 转为问用户 (或跳过)
            action = "ask"
            decision["question"] = (
                f"自动重试 {retry_count} 次仍失败 ({error[:80]})。"
                f"请提供下一步操作指引 (如按钮文字/位置), 或选择跳过。"
            )
            decision["options"] = []

        if action == "ask":
            if not self.ask_fn:
                entry["resolution"] = "skip_no_channel"
                entry["reason"] = "无用户问答通道"
                self.stats["skipped"] += 1
                return {"action": "skip", "reason": entry["reason"]}

            question = decision.get("question", "请提供下一步操作指引")
            options = list(decision.get("options") or [])
            if "跳过本步" not in options:
                options.append("跳过本步")

            self.stats["questions_asked"] += 1
            self._questions_asked += 1

            result = self.ask_fn(
                text=question,
                options=options,
                context=self._compact_dom(dom_snapshot),
                timeout_s=self.question_timeout,
                source="eval",
                meta={"kind": kind, "phase": phase_name, "step": step_name},
            )

            if result.get("timed_out"):
                self.stats["timed_out"] += 1
                entry["resolution"] = "skip_timeout"
                entry["reason"] = "等待用户回答超时, 按降级策略跳过本步"
                self.stats["skipped"] += 1
                return {"action": "skip", "reason": entry["reason"]}

            if result.get("skipped"):
                self.stats["skipped"] += 1
                entry["resolution"] = "skip_by_user"
                entry["reason"] = "用户选择跳过本步"
                return {"action": "skip", "reason": entry["reason"]}

            answer = result.get("answer", "")
            entry["answer"] = answer[:300]

            # ── 用户回答回灌 LLM → 生成 retry hint ──
            hint = self._llm_hint_from_answer(
                kind, phase_name, lesson_name, step_name, error, answer, dom_snapshot
            )
            self._retry_counts[key] = 0  # 用户提供了指引 → 重置重试计数
            self.stats["user_resolved"] += 1
            entry["resolution"] = "user_guided_retry"
            entry["hint"] = hint
            return {"action": "retry", "hint": hint}

        # skip / 未知动作 → 跳过
        self.stats["skipped"] += 1
        entry["resolution"] = "skip"
        entry["reason"] = decision.get("reason", "LLM 建议跳过")[:300]
        return {"action": "skip", "reason": entry["reason"]}

    # ── LLM 调用 ──

    def _llm_decide(self, kind, phase_name, lesson_name, step_name, error, dom_snapshot) -> Optional[dict]:
        try:
            from src.llm_client import get_llm_client
            client, model, _ = get_llm_client()
            if not client:
                return None
            user_msg = (
                f"卡点类型: {kind}\n"
                f"位置: Phase={phase_name or '?'} Lesson={lesson_name or '?'} Step={step_name or '?'}\n"
                f"错误信息: {error[:300]}\n\n"
                f"当前页面状态:\n{self._compact_dom(dom_snapshot)}"
            )
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": RESOLVER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=400, temperature=0.1, timeout=30,
            )
            content = resp.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.strip("`")
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
        except Exception as e:
            if self.verbose:
                print(f"  [Blocker] LLM 决策失败: {e}")
            return None

    def _llm_hint_from_answer(self, kind, phase_name, lesson_name, step_name,
                              error, answer, dom_snapshot) -> str:
        """用户回答 → LLM 提炼可执行 retry hint。失败则直接用回答文本作为 hint。"""
        try:
            from src.llm_client import get_llm_client
            client, model, _ = get_llm_client()
            if not client:
                return (answer or "").strip()[:300]
            user_msg = (
                f"卡点类型: {kind}\n位置: Phase={phase_name or '?'} Step={step_name or '?'}\n"
                f"错误: {error[:200]}\n\n"
                f"评测用户对'如何解决这个卡点'的回答:\n{answer[:800]}\n\n"
                f"当前页面按钮清单:\n{self._compact_dom(dom_snapshot)}\n\n"
                f"请从用户回答中提炼一个可执行的 retry hint: "
                f"优先输出用户提到的具体按钮文字 (与页面按钮清单中的文字完全一致); "
                f"如果用户描述的是操作步骤, 输出一句语义意图描述。只输出 hint 文本本身, 不要 JSON。"
            )
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=200, temperature=0.1, timeout=30,
            )
            hint = resp.choices[0].message.content.strip()
            return hint[:300] if hint else (answer or "").strip()[:300]
        except Exception:
            return (answer or "").strip()[:300]

    # ── 规则式降级 (LLM 不可用) ──

    def _rule_fallback(self, entry, kind, phase_name, lesson_name, step_name, error) -> dict:
        if not self.ask_fn:
            entry["resolution"] = "skip_no_llm_no_channel"
            entry["reason"] = "LLM 与问答通道均不可用"
            self.stats["skipped"] += 1
            return {"action": "skip", "reason": entry["reason"]}

        self.stats["questions_asked"] += 1
        self._questions_asked += 1

        kind_cn = {"navigation": "页面导航", "enter_content": "进入学习内容",
                   "step_action": "完成当前步骤", "agent": "唤起AI助手",
                   "quiz": "Quiz答题", "login": "登录"}.get(kind, kind)
        question = (
            f"测评在第'{step_name or lesson_name or phase_name}'处{kind_cn}时卡住了 ({error[:100]})。"
            f"请告诉我应该点击哪个按钮 (请给出按钮文字) 或如何操作; 或者选择跳过本步。"
        )
        result = self.ask_fn(
            text=question, options=["跳过本步"],
            context="", timeout_s=self.question_timeout,
            source="eval", meta={"kind": kind},
        )
        if result.get("timed_out") or result.get("skipped"):
            self.stats["timed_out" if result.get("timed_out") else "skipped"] += 1
            entry["resolution"] = "skip_timeout" if result.get("timed_out") else "skip_by_user"
            entry["reason"] = "等待用户回答超时" if result.get("timed_out") else "用户选择跳过本步"
            return {"action": "skip", "reason": entry["reason"]}

        answer = (result.get("answer") or "").strip()
        self.stats["user_resolved"] += 1
        entry["resolution"] = "user_guided_retry"
        entry["hint"] = answer[:300]
        return {"action": "retry", "hint": answer[:300]}

    # ── 工具 ──

    @staticmethod
    def _compact_dom(dom_snapshot: Optional[dict]) -> str:
        if not dom_snapshot:
            return "(无页面快照)"
        parts = []
        if dom_snapshot.get("url"):
            parts.append(f"URL: {dom_snapshot['url']}")
        buttons = dom_snapshot.get("buttons") or []
        if buttons:
            parts.append("按钮清单: " + json.dumps(
                [{"text": b.get("text", "")[:60]} for b in buttons[:25]],
                ensure_ascii=False))
        vt = dom_snapshot.get("visibleText") or dom_snapshot.get("visible_text") or ""
        if vt:
            parts.append(f"页面文本片段: {vt[:600]}")
        inputs = dom_snapshot.get("inputs") or []
        if inputs:
            parts.append("输入框: " + json.dumps(inputs[:8], ensure_ascii=False))
        return "\n".join(parts)

    def summary(self) -> dict:
        return {
            "stats": dict(self.stats),
            "resolved": sum(1 for e in self.log if e.get("resolution") in
                            ("retry", "user_guided_retry")),
            "log": self.log,
        }
