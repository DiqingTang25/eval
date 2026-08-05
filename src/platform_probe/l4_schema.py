"""
L4: Schema生成与验证层 (Schema Generation & Validation)

借鉴: Vespasian Generator (OpenAPI 3.0 生成)
      WALT Tool Registration (验证循环)
      Unbrowse Skill Packaging (凭证脱敏 + 版本管理)

职责:
  1. 汇总 L0~L3 输出 → 生成 platform_schema.yaml
  2. 自动脱敏凭证 (token/password/cookies)
  3. 验证 Schema 正确性 (重放关键API + 漂移检测)
输出: platform_schema.yaml + exploration_report.md
"""

from __future__ import annotations

import json
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .models import (
    AuthSchema, SessionState, CaptureResult,
    APICatalog, StepCatalog, TeachingStructure,
    AgentInteraction, ConfidenceReport, ExplorationReport,
    PlatformSchema, ClassifiedEndpoint,
)
from .confidence import compute_overall_confidence


# ═══════════════════════════════════════════════════════════════
# 凭证脱敏器
# ═══════════════════════════════════════════════════════════════

class Redactor:
    """
    凭证脱敏器

    借鉴 Unbrowse: credentials encrypted locally, never published
    Phase 1 简单替换方案; Phase 2 可升级为加密存储

    脱敏规则:
      - token / access_token / api_key / jwt → <REDACTED>
      - password / passwd / pwd / secret → <REDACTED>
      - cookie → <REDACTED>
      - Authorization header → <REDACTED>
    """

    SENSITIVE_KEYS = {
        "token", "access_token", "refresh_token", "api_key", "apikey",
        "jwt", "bearer", "authorization",
        "password", "passwd", "pwd", "secret", "private_key",
        "cookie", "set-cookie", "session", "sessionid",
        "x-api-key", "x-auth-token",
    }

    @classmethod
    def redact_dict(cls, data: dict, depth: int = 0) -> dict:
        """递归脱敏字典"""
        if depth > 10:
            return data

        result = {}
        for key, value in data.items():
            if cls._is_sensitive(key):
                result[key] = "<REDACTED>"
            elif isinstance(value, dict):
                result[key] = cls.redact_dict(value, depth + 1)
            elif isinstance(value, list):
                result[key] = [
                    cls.redact_dict(v, depth + 1) if isinstance(v, dict) else v
                    for v in value
                ]
            elif isinstance(value, str) and cls._looks_like_token(value):
                result[key] = "<REDACTED>"
            else:
                result[key] = value
        return result

    @classmethod
    def redact_yaml(cls, yaml_str: str) -> str:
        """对 YAML 字符串内容进行脱敏"""
        import re
        # 替换常见的 token 模式
        patterns = [
            (r'(token|api_key|apikey|jwt|bearer|secret)\s*:\s*["\']?[^\s"\']+["\']?',
             r'\1: "<REDACTED>"'),
            (r'(password|passwd|pwd)\s*:\s*["\']?[^\s"\']+["\']?',
             r'\1: "<REDACTED>"'),
            (r'Authorization\s*:\s*["\']?[^\s"\']+["\']?',
             r'Authorization: "<REDACTED>"'),
        ]
        for pattern, replacement in patterns:
            yaml_str = re.sub(pattern, replacement, yaml_str,
                              flags=re.IGNORECASE)
        return yaml_str

    @staticmethod
    def _is_sensitive(key: str) -> bool:
        key_lower = key.lower().replace("-", "_").replace(" ", "_")
        return key_lower in Redactor.SENSITIVE_KEYS

    @staticmethod
    def _looks_like_token(value: str) -> bool:
        """启发式判断是否像 token"""
        if len(value) < 20:
            return False
        # JWT 格式: xxx.yyy.zzz
        if value.count(".") == 2 and all(
            len(part) > 5 for part in value.split(".")
        ):
            return True
        # 长 hex/base64 字符串
        if len(value) > 40 and all(
            c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=_-"
            for c in value
        ):
            return True
        return False


# ═══════════════════════════════════════════════════════════════
# Schema 生成器
# ═══════════════════════════════════════════════════════════════

