"""
L2: 教学结构推断层 — 自适应版

策略优先级:
  1. API驱动: 解析捕获到的API响应JSON, 提取课程/阶段/课时层次
  2. DOM驱动: 从页面快照+URL模式推断
  3. LLM辅助: 将DOM/API数据交给LLM推断 (Phase 2)

借鉴: Unbrowse (API-first discovery), WALT (schema induction)
"""

from __future__ import annotations

from typing import Optional
from collections import defaultdict

from .models import (
    PageSnapshot, CaptureResult, RouteNode,
    TeachingStructure, PhaseInfo, LessonInfo, StepInfo,
    StepType, InteractionElement, Framework,
)


class StructureAPIParser:
    """从捕获的API响应中提取教学结构 — 自适应任意平台"""

    # 常见教学平台API的响应结构模式 (key=API路径关键词, value=结构提取路径)
    API_STRUCTURE_PATTERNS = [
        # 模式: (路径关键词, 响应中的课程列表路径, 子结构路径)
        {
            "path_keywords": ["graph-source", "graph", "structure"],
            "courses_path": ["courses"],
            "lessons_path": ["modules", "lessons", "chapters", "units", "sections"],
            "steps_path": ["steps", "topics", "items", "contents", "activities",
                          "tasks", "children", "subModules", "resources",
                          "exercises", "quizzes", "materials"],
            "title_field": ["title", "name", "label"],
            "id_field": ["id", "slug", "code"],
        },
        {
            "path_keywords": ["career", "category", "competency"],
            "courses_path": ["categories", "careers"],
            "lessons_path": ["competencies", "skills"],
            "steps_path": ["courses", "modules"],
            "title_field": ["title", "name", "categoryName"],
            "id_field": ["id", "categoryId", "slug"],
        },
        {
            "path_keywords": ["curriculum", "syllabus", "outline"],
            "courses_path": ["phases", "stages", "modules"],
            "lessons_path": ["lessons", "days", "weeks"],
            "steps_path": ["steps", "activities", "tasks"],
            "title_field": ["title", "name", "topic"],
            "id_field": ["id", "order", "index"],
        },
        {
            "path_keywords": ["course", "lesson", "class"],
            "courses_path": ["courses", "data", "results"],
            "lessons_path": ["lessons", "units", "sections"],
            "steps_path": ["steps", "contents", "materials"],
            "title_field": ["title", "name", "subject"],
            "id_field": ["id", "courseId", "lessonId"],
        },
    ]

    def extract_structure(self, capture: CaptureResult,
                          verbose: bool = True) -> TeachingStructure:
        """从API响应中提取教学结构 — 多API融合 + 自适应解包"""
        # ── 按优先级排序: graph-source > curriculum > course > career ──
        priority_keywords = ["graph-source", "graph", "structure", "curriculum",
                            "syllabus", "course", "career", "competency"]
        sorted_routes = sorted(
            [r for r in capture.routes if r.response_sample],
            key=lambda r: next((i for i, kw in enumerate(priority_keywords)
                               if kw in r.url.lower()), 99),
        )

        structure = TeachingStructure(confidence=0.0)
        all_phases: dict[str, PhaseInfo] = {}  # id → PhaseInfo (去重)
        all_lessons: list[LessonInfo] = []
        all_steps: list[StepInfo] = []

        for route in sorted_routes:
            data = route.response_sample
            if not isinstance(data, dict):
                continue

            # ── 自动解包常见API包装器: data/result/payload ──
            data = self._unwrap_response(data)

            if verbose:
                top_keys = list(data.keys())[:8] if isinstance(data, dict) else []
                print(f"  [L2] API: {route.url.split('/')[-1]} "
                      f"(keys={top_keys}, size={len(str(data))})")

            for pattern in self.API_STRUCTURE_PATTERNS:
                if not self._match_path(route.url, pattern["path_keywords"]):
                    continue

                courses = self._extract_list(data, pattern["courses_path"])
                if not courses:
                    # ── Fallback: 尝试递归搜索任何match路径的list ──
                    courses = self._find_list_recursive(data, max_depth=4)
                    if courses and verbose:
                        print(f"     [fallback] 递归发现list [{len(courses)}项]")

                if not courses:
                    if verbose:
                        print(f"     [warn] 匹配{pattern['path_keywords']}但无course列表")
                    continue

                for i, course in enumerate(courses):
                    if not isinstance(course, dict):
                        continue

                    title = self._extract_field(course, pattern["title_field"])
                    cid = self._extract_field(course, pattern["id_field"]) or f"course_{i}"

                    # Phase (去重)
                    if cid not in all_phases:
                        sub_lessons = self._extract_list(course, pattern["lessons_path"])
                        # 如果lessons_path找不到, 递归搜索course内的list
                        if not sub_lessons:
                            sub_lessons = self._find_list_recursive(course, max_depth=2)
                        all_phases[cid] = PhaseInfo(
                            id=cid, name=title, order=i + 1,
                            lesson_count=len(sub_lessons))

                    # Lessons
                    sub_lessons = self._extract_list(course, pattern["lessons_path"])
                    if not sub_lessons:
                        sub_lessons = self._find_list_recursive(course, max_depth=2,
                                                               require_dict_items=True)
                    for j, lesson in enumerate(sub_lessons):
                        if not isinstance(lesson, dict):
                            continue
                        ltitle = self._extract_field(lesson, pattern["title_field"])
                        lid = self._extract_field(lesson, pattern["id_field"]) or f"lesson_{i}_{j}"

                        # Steps — 多策略提取
                        sub_steps = self._extract_list(lesson, pattern["steps_path"])
                        if not sub_steps:
                            # 先尝试 dict-item 搜索, 再降级为任意类型
                            sub_steps = self._find_list_recursive(
                                lesson, max_depth=3, require_dict_items=True)
                            if not sub_steps:
                                sub_steps = self._find_list_recursive(
                                    lesson, max_depth=3, require_dict_items=False)

                        # 诊断: 输出lesson的keys (仅在第一个lesson打印, 避免刷屏)
                        if verbose and j == 0 and i == 0 and not sub_steps:
                            lesson_keys = list(lesson.keys())[:12]
                            print(f"     [diag] lesson keys: {lesson_keys}")
                            # 进一步: 检查每个value的类型
                            for lk in lesson_keys[:6]:
                                lv = lesson[lk]
                                if isinstance(lv, list):
                                    sample = str(lv[:2])[:80] if lv else "[]"
                                    print(f"       {lk}: list[{len(lv)}] {sample}")
                                elif isinstance(lv, dict):
                                    print(f"       {lk}: dict keys={list(lv.keys())[:6]}")
                                else:
                                    print(f"       {lk}: {type(lv).__name__} = {str(lv)[:60]}")

                        all_lessons.append(LessonInfo(
                            id=lid, name=ltitle, phase_id=cid, order=j + 1,
                            step_count=len(sub_steps),
                            topics=self._extract_topics(lesson),
                        ))

                        for k, step in enumerate(sub_steps):
                            if isinstance(step, str):
                                # 纯字符串step: 直接作为标题
                                all_steps.append(StepInfo(
                                    id=f"step_{i}_{j}_{k}",
                                    title=step[:120],
                                    lesson_id=lid,
                                    order_index=k + 1,
                                    type=StepType.UNKNOWN,
                                ))
                            elif isinstance(step, dict):
                                stitle = self._extract_field(step, pattern["title_field"])
                                sid = self._extract_field(step, pattern["id_field"]) or f"step_{i}_{j}_{k}"
                                all_steps.append(StepInfo(
                                    id=sid, title=stitle, lesson_id=lid,
                                    order_index=k + 1, type=StepType.UNKNOWN,
                                ))

        # ── 后处理: 根据实际 lessons 更新 phase 的 lesson_count ──
        for lesson in all_lessons:
            pid = lesson.phase_id
            if pid and pid in all_phases:
                all_phases[pid].lesson_count += 1
        # 同时更新 step_count (从实际 steps 计算)
        lesson_step_counts: dict[str, int] = {}
        for step in all_steps:
            lid = step.lesson_id
            if lid:
                lesson_step_counts[lid] = lesson_step_counts.get(lid, 0) + 1
        for lesson in all_lessons:
            if lesson.id in lesson_step_counts:
                lesson.step_count = lesson_step_counts[lesson.id]

        # ── 构建最终结构 ──
        if all_phases:
            structure = TeachingStructure(
                hierarchy=["phase", "lesson", "step"],
                phases=list(all_phases.values()),
                lessons=all_lessons,
                steps=all_steps,
                confidence=0.80 if all_lessons else 0.60,
                navigation_patterns=[{
                    "type": "api_driven_multi",
                    "sources": [r.url for r in sorted_routes
                               if r.response_sample],
                }],
            )

        return structure

    @staticmethod
    def _unwrap_response(data: dict) -> dict:
        """自动解包常见API响应包装器: data/result/payload/content"""
        wrappers = ["data", "result", "payload", "content", "response", "body"]
        for wrapper in wrappers:
            if wrapper in data and isinstance(data[wrapper], dict):
                inner = data[wrapper]
                # 如果内层有更多有意义的key，使用内层
                if len(inner) > len(data) * 0.5:
                    return inner
                # 递归解包
                nested = StructureAPIParser._unwrap_response(inner)
                if nested is not inner:
                    return nested
        return data

    @staticmethod
    def _find_list_recursive(obj: dict, max_depth: int = 4,
                            min_len: int = 1,
                            require_dict_items: bool = False) -> list:
        """递归搜索字典中的第一个有意义列表 (深度优先)

        :param require_dict_items: True → 仅接受元素为dict的list (用于course/lesson)
                                   False → 也接受字符串元素list (用于step)
        """
        if max_depth <= 0:
            return []

        # 排除keys: 不进入这些key的子树
        skip_keys = {"error", "errors", "message", "status", "code",
                    "meta", "pagination", "page", "timestamp"}

        for key, val in obj.items():
            if key.lower() in skip_keys:
                continue
            if isinstance(val, list) and len(val) >= min_len:
                if not val:
                    continue
                if require_dict_items:
                    if isinstance(val[0], dict):
                        return val
                else:
                    # 接受dict或字符串
                    if isinstance(val[0], (dict, str)):
                        return val
            elif isinstance(val, dict):
                result = StructureAPIParser._find_list_recursive(
                    val, max_depth - 1, min_len, require_dict_items)
                if result:
                    return result
        return []

    @staticmethod
    def _match_path(url: str, keywords: list[str]) -> bool:
        url_lower = url.lower()
        return any(kw.lower() in url_lower for kw in keywords)

    @staticmethod
    def _extract_list(data: dict, paths: list[str]) -> list:
        """从嵌套字典中按多个可能路径提取列表"""
        for path in paths:
            # 支持嵌套: "data.courses" → data["data"]["courses"]
            keys = path.split(".")
            current = data
            for key in keys:
                if isinstance(current, dict):
                    current = current.get(key)
                else:
                    current = None
                    break
            if isinstance(current, list) and len(current) > 0:
                return current
        return []

    @staticmethod
    def _extract_field(obj: dict, fields: list[str]) -> str:
        """从字典中按多个可能字段名提取值 (递归搜索)"""
        # 支持嵌套: "name.zh" → obj["name"]["zh"]
        for field in fields:
            keys = field.split(".")
            current = obj
            for key in keys:
                if isinstance(current, dict):
                    current = current.get(key)
                else:
                    current = None
                    break
            if isinstance(current, str) and current.strip():
                return current.strip()
        # 递归搜索所有字符串值, 取最长的 (兜底)
        return StructureAPIParser._find_longest_string(obj)

    @staticmethod
    def _find_longest_string(obj: dict, depth: int = 0) -> str:
        """递归查找字典中最长的字符串值 (通常是名称/标题)"""
        if depth > 5:
            return ""
        best = ""
        for k, v in obj.items():
            if isinstance(v, str) and len(v) > len(best) and len(v) < 200:
                # 排除明显不是标题的值 (URL, JSON, 纯数字)
                if not v.startswith(("http", "{", "[", "<")) and not v.isdigit():
                    best = v
            elif isinstance(v, dict):
                sub = StructureAPIParser._find_longest_string(v, depth + 1)
                if len(sub) > len(best):
                    best = sub
        return best

    @staticmethod
    def _extract_topics(obj: dict) -> list[str]:
        """提取知识点/主题列表"""
        for key in ["topics", "keywords", "tags", "skills", "competencies"]:
            val = obj.get(key)
            if isinstance(val, list):
                return [str(v) for v in val[:10] if v]
        return []


