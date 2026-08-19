"""
置信度计算与不确定性传播

借鉴: Vespasian (per-signal confidence scoring)
      A2A论文 (LLM推断置信度标记)
      WALT (validation feedback loop)

五层流水线中每层输出都携带 confidence，最终汇总为整体置信度。
"""

from __future__ import annotations

import math
from typing import Any


# ═══════════════════════════════════════════════════════════════
# 通用置信度工具
# ═══════════════════════════════════════════════════════════════

def weighted_average(scores: list[tuple[float, float]]) -> float:
    """
    加权平均置信度
    :param scores: [(score, weight), ...] — 每个子模块的 (分数, 权重)
    """
    if not scores:
        return 0.0
    total_weight = sum(w for _, w in scores)
    if total_weight == 0:
        return 0.0
    return sum(s * w for s, w in scores) / total_weight


def combine_confidence(*confidences: float, method: str = "min") -> float:
    """
    合并多个子置信度为单一值
    :param method: "min" (保守) | "mean" (平均) | "product" (累积)
    """
    confidences = [c for c in confidences if c > 0]
    if not confidences:
        return 0.0
    if method == "min":
        return min(confidences)
    elif method == "product":
        result = 1.0
        for c in confidences:
            result *= c
        return result
    else:  # mean
        return sum(confidences) / len(confidences)


def is_gray_zone(confidence: float, low: float = 0.50, high: float = 0.70) -> bool:
    """是否处于灰色地带 (需要 LLM 辅助)"""
    return low <= confidence < high


def needs_human_review(confidence: float, threshold: float = 0.60) -> bool:
    """是否需要人工复核"""
    return confidence < threshold


# ═══════════════════════════════════════════════════════════════
# L0: 认证置信度
# ═══════════════════════════════════════════════════════════════

def auth_detection_confidence(
    has_login_form: bool,
    has_username_field: bool,
    has_password_field: bool,
    has_oauth_redirect: bool,
    has_sso_domain: bool,
) -> float:
    """
    认证类型检测置信度
    借鉴 balage-core: ML表单识别 F1=0.93 的思路,
    这里用确定性规则版本 (Phase 1 不引入ML依赖)
    """
    signals = []
    # 表单检测信号
    if has_login_form:
        signals.append(0.7)
    if has_username_field and has_password_field:
        signals.append(0.9)
    elif has_username_field or has_password_field:
        signals.append(0.5)
    # OAuth/SSO 信号
    if has_oauth_redirect:
        signals.append(0.6)
    if has_sso_domain:
        signals.append(0.4)
    # 无认证信号
    if not any([has_login_form, has_username_field, has_password_field,
                has_oauth_redirect, has_sso_domain]):
        return 0.8  # 大概率无认证

    return sum(signals) / max(len(signals), 1)


# ═══════════════════════════════════════════════════════════════
# L3: API 分类置信度 (6信号系统, 借鉴 Vespasian)
# ═══════════════════════════════════════════════════════════════

# Vespasian 默认阈值: 0.50 (可配置)
DEFAULT_API_THRESHOLD = 0.50
HIGH_CONFIDENCE_THRESHOLD = 0.70

# 信号权重 (借鉴 Vespasian REST Classification 5 signals + 教学语义)
SIGNAL_WEIGHTS = {
    "content_type": 0.30,       # application/json → +0.30
    "path_heuristic": 0.20,     # /api/, /v1/, /graphql → +0.20
    "http_method": 0.15,        # POST/PUT/PATCH/DELETE → +0.15
    "response_structure": 0.25, # JSON 对象/数组 → +0.25
    "static_penalty": -0.50,    # .js/.css/.png → -0.50 penalty
    "teaching_semantic": 0.10,  # /lesson/, /step/, /quiz/ → +0.10
}


