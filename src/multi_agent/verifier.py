"""
Verifier Agent — Agent C

三通道并行验证: Text (10维评分) | Visual (GPT-4o截图) | API (MCP直调)
三取二投票 → verdict: pass/fail

降级策略:
  - MCP 不可用 → 跳过 API, Text+Visual 双通道 (共识: 2/2)
  - Visual 不可用 → 跳过 Visual, Text+API 双通道
  - 全部不可用 → 仅 Text (保持在现有能力范围内)
"""
from __future__ import annotations

import logging
from typing import Optional

from src.multi_agent.models import StepResult, VerificationResult

logger = logging.getLogger(__name__)


class VerifierAgent:
    """
    三通道 Step 验证。

    用法:
        verifier = VerifierAgent()
        result = verifier.verify(step_result, expected_question="...")
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._mcp_available: Optional[bool] = None
        self._visual_available: Optional[bool] = None

    # ── 公开 API ──

    def verify(
        self,
        step: StepResult,
        expected_question: str = "",
        golden_answer: str = "",
    ) -> VerificationResult:
        """
        对单个 Step 执行三通道验证。

        :param step: Executor 产出的 StepResult
        :param expected_question: 期望 Agent 回答的问题
        :param golden_answer: 参考答案 (如可用)
        :return: VerificationResult
        """
        result = VerificationResult(
            phase_name=step.phase_name,
            lesson_name=step.lesson_name,
            step_name=step.step_name,
        )

        # ── Channel 1: Text (10维评分) ──────────────────
        result.text_pass, result.text_score = self._verify_text(
            expected_question or step.step_name,
            step.agent_response or step.dom_snapshot.get("visibleText", ""),
            golden_answer,
        )

        # ── Channel 2: Visual (VLM 截图) ─────────────────
        if self._is_visual_available() and step.screenshot_path:
            result.visual_pass, result.visual_confidence, result.visual_reasoning = (
                self._verify_visual(step)
            )
        else:
            result.visual_skipped = True
            result.visual_pass = True  # 跳过时不参与否决

        # ── Channel 3: API (MCP 直调) ────────────────────
        if self._is_mcp_available():
            result.api_pass, result.api_response = self._verify_api(step)
        else:
            result.api_skipped = True
            result.api_pass = True  # 跳过时不参与否决

        # ── 三取二投票 ──────────────────────────────────
        votes = [result.text_pass, result.visual_pass, result.api_pass]
        result.verdict = "pass" if sum(votes) >= 2 else "fail"

        # ── 诊断 ─────────────────────────────────────────
        if result.verdict == "fail":
            reasons = []
            if not result.text_pass:
                reasons.append(f"Text评分过低 ({result.text_score})")
            if not result.visual_pass and not result.visual_skipped:
                reasons.append(f"Visual: {result.visual_reasoning[:100]}")
            if not result.api_pass and not result.api_skipped:
                reasons.append(f"API验证失败: {result.api_response}")
            result.diagnosis = "; ".join(reasons) if reasons else "三通道验证失败"

        return result

    # ── Text 通道 ──

    @staticmethod
    def _verify_text(question: str, answer: str, golden: str) -> tuple[bool, float]:
        """用现有 Evaluator 做文本评分"""
        if not answer or len(answer.strip()) < 10:
            return False, 0.0

        try:
            from src.llm_client import get_api_key, get_base_url, bridge_env_vars, get_judge_clients
            from src.evaluator import Evaluator

            # 桥接环境变量 → Evaluator 的多 Judge 系统能感知 DeepSeek + GPT-4o
            bridge_env_vars()

            api_key = get_api_key()
            if not api_key:
                has_content = len(answer) > 20
                return has_content, 3.0 if has_content else 0.0

            # 多 Judge: 用 DeepSeek-V4 + GPT-4o 两个模型投票
            judges = get_judge_clients()
            n_judges = min(len(judges), 2) if judges else 1

            evaluator = Evaluator(api_key, config={
                "n_judges": n_judges,    # 2 judges → 多模型投票
                "judge_temperatures": [0.1, 0.15],
                "use_embedding": False,
                "use_structure": False,
                "use_rag": False,
            }, base_url=get_base_url())
            scores = evaluator.evaluate(
                question=question,
                agent_answer=answer[:2000],
                golden_answer=golden or question,
            )
            overall = scores.get("overall", 0) if isinstance(scores, dict) else 0
            return overall >= 2.5, round(float(overall), 1)
        except Exception as e:
            logger.warning(f"Text verify failed: {e}")
            return False, 0.0

    # ── Visual 通道 ──

    def _verify_visual(self, step: StepResult) -> tuple[bool, float, str]:
        """用 VisualAssertion 做 VLM 截图判断"""
        try:
            from src.visual_assertion import VisualAssertion
            va = VisualAssertion(api_key=self.api_key)
            result = va.assert_that(
                screenshot_path=step.screenshot_path,
                intent=f"完成'{step.step_name}'后, 页面是否显示了完成状态? 是否有明显的错误或空白?",
                context=f"Phase: {step.phase_name}, Lesson: {step.lesson_name}",
            )
            if result.skipped:
                return True, 0.0, "VLM不可用, 跳过"
            return result.passed, result.confidence, result.reasoning[:300]
        except Exception as e:
            logger.warning(f"Visual verify failed: {e}")
            return True, 0.0, f"Visual错误: {e}"

    # ── API 通道 ──

    def _verify_api(self, step: StepResult) -> tuple[bool, dict]:
        """用 MCP Server 做 API 数据验证"""
        try:
            from src.mcp_server import get_mcp_server
            mcp = get_mcp_server()
            if not mcp.is_available:
                return True, {"skipped": "MCP schema unavailable"}

            # 尝试调 agent_context 获取课程数据
            result = mcp.call_tool("agent_context", {})
            return result.get("success", False), result
        except Exception as e:
            logger.warning(f"API verify failed: {e}")
            return True, {"error": str(e)}

    # ── 可用性检测 ──

    def _is_visual_available(self) -> bool:
        if self._visual_available is None:
            try:
                from src.visual_assertion import _get_available_vlm
                self._visual_available = _get_available_vlm() is not None
            except Exception:
                self._visual_available = False
        return self._visual_available

    def _is_mcp_available(self) -> bool:
        if self._mcp_available is None:
            try:
                from src.mcp_server import get_mcp_server
                self._mcp_available = get_mcp_server().is_available
            except Exception:
                self._mcp_available = False
        return self._mcp_available
