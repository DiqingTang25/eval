"""
LLM/VLM API Key 统一管理 — 从环境变量自动检测所有已配置的Provider

XJTLU AI Gateway 统一端点: https://aiagent.xjtlu.edu.cn/api/aigw/v1
  所有模型走 OpenAI-compatible /chat/completions, 用 "model" 字段传 model_id

支持的Provider:
  文本LLM:  DeepSeek, XJTLU GLM-5.2, XJTLU Doubao
  视觉VLM: Qwen3-VL-8B (专用), Doubao Seed 2.1 (备用)
"""

import os
from dataclasses import dataclass, field

# 确保 .env 已加载 (无论从哪个入口运行 explorer)
# 显式指向项目根目录 — systemd 服务 WorkingDirectory=/ 时按 cwd 找会失败
try:
    from pathlib import Path
    from dotenv import load_dotenv
    _ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
    if _ENV_FILE.exists():
        load_dotenv(_ENV_FILE)
except Exception:
    pass


@dataclass
class LLMProvider:
    """单个Provider的API配置"""
    name: str
    provider: str                # deepseek | xjtlu_glm | xjtlu_doubao | xjtlu_qwen3vl
    api_key: str
    base_url: str
    model_id: str = ""           # XJTLU Gateway 的 model ID (也是 "model" 字段的值)
    models: list = field(default_factory=list)
    has_vision: bool = False


class APIKeyRegistry:
    """从环境变量自动扫描所有LLM/VLM Provider"""

    def __init__(self):
        self.providers: list[LLMProvider] = []
        self._scan()

    def _scan(self):
        xjtl_base = os.getenv("XJTLU_BASE_URL", "").strip()

        # ── DeepSeek (OpenAI-compatible, 文本) ──
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if key:
            ds_url = os.getenv("OPENAI_BASE_URL", "").strip()
            self.providers.append(LLMProvider(
                name="DeepSeek", provider="deepseek",
                api_key=key,
                base_url=ds_url or "https://api.deepseek.com/v1",
                models=["deepseek-chat", "deepseek-reasoner"],
                model_id="deepseek-chat",
            ))

        # ── XJTLU GLM-5.2 (文本) ──
        key = os.getenv("XJTLU_JUDGE_GLM52_API_KEY", "").strip()
        model = os.getenv("XJTLU_JUDGE_GLM52_MODEL_ID", "").strip()
        if key and xjtl_base:
            self.providers.append(LLMProvider(
                name="XJTLU GLM-5.2", provider="xjtlu_glm",
                api_key=key, base_url=xjtl_base,
                models=[model] if model else ["glm-5.2"],
                model_id=model or "glm-5.2",
            ))

        # ── XJTLU Doubao Seed 2.1 (文本+视觉) ──
        key = os.getenv("XJTLU_JUDGE_DOUBAO_API_KEY", "").strip()
        model = os.getenv("XJTLU_JUDGE_DOUBAO_MODEL_ID", "").strip()
        if key and xjtl_base:
            self.providers.append(LLMProvider(
                name="XJTLU Doubao Seed 2.1", provider="xjtlu_doubao",
                api_key=key, base_url=xjtl_base,
                models=[model] if model else ["doubao-seed-2.1"],
                model_id=model or "doubao-seed-2.1",
                has_vision=True,  # Doubao支持多模态
            ))

        # ── XJTLU Qwen3-VL-8B (专用视觉模型) ──
        key = os.getenv("XJTLU_QWEN3VL_API_KEY", "").strip()
        model = os.getenv("XJTLU_QWEN3VL_MODEL_ID", "").strip()
        if key and xjtl_base:
            self.providers.append(LLMProvider(
                name="Qwen3-VL-8B-Instruct", provider="xjtlu_qwen3vl",
                api_key=key, base_url=xjtl_base,
                models=[model] if model else ["qwen3-vl-8b"],
                model_id=model or "d95koqj7u3anoctav5sg",
                has_vision=True,
            ))

        # ── XJTLU GPT-4o (最强多模态, 视觉+文本) ──
        key = os.getenv("XJTLU_GPT4O_API_KEY", "").strip()
        model = os.getenv("XJTLU_GPT4O_MODEL_ID", "").strip()
        if key and xjtl_base:
            self.providers.append(LLMProvider(
                name="GPT-4o", provider="xjtlu_gpt4o",
                api_key=key, base_url=xjtl_base,
                models=[model] if model else ["gpt-4o"],
                model_id=model or "d08pg3tdv7249m3l5dn0",
                has_vision=True,  # 🔥 最强视觉+推理
            ))

        # ── Anthropic Claude (文本+视觉, 需单独配置) ──
        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if key:
            self.providers.append(LLMProvider(
                name="Anthropic Claude", provider="anthropic",
                api_key=key, base_url="https://api.anthropic.com",
                models=["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5"],
                has_vision=True,
            ))

        # ── SiliconFlow (Embedding) ──
        key = os.getenv("SILICONFLOW_API_KEY", "").strip()
        if key:
            self.providers.append(LLMProvider(
                name="SiliconFlow", provider="siliconflow",
                api_key=key, base_url="https://api.siliconflow.cn/v1",
                models=["bge-m3"],
            ))

    # ═══════════════════════════════════════
    # 查询
    # ═══════════════════════════════════════

    def get(self, provider: str) -> LLMProvider | None:
        for p in self.providers:
            if p.provider == provider:
                return p
        return None

    def get_text_llm(self) -> LLMProvider | None:
        """最优文本LLM: DeepSeek > GLM-5.2 > Doubao"""
        for p in self.providers:
            if p.provider == "deepseek":
                return p
        for p in self.providers:
            if p.provider == "xjtlu_glm":
                return p
        for p in self.providers:
            if not p.has_vision:  # 纯文本provider
                return p
        return self.providers[0] if self.providers else None

    def get_vision_llm(self) -> LLMProvider | None:
        """最优视觉VLM: GPT-4o > Qwen3-VL > Doubao"""
        priority = ["xjtlu_gpt4o", "xjtlu_qwen3vl", "xjtlu_doubao"]
        for provider in priority:
            for p in self.providers:
                if p.provider == provider and p.has_vision:
                    return p
        # 任何其他支持视觉的
        for p in self.providers:
            if p.has_vision:
                return p
        return None

    @property
    def text_llm_count(self) -> int:
        return sum(1 for p in self.providers if not p.has_vision)

    @property
    def vision_llm_count(self) -> int:
        return sum(1 for p in self.providers if p.has_vision)


_registry: APIKeyRegistry | None = None


def get_api_keys() -> APIKeyRegistry:
    global _registry
    if _registry is None:
        _registry = APIKeyRegistry()
    return _registry
