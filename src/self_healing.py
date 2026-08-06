"""
Self-Healing 定位器恢复 — Agent C (SOTA Paradigm 4 基础设施)

适配 browser_evaluator.py 现有定位器模式, 不修改其内部代码。
接入方式: 调用 apply_self_healing(evaluator) → monkey-patch _find_and_click.

核心策略 (四层级联回退):
  L0: 原始定位器 (不变, 最快)
  L1: 语义文本匹配 (fuzzy text search, 容忍空格/大小写/部分匹配)
  L2: DOM 结构推断 (从 _dump_dom_state 找相似按钮)
  L3: AI 驱动的语义重定位 (调 LLM 从页面文本推断新选择器)

设计原则:
  - 所有 healing 事件记录到 healing_log.json → Agent A 可在 Health 页面展示
  - 纯函数设计, 不依赖 BrowserEvaluator 内部状态
  - 零修改接入: 仅需在 test_service.py 加一行 apply_self_healing(evaluator)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── 记录路径 ──
HEALING_LOG_PATH = Path(__file__).parent.parent / "data" / "healing_log.json"

# ── 语义相似度阈值 ──
SIMILARITY_THRESHOLD = 0.55  # SequenceMatcher ratio 最低接受值
HIGH_CONFIDENCE_THRESHOLD = 0.80


class HealingEvent:
    """单次自愈事件"""

    def __init__(
        self,
        original_text: str,
        strategy: str,  # "L1_fuzzy" | "L2_dom" | "L3_ai" | "failed"
        found_text: str = "",
        found_selector: str = "",
        confidence: float = 0.0,
        page_url: str = "",
        dom_snapshot: dict | None = None,
        ai_reasoning: str = "",
    ):
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.original_text = original_text
        self.strategy = strategy
        self.found_text = found_text
        self.found_selector = found_selector
        self.confidence = confidence
        self.page_url = page_url
        self.dom_snapshot = dom_snapshot
        self.ai_reasoning = ai_reasoning
        self.duration_ms = 0.0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "original_text": self.original_text,
            "strategy": self.strategy,
            "found_text": self.found_text[:120] if self.found_text else "",
            "found_selector": self.found_selector,
            "confidence": round(self.confidence, 3),
            "page_url": self.page_url,
            "ai_reasoning": self.ai_reasoning[:300],
            "duration_ms": round(self.duration_ms, 1),
        }


class HealingLog:
    """自愈事件记录器 — 持久化到 JSON, Agent A 的 Health 页面可消费"""

    def __init__(self):
        self.events: list[HealingEvent] = []
        self._load()

    def add(self, event: HealingEvent):
        self.events.append(event)
        self._save()

    def _load(self):
        try:
            if HEALING_LOG_PATH.exists():
                raw = json.loads(HEALING_LOG_PATH.read_text(encoding="utf-8"))
                # 只保留最近 500 条
                self.events = [
                    HealingEvent(**e) for e in raw.get("events", [])[-500:]
                ]
        except Exception:
            pass

    def _save(self):
        try:
            HEALING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            HEALING_LOG_PATH.write_text(
                json.dumps(
                    {
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "total_events": len(self.events),
                        "summary": self.summary(),
                        "events": [e.to_dict() for e in self.events[-500:]],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"HealingLog save failed: {e}")

    def summary(self) -> dict:
        """统计摘要 — Agent A 的 Health API 可直接序列化"""
        if not self.events:
            return {"total": 0, "by_strategy": {}, "success_rate": 0.0, "top_failures": []}

        by_strategy: dict[str, int] = {}
        failures: list[str] = []
        for e in self.events:
            by_strategy[e.strategy] = by_strategy.get(e.strategy, 0) + 1
            if e.strategy == "failed":
                failures.append(e.original_text[:80])

        success = sum(
            v for k, v in by_strategy.items() if k != "failed"
        )
        total = len(self.events)

        return {
            "total": total,
            "by_strategy": by_strategy,
            "success_rate": round(success / max(total, 1), 3),
            "top_failures": failures[-10:],
            "latest_healed": self.events[-1].original_text[:80] if self.events else "",
        }


# ── 全局单例 ──
_healing_log = HealingLog()


def get_healing_log() -> HealingLog:
    return _healing_log


# ═══════════════════════════════════════════════════════════════════
# L1: 语义文本匹配 (fuzzy text search)
# ═══════════════════════════════════════════════════════════════════

def _text_similarity(a: str, b: str) -> float:
    """计算两个文本的语义相似度 — 先标准化, 再 SequenceMatcher"""
    def _normalize(t: str) -> str:
        # 去空格、统一大小写、去常见前后缀
        t = re.sub(r"\s+", "", t.lower())
        t = t.lstrip("0123456789. )-】」》")
        return t

    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _fuzzy_find_button(
    page, target_text: str, buttons: list[dict]
) -> tuple[Optional[str], Optional[str], float]:
    """
    在 DOM snapshot 的 buttons 列表中模糊查找。

    :param page: Playwright page (用于验证候选按钮是否仍可点击)
    :param target_text: 原始失败的定位文本 (如 "Phase 01")
    :param buttons: _dump_dom_state()["buttons"] 列表
    :return: (found_text, css_selector, confidence) 或 (None, None, 0)
    """
    candidates: list[tuple[str, str, float]] = []

    for b in buttons:
        btn_text = b.get("text", "")
        btn_class = b.get("class", "")
        if b.get("disabled"):
            continue

        sim = _text_similarity(target_text, btn_text)
        if sim >= SIMILARITY_THRESHOLD:
            # 构造 Playwright 定位器
            if btn_class:
                selector = f"button.{'.'.join(btn_class.split()[:2])}:has-text('{btn_text[:30]}')"
            else:
                selector = f"button:has-text('{btn_text[:30]}')"
            candidates.append((btn_text, selector, sim))

    candidates.sort(key=lambda x: -x[2])

    # 验证最佳候选
    for text, selector, confidence in candidates:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=2000) and not el.is_disabled():
                return text, selector, confidence
        except Exception:
            continue

    return None, None, 0.0


# ═══════════════════════════════════════════════════════════════════
# L2: DOM 结构推断 (从 snapshot 找语义最近邻居)
# ═══════════════════════════════════════════════════════════════════

def _structural_find_button(
    page, target_text: str, dom_snapshot: dict
) -> tuple[Optional[str], Optional[str], float]:
    """
    从 DOM 结构中推断替代按钮。

    策略:
      1. 提取 target_text 中的关键 token (数字/核心名词)
      2. 在所有可见按钮中找包含同样 token 的
      3. 优先同 className 的 (结构相似)

    例: "Phase 01" 找不到 → 找包含 "Phase" 和 "1" 的按钮
    """
    # 提取关键 token
    tokens = re.findall(r"[一-鿿]+|[a-zA-Z]+|\d+", target_text)
    tokens = [t.lower() for t in tokens if len(t) >= 1]

    buttons = dom_snapshot.get("buttons", [])
    candidates: list[tuple[str, str, int, float]] = []

    for b in buttons:
        btn_text = b.get("text", "").lower()
        btn_class = b.get("class", "")
        if b.get("disabled"):
            continue

        # token 命中数
        hits = sum(1 for t in tokens if t in btn_text)
        if hits == 0:
            continue

        # 结构相似度加分: 相同 class 前缀
        class_bonus = 0.0
        if btn_class:
            # 大多数按钮 class 有模式: xxx-button, xxx-card, xxx-item
            class_tokens = set(re.findall(r"[a-zA-Z]+", btn_class.lower()))
            class_bonus = len(class_tokens) * 0.02

        # 综合得分
        score = hits / max(len(tokens), 1) + class_bonus
        selector = f"button:has-text('{b['text'][:30]}')"
        candidates.append((b["text"], selector, hits, score))

    candidates.sort(key=lambda x: -x[3])

    for text, selector, hits, score in candidates:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=2000) and not el.is_disabled():
                confidence = min(0.70, 0.50 + score)
                return text, selector, confidence
        except Exception:
            continue

    return None, None, 0.0


# ═══════════════════════════════════════════════════════════════════
# L3: AI 驱动的语义重定位 (LLM fallback — 最后手段)
# ═══════════════════════════════════════════════════════════════════

def _ai_relocate(
    target_text: str, dom_snapshot: dict, api_key: str = ""
) -> tuple[Optional[str], float, str]:
    """
    用 LLM 从页面文本推断正确的定位策略。

    :param target_text: 原始失败文本 (如 "本步已完成")
    :param dom_snapshot: _dump_dom_state() 输出
    :param api_key: OpenAI-compatible API key (默认从环境变量取)
    :return: (suggested_text, confidence, reasoning)
    """
    if not api_key:
        from src.llm_client import get_api_key
        api_key = get_api_key()

    if not api_key:
        return None, 0.0, "no API key"

    # 构建最小上下文
    buttons = dom_snapshot.get("buttons", [])
    visible_text = dom_snapshot.get("visibleText", "")[:1500]
    button_list = "\n".join(
        f"- text=\"{b['text'][:80]}\" class=\"{b.get('class', '')[:40]}\""
        for b in buttons[:20]
    )

    prompt = f"""你是UI测试专家。一个自动化测试想点击包含文字 "{target_text}" 的按钮, 但没找到。

