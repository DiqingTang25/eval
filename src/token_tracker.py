"""
Token 成本估算工具

支持:
- DeepSeek API token 估算 (按字符数近似: 中文约1.5 char/token, 英文约4 char/token)
- 基于 DeepSeek 官方定价: input $0.14/1M tokens, output $0.28/1M tokens
- 如果 API 返回了真实 usage.token_count, 优先使用真实值
"""

import json
import re
from datetime import datetime
from pathlib import Path

# ── DeepSeek 定价 (USD per 1M tokens) ──
# https://api-docs.deepseek.com/quick_start/pricing
DEEPSEEK_PRICING = {
    "deepseek-chat":    {"input": 0.14, "output": 0.28},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
}

# 默认使用 deepseek-chat 价格
DEFAULT_MODEL = "deepseek-chat"


def estimate_tokens(text: str, lang: str = "auto") -> int:
    """
    估算 token 数量 (无 API 调用时使用)

    规则:
    - 中文字符: ~1.5 char/token
    - 英文单词: ~1.3 word/token
    - 混合文本: 按字符比例折中
    """
    if not text:
        return 0

    # 统计中文字符占比
    chinese_chars = len(re.findall(r'[一-鿿　-〿＀-￯]', text))
    total_chars = len(text)

    if total_chars == 0:
        return 0

    chinese_ratio = chinese_chars / total_chars

    if lang == "zh" or chinese_ratio > 0.3:
        # 中文为主: ~1.5 char/token
        return max(1, int(total_chars / 1.5))
    else:
        # 英文为主: ~4 char/token
        return max(1, int(total_chars / 4.0))


def estimate_cost(
    prompt_text: str = "",
    completion_text: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    估算单次 LLM 调用成本

    优先使用传入的真实 token 数, 否则按字符估算

    Returns:
        {
            "prompt_tokens": int,
            "completion_tokens": int,
            "total_tokens": int,
            "cost_usd": float,
            "model": str,
            "estimated": bool,  # True=估算值, False=真实值
        }
    """
    pricing = DEEPSEEK_PRICING.get(model, DEEPSEEK_PRICING[DEFAULT_MODEL])
    estimated = False

    if prompt_tokens == 0 and prompt_text:
        prompt_tokens = estimate_tokens(prompt_text, "zh")
        estimated = True

    if completion_tokens == 0 and completion_text:
        completion_tokens = estimate_tokens(completion_text, "zh")
        estimated = True

    total_tokens = prompt_tokens + completion_tokens
    cost = (prompt_tokens / 1_000_000) * pricing["input"] + \
           (completion_tokens / 1_000_000) * pricing["output"]

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": round(cost, 8),
        "model": model,
        "estimated": estimated,
    }


def track_call(
    caller: str,
    prompt_text: str = "",
    completion_text: str = "",
    model: str = DEFAULT_MODEL,
) -> dict:
    """统一 LLM 调用记账 — 追加到 data/token_usage.json (失败静默, 绝不阻塞主流程)

    各 LLM 调用点 (explorer_chat / error_interpreter / executor 等) 调用本函数,
    成本数据在 Dashboard 可展示 (见后端 metrics API 扩展)。
    """
    try:
        est = estimate_cost(prompt_text=prompt_text, completion_text=completion_text,
                            model=model)
        rec = {
            "ts": datetime.now().isoformat(),
            "caller": (caller or "")[:40],
            "model": model,
            **est,
        }
        p = Path(__file__).resolve().parent.parent / "data" / "token_usage.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        entries = []
        if p.exists():
            try:
                entries = json.loads(p.read_text(encoding="utf-8") or "[]")
                if not isinstance(entries, list):
                    entries = []
            except Exception:
                entries = []
        entries.append(rec)
        entries = entries[-500:]  # 保留最近 500 条
        p.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        return est
    except Exception:
        return {}


def estimate_conversation_cost(
    turns: list[dict],
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    估算一轮对话的总成本

    Args:
        turns: [{"question": str, "response": str}, ...]

    Returns:
        {total_prompt_tokens, total_completion_tokens, total_tokens, total_cost_usd}
    """
    total_prompt = 0
    total_completion = 0

    for t in turns:
        total_prompt += estimate_tokens(t.get("question", ""), "zh")
        total_completion += estimate_tokens(t.get("response", ""), "zh")

    pricing = DEEPSEEK_PRICING.get(model, DEEPSEEK_PRICING[DEFAULT_MODEL])
    cost = (total_prompt / 1_000_000) * pricing["input"] + \
           (total_completion / 1_000_000) * pricing["output"]

    return {
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total_prompt + total_completion,
        "total_cost_usd": round(cost, 8),
        "model": model,
        "estimated": True,
    }