class SchemaGenerator:
    """
    Schema 生成器

    汇总 L0~L3 输出, 生成 platform_schema.yaml
    借鉴 Vespasian Generator: OpenAPI 3.0 格式启发
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def generate(
        self,
        target_url: str,
        auth_schema: AuthSchema,
        capture: CaptureResult,
        api_catalog: APICatalog,
        step_catalog: StepCatalog,
        confidence: dict,
    ) -> PlatformSchema:
        """生成完整的平台 Schema"""

        # ── 平台信息 ──
        frameworks = set()
        for page in capture.pages:
            for hint in page.framework_hints:
                if hint != "unknown":
                    frameworks.add(hint)

        platform_info = {
            "name": "auto-detected",
            "framework": list(frameworks)[0] if frameworks else "unknown",
            "spa": self._detect_spa(capture),
            "api_prefixes": api_catalog.prefixes,
        }

        # ── 认证 ──
        auth_info = {
            "type": auth_schema.type.value,
            "login_url": auth_schema.login_url,
            "login_method": auth_schema.login_method,
            "fields": [
                {"name": f.name, "type": f.type, "label": f.label}
                for f in auth_schema.fields
            ],
            "token_location": auth_schema.token_location,
            "token_key": auth_schema.token_key,
            "token_prefix": auth_schema.token_prefix,
            "has_captcha": auth_schema.has_captcha,
            "has_mfa": auth_schema.has_mfa,
        }

        # ── Agent 交互 ──
        agent_info = self._infer_agent_interaction(api_catalog)

        # ── 导航模式 ──
        nav_patterns = self._infer_navigation_patterns(capture)

        # ── API 端点 ──
        apis = self._format_apis(api_catalog)

        # ── 构建 Schema ──
        schema = PlatformSchema(
            schema_version="1.0",
            generated_by="platform_probe v0.1",
            exploration_timestamp=datetime.now(timezone.utc).isoformat(),
            target_url=target_url,
            platform=platform_info,
            auth=auth_info,
            structure={
                "hierarchy": ["phase", "lesson", "step"],  # Phase 1 默认层次
                "phases": [],
                "lessons": [],
                "steps": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "type": s.type.value,
                        "type_confidence": s.type_confidence,
                        "order_index": s.order_index,
                        "interaction_elements": [
                            {
                                "role": e.role,
                                "selector": e.selector,
                                "semantic": e.semantic,
                                "stable_hash": e.stable_hash,
                            }
                            for e in s.interaction_elements[:10]
                        ],
                    }
                    for s in step_catalog.steps
                ],
            },
            apis=apis,
            agent=agent_info,
            navigation={"patterns": nav_patterns},
            confidence_scores=confidence,
        )

        return schema

    def _detect_spa(self, capture: CaptureResult) -> bool:
        """检测是否为 SPA"""
        # 启发式: 如果大部分页面路由没有 .html 扩展名 → SPA
        spa_count = 0
        for page in capture.pages:
            path = page.url.split("?")[0]
            if not any(path.endswith(ext) for ext in [".html", ".htm", ".php"]):
                spa_count += 1
        return spa_count > max(len(capture.pages) * 0.5, 1)

    def _infer_agent_interaction(self, api_catalog: APICatalog) -> dict:
        """推断 Agent 交互模式"""
        agent_eps = api_catalog.by_category.get("agent", [])
        chat_eps = [ep for ep in api_catalog.endpoints
                    if "chat" in ep.path.lower() or "agent" in ep.path.lower()]

        all_agent_eps = agent_eps + chat_eps

        if not all_agent_eps:
            return {
                "chat_endpoint": "",
                "method": "POST",
                "triggers": [],
                "context_fields": [],
            }

        # 取置信度最高的
        best = max(all_agent_eps, key=lambda e: e.confidence)

        return {
            "chat_endpoint": best.path,
            "method": best.method,
            "input_schema": best.parameters.get("body", {}),
            "output_schema": best.response_schema or {},
            "triggers": [
                {"type": "element", "semantic": "帮帮我按钮", "role": "help_button"},
                {"type": "element", "semantic": "我卡住了按钮", "role": "stuck_button"},
            ],
            "context_fields": ["lesson_id", "step_id", "conversation_id"],
        }

    def _infer_navigation_patterns(self, capture: CaptureResult) -> list[dict]:
        """推断导航模式"""
        patterns = []

        # 从页面间链接关系推断
        url_graph = capture.url_graph
        if url_graph:
            # 检查是否有清晰的层次结构
            depth_dist = self._compute_depth_distribution(url_graph, capture.start_url)
            if max(depth_dist.values(), default=0) >= 2:
                patterns.append({
                    "type": "hierarchical",
                    "depth_distribution": depth_dist,
                })

        # 从交互元素推断
        for page in capture.pages:
            for el in page.interactive_elements:
                hint = el.get("semantic_hint", "")
                if hint in ("next_step", "prev_step"):
                    if not any(p["type"] == "step_sequence" for p in patterns):
                        patterns.append({
                            "type": "step_sequence",
                            "has_prev_next": True,
                            "evidence_url": page.url,
                        })
                if hint == "help_button":
                    if not any(p["type"] == "agent_sidebar" for p in patterns):
                        patterns.append({
                            "type": "agent_sidebar",
                            "trigger_selector": el.get("selector", ""),
                            "evidence_url": page.url,
                        })

        return patterns

    def _compute_depth_distribution(
        self, url_graph: dict, start_url: str
    ) -> dict[int, int]:
        """计算URL树的深度分布"""
        depths: dict[str, int] = {start_url: 0}
        queue = [start_url]

        while queue:
            current = queue.pop(0)
            current_depth = depths[current]
            for child in url_graph.get(current, []):
                if child not in depths:
                    depths[child] = current_depth + 1
                    queue.append(child)

        dist: dict[int, int] = {}
        for d in depths.values():
            dist[d] = dist.get(d, 0) + 1
        return dist

    def _format_apis(self, api_catalog: APICatalog) -> dict[str, list[dict]]:
        """格式化 API 端点列表"""
        formatted: dict[str, list[dict]] = {}

        for category, endpoints in api_catalog.by_category.items():
            formatted[category] = []
            for ep in endpoints:
                formatted[category].append({
                    "path": ep.path,
                    "method": ep.method,
                    "confidence": round(ep.confidence, 2),
                    "parameters": ep.parameters,
                    "response_schema": ep.response_schema,
                    "inferred_from": ep.inferred_from,
                    "is_hidden": ep.is_hidden,
                })

        return formatted


# ═══════════════════════════════════════════════════════════════
# Schema 验证器
# ═══════════════════════════════════════════════════════════════

class SchemaValidator:
    """
    Schema 验证器

    Phase 1: 基础检查 (字段完整性 + 格式正确性)
    Phase 2: API 重放验证 + Schema 漂移检测
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def validate(self, schema: PlatformSchema) -> tuple[bool, list[str]]:
        """
        验证 Schema 完整性和正确性
        :returns: (is_valid, warnings)
        """
        warnings = []

        # 必要字段检查
        if not schema.target_url:
            warnings.append("缺少 target_url")
        if not schema.auth.get("type"):
            warnings.append("缺少 auth.type")
        if not schema.platform.get("framework"):
            warnings.append("缺少 platform.framework")

        # API端点检查
        total_apis = sum(len(v) for v in schema.apis.values())
        if total_apis == 0:
            warnings.append("未发现任何API端点 (可能是探索不充分)")

        # Step检查
        steps = schema.structure.get("steps", [])
        if len(steps) == 0:
            warnings.append("未发现任何Step (可能是教学结构推断失败)")

        # 置信度检查
        confidence = schema.confidence_scores
        if confidence.get("overall", 0) < 0.5:
            warnings.append(f"整体置信度过低: {confidence.get('overall', 0)}")

        needs_review = confidence.get("fields_needing_human_review", [])
        if needs_review:
            warnings.append(f"以下字段需要人工复核: {needs_review}")

        is_valid = len([w for w in warnings if "缺少" in w or "失败" in w]) == 0

        if self.verbose:
            status = "✅" if is_valid else "⚠️"
            print(f"\n  {status} Schema 验证: {'通过' if is_valid else '有警告'}")
            for w in warnings:
                print(f"     {'❌' if '缺少' in w else '⚠️'} {w}")

        return is_valid, warnings


