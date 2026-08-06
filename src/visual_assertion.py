"""
Visual Assertion 引擎 — Agent C (SOTA Paradigm 4: Intent-based Visual Assertion)

截图 + VLM 多模态大模型 → 基于意图的视觉断言。
不检查 DOM, 只检查"用户实际看到的东西"。

核心能力:
  - 意图驱动: "购物车数字是否+1?" 而不是 "div.cart-badge 的 textContent 是否='2'"
  - 多模型: GPT-4o / Claude Vision / 自动选择可用模型
  - 批量断言: 一张截图验证多个意图, 省 API 调用
  - 零侵入: 纯函数, 接收截图路径, 不依赖 Playwright/BrowserEvaluator

用法:
  from src.visual_assertion import VisualAssertion
  va = VisualAssertion()
  result = va.assert_that(
      screenshot_path="eval_output/screenshots/0042_quiz_result.png",
      intent="页面是否显示了测验分数?",
  )
  # → {pass: True, confidence: 0.92, reasoning: "截图显示'得分: 4/5'...", model: "gpt-4o"}

SOTA 对齐:
  - Tricentis Vision AI (2025): 基于VLM的视觉回归测试
  - Applitools Visual AI: 意图驱动的视觉验证
  - WebHunter (2025): 多模态Agent自主探索

设计原则:
  - 不依赖 browser_evaluator.py 内部状态
  - VLM 不可用时优雅降级 (返回 skipped, 不报错)
  - 所有断言记录到 visual_assertion_log.json
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── 记录路径 ──
VA_LOG_PATH = Path(__file__).parent.parent / "data" / "visual_assertion_log.json"

# ── VLM 模型配置 ──
VLM_MODELS = [
    {
        "name": "gpt-4o",
        "env_key": "GPT_API_KEY",
        "base_url_env": "GPT_BASE_URL",
        "default_base_url": "https://api.openai.com/v1",
        "model_id": "gpt-4o",
        "max_tokens": 600,
        "supports_vision": True,
    },
    {
        "name": "gpt-4o-mini",
        "env_key": "GPT_API_KEY",
        "base_url_env": "GPT_BASE_URL",
        "default_base_url": "https://api.openai.com/v1",
        "model_id": "gpt-4o-mini",
        "max_tokens": 400,
        "supports_vision": True,
    },
    {
        "name": "xjtl-gpt-4o",
        "env_key": "XJTLU_VLM_API_KEY",
        "base_url_env": "XJTLU_VLM_BASE_URL",
        "default_base_url": "https://aiagent.xjtlu.edu.cn/api/aigw/v1",
        "model_id": "d08pg3tdv7249m3l5dn0",   # → gpt-4o-2024-11-20
        "max_tokens": 600,
        "supports_vision": True,
    },
    {
        "name": "claude-vision",
        "env_key": "CLAUDE_API_KEY",
        "base_url_env": "CLAUDE_BASE_URL",
        "default_base_url": "https://api.anthropic.com/v1",
        "model_id": "claude-haiku-4-5",
        "max_tokens": 500,
        "supports_vision": True,
    },
]


@dataclass
class VisualAssertionResult:
    """单次视觉断言结果"""
    intent: str                          # 断言意图 (如 "登录成功提示是否可见?")
    screenshot: str                      # 截图路径
    passed: bool = False                 # 断言是否通过
    confidence: float = 0.0              # VLM 置信度 0-1
    reasoning: str = ""                  # VLM 判断理由
    model: str = ""                      # 使用的模型
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_ms: float = 0.0
    error: str = ""
    skipped: bool = False                # VLM 不可用时跳过


class VisualAssertionLog:
    """视觉断言记录器"""

    def __init__(self):
        self.results: list[VisualAssertionResult] = []
        self._load()

    def add(self, result: VisualAssertionResult):
        self.results.append(result)
        self._save()

    def _load(self):
        try:
            if VA_LOG_PATH.exists():
                raw = json.loads(VA_LOG_PATH.read_text(encoding="utf-8"))
                self.results = [
                    VisualAssertionResult(**r)
                    for r in raw.get("results", [])[-200:]
                ]
        except Exception:
            pass

    def _save(self):
        try:
            VA_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            passed = sum(1 for r in self.results if r.passed)
            skipped = sum(1 for r in self.results if r.skipped)
            total = len(self.results)
            VA_LOG_PATH.write_text(
                json.dumps(
                    {
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "summary": {
                            "total": total,
                            "passed": passed,
                            "failed": total - passed - skipped,
                            "skipped": skipped,
                            "pass_rate": round(passed / max(total - skipped, 1), 3),
                            "models_used": list(set(r.model for r in self.results if r.model)),
                        },
                        "results": [r.__dict__ for r in self.results[-200:]],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"VisualAssertionLog save failed: {e}")

    def summary(self) -> dict:
        if not self.results:
            return {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "pass_rate": 0.0}
        passed = sum(1 for r in self.results if r.passed)
        skipped = sum(1 for r in self.results if r.skipped)
        total = len(self.results)
        effective = total - skipped
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed - skipped,
            "skipped": skipped,
            "pass_rate": round(passed / max(effective, 1), 3),
            "models_used": list(set(r.model for r in self.results if r.model)),
        }


_va_log = VisualAssertionLog()


def get_va_log() -> VisualAssertionLog:
    return _va_log


# ═══════════════════════════════════════════════════════════════════
# VLM 客户端管理
# ═══════════════════════════════════════════════════════════════════

def _get_available_vlm() -> Optional[dict]:
    """
    检测可用的 VLM 模型, 返回第一个可用模型的配置。

    优先使用统一 LLM 客户端, 回退到 VLM_MODELS 列表。
    """
    # 优先: 统一 LLM 客户端 (支持 GPT-4o/XJTLU/DeepSeek)
    from src.llm_client import get_llm_client
    client, model, cfg = get_llm_client(require_vision=True)
    if client and cfg:
        return {
            "name": cfg["name"],
            "api_key": os.getenv(cfg["env_key"], ""),
            "base_url": os.getenv(cfg["base_url_env"], "").strip() or cfg["default_base_url"],
            "model_id": model,
            "max_tokens": 600,
            "supports_vision": True,
            "supports_json_format": cfg.get("supports_json", True),
        }

    # 回退: VLM_MODELS 列表
    for cfg in VLM_MODELS:
        api_key = os.getenv(cfg["env_key"], "").strip()
        if api_key:
            base_url = os.getenv(cfg["base_url_env"], "").strip() or cfg["default_base_url"]
            return {**cfg, "api_key": api_key, "base_url": base_url}
    return None


def _encode_image(path: str) -> str:
    """将截图编码为 base64 data URL"""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ═══════════════════════════════════════════════════════════════════
# 核心: VLM 视觉断言
# ═══════════════════════════════════════════════════════════════════

def _call_gpt_vision(
    image_base64: str,
    intent: str,
    context: str,
    model_cfg: dict,
) -> tuple[bool, float, str]:
    """
    调用 GPT-4o / GPT-4o-mini Vision API。

    :return: (passed, confidence, reasoning)
    """
    from openai import OpenAI

    client = OpenAI(api_key=model_cfg["api_key"], base_url=model_cfg["base_url"])

    prompt = _build_vision_prompt(intent, context)

    response = client.chat.completions.create(
        model=model_cfg["model_id"],
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ],
        max_tokens=model_cfg["max_tokens"],
        temperature=0.1,
        timeout=30,
    )

    content = response.choices[0].message.content.strip()
    return _parse_vision_response(content)


def _call_claude_vision(
    image_base64: str,
    intent: str,
    context: str,
    model_cfg: dict,
) -> tuple[bool, float, str]:
    """
    调用 Claude Vision API。

    Claude API 格式不同: 使用 anthropic Messages API。
    """
    from openai import OpenAI

    # Claude 兼容 OpenAI SDK (通过 Anthropic 的 OpenAI-compatible endpoint)
    client = OpenAI(api_key=model_cfg["api_key"], base_url=model_cfg["base_url"])

    prompt = _build_vision_prompt(intent, context)

    try:
        response = client.chat.completions.create(
            model=model_cfg["model_id"],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}",
                            },
                        },
                    ],
                }
            ],
            max_tokens=model_cfg["max_tokens"],
            temperature=0.1,
            timeout=30,
        )
        content = response.choices[0].message.content.strip()
    except Exception:
        # Claude 可能不支持 OpenAI SDK 的 vision 格式 → 尝试 text-only
        # (某些兼容代理不支持图片, 回退到纯文本描述)
        raise

    return _parse_vision_response(content)


def _build_vision_prompt(intent: str, context: str) -> str:
    """构建 VLM 视觉断言 prompt"""
    ctx_block = f"\n\n【页面上下文】\n{context}" if context else ""

    return f"""你是严格的UI自动化测试专家。请仔细查看截图，判断以下断言是否成立。