class DOMStructureAnalyzer:
    """DOM结构分析器"""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def detect_framework(self, pages: list[PageSnapshot]) -> Framework:
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


class DOMStructureInferrer:
    """从DOM/URL推断教学结构 (fallback)"""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def infer(self, pages: list[PageSnapshot],
              url_graph: dict[str, list[str]]) -> TeachingStructure:
        """从页面快照中启发式推断"""
        structure = TeachingStructure(
            hierarchy=["phase", "lesson", "step"], confidence=0.3)

        import re
        for page in pages:
            title = page.title
            for prefix, entity_type in [("Phase", "phase"), ("阶段", "phase"),
                                         ("Lesson", "lesson"), ("Day", "lesson"),
                                         ("课时", "lesson"), ("Step", "step"),
                                         ("步骤", "step"), ("Task", "step")]:
                m = re.search(rf"{prefix}\s*(\d+)", title, re.IGNORECASE)
                if m:
                    idx = int(m.group(1))
                    if "phase" in entity_type:
                        structure.phases.append(PhaseInfo(
                            id=f"phase_{idx}", name=title, order=idx))
                    elif "lesson" in entity_type:
                        structure.lessons.append(LessonInfo(
                            id=f"lesson_{idx}", name=title, order=idx))
                    else:
                        structure.steps.append(StepInfo(
                            id=f"step_{idx}", title=title, order_index=idx))

        if structure.phases and structure.lessons:
            structure.confidence = 0.6
        elif structure.phases or structure.lessons:
            structure.confidence = 0.4

        return structure