def classify_api_endpoint(
    content_type: str,
    path: str,
    method: str,
    response_body: Any,
    url_extension: str = "",
) -> tuple[float, dict[str, float]]:
    """
    Vespasian 风格 6 信号分类器

    :returns: (total_confidence, signal_details)
    """
    signals: dict[str, float] = {}

    # 1. Content-Type 信号
    ct_lower = content_type.lower()
    if "application/json" in ct_lower:
        signals["content_type"] = 1.0
    elif "application/xml" in ct_lower or "text/xml" in ct_lower:
        signals["content_type"] = 0.8
    elif "text/html" in ct_lower:
        signals["content_type"] = 0.0  # 页面, 不是API
    elif "multipart/form-data" in ct_lower:
        signals["content_type"] = 0.6  # 上传类API
    else:
        signals["content_type"] = 0.3

    # 2. 路径启发式信号
    path_lower = path.lower()
    api_path_signals = [
        "/api/", "/v1/", "/v2/", "/v3/", "/rest/", "/rpc/",
        "/graphql", "/query", "/mutation",
    ]
    path_score = 0.0
    for sig in api_path_signals:
        if sig in path_lower:
            path_score = max(path_score, 1.0)
            break
    if path_score == 0.0:
        # 检查是否有参数化路径模式
        if any(c.isdigit() for c in path):  # /users/42
            path_score = 0.3
    signals["path_heuristic"] = path_score

    # 3. HTTP 方法信号
    method_upper = method.upper()
    if method_upper in ("POST", "PUT", "PATCH", "DELETE"):
        signals["http_method"] = 0.8
    elif method_upper == "GET":
        # GET 可能是API也可能是页面 — 综合判断
        if path_score > 0.3:
            signals["http_method"] = 0.6
        else:
            signals["http_method"] = 0.3
    else:
        signals["http_method"] = 0.2

    # 4. 响应结构信号
    if isinstance(response_body, dict):
        # JSON 对象 - 强API信号
        if any(k in str(response_body).lower() for k in ["data", "result", "error", "status", "code"]):
            signals["response_structure"] = 0.9
        else:
            signals["response_structure"] = 0.7
    elif isinstance(response_body, list):
        # JSON 数组 - 中等API信号
        signals["response_structure"] = 0.75
    elif isinstance(response_body, str):
        if response_body.strip().startswith(("{", "[")):
            signals["response_structure"] = 0.5   # 可能是JSON字符串
        elif "<html" in response_body.lower()[:200]:
            signals["response_structure"] = 0.0   # HTML页面
        elif len(response_body) < 500:
            signals["response_structure"] = 0.3   # 短文本响应
        else:
            signals["response_structure"] = 0.1
    else:
        signals["response_structure"] = 0.2

    # 5. 静态资源惩罚
    static_extensions = {".js", ".css", ".png", ".jpg", ".jpeg", ".gif",
                         ".svg", ".woff", ".woff2", ".ttf", ".ico", ".map"}
    static_paths = {"/static/", "/assets/", "/public/", "/dist/", "/build/"}
    is_static = False
    if url_extension.lower() in static_extensions:
        is_static = True
    for sp in static_paths:
        if sp in path_lower:
            is_static = True
            break
    signals["static_penalty"] = -0.50 if is_static else 0.0

    # 6. 教学语义信号
    teaching_patterns = {
        "/lesson": 0.5, "/lessons": 0.5, "/step": 0.4, "/steps": 0.4,
        "/phase": 0.5, "/phases": 0.5, "/quiz": 0.7, "/exam": 0.7,
        "/chat": 0.9, "/agent": 0.9, "/ai": 0.7, "/course": 0.5,
        "/progress": 0.6, "/profile": 0.5, "/knowledge": 0.6,
        "/search": 0.5, "/answer": 0.8, "/submit": 0.7,
    }
    teaching_score = 0.0
    for pattern, score in teaching_patterns.items():
        if pattern in path_lower:
            teaching_score = max(teaching_score, score)
    signals["teaching_semantic"] = teaching_score

    # 计算总分 (加权)
    total = 0.0
    for signal_name, weight in SIGNAL_WEIGHTS.items():
        signal_val = signals.get(signal_name, 0.0)
        if weight < 0:  # penalty
            total += signal_val  # signal_val is already negative
        else:
            total += signal_val * weight

    # Clamp to [0, 1]
    total = max(0.0, min(1.0, total))

    return total, signals