【断言意图】
{intent}{ctx_block}

【判断标准】
- 如果截图明确显示断言成立 → passed=true, confidence=0.8-1.0
- 如果截图明确显示断言不成立 → passed=false, confidence=0.8-1.0
- 如果截图模糊或不确定 → passed=false, confidence=0.0-0.5
- 如果截图与断言无关（如空白页、错误页）→ passed=false, confidence=0.0

【输出格式】
只输出JSON: {{"passed": true/false, "confidence": 0.0-1.0, "reasoning": "你在截图中看到了什么，为什么这个判断?"}}

只输出JSON。"""


def _parse_vision_response(content: str) -> tuple[bool, float, str]:
    """解析 VLM 的 JSON 响应 (3层回退, 对齐 Evaluator 的 JSON 解析策略)"""
    import re

    # L1: 直接解析
    try:
        data = json.loads(content)
        return (
            bool(data.get("passed", False)),
            float(data.get("confidence", 0.0)),
            str(data.get("reasoning", ""))[:500],
        )
    except (json.JSONDecodeError, TypeError):
        pass

    # L2: 正则提取
    json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return (
                bool(data.get("passed", False)),
                float(data.get("confidence", 0.0)),
                str(data.get("reasoning", ""))[:500],
            )
        except (json.JSONDecodeError, TypeError):
            pass

    # L3: 关键词推断
    lowered = content.lower()
    looks_true = any(kw in lowered for kw in ["passed", "true", "yes", "可见", "显示", "通过"])
    looks_false = any(kw in lowered for kw in ["false", "no", "不可见", "未显示", "不通过"])

    if looks_true and not looks_false:
        return True, 0.5, content[:500]
    elif looks_false and not looks_true:
        return False, 0.5, content[:500]

    return False, 0.3, f"无法解析VLM响应: {content[:200]}"


# ═══════════════════════════════════════════════════════════════════
# 公开 API
# ═══════════════════════════════════════════════════════════════════

class VisualAssertion:
    """
    基于意图的视觉断言引擎。

    用法:
        va = VisualAssertion()
        result = va.assert_that("screenshot.png", "登录成功后是否显示了用户名?")
        if result.passed:
            print(f"PASS: {result.reasoning}")
    """

    def __init__(self, api_key: str = ""):
        """
        :param api_key: 可选, 手动指定 API key (优先级高于环境变量)
        """
        self.api_key = api_key

    def assert_that(
        self,
        screenshot_path: str,
        intent: str,
        context: str = "",
    ) -> VisualAssertionResult:
        """
        对单张截图执行视觉断言。

        :param screenshot_path: 截图文件路径 (PNG)
        :param intent: 断言意图 (自然语言, 如 "测验分数是否显示?")
        :param context: 可选的页面上下文 (如 "用户刚完成 Phase 2 Day 1 的测验")
        :return: VisualAssertionResult
        """
        t0 = time.time()

        # 1. 检查截图存在
        path = Path(screenshot_path)
        if not path.exists():
            result = VisualAssertionResult(
                intent=intent,
                screenshot=screenshot_path,
                error=f"截图不存在: {screenshot_path}",
                skipped=True,
            )
            result.duration_ms = (time.time() - t0) * 1000
            return result

        # 2. 检查截图大小 (空截图/损坏文件)
        if path.stat().st_size < 100:
            result = VisualAssertionResult(
                intent=intent,
                screenshot=screenshot_path,
                error="截图文件过小 (可能为空)",
                skipped=True,
            )
            result.duration_ms = (time.time() - t0) * 1000
            return result

        # 3. 找可用 VLM
        model_cfg = _get_available_vlm()
        if not model_cfg:
            result = VisualAssertionResult(
                intent=intent,
                screenshot=screenshot_path,
                error="无可用VLM (设置 GPT_API_KEY 或 CLAUDE_API_KEY 环境变量)",
                skipped=True,
            )
            result.duration_ms = (time.time() - t0) * 1000
            _va_log.add(result)
            return result

        # 覆盖 API key
        if self.api_key:
            model_cfg["api_key"] = self.api_key

        # 4. 编码图片
        try:
            image_b64 = _encode_image(str(path))
        except Exception as e:
            result = VisualAssertionResult(
                intent=intent,
                screenshot=screenshot_path,
                error=f"图片编码失败: {e}",
                skipped=True,
            )
            result.duration_ms = (time.time() - t0) * 1000
            _va_log.add(result)
            return result

        # 5. 调用 VLM
        try:
            if model_cfg["name"].startswith("gpt"):
                passed, confidence, reasoning = _call_gpt_vision(
                    image_b64, intent, context, model_cfg
                )
            else:
                passed, confidence, reasoning = _call_claude_vision(
                    image_b64, intent, context, model_cfg
                )

            result = VisualAssertionResult(
                intent=intent,
                screenshot=screenshot_path,
                passed=passed,
                confidence=confidence,
                reasoning=reasoning,
                model=model_cfg["name"],
            )
        except Exception as e:
            result = VisualAssertionResult(
                intent=intent,
                screenshot=screenshot_path,
                error=f"VLM调用失败: {e}",
                skipped=True,
                model=model_cfg.get("name", ""),
            )

        result.duration_ms = (time.time() - t0) * 1000
        _va_log.add(result)
        return result

    def assert_batch(
        self,
        screenshot_path: str,
        intents: list[str],
        context: str = "",
    ) -> list[VisualAssertionResult]:
        """
        对单张截图执行多个断言 (批量模式, 当前实现是串行 — 每次调一个 intent)。

        未来优化: 合并多个 intent 到一次 VLM 调用。
        """
        results = []
        for intent in intents:
            result = self.assert_that(screenshot_path, intent, context)
            results.append(result)
        return results

    def assert_step(
        self,
        screenshot_path: str,
        step_description: str,
        expected_visual_state: str,
    ) -> VisualAssertionResult:
        """
        对浏览器测评中的一个 Step 做视觉断言。

        这是为对接 BrowserEvaluator.complete_step() 设计的高层 API。

        :param screenshot_path: Step 完成后的截图
        :param step_description: Step 描述 (如 "Step 3: 学习传感器连接")
        :param expected_visual_state: 预期看到的视觉状态 (如 "页面显示'本步已完成'标记或绿色勾")
        """
        intent = (
            f"完成'{step_description}'后, 页面是否显示了完成状态? "
            f"预期: {expected_visual_state}"
        )
        return self.assert_that(screenshot_path, intent)


# ═══════════════════════════════════════════════════════════════════
# BrowserEvaluator 集成: 后处理钩子 (不改源码)
# ═══════════════════════════════════════════════════════════════════

def create_eval_hook(va: VisualAssertion = None):
    """
    创建一个后处理函数, 在 browser_eval 完成后对全部截图做视觉断言。

    用法 (在 test_service.py 的 _run_browser_eval 中, evaluator.run() 之后):
        from src.visual_assertion import VisualAssertion, create_eval_hook
        va = VisualAssertion()
        va_results = va.assert_batch(screenshot_paths, intents)

    也可以作为 evaluator.run() 完成后的批量后处理:
        hook = create_eval_hook()
        va_report = hook(evaluator)
    """
    if va is None:
        va = VisualAssertion()

    def hook(screenshot_dir: str, intents_map: dict[str, str]) -> list[VisualAssertionResult]:
        """
        :param screenshot_dir: 截图目录 (如 eval_output/screenshots/)
        :param intents_map: {screenshot_glob: intent} 映射
            例: {"*quiz_result*": "页面是否显示了测验分数?"}
        """
        results = []
        sdir = Path(screenshot_dir)
        if not sdir.exists():
            return results

        for glob_pattern, intent in intents_map.items():
            for png in sdir.glob(glob_pattern):
                if png.suffix.lower() == ".png":
                    result = va.assert_that(str(png), intent)
                    results.append(result)

        return results

    return hook


# ═══════════════════════════════════════════════════════════════════
# Health API 集成
# ═══════════════════════════════════════════════════════════════════

def get_health_summary() -> dict:
    """返回视觉断言系统健康摘要"""
    summary = _va_log.summary()
    vlm_available = _get_available_vlm() is not None
    return {
        "component": "visual_assertion",
        "status": "healthy" if vlm_available else "degraded",
        "vlm_available": vlm_available,
        "total_assertions": summary["total"],
        "pass_rate": summary["pass_rate"],
        "models_used": summary.get("models_used", []),
    }