# ═══════════════════════════════════════════════════════════════
# L2 主入口 — 多策略融合
# ═══════════════════════════════════════════════════════════════

def _extract_steps_from_pages(pages, verbose=True):
    """从页面快照中提取 Step 信息 — fallback当API无嵌套steps时"""
    steps = []
    import re as _re

    for page in pages:
        if not page.url or not page.title:
            continue

        # 策略1: 从interactive_elements中找step-like结构
        step_count = 0
        for el in page.interactive_elements:
            hint = el.get("semantic_hint", "")
            tag = el.get("tag", "")
            role = el.get("role", "")
            text = el.get("text", "")

            # Step进度指示器
            if hint in ("step_indicator", "progress_step") or \
               "step" in hint.lower() or "progress" in hint.lower():
                step_count += 1

            # 如果有交互元素 (button/link) 可能是step操作
            if role in ("button", "link") and text:
                step_count += 1

        # 策略2: 从text_content提取编号列表
        content = page.text_content or ""
        # 匹配 "Step 1:", "步骤1:", "1. ", "(1)" 等模式
        step_patterns = [
            r'(?:Step|步骤|Task|任务|Activity|活动)\s*\d+',
            r'^\d+[\.\)]\s',  # "1. " or "1) "
        ]
        for pat in step_patterns:
            matches = _re.findall(pat, content, _re.IGNORECASE | _re.MULTILINE)
            if matches:
                step_count = max(step_count, len(matches))

        if step_count > 0:
            steps.append(StepInfo(
                id="step_{:03d}".format(len(steps)),
                title=page.title,
                type=StepType.UNKNOWN,
                type_confidence=0.5,
                order_index=len(steps),
            ))

        # 上限: 避免从单个页面提取过多steps
        if step_count > 20:
            step_count = 20

    if verbose and steps:
        print(f"  📄 DOM step extraction: {len(steps)} pages with step-like content")

    return steps


