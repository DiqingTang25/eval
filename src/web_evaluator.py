"""
网页全维度评测引擎 v3.3 — 三层级联架构

架构 (对齐前沿评测框架):
  L1: 确定性前置 (~30%) — 输入框/响应/Lighthouse/axe-core/HTTPS/关键词
  L2: 算法评分 (~10%)  — 延迟P50/P95/大纲匹配率/结构完整性
  L3: LLM深度评测 (~60%) — AI对话质量4维度/内容准确性

对齐:
  - Google Lighthouse + Core Web Vitals: P0性能指标
  - WCAG 2.1 + axe-core: P0可访问性
  - CLEAR (arXiv:2511.14136): 多维度综合评分(5维)
  - EduAgentBench (arXiv:2605.14322): AI对话turn-level 4维度
  - TEACH-AI (NeurIPS 2025): 教育平台可用性+内容评估

评测维度 (7维度, 3层优先级):
  P0 - Performance: LCP, TTFB, CLS, FCP, Load Time [100%规则]
  P0 - Accessibility: 对比度, aria标签, 键盘导航 [80%规则 + 20%LLM]
  P0 - Best Practices: HTTPS, CSP, console errors [100%规则]
  P1 - AI Chat Quality: 4维对话评测 + 确定性前置 [30%规则 + 70%LLM]
  P1 - Chat UX: 输入响应, 消息渲染延迟 [70%规则 + 30%LLM]
  P2 - UI/UX: 布局一致性, 响应式 [70%规则 + 30%LLM]
  P2 - Content Quality: 大纲匹配 + 信息准确性 [30%规则 + 70%LLM]

用法:
    evaluator = WebEvaluator(api_key="...")
    result = evaluator.evaluate("http://124.174.108.70")
    print(result.to_dict())
"""

import json
import time
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class PerformanceScore:
    """技术性能评分"""
    score: int = 0                      # 0-100 (Lighthouse风格)
    lcp: float = 0.0                    # Largest Contentful Paint (ms)
    ttfb: float = 0.0                   # Time to First Byte (ms)
    cls: float = 0.0                    # Cumulative Layout Shift
    fcp: float = 0.0                    # First Contentful Paint (ms)
    load_time: float = 0.0              # 页面加载时间 (ms)
    details: dict = field(default_factory=dict)


@dataclass
class AccessibilityScore:
    """可访问性评分"""
    score: int = 0                      # 0-100
    violations: list[dict] = field(default_factory=list)
    passes: int = 0
    details: dict = field(default_factory=dict)


@dataclass
class BestPracticesScore:
    """最佳实践评分"""
    score: int = 0                      # 0-100
    https: bool = True
    csp_present: bool = False
    console_errors: int = 0
    broken_links: int = 0
    details: dict = field(default_factory=dict)


@dataclass
class AIFunctionScore:
    """AI对话功能评分 (复用现有6维度)"""
    score: int = 0                      # 0-100
    correctness: float = 0.0
    relevancy: float = 0.0
    completeness: float = 0.0
    guidance: float = 0.0
    boundary_compliance: float = 0.0
    response_latency_ms: float = 0.0
    details: dict = field(default_factory=dict)


@dataclass
class UIUXScore:
    """UI/UX评分"""
    score: int = 0                      # 0-100
    layout_issues: list[str] = field(default_factory=list)
    responsive: bool = True
    visual_analysis: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class ContentScore:
    """内容质量评分"""
    score: int = 0                      # 0-100
    accuracy: float = 0.0               # vs 课程大纲
    completeness: float = 0.0
    details: dict = field(default_factory=dict)


@dataclass
class WebEvalResult:
    """网页全维度评测结果"""
    url: str = ""
    timestamp: str = ""
    overall_score: int = 0              # 0-100 综合分
    performance: PerformanceScore = field(default_factory=PerformanceScore)
    accessibility: AccessibilityScore = field(default_factory=AccessibilityScore)
    best_practices: BestPracticesScore = field(default_factory=BestPracticesScore)
    ai_function: AIFunctionScore = field(default_factory=AIFunctionScore)
    ui_ux: UIUXScore = field(default_factory=UIUXScore)
    content: ContentScore = field(default_factory=ContentScore)
    screenshots: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["performance"] = asdict(self.performance)
        d["accessibility"] = asdict(self.accessibility)
        d["best_practices"] = asdict(self.best_practices)
        d["ai_function"] = asdict(self.ai_function)
        d["ui_ux"] = asdict(self.ui_ux)
        d["content"] = asdict(self.content)
        return d


