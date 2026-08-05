"""Settings API — 系统配置管理 (LLM Keys, 平台URL, 全局参数)"""

import os
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

PROJECT_ROOT = Path(__file__).parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"


# ── 已知的 LLM Provider 及其环境变量 ──
KNOWN_PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "env_key": "OPENAI_API_KEY",
        "env_base_url": "",
        "default_base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "openai": {
        "name": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "env_base_url": "",
        "default_base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini"],
    },
    "siliconflow": {
        "name": "硅基流动 (SiliconFlow)",
        "env_key": "SILICONFLOW_API_KEY",
        "env_base_url": "",
        "default_base_url": "https://api.siliconflow.cn/v1",
        "models": ["bge-m3"],
    },
    "xjtlu_glm": {
        "name": "XJTLU GLM-5.2",
        "env_key": "XJTLU_GLM_JUDGE_KEY",
        "env_base_url": "XJTLU_BASE_URL",
        "default_base_url": "",
        "models": ["glm-5.2"],
    },
    "xjtlu_doubao": {
        "name": "XJTLU Doubao",
        "env_key": "XJTLU_DOUBAO_JUDGE_KEY",
        "env_base_url": "XJTLU_BASE_URL",
        "default_base_url": "",
        "models": ["doubao-seed-2.1"],
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "env_key": "ANTHROPIC_API_KEY",
        "env_base_url": "",
        "default_base_url": "https://api.anthropic.com",
        "models": ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5"],
    },
}


class LLMKeyUpdate(BaseModel):
    provider: str
    api_key: str
    base_url: Optional[str] = ""


class PlatformConfig(BaseModel):
    default_url: str = "http://124.174.108.70"
    default_username: str = "student001"
    default_password: str = "123456"


# ═══════════════════════════════════════════════════════════
# LLM Keys
# ═══════════════════════════════════════════════════════════

@router.get("/llm-keys")
async def get_llm_keys() -> dict:
    """
    获取所有LLM Provider的配置状态 (密钥已脱敏)
    """
    providers = {}
    for key, info in KNOWN_PROVIDERS.items():
        env_value = os.getenv(info["env_key"], "")
        base_url = os.getenv(info["env_base_url"], "") or info.get("default_base_url", "")

        providers[key] = {
            "name": info["name"],
            "configured": bool(env_value),
            "key_preview": _mask_key(env_value) if env_value else "",
            "base_url": base_url,
            "models": info["models"],
            "env_key_name": info["env_key"],
        }

    return {
        "providers": providers,
        "total_configured": sum(1 for p in providers.values() if p["configured"]),
        "total_providers": len(providers),
    }


@router.put("/llm-keys")
async def update_llm_key(body: LLMKeyUpdate) -> dict:
    """
    更新 LLM API Key (写入 .env 文件)

    支持更新已有provider或添加新provider。
    密钥在 .env 中存储, 下次服务重启后生效。
    """
    if body.provider not in KNOWN_PROVIDERS:
        # 允许自定义 provider
        env_key_name = f"CUSTOM_{body.provider.upper()}_API_KEY"
    else:
        env_key_name = KNOWN_PROVIDERS[body.provider]["env_key"]

    # 验证 key 格式 (基本检查)
    if not body.api_key or len(body.api_key) < 10:
        raise HTTPException(status_code=400, detail="API Key 格式无效")

    # 读取当前 .env
    if ENV_FILE.exists():
        content = ENV_FILE.read_text(encoding="utf-8")
    else:
        content = ""

    # 更新或追加
    escaped_key = body.api_key.replace("'", "'\\''")
    new_line = f'{env_key_name}={escaped_key}'

    if env_key_name in content:
        # 替换已存在行
        content = re.sub(
            rf'^{env_key_name}=.*$',
            new_line,
            content,
            flags=re.MULTILINE,
        )
    else:
        # 追加
        if content and not content.endswith("\n"):
            content += "\n"
        content += f"\n{new_line}\n"

    # 同时更新 base_url (如果有)
    if body.base_url and body.provider in KNOWN_PROVIDERS:
        base_url_env = KNOWN_PROVIDERS[body.provider].get("env_base_url", "")
        if base_url_env and body.base_url:
            base_line = f'{base_url_env}={body.base_url}'
            if base_url_env in content:
                content = re.sub(
                    rf'^{base_url_env}=.*$',
                    base_line,
                    content,
                    flags=re.MULTILINE,
                )
            else:
                content += f"\n{base_line}\n"

    # 写回 .env
    ENV_FILE.write_text(content, encoding="utf-8")

    # 同时更新当前进程环境变量 (即时生效)
    os.environ[env_key_name] = body.api_key
    if body.base_url and body.provider in KNOWN_PROVIDERS:
        base_env = KNOWN_PROVIDERS[body.provider].get("env_base_url", "")
        if base_env:
            os.environ[base_env] = body.base_url

    return {
        "status": "ok",
        "provider": body.provider,
        "env_key": env_key_name,
        "key_preview": _mask_key(body.api_key),
        "message": f"{KNOWN_PROVIDERS.get(body.provider, {}).get('name', body.provider)} API Key 已更新 (重启服务后对所有worker生效)",
    }


@router.delete("/llm-keys/{provider}")
async def delete_llm_key(provider: str) -> dict:
    """删除 LLM API Key 配置"""
    if provider not in KNOWN_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider 不存在")

    env_key_name = KNOWN_PROVIDERS[provider]["env_key"]

    if ENV_FILE.exists():
        content = ENV_FILE.read_text(encoding="utf-8")
        content = re.sub(
            rf'^{env_key_name}=.*\n?',
            '',
            content,
            flags=re.MULTILINE,
        )
        ENV_FILE.write_text(content, encoding="utf-8")

    # 清除当前进程环境变量
    if env_key_name in os.environ:
        del os.environ[env_key_name]

    return {"status": "ok", "message": f"{provider} API Key 已删除"}


# ═══════════════════════════════════════════════════════════
# 平台默认配置
# ═══════════════════════════════════════════════════════════

@router.get("/platform-defaults")
async def get_platform_defaults() -> dict:
    """获取默认平台配置"""
    return {
        "default_url": os.getenv("PLATFORM_URL", "http://124.174.108.70"),
        "default_username": os.getenv("PLATFORM_USERNAME", "student001"),
        "default_password": os.getenv("PLATFORM_PASSWORD", "123456"),
        "admin_username": os.getenv("ADMIN_USERNAME", "admin"),
        "admin_password": os.getenv("ADMIN_PASSWORD", "admin123"),
        "db_type": os.getenv("DB_TYPE", "sqlite"),
    }


# ═══════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════

def _mask_key(key: str) -> str:
    """脱敏显示 API Key"""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]