def run_l2_structure(
    capture: CaptureResult,
    verbose: bool = True,
) -> TeachingStructure:
    """
    L2 完整流程: API驱动 → DOM驱动 → 合并

    优先级: API数据 > DOM数据
    """
    if verbose:
        print(f"\n{'='*60}")
        print(f"L2: 教学结构推断 (API优先 + DOM回退)")
        print(f"{'='*60}")

    # 策略1: API驱动 (高置信度)
    api_parser = StructureAPIParser()
    api_structure = api_parser.extract_structure(capture, verbose=verbose)

    if api_structure.confidence >= 0.5:
        if verbose:
            print(f"  ✅ API驱动: {len(api_structure.phases)} phases, "
                  f"{len(api_structure.lessons)} lessons, "
                  f"{len(api_structure.steps)} steps "
                  f"(conf={api_structure.confidence:.2f})")

        # 补充DOM框架信息
        dom_analyzer = DOMStructureAnalyzer(verbose=False)
        api_structure.framework = dom_analyzer.detect_framework(capture.pages)

        # ── DOM fallback: API有phases+lessons但无steps → 从页面提取steps ──
        if len(api_structure.steps) == 0 and capture.pages:
            dom_steps = _extract_steps_from_pages(capture.pages, verbose=verbose)
            if dom_steps:
                api_structure.steps = dom_steps
                # 将steps均匀分配到lessons
                if api_structure.lessons:
                    steps_per = max(1, len(dom_steps) // max(1, len(api_structure.lessons)))
                    for idx, lesson in enumerate(api_structure.lessons):
                        lesson.step_count = min(steps_per,
                                               len(dom_steps) - idx * steps_per)
                if verbose:
                    print(f"  📄 DOM fallback: {len(dom_steps)} steps from pages")
        return api_structure

    # 策略2: DOM驱动 (回退)
    if verbose:
        print(f"  ⚠️ API未发现结构, 回退到DOM推断...")

    dom_inferrer = DOMStructureInferrer(verbose=verbose)
    dom_structure = dom_inferrer.infer(capture.pages, capture.url_graph)

    dom_analyzer = DOMStructureAnalyzer(verbose=False)
    dom_structure.framework = dom_analyzer.detect_framework(capture.pages)

    if verbose:
        print(f"  📊 DOM推断: {len(dom_structure.phases)} phases, "
              f"{len(dom_structure.lessons)} lessons, "
              f"{len(dom_structure.steps)} steps "
              f"(conf={dom_structure.confidence:.2f})")

    return dom_structure
