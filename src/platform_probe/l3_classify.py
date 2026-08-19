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
                page_url=page.url,
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
    LLM辅助端点枚举器 (借鉴 A2A论文 — 91.9%发现率)

    实现完整的 A2A 风格 LLM 端点枚举:
        1. 筛选 gray zone (conf 0.50-0.70) 端点
        2. 构建 Prompt (已知端点 + JS路由片段)
        3. 调用 LLM (DeepSeek/Haiku) 推断隐藏端点
        4. 发起 GET/OPTIONS 试探验证
        5. 返回验证通过的隐藏端点

    成本控制: 仅对 gray_zone 端点触发, 使用廉价模型, 每次最多10个候选
    """

    # Prompt 模板路径
    PROMPT_TEMPLATE_PATH = Path(__file__).parent / "prompts" / "api_enumeration.txt"

    def __init__(self, api_key: str = "", model: str = "deepseek-chat",
                 base_url: str = "", verbose: bool = True):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or "https://api.deepseek.com/v1"
        self.verbose = verbose
        self._enabled = bool(api_key)
        self._session = None  # lazy requests.Session

    def enumerate(self, known_endpoints: list[ClassifiedEndpoint],
                  js_bundle_content: str = "",
                  base_url: str = "") -> list[ClassifiedEndpoint]:
        """
        枚举隐藏端点 — 完整 A2A 流程

        :param known_endpoints: 已分类的端点列表
        :param js_bundle_content: JS源码文本 (用于Prompt上下文)
        :param base_url: 目标网站base URL (用于验证HTTP请求)
        :returns: 验证通过的隐藏端点列表
        """
        if not self._enabled:
            if self.verbose:
                print("  ⏭ LLM枚举跳过 (未配置API key)")
            return []

        # 1. 筛选 gray zone 端点 (conf 0.50-0.70)
        gray_eps = [ep for ep in known_endpoints
                    if is_gray_zone(ep.confidence)]
        if not gray_eps:
            if self.verbose:
                print("  ℹ️ 无灰色地带端点, 跳过LLM枚举")
            return []

        if self.verbose:
            print(f"\n  🧠 LLM枚举: {len(gray_eps)} 个灰色地带端点 → 推断隐藏API...")

        # 2. 构建Prompt
        prompt = self._build_prompt(gray_eps, js_bundle_content)
        if not prompt:
            return []

        # 3. 调用LLM
        candidates = self._call_llm(prompt)
        if not candidates:
            if self.verbose:
                print("  ⚠️ LLM未返回有效候选端点")
            return []

        if self.verbose:
            print(f"  💡 LLM推断出 {len(candidates)} 个候选端点")

        # 4. 验证 (GET/OPTIONS试探)
        verified = self._verify_candidates(candidates, base_url)

        if self.verbose:
            print(f"  ✅ 验证通过: {len(verified)} 个隐藏端点")

        return verified

    def _build_prompt(self, gray_eps: list[ClassifiedEndpoint],
                      js_fragments: str = "") -> str:
        """构建A2A风格的枚举Prompt"""
        # 读取模板
        try:
            template = self.PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            template = self._default_prompt_template()

        # 格式化已知端点列表
        known_lines = []
        for ep in gray_eps:
            known_lines.append(
                f"  - {ep.method} {ep.path} "
                f"(category={ep.category.value}, conf={ep.confidence:.2f})"
            )
        known_text = "\n".join(known_lines) if known_lines else "(none)"

        # JS片段 (截断到4KB)
        js_text = js_fragments[:4000] if js_fragments else "(no JS source available)"

        return template.replace("{known_endpoints}", known_text).replace(
            "{js_fragments}", js_text)

    def _call_llm(self, prompt: str) -> list[dict]:
        """调用LLM (OpenAI-compatible API)"""
        import requests as req

        try:
            resp = req.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system",
                         "content": "You are an API discovery expert. "
                                    "Always respond with valid JSON array only."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
                timeout=30,
            )
            if resp.status_code != 200:
                if self.verbose:
                    print(f"  ⚠️ LLM API error: {resp.status_code} {resp.text[:200]}")
                return []

            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()

            # 提取JSON (可能被markdown包裹)
            return self._parse_llm_json(content)

        except Exception as e:
            if self.verbose:
                print(f"  ⚠️ LLM调用失败: {e}")
            return []

    def _parse_llm_json(self, content: str) -> list[dict]:
        """从LLM响应中提取JSON数组"""
        import re

        # 尝试直接解析
        try:
            result = json.loads(content)
            if isinstance(result, list):
                return result
            if isinstance(result, dict) and "endpoints" in result:
                return result["endpoints"]
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 代码块
        m = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', content)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试提取任何JSON数组
        m = re.search(r'\[[\s\S]*\]', content)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

        if self.verbose:
            print(f"  ⚠️ 无法解析LLM响应: {content[:300]}")
        return []

    def _verify_candidates(self, candidates: list[dict],
                           base_url: str) -> list[ClassifiedEndpoint]:
        """对LLM推断的端点进行HTTP验证"""
        import requests as req
        from urllib.parse import urljoin

        verified = []
        session = req.Session()
        session.headers["User-Agent"] = (
            "Mozilla/5.0 (compatible; PlatformExplorer/1.0)"
        )

        for cand in candidates[:10]:  # 最多验证10个
            path = cand.get("path", "")
            method = cand.get("method", "GET").upper()
            llm_confidence = cand.get("confidence", "medium")
            reasoning = cand.get("reasoning", "")

            if not path:
                continue

            # 构建完整URL
            if base_url and not path.startswith("http"):
                full_url = urljoin(base_url, path)
            else:
                full_url = path

            try:
                # 先用GET试探
                r = session.get(full_url, timeout=10, allow_redirects=False)

                # 验证: 非404/500即认为端点存在
                if r.status_code < 400:
                    conf = {"high": 0.75, "medium": 0.60, "low": 0.45}.get(
                        llm_confidence, 0.55)

                    ep = ClassifiedEndpoint(
                        path=path,
                        method=method,
                        category=APICategory.UNKNOWN,
                        confidence=conf,
                        signals={"llm_enumeration": conf,
                                 "http_verified": 0.80},
                        inferred_from="llm_enumeration",
                        is_hidden=True,
                    )
                    verified.append(ep)

                    if self.verbose:
                        print(f"    ✅ {method} {path} → {r.status_code} "
                              f"(conf={conf:.2f}, {reasoning[:60]})")
                elif self.verbose:
                    print(f"    ❌ {method} {path} → {r.status_code} (排除)")

            except Exception as e:
                if self.verbose:
                    print(f"    ⚠️ {method} {path} → {str(e)[:50]}")

        return verified

    @staticmethod
    def _default_prompt_template() -> str:
        """内置默认Prompt模板 (当模板文件缺失时使用)"""
        return """You are an API discovery expert. Given known API endpoints and JS source, infer hidden endpoints.

