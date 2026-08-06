"""
统一 LLM 客户端 — Agent C

解决多模块各自查找 API Key 的问题。
优先级: OPENAI_API_KEY > DEEPSEEK_API_KEY > XJTLU_VLM_API_KEY > GPT_API_KEY

用法:
    from src.llm_client import get_llm_client
    client, model_name = get_llm_client()
    resp = client.chat.completions.create(model=model_name, messages=[...])
"""
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Optional

# 自动加载 .env (本地开发用, 云端 systemd env 已设)
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except Exception:
    pass

logger = logging.getLogger(__name__)

# ── 模型配置优先级 ──
# 按优先级排列: 排前面的先匹配
# require_vision=True 时跳过 supports_vision=False 的配置
LLM_CONFIGS = [
    {
        "name": "xjtl-deepseek-v4",
        "env_key": "XJTLU_DEEPSEEK_API_KEY",
        "base_url_env": "XJTLU_DEEPSEEK_BASE_URL",
        "default_base_url": "https://aiagent.xjtlu.edu.cn/api/aigw/v1",
        "default_model": "d8j2d4r9dhtg6s3fevfg",   # → deepseek-v4-pro-260425
        "supports_vision": False,                     # DeepSeek 不支持视觉
        "supports_json": True,
        "role": "primary_text",                       # 主力文本评判
    },
    {
        "name": "xjtl-gpt-4o",
        "env_key": "XJTLU_VLM_API_KEY",
        "base_url_env": "XJTLU_VLM_BASE_URL",
        "default_base_url": "https://aiagent.xjtlu.edu.cn/api/aigw/v1",
        "default_model": "d08pg3tdv7249m3l5dn0",     # → gpt-4o-2024-11-20
        "supports_vision": True,                      # GPT-4o 支持视觉
        "supports_json": True,
        "role": "primary_vision",                     # 主力视觉判断
    },
    {
        "name": "openai",
        "env_key": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_BASE_URL",
        "default_base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "supports_vision": True,
        "supports_json": True,
    },
    {
        "name": "deepseek",
        "env_key": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "default_base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "supports_vision": False,
        "supports_json": True,
    },
    {
        "name": "gpt",
        "env_key": "GPT_API_KEY",
        "base_url_env": "GPT_BASE_URL",
        "default_base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "supports_vision": True,
        "supports_json": True,
    },
]

# ── 缓存 ──
_cached_client = None
_cached_config = None


def get_llm_client(require_vision: bool = False):
    """
    获取可用的 LLM 客户端和模型名。

    :param require_vision: 是否必须支持 Vision (多模态)
    :return: (OpenAI client, model_name, config_dict) 或 (None, None, None)
    """
    global _cached_client, _cached_config

    if _cached_client is not None:
        if not require_vision or _cached_config.get("supports_vision"):
            return _cached_client, _cached_config["default_model"], _cached_config

    for cfg in LLM_CONFIGS:
        api_key = os.getenv(cfg["env_key"], "").strip()
        if not api_key:
            continue
        if require_vision and not cfg["supports_vision"]:
            continue

        base_url = os.getenv(cfg["base_url_env"], "").strip() or cfg["default_base_url"]

        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=60)
            _cached_client = client
            _cached_config = cfg
            logger.info(f"LLM client: {cfg['name']} ({cfg['default_model']}) @ {base_url}")
            return client, cfg["default_model"], cfg
        except Exception as e:
            logger.warning(f"Failed to init {cfg['name']}: {e}")
            continue

    return None, None, None


def get_api_key() -> str:
    """获取当前可用的 API Key (纯字符串, 给 Evaluator 等需要直接传 key 的模块)"""
    for cfg in LLM_CONFIGS:
        key = os.getenv(cfg["env_key"], "").strip()
        if key:
            return key
    return ""


def get_base_url() -> str:
    """获取当前可用的 base URL"""
    for cfg in LLM_CONFIGS:
        key = os.getenv(cfg["env_key"], "").strip()
        if key:
            return os.getenv(cfg["base_url_env"], "").strip() or cfg["default_base_url"]
    return "https://api.openai.com/v1"


