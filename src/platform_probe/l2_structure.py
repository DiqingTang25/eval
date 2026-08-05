"""
L2: 交互元素与教学结构推断层 (Structure & Element Indexing)

借鉴: KaBOOM (语义选择器+Shadow DOM穿透)
      WALT Tool Discovery (元素→工具候选)
      Explorbot Research (5步工作流: Research→Plan→Execute→Verify→Keep)

职责:
  1. DOM 结构分析 (框架检测/Shadow DOM/iframe)
  2. 教学层次推断 (★核心★ Phase→Lesson→Step)
  3. Step 类型分类
  4. 交互元素语义索引

Phase 1 (当前): 简化版 — 基于L1捕获的页面快照进行基础推断
Phase 2 (后续): 完整版 — 使用LLM辅助推断 + Shadow DOM穿透
"""

from __future__ import annotations

from typing import Optional
from collections import defaultdict

from .models import (
    PageSnapshot, CaptureResult,
    TeachingStructure, PhaseInfo, LessonInfo, StepInfo,
    StepType, InteractionElement, Framework,
)
from .confidence import classify_step_type


class DOMStructureAnalyzer:
    """DOM结构分析器 (Phase 1: 基础版)"""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def detect_framework(self, pages: list[PageSnapshot]) -> Framework:
        """从页面快照中检测前端框架"""
        framework_votes = defaultdict(int)

        for page in pages:
            for hint in page.framework_hints:
                if hint in ("react", "vue", "angular", "next"):
                    framework_votes[hint] += 1

        if not framework_votes:
            return Framework.UNKNOWN

        best = max(framework_votes, key=framework_votes.get)
        try:
            return Framework(best)
        except ValueError:
            return Framework.UNKNOWN


class TeachingStructureInferrer:
    """
    教学结构推断器 — ★核心模块★

    Phase 1: 基于 URL 模式和页面标题进行启发式推断
    Phase 2: 使用 LLM 辅助推断 (分析DOM片段 → 推断层次关系)
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def infer(
        self,
        pages: list[PageSnapshot],
        url_graph: dict[str, list[str]],
    ) -> TeachingStructure:
        """
        从页面快照和URL图中推断教学层次

        Phase 1: 启发式规则
          - URL 包含 /phase/ /lesson/ /step/ → 明确层次
          - 页面标题包含 "Phase 1" "Lesson 2" "Step 3" → 带序号
          - 导航深度 → 层次深度
        """
        structure = TeachingStructure(
            hierarchy=["phase", "lesson", "step"],
            confidence=0.5,  # Phase 1 默认中等置信度
        )

        # ── 从URL推断 ──
        url_patterns = self._extract_url_patterns(pages)
        if url_patterns:
            structure.navigation_patterns.append({
                "type": "url_structure",
                "patterns": url_patterns,
            })

        # ── 从页面标题推断层次 ──
        for page in pages:
            title = page.title

            # 检测 Phase 标题
            phase_match = self._extract_numbered(title, ["Phase", "阶段", "Part", "部分", "模块"])
            if phase_match:
                phase = PhaseInfo(
                    id=f"phase_{phase_match}",
                    name=title,
                    order=phase_match,
                )
                if phase.id not in [p.id for p in structure.phases]:
                    structure.phases.append(phase)

            # 检测 Lesson 标题
            lesson_match = self._extract_numbered(title, ["Lesson", "Day", "课时", "第", "课", "Week"])
            if lesson_match:
                lesson = LessonInfo(
                    id=f"lesson_{lesson_match}",
                    name=title,
                    order=lesson_match,
                )
                if lesson.id not in [l.id for l in structure.lessons]:
                    structure.lessons.append(lesson)

            # 检测 Step 标题
            step_match = self._extract_numbered(title, ["Step", "步骤", "任务", "Task"])
            if step_match:
                step = StepInfo(
                    id=f"step_{step_match}",
                    title=title,
                    type=StepType.UNKNOWN,
                    order_index=step_match,
                )
                if step.id not in [s.id for s in structure.steps]:
                    structure.steps.append(step)

        # ── 从URL路径深度推断层次 ──
        depth_groups = self._group_by_url_depth(pages)
        if len(depth_groups) >= 3:
            # 3层深度 → Phase/Lesson/Step 模式
            if not structure.phases:
                structure.navigation_patterns.append({
                    "type": "depth_based_hierarchy",
                    "depths": list(depth_groups.keys()),
                })

        # ── 调整置信度 ──
        if structure.phases and structure.lessons:
            structure.confidence = 0.7
        elif structure.phases or structure.lessons:
            structure.confidence = 0.5
        else:
            structure.confidence = 0.3

        if self.verbose:
            print(f"\n  📊 教学结构推断:")
            print(f"     Phase: {len(structure.phases)}")
            print(f"     Lesson: {len(structure.lessons)}")
            print(f"     Step: {len(structure.steps)}")
            print(f"     置信度: {structure.confidence:.2f}")

        return structure

    @staticmethod
    def _extract_numbered(title: str, prefixes: list[str]) -> Optional[int]:
        """从标题中提取数字编号, 如 'Phase 2: ...' → 2"""
        import re
        for prefix in prefixes:
            pattern = rf"{prefix}\s*(\d+)"
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    @staticmethod
    def _extract_url_patterns(pages: list[PageSnapshot]) -> list[str]:
        """提取 URL 中的通用模式"""
        patterns = set()
        for page in pages:
            path = page.url.split("?")[0]
            parts = path.split("/")
            for i, part in enumerate(parts):
                if part.isdigit():
                    # 参数化: /lesson/4 → /lesson/{id}
                    if i > 0:
                        pattern = "/".join(parts[:i]) + "/{id}"
                        patterns.add(pattern)
        return sorted(patterns)

    @staticmethod
    def _group_by_url_depth(pages: list[PageSnapshot]) -> dict[int, list[str]]:
        """按URL路径深度分组"""
        groups = defaultdict(list)
        for page in pages:
            path = page.url.split("?")[0].rstrip("/")
            depth = len([p for p in path.split("/") if p])
            groups[depth].append(page.url)
        return dict(groups)


# ═══════════════════════════════════════════════════════════════
# L2 主入口 (Phase 1: 简化版)
# ═══════════════════════════════════════════════════════════════

def run_l2_structure(
    capture: CaptureResult,
    verbose: bool = True,
) -> TeachingStructure:
    """
    L2 完整流程: DOM分析 → 层次推断 → 类型分类 → 元素索引

    Phase 1: 使用 L1 页面快照进行启发式推断
    Phase 2: 加入 LLM 辅助 + Shadow DOM + 完整语义索引
    """
    if verbose:
        print(f"\n{'='*60}")
        print(f"L2: 教学结构推断 (Phase 1: 启发式)")
        print(f"{'='*60}")

    # DOM 框架分析
    analyzer = DOMStructureAnalyzer(verbose=verbose)
    framework = analyzer.detect_framework(capture.pages)

    # 教学层次推断
    inferrer = TeachingStructureInferrer(verbose=verbose)
    structure = inferrer.infer(capture.pages, capture.url_graph)
    structure.framework = framework

    # Phase 1: step类型分类已在L3完成 (StepTypeClassifier),
    #          这里只是结构层次推断

    return structure
