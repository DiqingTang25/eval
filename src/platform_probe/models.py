"""
Platform Explorer 数据模型

所有 dataclass 定义，涵盖 L0~L4 五层的输入/输出结构。
借鉴: Vespasian (capture.json), WALT (ToolCandidate), Unbrowse (RouteNode)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


# ═══════════════════════════════════════════════════════════════
# 枚举类型
# ═══════════════════════════════════════════════════════════════

class AuthType(str, Enum):
    FORM = "form"
    OAUTH = "oauth"
    SSO = "sso"
    MFA = "mfa"
    NONE = "none"
    UNKNOWN = "unknown"


class StepType(str, Enum):
    VIDEO = "video"
    QUIZ = "quiz"
    CODING = "coding"
    READING = "reading"
    CHAT = "chat"
    UPLOAD = "upload"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class APICategory(str, Enum):
    CONTENT = "content"       # 内容类: Phase/Lesson/Step 数据
    AGENT = "agent"           # AI Agent 对话
    QUIZ = "quiz"             # 测验/考试
    PROGRESS = "progress"     # 进度追踪
    AUTH = "auth"             # 认证
    PROFILE = "profile"       # 用户画像
    SEARCH = "search"         # 搜索/知识库
    EVENT = "event"           # 埋点/事件追踪
    UNKNOWN = "unknown"


class Framework(str, Enum):
    REACT = "react"
    VUE = "vue"
    ANGULAR = "angular"
    NEXT = "next"
    UNKNOWN = "unknown"


# ═══════════════════════════════════════════════════════════════
# L0: 认证与会话
# ═══════════════════════════════════════════════════════════════

@dataclass
class AuthField:
    """登录表单字段"""
    name: str                # 字段名 (username, password, captcha...)
    type: str                # HTML input type (text, password, ...)
    label: str               # 显示标签
    required: bool = True
    placeholder: str = ""


@dataclass
class AuthSchema:
    """认证方式描述 (凭证已脱敏, 运行时从环境变量注入)"""
    type: AuthType
    login_url: str
    login_method: str = "POST"
    fields: list[AuthField] = field(default_factory=list)
    token_location: str = "header"       # header | cookie | body
    token_key: str = "Authorization"
    token_prefix: str = "Bearer "
    has_captcha: bool = False
    has_mfa: bool = False
    notes: str = ""                      # 人工备注


@dataclass
class SessionState:
    """会话状态"""
    storage_state_path: str              # Playwright storage_state JSON 路径
    jwt_token: Optional[str] = None
    jwt_expiry: Optional[str] = None
    cookies_count: int = 0
    logged_in: bool = False


# ═══════════════════════════════════════════════════════════════
# L1: 流量与结构捕获
# ═══════════════════════════════════════════════════════════════

@dataclass
class RouteNode:
    """捕获到的一个 HTTP 请求 (借鉴 Unbrowse RouteNode)"""
    url: str
    method: str                          # GET/POST/PUT/DELETE/PATCH
    status: int
    content_type: str = ""
    request_headers: dict = field(default_factory=dict)
    request_payload: Any = None
    response_headers: dict = field(default_factory=dict)
    response_sample: Any = None          # 响应体摘要 (截断)
    response_size: int = 0
    duration_ms: float = 0.0
    parent_url: Optional[str] = None     # 从哪个页面触发
    initiator_type: str = ""             # xhr/fetch/document/script


@dataclass
class PageSnapshot:
    """页面快照 (借鉴 Explorbot Research 输出)"""
    url: str
    title: str
    dom_summary: str                     # ARIA 可访问性树摘要 (截断到2KB)
    text_content: str                    # 页面主要文本 (截断到5KB)
    interactive_elements: list[dict] = field(default_factory=list)
    # [{role, tag, text, selector, semantic_hint}]
    screenshot_path: str = ""
    framework_hints: list[str] = field(default_factory=list)
    # ["react_root", "antd_components", "vue_app"]


@dataclass
class CaptureResult:
    """L1 层完整输出 (借鉴 Vespasian capture.json)"""
    base_url: str
    start_url: str
    routes: list[RouteNode] = field(default_factory=list)
    pages: list[PageSnapshot] = field(default_factory=list)
    url_graph: dict[str, list[str]] = field(default_factory=dict)
    # {parent_url: [child_urls]} — 导航关系图
    har_path: str = ""                   # HAR 文件路径
    total_requests: int = 0
    api_requests: int = 0
    static_requests: int = 0


# ═══════════════════════════════════════════════════════════════
# L2: 交互元素与教学结构
# ═══════════════════════════════════════════════════════════════

@dataclass
class InteractionElement:
    """交互元素 (借鉴 KaBOOM semantic selectors + WALT element hashes)"""
    role: str                            # button/link/input/select/modal_trigger
    semantic: str                        # 语义描述 (如 "帮帮我按钮")
    selector: str                        # 主 CSS selector
    alternative_selectors: list[str] = field(default_factory=list)
    stable_hash: str = ""                # WALT 风格的元素 hash
    scope: str = ""                      # KaBOOM scope (iframe/modal/sidebar)
    is_agent_trigger: bool = False       # 是否触发 AI Agent


@dataclass
class StepInfo:
    """单个 Step 信息 (借鉴 WALT ToolCandidate)"""
    id: str
    title: str
    type: StepType = StepType.UNKNOWN
    type_confidence: float = 0.0
    lesson_id: str = ""
    order_index: int = 0
    interaction_elements: list[InteractionElement] = field(default_factory=list)
    completion_trigger: Optional[dict] = None
    # {type: "button_click"|"api_call"|"auto", selector: "...", api_path: "..."}
    prerequisite_step_ids: list[str] = field(default_factory=list)
    estimated_duration_minutes: int = 0


@dataclass
class LessonInfo:
    """课时信息"""
    id: str
    name: str
    phase_id: str = ""
    order: int = 0
    step_count: int = 0
    topics: list[str] = field(default_factory=list)
    prerequisite_lesson_ids: list[str] = field(default_factory=list)


@dataclass
class PhaseInfo:
    """阶段信息"""
    id: str
    name: str
    order: int = 0
    lesson_count: int = 0


@dataclass
class TeachingStructure:
    """教学结构 (L2 核心输出)"""
    hierarchy: list[str] = field(default_factory=list)  # ["course","phase","lesson","step"]
    phases: list[PhaseInfo] = field(default_factory=list)
    lessons: list[LessonInfo] = field(default_factory=list)
    steps: list[StepInfo] = field(default_factory=list)
    framework: Framework = Framework.UNKNOWN
    confidence: float = 0.0
    # 导航模式
    navigation_patterns: list[dict] = field(default_factory=list)
    # [{type: "sidebar_tree"|"breadcrumb"|"step_sequence"|"tab_bar", selector: "..."}]


# ═══════════════════════════════════════════════════════════════
# L3: API分类与推断
# ═══════════════════════════════════════════════════════════════

@dataclass
class ClassifiedEndpoint:
    """分类后的 API 端点 (借鉴 Vespasian Classifier 输出)"""
    path: str
    method: str
    category: APICategory = APICategory.UNKNOWN
    confidence: float = 0.0
    signals: dict[str, float] = field(default_factory=dict)
    # {content_type: 0.3, path_heuristic: 0.2, method: 0.15, ...}
    parameters: dict[str, Any] = field(default_factory=dict)
    # {query: {name: type}, body: {name: type}, path: {name: type}}
    response_schema: Optional[dict] = None  # 推断的 JSON Schema
    inferred_from: str = ""                # "traffic" | "llm_enumeration" | "js_bundle" | "dom_form"
    is_hidden: bool = False                # 是否 LLM 推断的隐藏端点
    sample_request: Optional[dict] = None
    sample_response: Optional[dict] = None


@dataclass
class APICatalog:
    """API 端点完整清单 (L3 核心输出)"""
    endpoints: list[ClassifiedEndpoint] = field(default_factory=list)
    by_category: dict[str, list[ClassifiedEndpoint]] = field(default_factory=dict)
    # {"content": [...], "agent": [...], "quiz": [...], ...}
    prefixes: list[str] = field(default_factory=list)
    # ["/api/v1", "/phase3-api"]
    graphql_endpoints: list[str] = field(default_factory=list)
    websocket_endpoints: list[str] = field(default_factory=list)
    total_found: int = 0
    llm_inferred_count: int = 0           # LLM枚举发现的数量


@dataclass
class StepCatalog:
    """Step 清单 (L3 输出, L2 + L3 融合)"""
    steps: list[StepInfo] = field(default_factory=list)
    type_distribution: dict[str, int] = field(default_factory=dict)
    # {video: 15, quiz: 23, coding: 8, reading: 45, chat: 3}


# ═══════════════════════════════════════════════════════════════
# L4: Schema 生成与验证
# ═══════════════════════════════════════════════════════════════

@dataclass
class AgentInteraction:
    """Agent 交互模式描述"""
    chat_endpoint: str = ""
    method: str = "POST"
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    triggers: list[dict] = field(default_factory=list)
    # [{type: "element", semantic: "帮帮我", role: "help_button"}, {type: "auto", event: "quiz_completed"}]
    context_fields: list[str] = field(default_factory=list)
    # 调用时传递的上下文字段


@dataclass
class ConfidenceReport:
    """置信度报告 (借鉴 Vespasian confidence scoring)"""
    overall: float = 0.0
    structure: float = 0.0
    step_types: float = 0.0
    apis: float = 0.0
    auth: float = 0.0
    fields_needing_human_review: list[str] = field(default_factory=list)
    # ["steps[3].type", "apis[5].category"]


@dataclass
class ExplorationReport:
    """探索报告 (L4 最终输出之一, 给人类阅读)"""
    target_url: str
    timestamp: str
    duration_seconds: float
    phases_found: int
    lessons_found: int
    steps_found: int
    api_endpoints_found: int
    hidden_endpoints_found: int
    confidence: ConfidenceReport = field(default_factory=ConfidenceReport)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class PlatformSchema:
    """平台完整 Schema (L4 最终输出, 写入 platform_schema.yaml)"""
    schema_version: str = "1.0"
    generated_by: str = "platform_probe"
    exploration_timestamp: str = ""
    target_url: str = ""
    platform: dict = field(default_factory=dict)
    auth: dict = field(default_factory=dict)
    structure: dict = field(default_factory=dict)
    apis: dict[str, list[dict]] = field(default_factory=dict)
    agent: dict = field(default_factory=dict)
    navigation: dict = field(default_factory=dict)
    confidence_scores: dict = field(default_factory=dict)