## Known Endpoints
{known_endpoints}

## JavaScript Source Fragments
{js_fragments}

## Task
1. Analyze naming patterns in known endpoints
2. Look for API path strings in JS fragments
3. Propose up to 10 hidden endpoints
4. For each: method, path, confidence (high/medium/low), reasoning

## Output Format
Return ONLY a JSON array:
```json
[{{"path": "/api/v1/example", "method": "GET", "confidence": "medium", "reasoning": "..."}}]
```

Only propose plausible endpoints based on evidence. Do not hallucinate."""


# ═══════════════════════════════════════════════════════════════
# L3 主入口
# ═══════════════════════════════════════════════════════════════

def run_l3_classify(
    capture: CaptureResult,
    api_threshold: float = DEFAULT_API_THRESHOLD,
    llm_api_key: str = "",
    llm_model: str = "deepseek-chat",
    llm_base_url: str = "",
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

    # Step 3: LLM 枚举 (Phase 2 — 完整实现)
    enumerator = LLMEnumerator(
        api_key=llm_api_key, model=llm_model,
        base_url=llm_base_url, verbose=verbose)
    hidden = enumerator.enumerate(
        classified,
        js_bundle_content="",  # TODO: 从 l1_js_analyzer 获取
        base_url=capture.base_url,
    )

    # Step 4: 构建 API Catalog
    by_category: dict[str, list[ClassifiedEndpoint]] = defaultdict(list)
    for ep in classified + hidden:
        by_category[ep.category.value].append(ep)

    # 提取API前缀
    from urllib.parse import urlparse as _urlparse
    prefixes = set()
    for ep in classified:
        raw_path = ep.path.split("?")[0]
        # 如果是完整URL, 先提取path部分
        if raw_path.startswith("http"):
            parsed = _urlparse(raw_path)
            path = parsed.path
        else:
            path = raw_path
        parts = [p for p in path.split("/") if p]  # 过滤空段
        # 前缀: 取到 /v1/ 或 /v2/ 或最后一个非数字段之前
        for i, part in enumerate(parts):
            if part in ("v1", "v2", "v3", "api", "graphql"):
                prefix = "/" + "/".join(parts[:i + 1])
                prefixes.add(prefix)
                break
        else:
            # Fallback: 前两段 (如 /personalized-secure-api)
            if len(parts) >= 1:
                prefixes.add("/" + parts[0])

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