# ═══════════════════════════════════════════════════════════════
# L4 主入口
# ═══════════════════════════════════════════════════════════════

def run_l4_schema(
    target_url: str,
    auth_schema: AuthSchema,
    capture: CaptureResult,
    api_catalog: APICatalog,
    step_catalog: StepCatalog,
    output_dir: Path,
    verbose: bool = True,
) -> tuple[PlatformSchema, ExplorationReport, str]:
    """
    L4 完整流程: 生成 → 脱敏 → 验证 → 报告

    :returns: (schema, report, yaml_path)
    """
    if verbose:
        print(f"\n{'='*60}")
        print(f"L4: Schema生成与验证")
        print(f"{'='*60}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: 计算整体置信度
    structure_conf = 0.5  # Phase 1: L2未完整实现, 给默认值
    step_type_conf = sum(s.type_confidence for s in step_catalog.steps)
    step_type_conf = step_type_conf / max(len(step_catalog.steps), 1)

    api_conf = sum(ep.confidence for ep in api_catalog.endpoints)
    api_conf = api_conf / max(len(api_catalog.endpoints), 1)

    confidence = compute_overall_confidence(
        auth_conf=0.95,   # Phase 1 认证检测较可靠
        structure_conf=structure_conf,
        step_type_conf=step_type_conf,
        api_conf=api_conf,
    )

    # Step 2: 生成 Schema
    generator = SchemaGenerator(verbose=verbose)
    schema = generator.generate(
        target_url=target_url,
        auth_schema=auth_schema,
        capture=capture,
        api_catalog=api_catalog,
        step_catalog=step_catalog,
        confidence=confidence,
    )

    # Step 3: 脱敏
    # 将 schema 转换为 dict, 脱敏, 再写回
    schema_dict = _schema_to_dict(schema)
    schema_dict = Redactor.redact_dict(schema_dict)

    # Step 4: 写入 YAML
    yaml_path = output_dir / "platform_schema.yaml"
    yaml_content = yaml.dump(schema_dict, allow_unicode=True,
                             default_flow_style=False, sort_keys=False)
    # 二次脱敏 (针对 YAML 字符串级别的 token 模式)
    yaml_content = Redactor.redact_yaml(yaml_content)
    yaml_path.write_text(yaml_content, encoding="utf-8")

    # Step 5: 验证
    validator = SchemaValidator(verbose=verbose)
    is_valid, warnings = validator.validate(schema)

    # Step 6: 生成探索报告
    report = ExplorationReport(
        target_url=target_url,
        timestamp=datetime.now(timezone.utc).isoformat(),
        duration_seconds=0,  # 由 explorer 填充
        phases_found=len(schema.structure.get("phases", [])),
        lessons_found=len(schema.structure.get("lessons", [])),
        steps_found=len(schema.structure.get("steps", [])),
        api_endpoints_found=api_catalog.total_found,
        hidden_endpoints_found=api_catalog.llm_inferred_count,
        warnings=warnings,
        recommendations=_generate_recommendations(schema, warnings),
    )

    # 写入报告
    report_path = output_dir / "exploration_report.md"
    report_path.write_text(_format_report_md(report, schema), encoding="utf-8")

    if verbose:
        print(f"\n  📄 Schema: {yaml_path}")
        print(f"  📄 报告: {report_path}")
        print(f"  ✅ L4 完成")

    return schema, report, str(yaml_path)


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _schema_to_dict(schema: PlatformSchema) -> dict:
    """将 PlatformSchema 转换为可序列化的 dict"""
    return {
        "schema_version": schema.schema_version,
        "generated_by": schema.generated_by,
        "exploration_timestamp": schema.exploration_timestamp,
        "target_url": schema.target_url,
        "platform": schema.platform,
        "auth": schema.auth,
        "structure": schema.structure,
        "apis": schema.apis,
        "agent": schema.agent,
        "navigation": schema.navigation,
        "confidence_scores": schema.confidence_scores,
    }


def _generate_recommendations(schema: PlatformSchema, warnings: list[str]) -> list[str]:
    """基于 Schema 生成改进建议"""
    recs = []

    if not schema.structure.get("phases"):
        recs.append("建议人工标注 Phase/Lesson 层次结构 (自动推断未发现清晰层次)")
    if not schema.agent.get("chat_endpoint"):
        recs.append("未发现 Agent 对话端点, 请确认平台是否包含 AI 教学助手")
    if schema.confidence_scores.get("overall", 0) < 0.6:
        recs.append("整体置信度较低, 建议人工复核 platform_schema.yaml")
    if schema.structure.get("steps") and len(schema.structure["steps"]) < 5:
        recs.append("发现Step数量较少, 可能探索不充分 (检查BFS深度和认证状态)")

    return recs


def _format_report_md(report: ExplorationReport, schema: PlatformSchema) -> str:
    """生成 Markdown 格式的探索报告"""
    return f"""# 平台探索报告

## 基本信息
- **目标URL**: {report.target_url}
- **探索时间**: {report.timestamp}
- **耗时**: {report.duration_seconds:.1f}秒
- **前端框架**: {schema.platform.get('framework', 'unknown')}
- **SPA**: {'是' if schema.platform.get('spa') else '否'}

## 发现概况
| 项目 | 数量 |
|------|------|
| Phase | {report.phases_found} |
| Lesson | {report.lessons_found} |
| Step | {report.steps_found} |
| API端点 | {report.api_endpoints_found} |
| 隐藏端点(LLM推断) | {report.hidden_endpoints_found} |

## 置信度
| 维度 | 置信度 |
|------|--------|
| 整体 | {report.confidence.overall:.0%} |
| 教学结构 | {report.confidence.structure:.0%} |
| Step类型 | {report.confidence.step_types:.0%} |
| API | {report.confidence.apis:.0%} |
| 认证 | {report.confidence.auth:.0%} |

{f"## 需要人工复核" if report.confidence.fields_needing_human_review else ""}
{f"以下字段置信度较低，建议人工复核: {', '.join(report.confidence.fields_needing_human_review)}" if report.confidence.fields_needing_human_review else ""}

{f"## 警告" if report.warnings else ""}
{chr(10).join(f'- {w}' for w in report.warnings) if report.warnings else ""}

## 建议
{chr(10).join(f'{i+1}. {r}' for i, r in enumerate(report.recommendations)) if report.recommendations else "无"}

---
*由 Platform Explorer (PX) v0.1 自动生成*
"""