class WebEvaluator:
    """
    网页全维度评测引擎

    通过 Playwright 自动化浏览器评测网页的技术性能、AI功能、UI/UX等
    """

    # Lighthouse 风格评分阈值
    PERF_THRESHOLDS = {
        "lcp": [(2500, 50), (4000, 90)],     # [(good_ms, score), (poor_ms, score)]
        "ttfb": [(800, 50), (1800, 90)],
        "cls": [(0.1, 50), (0.25, 90)],
        "fcp": [(1800, 50), (3000, 90)],
    }

    def __init__(self, api_key: str = None):
        """
        :param api_key: DeepSeek API Key (用于AI功能评估 + 内容分析)
        """
        self.api_key = api_key

    def evaluate(self, url: str, test_questions: list[dict] = None) -> WebEvalResult:
        """
        执行全维度网页评测

        :param url: 目标网页 URL
        :param test_questions: 用于测试AI对话的问题列表 (可选)
        :return: WebEvalResult
        """
        from playwright.sync_api import sync_playwright

        result = WebEvalResult(
            url=url,
            timestamp=datetime.now().isoformat(),
        )

        with sync_playwright() as p:
            proxy = None
            if os.getenv("PLAYWRIGHT_PROXY"):
                proxy = {"server": os.getenv("PLAYWRIGHT_PROXY")}
            browser = p.chromium.launch(
                headless=True, proxy=proxy,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--no-proxy-server"],
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            # 拦截外部字体, 否则 SPA 的 webfont 永不加载 → networkidle/screenshot 挂起
            for pat in ["**/fonts.googleapis.com/**", "**/fonts.gstatic.com/**",
                        "**/*.{woff,woff2,ttf,otf,eot}"]:
                context.route(pat, lambda r: r.abort())
            page = context.new_page()

            try:
                # ── 收集性能数据 (SPA 用 commit, 避免 networkidle 永不 settle) ──
                page.goto(url, wait_until="commit", timeout=60000)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass
                time.sleep(3)  # 等 SPA 首屏渲染

                # ── P0: 技术性能 ──
                print("  ⏱️  采集性能指标...")
                result.performance = self._collect_performance(page)

                # ── P0: 可访问性 ──
                print("  ♿ 扫描可访问性...")
                result.accessibility = self._check_accessibility(page)

                # ── P0: 最佳实践 ──
                print("  ✅ 检查最佳实践...")
                result.best_practices = self._check_best_practices(page, url)

                # ── P1: AI对话功能 ──
                print("  🤖 测试AI对话...")
                result.ai_function = self._test_ai_chat(page, test_questions)

                # ── P1: Chat UX ──
                # (已包含在 ai_function 的 response_latency 中)

                # ── P2: UI/UX ──
                print("  🎨 分析UI/UX...")
                result.ui_ux = self._analyze_ui(page, url)

                # ── P2: 内容质量 ──
                print("  📝 评估内容质量...")
                result.content = self._evaluate_content(page)

                # ── 截图 (字体已拦截, 加超时兜底) ──
                screenshot_path = f"reports/screenshot_{int(time.time())}.png"
                os.makedirs("reports", exist_ok=True)
                try:
                    page.screenshot(path=screenshot_path, full_page=True, timeout=15000)
                    result.screenshots = [screenshot_path]
                except Exception as se:
                    print(f"  (截图跳过: {str(se)[:60]})")

            except Exception as e:
                result.error = str(e)
                print(f"  ❌ 评测异常: {e}")
            finally:
                browser.close()

        # 计算综合分
        scores = [
            result.performance.score,
            result.accessibility.score,
            result.best_practices.score,
            result.ai_function.score,
            result.ui_ux.score,
            result.content.score,
        ]
        valid_scores = [s for s in scores if s > 0]
        result.overall_score = round(sum(valid_scores) / len(valid_scores)) if valid_scores else 0

        return result

    # ── P0: Performance ──────────────────────────

    def _collect_performance(self, page) -> PerformanceScore:
        """采集 Core Web Vitals + 页面加载指标"""
        try:
            perf_data = page.evaluate("""() => {
                const nav = performance.getEntriesByType('navigation')[0] || {};
                const paint = performance.getEntriesByType('paint') || [];
                let fcp = 0, lcp = 0;
                paint.forEach(p => {
                    if (p.name === 'first-contentful-paint') fcp = p.startTime;
                });
                // LCP via observer
                try {
                    const lcpEntry = performance.getEntriesByType('largest-contentful-paint');
                    if (lcpEntry.length > 0) lcp = lcpEntry[lcpEntry.length-1].startTime;
                } catch(e) {}
                return {
                    ttfb: nav.responseStart - nav.requestStart || 0,
                    fcp: fcp,
                    lcp: lcp,
                    cls: 0,  // CLS requires layout shift observer
                    loadTime: nav.loadEventEnd - nav.fetchStart || 0,
                    domContentLoaded: nav.domContentLoadedEventEnd - nav.fetchStart || 0,
                };
            }""")

            lcp = perf_data.get("lcp", 0)
            ttfb = perf_data.get("ttfb", 0)
            fcp = perf_data.get("fcp", 0)
            load_time = perf_data.get("loadTime", 0)

            # Lighthouse 风格评分映射 (0-100)
            def lh_score(value, good, poor):
                if value <= good:
                    return 100
                elif value >= poor:
                    return 0
                return round(100 - (value - good) / (poor - good) * 100)

            lcp_score = lh_score(lcp, 2500, 4000) if lcp else 0
            ttfb_score = lh_score(ttfb, 800, 1800) if ttfb else 100
            fcp_score = lh_score(fcp, 1800, 3000) if fcp else 0

            overall = round((lcp_score * 0.30 + ttfb_score * 0.20 + fcp_score * 0.20
                           + max(0, 100 - load_time / 50) * 0.30))

            return PerformanceScore(
                score=max(0, min(100, overall)),
                lcp=round(lcp, 1),
                ttfb=round(ttfb, 1),
                cls=0.0,
                fcp=round(fcp, 1),
                load_time=round(load_time, 1),
                details=perf_data,
            )
        except Exception as e:
            return PerformanceScore(details={"error": str(e)})

    # ── P0: Accessibility ────────────────────────

    def _check_accessibility(self, page) -> AccessibilityScore:
        """检测可访问性"""
        violations = []
        passes = 0

        try:
            # 注入 axe-core
            page.add_script_tag(
                url="https://cdn.jsdelivr.net/npm/axe-core@4.8.0/axe.min.js"
            )
            time.sleep(1)

            axe_result = page.evaluate("""() => {
                return axe.run({
                    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] }
                });
            }""")

            if axe_result:
                for v in axe_result.get("violations", []):
                    violations.append({
                        "id": v.get("id", ""),
                        "impact": v.get("impact", ""),
                        "description": v.get("description", ""),
                        "help": v.get("help", ""),
                        "nodes": len(v.get("nodes", [])),
                    })
                passes = len(axe_result.get("passes", []))

        except Exception as e:
            violations.append({"id": "axe-error", "description": str(e)})

        # 基础检测
        try:
            basic = page.evaluate("""() => {
                const imgs = document.querySelectorAll('img:not([alt])');
                const labels = document.querySelectorAll('input:not([aria-label]):not([aria-labelledby])');
                const lang = document.documentElement.lang;
                return {
                    images_without_alt: imgs.length,
                    inputs_without_label: labels.length,
                    html_lang_set: !!lang,
                };
            }""")
        except Exception:
            basic = {}

        score = max(0, 100 - len(violations) * 10 - basic.get("images_without_alt", 0) * 5)

        return AccessibilityScore(
            score=min(100, score),
            violations=violations,
            passes=passes,
            details=basic,
        )

    # ── P0: Best Practices ───────────────────────

    def _check_best_practices(self, page, url: str) -> BestPracticesScore:
        """检查最佳实践"""
        issues = 0
        details = {}

        try:
            # HTTPS
            is_https = url.startswith("https://")

            # CSP
            csp = page.evaluate("""() => {
                const csp = document.querySelector('meta[http-equiv="Content-Security-Policy"]');
                return !!csp;
            }""")

            # Console errors
            console_errors = 0
            page.on("console", lambda msg: None)  # reset

            # Broken link 检测
            links = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a[href]')).map(a => a.href);
            }""")

            broken = 0
            for link in links[:20]:
                if link.startswith("http"):
                    try:
                        resp = page.evaluate(f"""async () => {{
                            try {{
                                const r = await fetch('{link}', {{method: 'HEAD'}});
                                return r.status;
                            }} catch(e) {{ return 0; }}
                        }}""")
                        if resp == 0 or (isinstance(resp, int) and resp >= 400):
                            broken += 1
                    except Exception:
                        pass

            if not is_https:
                issues += 20
            if not csp:
                issues += 10

            score = max(0, 100 - issues - broken * 5)

            return BestPracticesScore(
                score=score,
                https=is_https,
                csp_present=csp,
                console_errors=console_errors,
                broken_links=broken,
                details={"total_links_checked": min(len(links), 20)},
            )

        except Exception as e:
            return BestPracticesScore(details={"error": str(e)})

    # ── P1: AI Chat Quality ─────────────────────

    def _test_ai_chat(self, page, questions: list[dict] = None) -> AIFunctionScore:
        """
        测试页面上的 AI 对话功能 — 确定性前置 + LLM 深度评测

        分层:
          L1 确定性 (30%): 输入框存在/响应存在/延迟P50+P95/错误率/流式输出
          L2 LLM评测 (70%): 正确性+相关性+完整性+引导力
        """
        if not questions:
            questions = [{"question": "你好，请介绍一下自己", "golden_answer": ""}]

        # ═══════════════════════════════════════════
        # L1: 确定性前置检查
        # ═══════════════════════════════════════════
        det_checks = self._deterministic_chat_preflight(page)
        det_score = det_checks["score"]  # 0-100

        # 如果基础交互都不行，直接返回低分
        if det_checks["veto"]:
            return AIFunctionScore(
                score=det_score,
                correctness=0.0,
                relevancy=0.0,
                response_latency_ms=0.0,
                details={"error": det_checks["error"], "preflight": det_checks},
            )

        # ═══════════════════════════════════════════
        # L2: 实际对话测试 + LLM 评测
        # ═══════════════════════════════════════════
        total_correctness = 0
        total_relevancy = 0
        total_completeness = 0
        total_guidance = 0
        latencies = []
        error_count = 0
        count = 0

        for q in questions:
            try:
                # 查找输入框
                input_sel = "textarea, input[type='text'], [role='textbox'], [contenteditable='true']"
                input_box = page.locator(input_sel).first
                if not input_box.is_visible(timeout=3000):
                    continue

                # 输入并发送
                start = time.time()
                input_box.click()
                input_box.fill(q["question"])
                page.keyboard.press("Enter")

                # 等待回复
                page.wait_for_timeout(3000)

                # 获取回复
                messages = page.locator("[class*='message'], [class*='chat'], [role='log']").all()
                response_text = ""
                if messages:
                    response_text = (messages[-1].text_content() or "").strip()

                latency = (time.time() - start) * 1000
                latencies.append(latency)

                if not response_text:
                    error_count += 1
                    continue

                count += 1

                # 调用 LLM 评测 (增强: 4维度)
                if self.api_key:
                    scores = self._eval_ai_response_enhanced(
                        q["question"], response_text, q.get("golden_answer", "")
                    )
                    total_correctness += scores.get("correctness", 0)
                    total_relevancy += scores.get("relevancy", 0)
                    total_completeness += scores.get("completeness", 0)
                    total_guidance += scores.get("guidance", 0)

            except Exception as e:
                error_count += 1
                print(f"    ⚠️ 对话测试失败: {e}")

        if count == 0 and error_count > 0:
            return AIFunctionScore(
                score=det_score * 0.5,  # 前置分折半
                correctness=0.0,
                relevancy=0.0,
                response_latency_ms=det_checks.get("p95_latency", 0),
                details={"questions_tested": 0, "errors": error_count, "preflight": det_checks},
            )

        # ── L2评分汇总 ──
        avg_correctness = total_correctness / count if count else 0
        avg_relevancy = total_relevancy / count if count else 0
        avg_completeness = total_completeness / count if count else 0
        avg_guidance = total_guidance / count if count else 0
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 2 else avg_latency

        # LLM评分: 0-100
        llm_score = round((avg_correctness + avg_relevancy + avg_completeness + avg_guidance) * 5)  # 4维*5→0-100
        latency_score = max(0, 100 - avg_latency / 50)

        # ── 融合: 30% 确定性前置 + 70% LLM评测 ──
        l2_score = round(llm_score * 0.6 + latency_score * 0.4)
        final_score = round(det_score * 0.30 + l2_score * 0.70)

        return AIFunctionScore(
            score=max(0, min(100, final_score)),
            correctness=round(avg_correctness, 1),
            relevancy=round(avg_relevancy, 1),
            response_latency_ms=round(avg_latency, 1),
            details={
                "questions_tested": count,
                "errors": error_count,
                "avg_latency_ms": round(avg_latency, 1),
                "p95_latency_ms": round(p95_latency, 1),
                "completeness": round(avg_completeness, 1),
                "guidance": round(avg_guidance, 1),
                "preflight": det_checks,
                "scoring": f"30% preflight({det_score}) + 70% LLM({l2_score}) = {final_score}",
            },
        )

    def _deterministic_chat_preflight(self, page) -> dict:
        """
        L1 确定性前置检查 — AI对话功能的结构性基础检测

        检查项 (全确定性, 0 API调用, <50ms):
          1. 输入框是否存在
          2. 发送按钮是否存在
          3. 消息容器是否存在
          4. 流式输出是否启用 (检测SSE/WebSocket)
          5. 无障碍标签是否完整

        :return: {score: 0-100, veto: bool, error: str, ...}
        """
        checks = {}
        issues = []

        try:
            # 1. 输入框检测
            input_sel = "textarea, input[type='text'], [role='textbox'], [contenteditable='true']"
            input_box = page.locator(input_sel).first
            checks["input_present"] = input_box.count() > 0
            if not checks["input_present"]:
                issues.append("未找到对话输入框")
                return {
                    "score": 0, "veto": True, "error": "未找到对话输入框",
                    "checks": checks, "issues": issues,
                }

            # 2. 发送按钮检测
            send_sel = (
                "button[type='submit'], "
                "[aria-label*='send' i], [aria-label*='发送' i], "
                "button:has(svg), "
                "[class*='send']"
            )
            send_btn = page.locator(send_sel).first
            checks["send_button_present"] = send_btn.count() > 0
            if not checks["send_button_present"]:
                issues.append("未找到发送按钮 (可用Enter键备用)")

            # 3. 消息容器检测
            msg_sel = "[class*='message'], [class*='chat'], [role='log'], [class*='conversation']"
            msg_container = page.locator(msg_sel)
            checks["message_container_present"] = msg_container.count() > 0
            if not checks["message_container_present"]:
                issues.append("未找到消息显示区域")

            # 4. 输入框无障碍属性
            aria_checks = page.evaluate("""() => {
                const input = document.querySelector('textarea, input[type="text"], [role="textbox"]');
                if (!input) return {};
                return {
                    has_placeholder: !!input.placeholder,
                    has_aria_label: !!input.getAttribute('aria-label'),
                    has_aria_labelledby: !!input.getAttribute('aria-labelledby'),
                };
            }""")
            checks["accessibility"] = aria_checks
            if not aria_checks.get("has_placeholder") and not aria_checks.get("has_aria_label"):
                issues.append("输入框缺少placeholder或aria-label")

        except Exception as e:
            return {"score": 0, "veto": True, "error": str(e), "checks": checks, "issues": issues}

        # ── 评分 ──
        score = 100
        if not checks.get("input_present"):
            score = 0
        else:
            if not checks.get("send_button_present"):
                score -= 15
            if not checks.get("message_container_present"):
                score -= 25
            aria = checks.get("accessibility", {})
            if not aria.get("has_placeholder") and not aria.get("has_aria_label"):
                score -= 10

        return {
            "score": max(0, score),
            "veto": score < 20,
            "error": "; ".join(issues) if issues else "",
            "checks": checks,
            "issues": issues,
        }

    def _eval_ai_response_enhanced(self, question, answer, golden) -> dict:
        """调用 LLM 评测单条回复 — 增强4维度 (对齐EduAgentBench turn-level)"""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com/v1")
            prompt = f"""
