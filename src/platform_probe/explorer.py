"""
Platform Explorer — 通用教学平台自动探索器

六阶段流水线:
  Phase 0 — 认证 (Auth)
  Phase 1 — 流量捕获 (Capture)
            ├─ 1A JS逆向 (JS Analysis)
            ├─ 1B 路由诊断 (Route Diagnostics)
            └─ 1C JWT提取 (JWT Extraction)
  Phase 2 — 深度交互探索 (Deep Explore)
            ├─ DOM Step发现 (可选, 有 graph-source 数据时)
            └─ LLM递归探索 (主路径, LLM自主规划交互)
  Phase 3 — 教学结构推断 (Structure)
            API驱动 + 深度探索结果合并
  Phase 4 — 分类与推断 (Classify)
            ├─ API端点分类 + Step类型分类 + LLM枚举
            └─ 参数Fuzzing (可选, 需JWT)
  Phase 5 — Schema生成 (Generate)
            Schema生成 + 验证 + 脱敏 + 报告

用法:
  from src.platform_probe.explorer import PlatformExplorer
  explorer = PlatformExplorer(headless=True)
  schema, report = explorer.explore("https://some-platform.com", username="...", password="...")
"""

from __future__ import annotations

import logging
import time
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

from .models import (
    PlatformSchema, ExplorationReport, AuthSchema, SessionState,
    CaptureResult, APICatalog, StepCatalog, RouteNode, StepType, StepInfo,
    LessonInfo,
)
from .l0_auth import run_l0_auth
from .l1_capture import run_l1_capture
from .l3_classify import run_l3_classify
from .l4_schema import run_l4_schema

# 默认输出目录
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output" / "platform_probe"