def classify_api_category(
    path: str,
    method: str,
    request_payload: dict | None,
    response_body: Any,
) -> tuple[str, float]:
    """
    对已确认的API端点进行细粒度分类
    :returns: (category_name, confidence)
    """
    path_lower = path.lower()
    scores: dict[str, float] = {}

    # Agent 对话
    agent_patterns = ["/chat", "/agent", "/conversation", "/message", "/ask", "/reply",
                      "/digital-teacher", "/ai-tutor", "/assistant", "/coach", "/tutor"]
    if any(p in path_lower for p in agent_patterns):
        scores["agent"] = 0.85
    elif method.upper() == "POST" and request_payload:
        payload_str = str(request_payload).lower()
        if any(k in payload_str for k in ["message", "question", "prompt", "query"]):
            scores["agent"] = 0.6

    # Quiz
    quiz_patterns = ["/quiz", "/exam", "/test", "/question", "/answer", "/submit"]
    if any(p in path_lower for p in quiz_patterns):
        scores["quiz"] = 0.85

    # 进度
    progress_patterns = ["/progress", "/complete", "/checkpoint", "/unlock"]
    if any(p in path_lower for p in progress_patterns):
        scores["progress"] = 0.85

    # 认证
    auth_patterns = ["/auth", "/login", "/logout", "/register", "/token", "/session"]
    if any(p in path_lower for p in auth_patterns):
        scores["auth"] = 0.90

    # 内容
    content_patterns = ["/phase", "/lesson", "/step", "/course", "/curriculum", "/syllabus"]
    if any(p in path_lower for p in content_patterns):
        scores["content"] = 0.80

    # Profile
    profile_patterns = ["/profile", "/user", "/student", "/me", "/account"]
    if any(p in path_lower for p in profile_patterns):
        scores["profile"] = 0.80

    # 搜索
    search_patterns = ["/search", "/knowledge", "/kb", "/faq", "/lookup"]
    if any(p in path_lower for p in search_patterns):
        scores["search"] = 0.80

    # 事件
    event_patterns = ["/event", "/track", "/analytics", "/log", "/beacon"]
    if any(p in path_lower for p in event_patterns):
        scores["event"] = 0.80

    if not scores:
        return ("unknown", 0.3)

    best_category = max(scores, key=scores.get)
    return (best_category, scores[best_category])


# ═══════════════════════════════════════════════════════════════
# L2: Step 类型分类置信度
# ═══════════════════════════════════════════════════════════════

