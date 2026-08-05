"""
L3: API分类与推断层 (Classification & Inference)

借鉴: Vespasian Classifier (6信号置信度打分 + 阈值 0.50)
      A2A论文 (LLM端点枚举, 91.9%发现率, MCP协议)
      WALT Schema Induction (参数推断 + URL Promotion)

职责:
  1. 对L1捕获的所有请求进行API分类 (确定性规则)
  2. 对灰色地带端点进行LLM辅助枚举 (Phase 2, 此处留接口)
  3. 推断参数Schema (路径参数化 + JSON Schema)
输出: APICatalog + StepCatalog
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional
from collections import defaultdict

from .models import (
    RouteNode, PageSnapshot, CaptureResult,
    ClassifiedEndpoint, APICatalog, StepCatalog,
    APICategory, StepType, StepInfo, InteractionElement,
)
from .confidence import (
    classify_api_endpoint, classify_api_category,
    classify_step_type, is_gray_zone,
    DEFAULT_API_THRESHOLD, HIGH_CONFIDENCE_THRESHOLD,
)


# ═══════════════════════════════════════════════════════════════
# API 分类器
# ═══════════════════════════════════════════════════════════════

class APIClassifier:
    """API端点分类器 (借鉴 Vespasian Classifier + 6信号系统)"""

    def __init__(self, threshold: float = DEFAULT_API_THRESHOLD,
                 verbose: bool = True):
        self.threshold = threshold
        self.verbose = verbose

    def classify_all(self, capture: CaptureResult) -> list[ClassifiedEndpoint]:
        """
        对所有捕获的路由进行分类
        :returns: 分类后的端点列表
        """
        classified: list[ClassifiedEndpoint] = []

        # 按 URL+Method 去重
        seen = set()
        unique_routes = []
        for r in capture.routes:
            key = (r.url, r.method)
            if key not in seen:
                seen.add(key)
                unique_routes.append(r)

        for route in unique_routes:
            result = self._classify_one(route)
            if result.confidence >= self.threshold:
                classified.append(result)

        # 按类别分组统计
        by_cat = defaultdict(int)
        for ep in classified:
            by_cat[ep.category] += 1

        if self.verbose:
            print(f"\n  📊 API 分类完成:")
            print(f"     总请求: {len(capture.routes)}")
            print(f"     去重后: {len(unique_routes)}")
            print(f"     确认API: {len(classified)} (阈值≥{self.threshold})")
            for cat, count in sorted(by_cat.items()):
                print(f"       {cat}: {count}")

        return classified

    def _classify_one(self, route: RouteNode) -> ClassifiedEndpoint:
        """对单个路由分类"""
        # 1. 提取扩展名
        ext = Path(route.url.split("?")[0]).suffix if "." in route.url else ""

        # 2. 6信号分类
        confidence, signals = classify_api_endpoint(
            content_type=route.content_type,
            path=route.url,
            method=route.method,
            response_body=route.response_sample,
            url_extension=ext,
        )

        # 3. 细粒度类别分类 (仅当确认为API时)
        category = APICategory.UNKNOWN
        cat_confidence = 0.0
        if confidence >= self.threshold:
            cat_name, cat_confidence = classify_api_category(
                path=route.url,
                method=route.method,
                request_payload=route.request_payload,
                response_body=route.response_sample,
            )
            try:
                category = APICategory(cat_name)
            except ValueError:
                category = APICategory.UNKNOWN

        # 4. 推断参数Schema
        parameters = self._infer_parameters(route)

        # 5. 推断响应Schema
        response_schema = self._infer_response_schema(route)

        return ClassifiedEndpoint(
            path=route.url,
            method=route.method,
            category=category,
            confidence=confidence,
            signals=signals,
            parameters=parameters,
            response_schema=response_schema,
            inferred_from="traffic",
            is_hidden=False,
            sample_request=(
                {"payload": route.request_payload}
                if route.request_payload else None
            ),
            sample_response=(
                {"body": route.response_sample}
                if route.response_sample else None
            ),
        )

    @staticmethod
    def _infer_parameters(route: RouteNode) -> dict[str, Any]:
        """推断请求参数 (WALT Schema Induction)"""
        params: dict[str, Any] = {
            "query": {},
            "path": {},
            "body": {},
        }

        # 从URL提取路径参数
        path = route.url.split("?")[0]
        # 参数化: /users/42 → /users/{id}
        segments = path.split("/")
        param_names = ["id", "user_id", "lesson_id", "step_id", "phase_id",
                       "course_id", "quiz_id", "message_id", "conversation_id"]
        for i, seg in enumerate(segments):
            if seg.isdigit() or (len(seg) == 36 and seg.count("-") == 4):
                # 尝试匹配参数名
                if i > 0:
                    context = segments[i - 1].rstrip("s")  # lessons → lesson
                    param_name = f"{context}_id"
                else:
                    param_name = "id"
                params["path"][param_name] = "string"

        # 从URL提取查询参数
        if "?" in route.url:
            query_str = route.url.split("?")[1]
            for pair in query_str.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    # 推断类型
                    if v.isdigit():
                        params["query"][k] = "integer"
                    elif v in ("true", "false"):
                        params["query"][k] = "boolean"
                    else:
                        params["query"][k] = "string"

        # 从请求体推断body schema
        if route.request_payload and isinstance(route.request_payload, dict):
            for k, v in route.request_payload.items():
                if isinstance(v, str):
                    params["body"][k] = "string"
                elif isinstance(v, int):
                    params["body"][k] = "integer"
                elif isinstance(v, float):
                    params["body"][k] = "number"
                elif isinstance(v, bool):
                    params["body"][k] = "boolean"
                elif isinstance(v, list):
                    params["body"][k] = "array"
                elif isinstance(v, dict):
                    params["body"][k] = "object"

        return params

    @staticmethod
    def _infer_response_schema(route: RouteNode) -> Optional[dict]:
        """从响应体推断 JSON Schema"""
        if not route.response_sample:
            return None

        if isinstance(route.response_sample, dict):
            schema = {"type": "object", "properties": {}}
            for k, v in route.response_sample.items():
                if isinstance(v, str):
                    schema["properties"][k] = {"type": "string"}
                elif isinstance(v, int):
                    schema["properties"][k] = {"type": "integer"}
                elif isinstance(v, float):
                    schema["properties"][k] = {"type": "number"}
                elif isinstance(v, bool):
                    schema["properties"][k] = {"type": "boolean"}
                elif isinstance(v, list):
                    if v and isinstance(v[0], dict):
                        schema["properties"][k] = {
                            "type": "array",
                            "items": {"type": "object"},
                        }
                    else:
                        schema["properties"][k] = {"type": "array"}
                elif isinstance(v, dict):
                    schema["properties"][k] = {"type": "object"}
                elif v is None:
                    schema["properties"][k] = {"type": "null"}
            return schema

        elif isinstance(route.response_sample, list):
            return {"type": "array", "items": {}}

        return None


# ═══════════════════════════════════════════════════════════════
# Step 类型分类器
# ═══════════════════════════════════════════════════════════════

class StepTypeClassifier:
    """Step类型分类器 (基于DOM元素 + 文本 + API流量)"""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def classify_pages(self, pages: list[PageSnapshot]) -> list[StepInfo]:
        """
        对页面快照进行 Step 类型分类
        教学平台中每个页面很可能对应一个 Step
        """
        steps: list[StepInfo] = []

        for i, page in enumerate(pages):
            if not page.url or not page.title:
                continue

            # 收集DOM元素描述
            dom_elements = []
            for el in page.interactive_elements:
                dom_elements.append(f"{el.get('tag', '')} {el.get('text', '')} "
                                    f"{el.get('semantic_hint', '')}")

            # 分类
            step_type, confidence = classify_step_type(
                dom_elements=dom_elements,
                text_content=page.text_content,
                page_title=page.title,
            )

            try:
                type_enum = StepType(step_type)
            except ValueError:
                type_enum = StepType.UNKNOWN

            # 构建交互元素列表
            elements = []
            for el in page.interactive_elements:
                elements.append(InteractionElement(
                    role=el.get("role", "unknown"),
                    semantic=el.get("semantic_hint", ""),
                    selector=el.get("selector", ""),
                    stable_hash=el.get("stable_hash", ""),
                ))

            step = StepInfo(
                id=f"step_{i:03d}",
                title=page.title,
                type=type_enum,
                type_confidence=confidence,
                order_index=i,
                interaction_elements=elements,
            )

            steps.append(step)

        if self.verbose:
            by_type = defaultdict(int)
            for s in steps:
                by_type[s.type.value] += 1
            print(f"\n  📊 Step 类型分类完成: {len(steps)} 个页面")
            for t, c in sorted(by_type.items()):
                print(f"       {t}: {c}")

        return steps


# ═══════════════════════════════════════════════════════════════
# LLM 端点枚举器 (Phase 2 实现, Phase 1 留接口)
# ═══════════════════════════════════════════════════════════════

class LLMEnumerator:
    """
    LLM辅助端点枚举器 (借鉴 A2A论文)

    Phase 1: 接口占位, 不实际调用 LLM
    Phase 2: 实现完整的 A2A 风格 LLM 端点枚举
        - 仅对 gray zone (conf 0.50-0.70) 端点触发
        - 使用廉价模型 (Haiku)
        - Prompt: 见 prompts/api_enumeration.txt
    """

    def __init__(self, api_key: str = "", model: str = "deepseek-chat",
                 verbose: bool = True):
        self.api_key = api_key
        self.model = model
        self.verbose = verbose
        self._enabled = bool(api_key)

    def enumerate(self, known_endpoints: list[ClassifiedEndpoint],
                  js_bundle_content: str = "") -> list[ClassifiedEndpoint]:
        """
        枚举隐藏端点

        Phase 1: 返回空列表
        Phase 2: LLM推断 + GET/OPTIONS验证
        """
        if not self._enabled:
            if self.verbose:
                print("  ⏭ LLM枚举跳过 (未配置API key)")
            return []

        # Phase 2 实现:
        # 1. 筛选 gray zone 端点
        # 2. 构建 Prompt (已知端点 + JS路由片段)
        # 3. 调用 LLM 推断隐藏端点
        # 4. 发起 OPTIONS/GET 试探验证
        # 5. 返回验证通过的隐藏端点

        if self.verbose:
            print("  ℹ️ LLM枚举器已启用, 但Phase 1不实际调用")
        return []


# ═══════════════════════════════════════════════════════════════
# L3 主入口
# ═══════════════════════════════════════════════════════════════

def run_l3_classify(
    capture: CaptureResult,
    api_threshold: float = DEFAULT_API_THRESHOLD,
    llm_api_key: str = "",
    verbose: bool = True,
) -> tuple[APICatalog, StepCatalog]:
    """
    L3 完整流程: API分类 → Step分类 → LLM枚举(Phase2)

    :returns: (api_catalog, step_catalog)
    """
    if verbose:
        print(f"\n{'='*60}")
        print(f"L3: API分类与推断 (阈值={api_threshold})")
        print(f"{'='*60}")

    # Step 1: API 分类
    api_classifier = APIClassifier(threshold=api_threshold, verbose=verbose)
    classified = api_classifier.classify_all(capture)

    # Step 2: Step 类型分类
    step_classifier = StepTypeClassifier(verbose=verbose)
    steps = step_classifier.classify_pages(capture.pages)

    # Step 3: LLM 枚举 (Phase 2)
    enumerator = LLMEnumerator(api_key=llm_api_key, verbose=verbose)
    hidden = enumerator.enumerate(classified)

    # Step 4: 构建 API Catalog
    by_category: dict[str, list[ClassifiedEndpoint]] = defaultdict(list)
    for ep in classified + hidden:
        by_category[ep.category.value].append(ep)

    # 提取API前缀
    prefixes = set()
    for ep in classified:
        path = ep.path.split("?")[0]
        # 取到第一个非字母数字字符段
        parts = path.split("/")
        if len(parts) >= 2:
            # 收集顶层前缀: /api, /phase3-api, /v1, etc.
            for part in parts[1:3]:
                if part and not part[0].isdigit():
                    prefix = "/" + "/".join(
                        p for p in parts[1:4] if p and not p[0].isdigit()
                    )
                    if prefix and len(prefix) > 2:
                        prefixes.add(prefix)
                        break
            # 如果没找到有意义前缀, 用前两段
            if len(parts) >= 3 and not any(
                p and not p[0].isdigit() for p in parts[1:4]
            ):
                prefixes.add("/" + "/".join(parts[1:3]))

    api_catalog = APICatalog(
        endpoints=classified + hidden,
        by_category=dict(by_category),
        prefixes=sorted(prefixes),
        total_found=len(classified) + len(hidden),
        llm_inferred_count=len(hidden),
    )

    # Step 5: 构建 Step Catalog
    type_dist = defaultdict(int)
    for s in steps:
        type_dist[s.type.value] += 1

    step_catalog = StepCatalog(
        steps=steps,
        type_distribution=dict(type_dist),
    )

    if verbose:
        print(f"\n  📊 L3 完成:")
        print(f"     API端点: {api_catalog.total_found} "
              f"(含{api_catalog.llm_inferred_count}个LLM推断)")
        print(f"     API前缀: {api_catalog.prefixes}")
        print(f"     Step类型分布: {dict(type_dist)}")

    return api_catalog, step_catalog