class PlatformExplorer:
    """
    平台探索器 — 五层流水线协调器

    Phase 1: L0 → L1 → L3 → L4 (跳过L2完整实现)
    Phase 2: 加入完整L2 (教学结构推断)
    """

    def __init__(
        self,
        headless: bool = True,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        api_threshold: float = 0.50,
        llm_api_key: str = "",
        llm_model: str = "",
        llm_base_url: str = "",
        vlm_api_key: str = "",
        max_depth: int = 3,
        max_pages: int = 50,
        verbose: bool = True,
    ):
        self.headless = headless
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.api_threshold = api_threshold
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.verbose = verbose   # ← 必须在使用前设置

        # ── 自动检测API Keys (非致命: 失败时探索器仍可运行) ──
        try:
            from .api_keys import get_api_keys
            keys = get_api_keys()
            llm_provider = keys.get_text_llm()
            vlm_provider = keys.get_vision_llm()
            self.llm_api_key = llm_api_key or (llm_provider.api_key if llm_provider else "")
            self.llm_model = llm_model or (llm_provider.model_id or llm_provider.models[0] if llm_provider else "deepseek-chat")
            self.llm_base_url = llm_base_url or (llm_provider.base_url if llm_provider else "")
            self.vlm_api_key = vlm_api_key or (vlm_provider.api_key if vlm_provider else "")
            self.vlm_model = vlm_provider.models[0] if vlm_provider else ""
            self.vlm_base_url = vlm_provider.base_url if vlm_provider else ""
            self.vlm_model_id = vlm_provider.model_id if vlm_provider else ""
            self.vlm_provider = vlm_provider.provider if vlm_provider else ""
            self._key_count = f"{keys.text_llm_count}LLM+{keys.vision_llm_count}VLM"
            if self.verbose:
                print(f"  🔑 LLM: {llm_provider.name if llm_provider else 'N/A'} "
                      f"| VLM: {vlm_provider.name if vlm_provider else 'N/A (仅DOM模式)'} "
                      f"| {self._key_count}")
        except Exception as e:
            # 非致命: API keys不可用时探索器仍能运行 (L0-L4基础功能)
            self.llm_api_key = llm_api_key
            self.llm_model = llm_model or "deepseek-chat"
            self.llm_base_url = llm_base_url
            self.vlm_api_key = vlm_api_key
            self.vlm_model = ""
            self.vlm_base_url = ""
            self.vlm_model_id = ""
            self.vlm_provider = ""
            self._key_count = "auto-detect failed"
            if self.verbose:
                print(f"  ⚠️ API Key自动检测失败: {e} (探索器基础功能不受影响)")

    def explore(
        self,
        target_url: str,
        username: str = "",
        password: str = "",
        auth_state_path: str = "",
        ask_callback=None,
    ) -> tuple[PlatformSchema, ExplorationReport, str]:
        """
        执行完整五层探索流水线

        :param target_url: 目标教学平台URL
        :param username: 登录用户名 (可选)
        :param password: 登录密码 (可选)
        :param ask_callback: 交互式登录问答通道 callable(text, options, context, timeout_s) -> dict
                             非标准登录模式 (验证码/SSO/短信等) 时以 LLM 对话向评测用户确认
        :returns: (schema, report, schema_yaml_path)
        """
        start_time = time.time()
        self._last_username = username
        self._last_password = password

        if self.verbose:
            print(f"\n{'='*70}")
            print(f"  Platform Explorer (PX) v0.1 — 通用教学平台探索器")
            print(f"  目标: {target_url}")
            print(f"{'='*70}")

        with sync_playwright() as p:
            # ── 启动浏览器 (全新上下文, 无缓存/cookie干扰) ──
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                storage_state=None,  # 全新, 无残留登录态
            )
            page = context.new_page()
            page.set_default_navigation_timeout(20000)
            page.set_default_timeout(20000)

            try:
                # ═══════════════════════════════════════════════
                # Phase 0 — 认证 (Auth)
                # ═══════════════════════════════════════════════
                if self.verbose:
                    print(f"\n── Phase 0: 认证检测 ──")

                auth_schema, session_state = run_l0_auth(
                    page=page,
                    context=context,
                    base_url=target_url,
                    username=username,
                    password=password,
                    output_dir=self.output_dir,
                    auth_state_path=auth_state_path,
                    verbose=self.verbose,
                    ask_callback=ask_callback,
                )
                # 提取L0真实置信度 (避免硬编码, 多格式兼容)
                import re as _re
                auth_confidence = 0.95  # 默认
                if auth_schema.notes:
                    _am = _re.search(r'conf(?:idence)?[=:]\s*([\d.]+)', auth_schema.notes)
                    if _am:
                        try:
                            auth_confidence = float(_am.group(1))
                        except ValueError:
                            pass
                if self.verbose:
                    print(f"  auth_confidence: {auth_confidence:.2f}")

                # 交互式登录结果 (L0-Interactive)
                self._interactive_auth = getattr(auth_schema, "interactive", None)
                if self._interactive_auth:
                    try:
                        import json as _ijson
                        (self.output_dir / "l0_interactive.json").write_text(
                            _ijson.dumps(self._interactive_auth, ensure_ascii=False,
                                         indent=2, default=str),
                            encoding="utf-8")
                        if self.verbose:
                            print(f"  🤝 交互式登录: {self._interactive_auth.get('notes', '')[:120]}")
                    except Exception:
                        pass

                # ═══════════════════════════════════════════════
                # Phase 1 — 流量捕获 (Capture)
                # ═══════════════════════════════════════════════
                capture = run_l1_capture(
                    page=page,
                    context=context,
                    base_url=target_url,
                    output_dir=self.output_dir,
                    max_depth=self.max_depth,
                    max_pages=self.max_pages,
                    verbose=self.verbose,
                )

                # ── Phase 1A: JS Bundle 逆向 ──
                try:
                    from .l1_js_analyzer import run_js_analysis
                    js_result = run_js_analysis(page, target_url,
                                                self.output_dir, verbose=self.verbose)
                    for api_path in js_result.get("api_paths", []):
                        if not any(r.url == api_path for r in capture.routes):
                            capture.routes.append(RouteNode(
                                url=api_path, method="GET", status=0,
                                content_type="", request_headers={},
                                request_payload=None, response_headers={},
                                response_sample=None, response_size=0,
                                duration_ms=0, parent_url=target_url,
                                initiator_type="js_bundle",
                            ))
                except Exception as e:
                    if self.verbose:
                        print(f"  ⚠️ JS分析跳过: {e}")

                # ═══════════════════════════════════════════════
                # ── Phase 1B: graph-source 响应体诊断 ── (route模式已捕获, 此处仅验证)
                # ═══════════════════════════════════════════════
                if capture.routes:
                    graph_route = next((r for r in capture.routes
                                      if 'graph-source' in r.url), None)
                    if graph_route:
                        if graph_route.response_sample:
                            if self.verbose:
                                courses = graph_route.response_sample.get("courses", [])
                                print(f"\n── L1.55: graph-source route已捕获 ({len(courses)} courses) ✓ ──")
                        else:
                            if self.verbose:
                                print(f"\n── L1.55: graph-source route未捕获响应体, 尝试浏览器fetch ──")
                            try:
                                graph_data = page.evaluate('''async (url) => {
                                    try {
                                        const resp = await fetch(url, {credentials: "include"});
                                        if (!resp.ok) return null;
                                        return await resp.json();
                                    } catch(e) { return null; }
                                }''', graph_route.url)
                                if graph_data and isinstance(graph_data, dict):
                                    graph_route.response_sample = graph_data
                                    import json as _json
                                    graph_route.response_size = len(_json.dumps(graph_data))
                                    if self.verbose:
                                        courses = graph_data.get("courses", [])
                                        print(f"  ✅ [fallback] graph-source: {len(courses)} courses")
                            except Exception as e:
                                if self.verbose:
                                    print(f"  ⚠️ graph-source fallback失败: {e}")
                    elif self.verbose:
                        print(f"\n── L1.55: 未发现graph-source路由 ──")

                # ── Phase 1C: JWT提取 + Route模式覆盖诊断 ──
                jwt = self._extract_jwt(page, capture, verbose=self.verbose)

                # ── Route模式覆盖诊断 ──
                if self.verbose and capture.routes:
                    routes_with_body = sum(1 for r in capture.routes if r.response_sample)
                    api_routes = [r for r in capture.routes
                                 if any(kw in r.url.lower() for kw in
                                       ["api", "graph", "v1/", "v2/"])]
                    api_with_body = sum(1 for r in api_routes if r.response_sample)
                    print(f"\n── L1.6: Route模式覆盖 {routes_with_body}/{len(capture.routes)} 路由"
                          f" (API: {api_with_body}/{len(api_routes)}) ──")
                    for r in api_routes:
                        marker = " ✓" if r.response_sample else " ✗"
                        print(f"    {marker} {r.url.split('/')[-1][:60]} "
                              f"({r.response_size or 0}B)")

                # ═══════════════════════════════════════════════
                # Phase 2A — DOM Step发现 (可选, 有graph-source数据时)
                # ═══════════════════════════════════════════════
                _all_dom_steps: dict[str, list] = {}
                try:
                    _graph_route = next((r for r in capture.routes
                                        if 'graph-source' in r.url), None)
                    _graph_data = _graph_route.response_sample if _graph_route else None
                    if _graph_data and _graph_data.get("courses"):
                        from .dom_step_discovery import discover_steps
                        if self.verbose:
                            print(f"\n── Phase 2A: DOM Step发现 "
                                  f"({len(_graph_data['courses'])} courses) ──")
                        _all_dom_steps = discover_steps(
                            page=page, base_url=target_url,
                            graph_source_data=_graph_data,
                            max_courses=min(10, len(_graph_data["courses"])),
                            verbose=self.verbose,
                        )
                        if _all_dom_steps:
                            total = sum(len(v) for v in _all_dom_steps.values())
                            if self.verbose:
                                print(f"  ✅ Phase 2A 发现 {total} steps in {len(_all_dom_steps)} courses")
                    elif self.verbose:
                        print(f"\n── Phase 2A: 跳过 (无graph-source数据或无courses) ──")
                except Exception as e:
                    if self.verbose:
                        print(f"  ⚠️ Phase 2A跳过: {e}")

                # ═══════════════════════════════════════════════
                # Phase 2B — LLM递归深度探索 (主路径)
                # ═══════════════════════════════════════════════
                _diag = []
                _all_deep_steps: list[dict] = []
                _diag.append("Phase 2B Deep Explorer: LLM={} VLM={}".format(
                    'available' if self.llm_api_key else 'N/A',
                    'available' if self.vlm_api_key else 'N/A'))
                try:
                    from .deep_explorer import DeepExplorer

                    deep = DeepExplorer(
                        page=page,
                        home_url=target_url,
                        text_api_key=self.llm_api_key,
                        text_model=self.llm_model,
                        text_base_url=self.llm_base_url,
                        max_depth=8,
                        max_total_interactions=150,
                        verbose=True,
                        diag=_diag,
                    )

                    deep_steps, deep_features, deep_path = deep.explore()
                    _all_deep_steps = deep_steps  # 保存到外层作用域

                    _diag.append("Phase 2B: {} steps, {} features, {} interactions, "
                                "{} states visited".format(
                        len(deep_steps), len(deep_features),
                        deep.interaction_count, len(deep.visited_fingerprints)))

                    if deep_features:
                        _diag.append("Phase 2B Features discovered:")
                        for f in deep_features[:20]:
                            _diag.append("  d={}: {} → {}".format(
                                f["depth"], f["title"][:50],
                                list(f.get("features", {}).keys())))

                    if deep_path:
                        _diag.append("Phase 2B Exploration path (last 20):")
                        for p in deep_path[-20:]:
                            _diag.append("  d={}: {} #{} '{}'".format(
                                p["depth"], p["action"]["action"],
                                p["action"]["index"],
                                p["element_text"][:50]))

                except Exception as e:
                    import traceback
                    _diag.append("Phase 2B Error: {}".format(e))
                    _diag.append(traceback.format_exc())
                    _diag.append("Phase 2B failed, falling back to L1.8...")
                    try:
                        from .step_extractor import extract_steps_deep
                        llm_steps = extract_steps_deep(
                            page=page, base_url=target_url,
                            text_api_key=self.llm_api_key,
                            text_model=self.llm_model,
                            text_base_url=self.llm_base_url,
                            vlm_api_key=self.vlm_api_key,
                            vlm_model=self.vlm_model_id,
                            vlm_base_url=self.vlm_base_url,
                            max_careers=5, verbose=True, diag=_diag,
                        )
                        if llm_steps:
                            _all_deep_steps = llm_steps
                    except Exception as e2:
                        _diag.append("StepExtractor fallback also failed: {}".format(e2))

                # ═══════════════════════════════════════════════
                # Phase 3 — 教学结构推断 (Structure)
                # API驱动 + Phase 2 探索结果合并
                # ═══════════════════════════════════════════════
                from .l2_structure import run_l2_structure
                teaching_structure = run_l2_structure(capture, verbose=self.verbose)

                # 合并 Phase 2A DOM steps 到 L2 结构
                if _all_dom_steps:
                    from .dom_step_discovery import inject_steps_into_structure
                    teaching_structure = inject_steps_into_structure(
                        teaching_structure, _all_dom_steps, verbose=self.verbose)

                # 合并 Phase 2B/L1.8 发现的 steps 到 L2 结构中
                if _all_deep_steps:
                    for s in _all_deep_steps:
                        stype = StepType.UNKNOWN
                        try:
                            stype = StepType(s.get("type_guess", "unknown"))
                        except ValueError:
                            pass
                        teaching_structure.steps.append(StepInfo(
                            id=f"deep_{len(teaching_structure.steps):03d}",
                            title=s["title"][:120],
                            type=stype,
                            type_confidence=0.75,
                            order_index=s.get("order_index", 0)))
                    _diag.append("L2+Deep: merged {} deep steps (total: {})".format(
                        len(_all_deep_steps), len(teaching_structure.steps)))

                # ═══════════════════════════════════════════════
                # Phase 2C — 视觉理解 (可选, l2_vision VLM 页面分析)
                # 补充 DOM/LLM 盲区: 登录后弹窗/图表类页面/Shadow DOM
                # VLM key 不可用时静默跳过, 不影响主流程
                # ═══════════════════════════════════════════════
                _vision_notes = ""
                try:
                    from .l2_vision import VisualAnalyzer
                    va = VisualAnalyzer(verbose=self.verbose)
                    if va._vlm_enabled:
                        vres = va.analyze_page(page)
                        vres = vres or {}
                        bits = []
                        for k in ("has_agent_panel", "shadow_dom_detected",
                                  "page_type", "has_modal"):
                            v = vres.get(k)
                            if v not in (None, "", False):
                                bits.append(f"{k}={v}")
                        if vres.get("dom_regions"):
                            bits.append(f"regions={len(vres['dom_regions'])}")
                        _vision_notes = "; ".join(bits)[:300]
                        if _vision_notes:
                            _diag.append(f"L2C Vision: {_vision_notes}")
                            if self.verbose:
                                print(f"  👁 L2C 视觉理解: {_vision_notes}")
                except Exception as _ve:
                    _diag.append(f"L2C Vision 跳过: {str(_ve)[:100]}")

                # 写入诊断文件
                (self.output_dir / "l1_9_diag.txt").write_text("\n".join(_diag))

                # ═══════════════════════════════════════════════
                # Phase 4 — 分类与推断 (Classify)
                # API端点分类 + Step类型分类 + LLM端点枚举
                # ═══════════════════════════════════════════════
                api_catalog, step_catalog = run_l3_classify(
                    capture=capture,
                    api_threshold=self.api_threshold,
                    llm_api_key=self.llm_api_key,
                    llm_model=self.llm_model,
                    llm_base_url=self.llm_base_url,
                    verbose=self.verbose,
                )

                # ── Phase 4A: 参数Fuzzing (IDOR/隐藏资源探测) ──
                fuzz_findings = []
                if jwt or session_state.logged_in:
                    try:
                        from .l3_fuzzer import run_l3_fuzzer
                        fuzz_findings = run_l3_fuzzer(
                            endpoints=api_catalog.endpoints,
                            base_url=target_url,
                            jwt_token=jwt,
                            verbose=self.verbose,
                        )
                    except Exception as e:
                        if self.verbose:
                            print(f"  ⚠️ Fuzzing跳过: {e}")
                elif self.verbose:
                    print(f"\n  ⏭ L3.5 Fuzzing跳过 (需登录获取JWT)")

                # ═══════════════════════════════════════════════
                # Phase 5 — Schema生成与验证 (Generate)
                # ═══════════════════════════════════════════════
                schema, report, yaml_path = run_l4_schema(
                    target_url=target_url,
                    auth_schema=auth_schema,
                    capture=capture,
                    api_catalog=api_catalog,
                    step_catalog=step_catalog,
                    teaching_structure=teaching_structure,
                    output_dir=self.output_dir,
                    verbose=self.verbose,
                    auth_confidence=auth_confidence,
                    fuzz_findings=fuzz_findings,
                )

                # 填充耗时
                elapsed = max(0.1, time.time() - start_time)
                report.duration_seconds = elapsed
                if self.verbose:
                    print(f"  ⏱ 耗时: {elapsed:.1f}秒")

                # ═══════════════════════════════════════════════
                # 生成 platform_profile.json (全链路桥梁)
                # ═══════════════════════════════════════════════
                # 从捕获的API URL中提取前缀和登录端点
                _api_prefix = self._infer_api_prefix(capture, target_url)
                _login_url = self._infer_login_url(capture, target_url, _api_prefix)

                # 交互式登录信息 (评测用户协作)
                _ia = self._interactive_auth or {}
                try:
                    if _ia.get("degraded"):
                        report.warnings.append(
                            f"交互式登录未成功 (降级为未登录探索): {_ia.get('notes', '')}")
                    elif _ia.get("asked_user"):
                        report.warnings.append(
                            f"交互式登录: 用户参与 {_ia.get('rounds', 0)} 轮问答, "
                            f"最终{'成功' if _ia.get('logged_in') else '未登录'}")
                except Exception:
                    pass

                profile = {
                    "target_url": target_url,
                    "auth_type": auth_schema.type.value,
                    "credentials": {
                        "username": username,
                        "password": password,
                    },
                    "auth": {
                        "login_url": _login_url,
                        "login_method": "POST",
                    },
                    "api_prefix": _api_prefix,
                    "schema_path": yaml_path,
                    "explored_at": datetime.now(timezone.utc).isoformat(),
                    "session_id": getattr(self, '_session_id', ''),
                    "phases_found": report.phases_found,
                    "steps_found": report.steps_found,
                    "api_endpoints_found": report.api_endpoints_found,
                    "overall_confidence": report.confidence.overall,
                    "framework": teaching_structure.framework.value if hasattr(teaching_structure, 'framework') else "unknown",
                    "auth_interactive": bool(_ia),
                    "auth_degraded": bool(_ia.get("degraded") or not session_state.logged_in),
                    "auth_notes": _ia.get("notes", "")[:500],
                    "interactive_asked_user": bool(_ia.get("asked_user")),
                }
                import json as _json
                profile_path = self.output_dir / "platform_profile.json"
                profile_path.write_text(_json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
                # 同时写一份到全局位置 (供API读取)
                global_profile = Path(self.output_dir).parent / "platform_profile.json"
                global_profile.write_text(_json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
                # 平台库归档 — 按 URL 指纹保存, 换平台探索不丢历史 (自演化基础)
                try:
                    from src.platform_profile_store import archive_profile
                    archive_profile(profile)
                except Exception:
                    pass

                if self.verbose:
                    print(f"\n{'='*70}")
                    print(f"  ✅ 探索完成! 耗时 {elapsed:.1f}秒")
                    print(f"  📄 Schema: {yaml_path}")
                    print(f"  📊 API端点: {api_catalog.total_found}")
                    print(f"  📊 Step: {len(step_catalog.steps)}")
                    print(f"  🎯 置信度: {report.confidence.overall:.0%}")
                    print(f"{'='*70}")

                return schema, report, yaml_path

            finally:
                browser.close()

    def _extract_jwt(self, page, capture, verbose=True) -> str:
        """从浏览器存储提取JWT (供L3.5 Fuzzer使用)

        Route模式已通过page.route()捕获所有API响应体,
        此方法仅提取JWT — 不做任何API请求。
        """
        jwt = None

        # ── 策略0: localStorage/sessionStorage — 宽松匹配 ──
        try:
            jwt = page.evaluate("""() => {
                // 先精确匹配常见token key
                for (const storage of [localStorage, sessionStorage]) {
                    try {
                        for (let i = 0; i < storage.length; i++) {
                            const key = storage.key(i);
                            const val = storage.getItem(key);
                            if (!key || !val || val.length < 20) continue;
                            const kl = key.toLowerCase();
                            if (kl.includes('token') || kl.includes('access') ||
                                kl.includes('jwt') || kl.includes('auth') ||
                                kl.includes('bearer') || kl.includes('session') ||
                                kl.includes('credential')) {
                                return val;
                            }
                        }
                    } catch(e) {}
                }
                // 模糊匹配: 长base64-like值
                for (const storage of [localStorage, sessionStorage]) {
                    try {
                        for (let i = 0; i < storage.length; i++) {
                            const val = storage.getItem(storage.key(i));
                            if (val && val.length > 40 &&
                                /^[A-Za-z0-9+/=_-]+$/.test(val) &&
                                val.split('.').length >= 2) {
                                return val;  // JWT-like: xxx.yyy.zzz
                            }
                        }
                    } catch(e) {}
                }
                return null;
            }""")
        except Exception:
            pass

        # ── 策略0b: 从cookie读 ──
        if not jwt:
            try:
                cookies = page.context.cookies()
                for c in cookies:
                    if 'token' in c.get('name', '').lower() or \
                       'auth' in c.get('name', '').lower() or \
                       'jwt' in c.get('name', '').lower():
                        jwt = c.get('value', '')
                        if jwt and len(jwt) > 10:
                            break
            except Exception:
                pass

        if verbose:
            if jwt:
                print(f"\n── L1.6: JWT提取成功 ({len(jwt)} chars) ──")
            else:
                print(f"\n── L1.6: 未提取到JWT (fuzzer将不可用) ──")

        return jwt or ""

    @staticmethod
    def _infer_api_prefix(capture, target_url):
        """从捕获的API URL推断前缀, 如 /personalized-secure-api/v1"""
        from urllib.parse import urlparse
        prefixes = {}
        for r in capture.routes:
            url = r.url
            parsed = urlparse(url)
            path = parsed.path
            # 匹配 /xxx-api 或 /api 前缀
            for seg in path.split("/"):
                if seg and ("api" in seg.lower() or seg.startswith("v") and seg[1:].isdigit()):
                    prefix = "/" + seg
                    prefixes[prefix] = prefixes.get(prefix, 0) + 1
        # 返回出现最多的前缀
        if prefixes:
            return max(prefixes, key=prefixes.get)
        return ""

    @staticmethod
    def _infer_login_url(capture, target_url, api_prefix):
        """从捕获的API和已知模式推断登录URL"""
        from urllib.parse import urlparse
        # 策略1: 从捕获的请求中找auth/login或auth/me反推
        for r in capture.routes:
            url = r.url
            if "auth/me" in url:
                # auth/me → auth/login
                return url.replace("auth/me", "auth/login")
            if "auth/login" in url:
                return url
        # 策略2: 从api_prefix构造
        if api_prefix:
            parsed = urlparse(target_url)
            base = f"{parsed.scheme}://{parsed.netloc}"
            return f"{base}{api_prefix}/auth/login"
        # 策略3: 从target_url构造
        parsed = urlparse(target_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        return f"{base}/api/auth/login"

    def explore_to_schema(self, target_url: str, **kwargs) -> PlatformSchema:
        """简化接口: 只返回 Schema"""
        schema, _, _ = self.explore(target_url, **kwargs)
        return schema


# ═══════════════════════════════════════════════════════════════
# 便捷函数 (CLI 和 SDK 使用)
# ═══════════════════════════════════════════════════════════════

def explore_platform(
    target_url: str,
    username: str = "",
    password: str = "",
    headless: bool = True,
    output_dir: str = "",
    verbose: bool = True,
) -> str:
    """
    一行式探索: 输入 URL → 输出 schema 文件路径

    :returns: platform_schema.yaml 的文件路径
    """
    od = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    explorer = PlatformExplorer(
        headless=headless,
        output_dir=od,
        verbose=verbose,
    )
    _, _, yaml_path = explorer.explore(
        target_url=target_url,
        username=username,
        password=password,
    )
    return yaml_path