# DOM 元素 → StepType 映射规则
STEP_TYPE_INDICATORS = {
    "video": {
        "elements": ["video", "player", "youtube", "bilibili", "vimeo", "watch",
                     "lecture", "播放器",
                     "iframe[src*='youtube']", "iframe[src*='bilibili']",
                     "iframe[src*='vimeo']", "[class*='player']", "[class*='video']"],
        "keywords": ["视频", "播放", "video", "watch", "观看", "player", "lecture",
                     "youtube", "bilibili"],
        "weight": 0.90,
    },
    "coding": {
        "elements": ["monaco", "codemirror", "ace_editor", "code-editor",
                     "ide", "editor", "code", "terminal", "console", "run",
                     "python", "javascript", "java", "debug",
                     ".monaco-editor", ".CodeMirror", ".ace_editor",
                     "[class*='code-editor']", "[class*='ide']", "textarea[class*='code']"],
        "keywords": ["代码", "编程", "code", "editor", "运行", "run", "compile",
                     "debug", "console", "terminal", "python", "javascript"],
        "weight": 0.90,
    },
    "quiz": {
        "elements": ["radio", "checkbox", "quiz", "question", "choice",
                     "answer", "select", "option", "multiple-choice",
                     "input[type='radio']", "input[type='checkbox']",
                     "[class*='quiz']", "[class*='question']", "[class*='choice']",
                     "select[class*='answer']"],
        "keywords": ["题目", "选择", "quiz", "question", "正确", "answer", "test",
                     "考试", "测评"],
        "weight": 0.85,
    },
    "chat": {
        "elements": ["chat", "message", "conversation", "agent", "assistant",
                     "dialog", "bot", "coach", "tutor", "ai",
                     "[class*='chat']", "[class*='message']", "[class*='conversation']",
                     "[class*='agent']", "[class*='assistant']", "[class*='dialog']"],
        "keywords": ["对话", "聊天", "chat", "agent", "助手", "AI", "message",
                     "conversation", "assistant", "coach"],
        "weight": 0.85,
    },
    "upload": {
        "elements": ["upload", "file", "dropzone", "drop",
                     "input[type='file']", "[class*='upload']", "[class*='dropzone']"],
        "keywords": ["上传", "提交", "upload", "submit", "file", "附件", "作业"],
        "weight": 0.80,
    },
    "reading": {
        "elements": ["article", "content", "markdown", "document", "text", "reading",
                     "paragraph", "section", "material",
                     "article", "[class*='content']", "[class*='markdown']",
                     "[class*='article']", "[class*='document']"],
        "keywords": ["阅读", "文档", "材料", "read", "document", "说明", "text",
                     "content", "article"],
        "weight": 0.70,  # reading 是默认类型, 权重最低
    },
}


# ── URL 模式 → StepType 强映射 ──
URL_PATTERN_INDICATORS = {
    "video": {"patterns": ["/video", "/watch", "/player", "/lecture"],
              "weight": 0.85},
    "coding": {"patterns": ["/code", "/ide", "/editor", "/practice", "/exercise",
                            "/lab", "/programming"],
               "weight": 0.85},
    "quiz": {"patterns": ["/quiz", "/exam", "/test", "/question", "/answer",
                          "/assessment", "/evaluate"],
             "weight": 0.85},
    "chat": {"patterns": ["/chat", "/agent", "/assistant", "/tutor", "/coach",
                          "/conversation", "/message", "/ask"],
             "weight": 0.85},
    "upload": {"patterns": ["/upload", "/submit", "/assignment", "/file",
                            "/homework"],
               "weight": 0.80},
    "reading": {"patterns": ["/lesson", "/course", "/module", "/content",
                             "/material", "/read", "/document", "/article",
                             "/phase", "/step", "/chapter", "/topic"],
                "weight": 0.75},
}