def is_available(require_vision: bool = False) -> bool:
    """检查是否有可用的 LLM"""
    client, _, _ = get_llm_client(require_vision=require_vision)
    return client is not None


def bridge_env_vars():
    """
    桥接环境变量 → 让现有 Evaluator 的多 Judge 系统找到所有 Key。

    优先级: .env 已设的值 > XJTLU 专用 Key > 回退

    Evaluator._init_judge_clients() 查找:
      - OPENAI_API_KEY → Judge 1: DeepSeek
      - CLAUDE_API_KEY → Judge 2: Claude (通常未设)
      - GPT_API_KEY → Judge 3: GPT-4o
      - XJTLU_JUDGE_GLM52_* → Judge 4: GLM-5.2
      - XJTLU_JUDGE_DOUBAO_* → Judge 5: Doubao

    确保 GPT_MODEL / OPENAI_MODEL 匹配 XJTLU 网关格式。
    """
    # ── .env OPENAI_API_KEY=sk-4fb53cb... (官方DeepSeek, 暂时弃用) → 替换为 XJTLU DeepSeek-V4 ──
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if "sk-4fb53cb" in openai_key:
        ds4_key = os.getenv("XJTLU_DEEPSEEK_API_KEY", "").strip()
        if ds4_key:
            os.environ["OPENAI_API_KEY"] = ds4_key
            os.environ["OPENAI_BASE_URL"] = os.getenv("XJTLU_DEEPSEEK_BASE_URL",
                os.getenv("XJTLU_BASE_URL", "https://aiagent.xjtlu.edu.cn/api/aigw/v1"))
            os.environ["OPENAI_MODEL"] = "d8j2d4r9dhtg6s3fevfg"
    elif not openai_key:
        for env_name in ["XJTLU_DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY"]:
            key = os.getenv(env_name, "").strip()
            if key:
                os.environ["OPENAI_API_KEY"] = key
                if env_name.startswith("XJTLU"):
                    os.environ["OPENAI_BASE_URL"] = os.getenv("XJTLU_DEEPSEEK_BASE_URL",
                        os.getenv("XJTLU_BASE_URL", "https://aiagent.xjtlu.edu.cn/api/aigw/v1"))
                    os.environ["OPENAI_MODEL"] = "d8j2d4r9dhtg6s3fevfg"
                break

    # GPT-4o: .env 用 XJTLU_GPT4O_API_KEY, 桥接到 GPT_API_KEY
    if not os.getenv("GPT_API_KEY"):
        for env_name in ["XJTLU_GPT4O_API_KEY", "XJTLU_VLM_API_KEY"]:
            key = os.getenv(env_name, "").strip()
            if key:
                os.environ["GPT_API_KEY"] = key
                os.environ["GPT_BASE_URL"] = os.getenv("XJTLU_BASE_URL",
                    "https://aiagent.xjtlu.edu.cn/api/aigw/v1")
                os.environ["GPT_MODEL"] = os.getenv("XJTLU_GPT4O_MODEL_ID", "d08pg3tdv7249m3l5dn0")
                break


def get_judge_clients() -> list[dict]:
    """
    返回所有可用 Judge 的 OpenAI 客户端列表 (给 Verifier 做多 Judge 投票)。

    :return: [{"name": "deepseek-v4", "client": OpenAI(...), "model": "...", ...}, ...]
    """
    bridge_env_vars()  # 确保 Evaluator 能感知

    clients = []
    for cfg in LLM_CONFIGS:
        key = os.getenv(cfg["env_key"], "").strip()
        if not key:
            continue
        base_url = os.getenv(cfg["base_url_env"], "").strip() or cfg["default_base_url"]
        try:
            from openai import OpenAI
            client = OpenAI(api_key=key, base_url=base_url, timeout=60)
            clients.append({
                "name": cfg["name"],
                "client": client,
                "model": cfg["default_model"],
                "temperature": 0.1,
                "supports_vision": cfg.get("supports_vision", False),
                "supports_json_format": cfg.get("supports_json", True),
            })
        except Exception:
            continue

    return clients


def reset_cache():
    """清除缓存 (环境变量变更后调用)"""
    global _cached_client, _cached_config
    _cached_client = None
    _cached_config = None
