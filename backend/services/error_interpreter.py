"""错误转译层 — 评测卡点报错 → LLM → 自然语言求助卡 (六要素)

设计原则 (2026-08-19 迭代):
  1. 自动化优先: 转译失败/无 key 时用固定模板, 卡点照常询问
  2. 非技术用户视角: 不暴露堆栈/选择器/供应商名
  3. 风险分级超时: low=120s / mid=300s / high=600s, 超时走默认动作
  4. 六要素求助卡: decision / reason / evidence / consequence / expiry / recovery

用法:
    from backend.services.error_interpreter import interpret
    card = interpret(kind="login_failed", error="401 Unauthorized",
                     context={"url": "...", "attempt": 2})
    # card: {"question", "options", "default", "timeout_s", "risk",
    #        "reason", "recovery", "evidence"}  — 直接传给 TestService.ask_user(card=...)
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

# 风险分级 → 超时秒数
RISK_TIMEOUTS = {"low": 120, "mid": 300, "high": 600}

# 模板映射: kind → 求助卡 (无 LLM 时兜底)
_TEMPLATES = {
    "login_failed": {
        "risk": "high",
        "question": "登录失败 — 平台没让我用当前账号密码进去。",
        "options": ["重试登录", "提供新凭证", "终止测评"],
        "default": "终止测评",
        "reason": "平台拒绝了当前登录凭证，或登录页面结构发生了变化。",
        "recovery": "提供新的账号密码（格式：账号 xxx 密码 xxx），或告诉我先跳过登录。",
    },
    "navigation_failed": {
        "risk": "mid",
        "question": "找不到页面上要点击的入口。",
        "options": ["跳过这个环节继续", "我来描述入口位置", "终止测评"],
        "default": "跳过这个环节继续",
        "reason": "自动评测没能在页面上找到预期的按钮或链接。",
        "recovery": "描述一下入口长什么样（文字/位置），我会换一种方式再找。",
    },
    "schema_missing": {
        "risk": "high",
        "question": "还没有可用的平台画像，暂时无法生成评测计划。",
        "options": ["终止", "先去探索平台", "继续(仅文本验证)"],
        "default": "终止",
        "reason": "系统缺少平台结构数据（schema），没有评测依据。",
        "recovery": "先去「Explorer」页面完成一次平台探索，系统会自动生成画像。",
    },
    "day_error": {
        "risk": "mid",
        "question": "当前学习环节的测评卡住了。",
        "options": ["跳过这个环节继续", "终止测评"],
        "default": "跳过这个环节继续",
        "reason": "自动评测在这个环节遇到了预期外的情况（页面元素变化或流程异常）。",
        "recovery": "可以先跳过它，其余环节照常测评；结束后可在报告中查看详情。",
    },
    "quiz_blocked": {
        "risk": "mid",
        "question": "测验环节卡住了 — 检测到题目但没有自动完成。",
        "options": ["跳过测验继续", "终止测评"],
        "default": "跳过测验继续",
        "reason": "自动答题没能在页面上完成作答。",
        "recovery": "可以跳过测验（结果会标注为未完成），不影响其他环节的测评。",
    },
    "agent_no_response": {
        "risk": "mid",
        "question": "AI 助教没有回应 — 我在页面上找不到可以提问的输入框。",
        "options": ["跳过此环节继续", "我来描述输入框位置", "终止测评"],
        "default": "跳过此环节继续",
        "reason": "自动评测没能在页面上找到 AI 对话的输入框。",
        "recovery": "描述输入框大概在页面什么位置，我会换个方式再试。",
    },
    "eval_exception": {
        "risk": "high",
        "question": "测评遇到了意外错误，流程中断。",
        "options": ["保存结果并终止", "重试一次"],
        "default": "保存结果并终止",
        "reason": "系统执行测评时遇到了未预料的异常（已自动保存已完成的结果）。",
        "recovery": "可以选择重试；如果反复失败，报告页面会给出建议。",
    },
}

_LLM_PROMPT = (
    "你是测评系统的故障播报员。把技术错误转译成非技术用户能懂的中文求助卡。\n"
    "要求: 不出现堆栈/选择器/供应商名; 用「平台/页面/系统」代替技术名词。\n"
    "输出严格 JSON: {\"question\": \"一句话说明卡在哪\", "
    "\"options\": [\"选项1\",\"选项2\",\"选项3\"], \"default\": \"默认选项\", "
    "\"reason\": \"为什么会这样(1句)\", \"recovery\": \"用户怎么做能解决(1句)\", "
    "\"risk\": \"low|mid|high\"}\n"
    "默认动作规则: 高风险(登录/数据丢失)默认终止; 低中风险默认跳过继续。"
)


def interpret(kind: str, error: str = "", context: dict | None = None) -> dict:
    """把卡点错误转译为自然语言求助卡。永不抛异常 — 最坏返回通用模板。"""
    tpl = _TEMPLATES.get(kind, _TEMPLATES["eval_exception"])
    card = dict(tpl)
    card["kind"] = kind
    card["timeout_s"] = RISK_TIMEOUTS.get(card["risk"], 300)
    card["evidence"] = _clean_evidence(error, context)

    # LLM 增强 (可选): 成功则用 LLM 文案替换模板文案
    llm = _call_llm(kind, error, context)
    if llm:
        for key in ("question", "options", "default", "reason", "recovery", "risk"):
            if llm.get(key):
                card[key] = llm[key]
        card["timeout_s"] = RISK_TIMEOUTS.get(card.get("risk"), 300)
    return card


def _clean_evidence(error: str, context: dict | None) -> str:
    """证据摘要 — 截断 + 去敏感信息, 前端展示用"""
    parts = []
    if error:
        e = re.sub(r"(password|passwd|pwd)\s*[:=]\s*\S+", "密码: ******", error, flags=re.I)
        parts.append(str(e)[:200])
    if context:
        parts.append(str({k: v for k, v in list(context.items())[:6]})[:200])
    return " | ".join(parts)[:400]


def _call_llm(kind: str, error: str, context: dict | None) -> Optional[dict]:
    """调 LLM 转译 (失败静默返回 None → 模板兜底)"""
    try:
        from src.platform_probe.api_keys import get_api_keys
        provider = get_api_keys().get_text_llm()
        if not provider:
            return None
        payload = json.dumps({
            "model": provider.model_id,
            "messages": [
                {"role": "system", "content": _LLM_PROMPT},
                {"role": "user", "content": json.dumps(
                    {"kind": kind, "error": str(error)[:500],
                     "context": {k: str(v)[:200] for k, v in (context or {}).items()}},
                    ensure_ascii=False)},
            ],
            "temperature": 0.1,
            "max_tokens": 400,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{provider.base_url.rstrip('/')}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {provider.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            return None
        data = json.loads(m.group(0))
        # options 必须是字符串列表
        if isinstance(data.get("options"), list):
            data["options"] = [str(o) for o in data["options"]][:5]
        if data.get("risk") not in RISK_TIMEOUTS:
            data.pop("risk", None)
        return data
    except Exception as e:
        logger.warning("ErrorInterpreter LLM call failed: %s", e)
        return None