def classify_step_type(
    dom_elements: list[str],
    text_content: str,
    page_title: str = "",
    page_url: str = "",
) -> tuple[str, float]:
    """
    基于 DOM元素 + 文本 + URL模式 多信号推断 Step 类型
    :returns: (step_type, confidence)
    """
    dom_lower = " ".join(dom_elements).lower()
    text_lower = (text_content + " " + page_title).lower()
    combined = dom_lower + " " + text_lower
    url_lower = page_url.lower()

    scores: dict[str, float] = {}
    signal_counts: dict[str, int] = {}  # 每个类型有多少信号命中

    for step_type, indicators in STEP_TYPE_INDICATORS.items():
        element_score = 0.0
        keyword_score = 0.0
        url_score = 0.0
        signals_hit = 0

        # 信号1: DOM 元素匹配 (权重 0.50)
        # 规范化匹配: 忽略引号差异 (input[type='radio'] vs input[type=radio])
        dom_normalized = dom_lower.replace("'", "").replace('"', "")
        for elem_pattern in indicators["elements"]:
            pattern_normalized = elem_pattern.lower().replace("'", "").replace('"', "")
            if pattern_normalized in dom_normalized:
                element_score = max(element_score, 1.0)
                break

        # 信号2: 关键词匹配 (权重 0.30)
        keyword_hits = 0
        for kw in indicators["keywords"]:
            if kw.lower() in combined:
                keyword_hits += 1
        if indicators["keywords"]:
            keyword_score = keyword_hits / len(indicators["keywords"])

        # 信号3: URL 模式匹配 (权重 0.20)
        url_info = URL_PATTERN_INDICATORS.get(step_type, {})
        if url_info and url_lower:
            for pat in url_info.get("patterns", []):
                if pat.lower() in url_lower:
                    url_score = url_info.get("weight", 0.7)
                    break

        # 计数命中的信号
        if element_score >= 1.0:
            signals_hit += 1
        if keyword_score > 0.15:
            signals_hit += 1
        if url_score > 0:
            signals_hit += 1

        signal_counts[step_type] = signals_hit

        # 综合评分
        if element_score > 0:
            # DOM元素是强信号
            scores[step_type] = 0.50 * element_score + 0.25 * keyword_score + 0.25 * url_score
        elif url_score > 0:
            # URL模式是中等信号
            scores[step_type] = 0.40 * url_score + 0.30 * keyword_score + 0.30 * 0.1
        else:
            # 仅关键词
            scores[step_type] = 0.30 * keyword_score + 0.10 * 0.1

    if not scores:
        return ("unknown", 0.2)

    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]
    signals_for_best = signal_counts.get(best_type, 0)

    # ── 多信号共识：提升置信度 ──
    if signals_for_best >= 3:
        best_score = min(1.0, best_score * 1.15)  # 3信号全中 +15%
    elif signals_for_best >= 2:
        best_score = min(1.0, best_score * 1.08)  # 2信号 +8%

    # 如果最高分太低, 默认 reading
    if best_score < 0.3:
        return ("reading", 0.4)

    # 对 reading 类型, 当有其他更强候选时降权
    if best_type == "reading":
        runner_up = sorted(
            [(t, s) for t, s in scores.items() if t != "reading"],
            key=lambda x: x[1], reverse=True)
        if runner_up and runner_up[0][1] > best_score * 0.8:
            # 仅reading信号略强, 降低置信度
            best_score *= 0.7

    return (best_type, min(best_score, 1.0))


# ═══════════════════════════════════════════════════════════════
# L4: 整体置信度汇总
# ═══════════════════════════════════════════════════════════════

def compute_overall_confidence(
    auth_conf: float,
    structure_conf: float,
    step_type_conf: float,
    api_conf: float,
) -> dict[str, Any]:
    """
    汇总五层流水线的整体置信度
    权重: L0(auth)=0.15, L2(structure)=0.35, L2(step_types)=0.25, L3(api)=0.25
    """
    weights = {
        "auth": 0.15,
        "structure": 0.35,
        "step_types": 0.25,
        "apis": 0.25,
    }

    overall = (
        weights["auth"] * auth_conf +
        weights["structure"] * structure_conf +
        weights["step_types"] * step_type_conf +
        weights["apis"] * api_conf
    )

    # 找出需要人工复核的字段
    needs_review: list[str] = []
    if needs_human_review(auth_conf):
        needs_review.append("auth")
    if needs_human_review(structure_conf):
        needs_review.append("structure")
    if needs_human_review(step_type_conf):
        needs_review.append("step_types")
    if needs_human_review(api_conf):
        needs_review.append("apis")

    return {
        "overall": round(overall, 2),
        "auth": round(auth_conf, 2),
        "structure": round(structure_conf, 2),
        "step_types": round(step_type_conf, 2),
        "apis": round(api_conf, 2),
        "fields_needing_human_review": needs_review,
    }