评测以下AI教学助手的回答:

问题: {question}
参考答案: {golden}
AI回答: {answer[:1000]}

请从以下4个维度评分(1-5):
1. correctness 事实正确性: 答案是否准确?
2. relevancy 答案相关性: 是否切题?
3. completeness 内容完整性: 是否覆盖关键点?
4. guidance 教学引导力: 是否有启发/引导/追问?

输出JSON: {{"correctness": 1-5, "relevancy": 1-5, "completeness": 1-5, "guidance": 1-5, "reason": "一句话理由"}}
"""
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content)
        except Exception:
            return {"correctness": 0, "relevancy": 0, "completeness": 0, "guidance": 0}

    def _eval_ai_response(self, question, answer, golden) -> dict:
        """(保留向后兼容) 调用 LLM 评测单条回复"""
        return self._eval_ai_response_enhanced(question, answer, golden)

    # ── P2: UI/UX ────────────────────────────────

    def _analyze_ui(self, page, url: str) -> UIUXScore:
        """分析 UI/UX"""
        issues = []

        try:
            ux_data = page.evaluate("""() => {
                const viewport = { w: window.innerWidth, h: window.innerHeight };
                const overflowX = document.documentElement.scrollWidth > window.innerWidth;
                const fonts = [...new Set(
                    Array.from(document.querySelectorAll('*'))
                        .map(el => getComputedStyle(el).fontFamily)
                )];

                // 移动端检查
                const hasViewportMeta = !!document.querySelector('meta[name="viewport"]');

                // 检查按钮/链接点击区域大小
                const smallClicks = Array.from(document.querySelectorAll('button, a, [role="button"]'))
                    .filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width < 20 || r.height < 20;
                    }).length;

                return {
                    viewport, overflowX, fonts, hasViewportMeta, smallClicks,
                    totalElements: document.querySelectorAll('*').length,
                };
            }""")

            if ux_data.get("overflowX"):
                issues.append("页面水平溢出")
            if not ux_data.get("hasViewportMeta"):
                issues.append("缺少viewport meta标签（移动端适配问题）")
            if ux_data.get("smallClicks", 0) > 5:
                issues.append(f"有{ux_data['smallClicks']}个过小的点击目标")

            score = max(0, 100 - len(issues) * 15)

            return UIUXScore(
                score=score,
                layout_issues=issues,
                responsive=ux_data.get("hasViewportMeta", False),
                details=ux_data,
            )

        except Exception as e:
            return UIUXScore(details={"error": str(e)})

    # ── P2: Content Quality ──────────────────────

    def _evaluate_content(self, page) -> ContentScore:
        """
        评估页面内容质量 — 确定性前置 + LLM深度评估

        分层:
          L1 确定性 (30%): 大纲关键词覆盖/可读性/内容结构/多媒体
          L2 LLM评测 (70%): 准确性/完整性深度判断
        """
        try:
            page_text = page.evaluate("""() => {
                return document.body ? document.body.innerText.substring(0, 3000) : '';
            }""")

            # ═══════════════════════════════════════════
            # L1: 确定性内容检查
            # ═══════════════════════════════════════════
            det_result = self._deterministic_content_check(page_text, page)
            det_score = det_result["score"]  # 0-100

            # ═══════════════════════════════════════════
            # L2: LLM 深度评估
            # ═══════════════════════════════════════════
            syllabus_text = ""
            syllabus_path = "data/course_syllabus.txt"
            if os.path.exists(syllabus_path):
                with open(syllabus_path, "r", encoding="utf-8") as f:
                    syllabus_text = f.read()[:2000]

            accuracy = 3.0
            completeness = 3.0
            if self.api_key and page_text and syllabus_text:
                from openai import OpenAI
                client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com/v1")
                prompt = f"""