当前页面可见按钮:
{button_list if button_list else "(无按钮数据)"}

页面文本片段:
{visible_text[:800]}

请找出页面上最可能对应 "{target_text}" 功能的按钮, 即使文字不完全一样。
输出JSON: {{"found_text": "按钮文字", "confidence": 0.0-1.0, "reasoning": "一行解释"}}
如果实在找不到, 输出: {{"found_text": "", "confidence": 0, "reasoning": "解释"}}
只输出JSON。"""

    try:
        from openai import OpenAI
        from src.llm_client import get_base_url, get_llm_client

        _client, _model, _cfg = get_llm_client()
        if _client:
            client = _client
            model = _model
        else:
            base_url = get_base_url()
            client = OpenAI(api_key=api_key, base_url=base_url)
            model = "deepseek-chat"

        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
            response_format={"type": "json_object"},
            timeout=15,
        )
        result = json.loads(resp.choices[0].message.content)
        return (
            result.get("found_text", ""),
            float(result.get("confidence", 0)),
            result.get("reasoning", ""),
        )
    except Exception as e:
        logger.warning(f"AI relocate failed: {e}")
        return None, 0.0, f"AI error: {e}"


# ═══════════════════════════════════════════════════════════════════
# 核心: 四层级联自愈
# ═══════════════════════════════════════════════════════════════════

def heal_click(
    page,
    target_text: str,
    dom_snapshot: dict | None = None,
    api_key: str = "",
) -> tuple[bool, str, HealingEvent]:
    """
    四层级联自愈点击。

    :param page: Playwright page 对象
    :param target_text: 原始定位文本
    :param dom_snapshot: 预先采集的 _dump_dom_state() (可选, 不传则自动采集)
    :param api_key: L3 AI 回退用的 API key
    :return: (success, found_text, HealingEvent)
    """
    t0 = time.time()

    # 采集 DOM snapshot (如果未预传入)
    if dom_snapshot is None:
        try:
            dom_snapshot = page.evaluate("""() => ({
                url: location.href,
                title: document.title,
                buttons: [...document.querySelectorAll('button')]
                    .filter(b => b.offsetParent)
                    .map(b => ({
                        text: b.textContent.trim().substring(0, 100),
                        class: b.className.substring(0, 60),
                        disabled: b.disabled
                    })),
                visibleText: document.body.textContent.substring(0, 1500)
            })""")
        except Exception:
            dom_snapshot = {"buttons": [], "visibleText": "", "url": ""}

    page_url = dom_snapshot.get("url", "")
    buttons = dom_snapshot.get("buttons", [])

    # ── L1: 语义模糊匹配 ──────────────────────────
    found_text, found_selector, confidence = _fuzzy_find_button(
        page, target_text, buttons
    )
    if found_text and found_selector:
        try:
            page.locator(found_selector).first.click()
            event = HealingEvent(
                original_text=target_text,
                strategy="L1_fuzzy",
                found_text=found_text,
                found_selector=found_selector,
                confidence=confidence,
                page_url=page_url,
                dom_snapshot=dom_snapshot,
            )
            event.duration_ms = (time.time() - t0) * 1000
            _healing_log.add(event)
            return True, found_text, event
        except Exception:
            pass  # L1 声称找到了但实际点不了 → 继续 L2

    # ── L2: DOM 结构推断 ──────────────────────────
    found_text, found_selector, confidence = _structural_find_button(
        page, target_text, dom_snapshot
    )
    if found_text and found_selector:
        try:
            page.locator(found_selector).first.click()
            event = HealingEvent(
                original_text=target_text,
                strategy="L2_dom",
                found_text=found_text,
                found_selector=found_selector,
                confidence=confidence,
                page_url=page_url,
                dom_snapshot=dom_snapshot,
            )
            event.duration_ms = (time.time() - t0) * 1000
            _healing_log.add(event)
            return True, found_text, event
        except Exception:
            pass

    # ── L3: AI 语义重定位 ─────────────────────────
    # 仅在 L1+L2 都失败时调用 (昂贵, 有延迟)
    ai_text, ai_confidence, ai_reasoning = _ai_relocate(
        target_text, dom_snapshot, api_key
    )
    if ai_text and ai_confidence >= 0.5:
        # 验证 LLM 建议
        try:
            ai_selector = f"button:has-text('{ai_text[:30]}')"
            el = page.locator(ai_selector).first
            if el.is_visible(timeout=3000) and not el.is_disabled():
                el.click()
                event = HealingEvent(
                    original_text=target_text,
                    strategy="L3_ai",
                    found_text=ai_text,
                    found_selector=ai_selector,
                    confidence=ai_confidence,
                    page_url=page_url,
                    dom_snapshot=dom_snapshot,
                    ai_reasoning=ai_reasoning,
                )
                event.duration_ms = (time.time() - t0) * 1000
                _healing_log.add(event)
                return True, ai_text, event
        except Exception:
            pass

    # ── 全部失败 ──────────────────────────────────
    event = HealingEvent(
        original_text=target_text,
        strategy="failed",
        page_url=page_url,
        dom_snapshot=dom_snapshot,
    )
    event.duration_ms = (time.time() - t0) * 1000
    _healing_log.add(event)
    return False, "", event


# ═══════════════════════════════════════════════════════════════════
# 接入层: monkey-patch BrowserEvaluator (一行接入, 不改原代码)
# ═══════════════════════════════════════════════════════════════════

def apply_self_healing(evaluator, api_key: str = ""):
    """
    对 BrowserEvaluator 实例启用自愈能力。

    用法 (在 test_service.py 或任何创建 BrowserEvaluator 的地方):
        from src.self_healing import apply_self_healing
        evaluator = BrowserEvaluator(headless=True)
        apply_self_healing(evaluator)  # ← 仅此一行

    原理: monkey-patch _find_and_click, 在原始方法失败后自动进入四层回退。
    不修改 browser_evaluator.py 源码。
    """
    original_find_and_click = evaluator._find_and_click

    def healed_find_and_click(texts: list[str]) -> tuple[bool, str]:
        # L0: 先尝试原始方法 (保持最快路径)
        ok, text = original_find_and_click(texts)
        if ok:
            return ok, text

        # 原始方法失败 → 对每个候选文本依次尝试自愈
        for target in texts:
            # 预采集 DOM snapshot (所有 L1/L2/L3 复用)
            try:
                dom = evaluator._dump_dom_state()
            except Exception:
                dom = None

            healed, found, event = heal_click(
                evaluator.page, target, dom_snapshot=dom, api_key=api_key
            )
            if healed:
                evaluator._log(
                    f"🩹 自愈: '{target[:40]}' → '{found[:40]}' "
                    f"({event.strategy}, confidence={event.confidence:.0%})",
                    "ok",
                )
                return True, found

        # 全部失败 → 记录详细诊断信息
        try:
            dom = evaluator._dump_dom_state()
            available = [b["text"][:60] for b in dom.get("buttons", [])[:10]]
            evaluator._log(
                f"自愈失败: {texts[:3]} — 页面可用按钮: {available}", "error"
            )
        except Exception:
            evaluator._log(f"自愈失败: {texts[:3]}", "error")

        return False, ""

    evaluator._find_and_click = healed_find_and_click
    return evaluator


# ═══════════════════════════════════════════════════════════════════
# 高级 API: 通用元素自愈 (用于非按钮元素)
# ═══════════════════════════════════════════════════════════════════

def heal_locator(
    page,
    original_selector: str,
    dom_snapshot: dict | None = None,
    api_key: str = "",
) -> tuple[bool, str]:
    """
    通用 CSS 选择器级别的自愈。

    适用于非按钮场景: input, textarea, div 等。

    :param page: Playwright page
    :param original_selector: 原始 CSS 选择器 (如 "[class*=step-title]")
    :param dom_snapshot: DOM snapshot
    :param api_key: AI API key
    :return: (success, new_selector)
    """
    # 先验证原始选择器是否已经可用
    try:
        el = page.locator(original_selector).first
        if el.is_visible(timeout=2000):
            return True, original_selector
    except Exception:
        pass

    # L1: 尝试语义等价的 CSS 变体
    # "button:has-text('X')" → 尝试不同引号、大小写
    variants = _generate_selector_variants(original_selector)
    for variant in variants:
        try:
            el = page.locator(variant).first
            if el.is_visible(timeout=1500):
                return True, variant
        except Exception:
            continue

    # L2: 回退到 JS 通用查找 (最后手段)
    try:
        found = page.evaluate(f"""
            (() => {{
                const sel = {json.dumps(original_selector)};
                // 尝试部分属性匹配
                const parts = sel.match(/[a-zA-Z*-]+/g) || [];
                for (const part of parts) {{
                    if (part.length < 3) continue;
                    const els = document.querySelectorAll(`[${{part}}]`);
                    if (els.length > 0) return `[${{part}}]`;
                }}
                return null;
            }})()
        """)
        if found:
            return True, found
    except Exception:
        pass

    return False, original_selector


def _generate_selector_variants(selector: str) -> list[str]:
    """生成语义等价的 CSS 选择器变体"""
    variants = []

    # button:has-text('X') → button:has-text("X")
    if ":has-text(" in selector:
        m = re.search(r":has-text\('([^']*)'\)", selector)
        if m:
            variants.append(selector.replace(f"'{m.group(1)}'", f'"{m.group(1)}"'))
            # 尝试部分文本
            text = m.group(1)
            if len(text) > 3:
                variants.append(selector.replace(f"'{text}'", f"'{text[:len(text)//2]}'"))

    # [class*=xxx] → [class~=xxx], .xxx
    class_attr = re.search(r"\[class\*=([^\]]+)\]", selector)
    if class_attr:
        cls = class_attr.group(1).strip('"').strip("'")
        variants.append(selector.replace(f"[class*={class_attr.group(1)}]", f".{cls}"))
        variants.append(selector.replace(f"[class*={class_attr.group(1)}]", f"[class~={class_attr.group(1)}]"))

    return variants


# ═══════════════════════════════════════════════════════════════════
# Health API 集成: 暴露给 Agent A 的 dashboard_service.py
# ═══════════════════════════════════════════════════════════════════

def get_health_summary() -> dict:
    """
    返回自愈系统的健康摘要 → 供 dashboard_service._quick_probe 调用。
    格式与现有 health API 对齐。
    """
    summary = _healing_log.summary()
    return {
        "component": "self_healing",
        "status": "healthy" if summary["success_rate"] >= 0.5 else "degraded",
        "total_heals": summary["total"],
        "success_rate": summary["success_rate"],
        "strategies_used": summary["by_strategy"],
        "recent_failures": summary["top_failures"][-5:],
        "latest_healed": summary.get("latest_healed", ""),
    }