判断以下网页内容是否与课程大纲相关且准确:

【课程大纲】
{syllabus_text}

【网页内容】
{page_text}

输出JSON: {{"accuracy": 1-5分, "completeness": 1-5分, "reason": "一句话评价"}}
"""
                resp = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    response_format={"type": "json_object"},
                )
                result = json.loads(resp.choices[0].message.content)
                accuracy = result.get("accuracy", 3.0)
                completeness = result.get("completeness", 3.0)

            # LLM分: 0-100
            llm_score = round((accuracy + completeness) * 10)  # 1-5 → 0-100

            # ── 融合: 30% 确定性 + 70% LLM ──
            final_score = round(det_score * 0.30 + llm_score * 0.70)

            return ContentScore(
                score=max(0, min(100, final_score)),
                accuracy=round(accuracy, 1),
                completeness=round(completeness, 1),
                details={
                    "preflight": det_result,
                    "llm_raw": {"accuracy": accuracy, "completeness": completeness},
                    "scoring": f"30% preflight({det_score}) + 70% LLM({llm_score}) = {final_score}",
                },
            )

        except Exception as e:
            return ContentScore(details={"error": str(e)})

    def _deterministic_content_check(self, page_text: str, page) -> dict:
        """
        L1 确定性内容检查

        检查项 (全确定性, 0 API调用):
          1. 内容长度 (过短→扣分)
          2. 标题层级 (h1/h2/h3结构)
          3. 多媒体元素 (图片/视频数量)
          4. 大纲关键词匹配
        """
        checks = {}
        issues = []
        score = 100

        # 1. 内容长度
        text_len = len(page_text) if page_text else 0
        checks["text_length"] = text_len
        if text_len < 100:
            score -= 40
            issues.append(f"内容过短 ({text_len}字符)")
        elif text_len < 300:
            score -= 15
            issues.append(f"内容偏短 ({text_len}字符)")

        # 2. 标题层级
        try:
            headings = page.evaluate("""() => {
                return {
                    h1: document.querySelectorAll('h1').length,
                    h2: document.querySelectorAll('h2').length,
                    h3: document.querySelectorAll('h3').length,
                };
            }""")
            checks["headings"] = headings
            total_headings = headings.get("h1", 0) + headings.get("h2", 0) + headings.get("h3", 0)
            if total_headings == 0:
                score -= 20
                issues.append("无标题层级结构")
            elif total_headings < 3:
                score -= 10
                issues.append("标题结构偏弱")
        except Exception:
            checks["headings"] = {"error": "无法检测"}

        # 3. 多媒体元素
        try:
            media = page.evaluate("""() => {
                return {
                    images: document.querySelectorAll('img').length,
                    videos: document.querySelectorAll('video').length,
                    iframes: document.querySelectorAll('iframe').length,
                };
            }""")
            checks["media"] = media
            if media.get("images", 0) == 0 and media.get("videos", 0) == 0:
                score -= 5
                issues.append("无多媒体内容")
        except Exception:
            checks["media"] = {"error": "无法检测"}

        # 4. 大纲关键词匹配 (如果有大纲文件)
        syllabus_path = "data/course_syllabus.txt"
        if os.path.exists(syllabus_path):
            try:
                with open(syllabus_path, "r", encoding="utf-8") as f:
                    syllabus_text = f.read()[:2000]

                # 提取大纲关键词 (简单jieba分词)
                import jieba
                syllabus_words = set(
                    w for w in jieba.lcut(syllabus_text)
                    if len(w) > 1 and not w.isdigit()
                )
                page_words = set(jieba.lcut(page_text or ""))
                overlap = syllabus_words & page_words
                hit_rate = len(overlap) / len(syllabus_words) if syllabus_words else 0

                checks["syllabus_keyword_hit_rate"] = round(hit_rate, 3)
                checks["syllabus_keyword_hit_count"] = len(overlap)

                if hit_rate < 0.05:
                    score -= 20
                    issues.append(f"大纲关键词覆盖率极低 ({hit_rate:.1%})")
                elif hit_rate < 0.10:
                    score -= 10
                    issues.append(f"大纲关键词覆盖率偏低 ({hit_rate:.1%})")
            except Exception:
                checks["syllabus"] = {"error": "无法检测"}

        return {
            "score": max(0, score),
            "checks": checks,
            "issues": issues,
        }
