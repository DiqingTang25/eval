"""
L1: 流量与结构捕获层 (Traffic & Structure Capture)

借鉴: Vespasian Capture (HAR→capture.json 两阶段分离)
      Unbrowse Passive Capture (6层路由发现管线)
      Explorbot Research (页面分块+ARIA树索引)

职责: Playwright 拦截 XHR/Fetch/WS → HAR, BFS 遍历页面 → 快照
输出: CaptureResult (routes + pages + url_graph + har)
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from playwright.sync_api import Page, BrowserContext, Route, Request, Response

from .models import RouteNode, PageSnapshot, CaptureResult

# ── 静态资源扩展名 (不纳入API分析) ──
STATIC_EXTENSIONS = {
    ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".ico", ".woff", ".woff2", ".ttf", ".eot", ".map", ".webp",
    ".mp4", ".webm", ".mp3", ".wav", ".pdf", ".zip",
}

# ── 静态资源路径前缀 ──
STATIC_PATH_PREFIXES = [
    "/static/", "/assets/", "/public/", "/dist/", "/build/",
    "/_next/", "/__next/", "/node_modules/", "/cdn/",
    "/favicon", "/manifest", "/robots.txt", "/sitemap",
]

# ── 页面内容扩展名 (会渲染为页面的URL) ──
PAGE_EXTENSIONS = {"", ".html", ".htm", ".php", ".asp", ".aspx", ".jsp"}

# ── BFS 最大深度 ──
MAX_CRAWL_DEPTH = 3
MAX_PAGES = 50


def _is_static_resource(url: str) -> bool:
    """判断URL是否为静态资源"""
    parsed = urlparse(url)
    path = parsed.path.lower()

    # 检查扩展名
    for ext in STATIC_EXTENSIONS:
        if path.endswith(ext):
            return True

    # 检查路径前缀
    for prefix in STATIC_PATH_PREFIXES:
        if prefix in path:
            return True

    return False


def _is_same_origin(url: str, base_url: str) -> bool:
    """检查是否同源"""
    try:
        target = urlparse(url)
        base = urlparse(base_url)
        return (target.scheme == base.scheme and
                target.netloc == base.netloc)
    except Exception:
        return False


def _is_page_url(url: str) -> bool:
    """判断URL是否可能是页面 (而非API或资源)"""
    parsed = urlparse(url)
    path = parsed.path.lower()

    # 明确是页面的情况
    if any(path.endswith(ext) for ext in PAGE_EXTENSIONS):
        return True

    # 明确是API的情况
    api_indicators = ["/api/", "/graphql", "/rpc/", "/v1/", "/v2/"]
    if any(ind in path for ind in api_indicators):
        return False

    # 默认: 没有扩展名且不包含API关键词 → 可能是SPA路由
    ext = Path(path).suffix
    if not ext:
        return True

    return False


def _truncate_text(text: str, max_chars: int = 5000) -> str:
    """截断文本到最大字符数"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... [截断, 原长度 {len(text)} 字符]"


def _extract_dom_summary(page: Page, max_chars: int = 2000) -> str:
    """提取 DOM/ARIA 树摘要"""
    try:
        # 尝试获取 ARIA 快照 (Playwright 的 accessibility snapshot)
        snapshot = page.accessibility.snapshot()
        if snapshot:
            summary = json.dumps(snapshot, ensure_ascii=False, default=str)
            return _truncate_text(summary, max_chars)
    except Exception:
        pass

    # Fallback: 提取可见文本
    try:
        text = page.inner_text("body")
        return _truncate_text(text, max_chars)
    except Exception:
        return ""


def _detect_framework(page: Page) -> list[str]:
    """检测前端框架"""
    hints = []
    try:
        html = page.content().lower()

        # React
        if 'react' in html or 'data-reactroot' in html or '__react' in html:
            hints.append("react")
        if 'react-dom' in html or 'react.development' in html:
            hints.append("react")

        # Vue
        if 'vue' in html or 'data-v-' in html or '__vue__' in html:
            hints.append("vue")
        if 'vue.js' in html or 'vue.min.js' in html:
            hints.append("vue")

        # Angular
        if 'ng-version' in html or 'ng-app' in html or '_ngcontent' in html:
            hints.append("angular")

        # Next.js
        if '__next' in html or '__NEXT_DATA__' in html:
            hints.append("next")

        # Ant Design (常见于教学平台)
        if 'ant-' in html or 'antd' in html:
            hints.append("antd")

        # Element UI
        if 'el-' in html and ('element' in html or 'element-ui' in html):
            hints.append("element_ui")

    except Exception:
        pass

    return hints if hints else ["unknown"]


def _extract_interactive_elements(page: Page) -> list[dict]:
    """提取交互元素清单 (借鉴 Explorbot Research 的页面分块)"""
    elements = []
    selectors = [
        ("button", "button:visible"),
        ("link", "a[href]:visible"),
        ("input", "input:visible"),
        ("select", "select:visible"),
    ]

    for role, selector in selectors:
        try:
            els = page.locator(selector).all()
            for i, el in enumerate(els[:20]):  # 每种最多20个
                try:
                    text = el.inner_text().strip()[:50] if role != "input" else ""
                    tag = el.evaluate("el => el.tagName").lower() if i == 0 else role

                    # 生成语义提示
                    semantic = ""
                    if text:
                        if any(kw in text for kw in ["帮助", "帮帮我", "help", "卡住", "stuck"]):
                            semantic = "help_button"
                        elif any(kw in text for kw in ["下一步", "next", "继续", "continue"]):
                            semantic = "next_step"
                        elif any(kw in text for kw in ["上一", "prev", "back", "返回"]):
                            semantic = "prev_step"
                        elif any(kw in text for kw in ["提交", "submit", "完成", "complete"]):
                            semantic = "submit"
                        elif any(kw in text for kw in ["登录", "login", "登入"]):
                            semantic = "login"
                        elif any(kw in text for kw in ["发送", "send", "chat"]):
                            semantic = "send_message"

                    # 生成稳定hash (WALT技术)
                    el_id = el.get_attribute("id") or ""
                    el_class = el.get_attribute("class") or ""
                    el_name = el.get_attribute("name") or ""
                    hash_input = f"{tag}|{el_id}|{el_class[:50]}|{el_name}|{text[:50]}"
                    stable_hash = hashlib.md5(hash_input.encode()).hexdigest()[:8]

                    elements.append({
                        "role": role if not semantic else semantic,
                        "tag": tag,
                        "text": text[:80],
                        "selector": f"{tag}#{el_id}" if el_id else f"{tag}.{el_class[:30]}",
                        "semantic_hint": semantic,
                        "stable_hash": stable_hash,
                    })
                except Exception:
                    continue
        except Exception:
            continue

    return elements


# ═══════════════════════════════════════════════════════════════
# 主类
# ═══════════════════════════════════════════════════════════════

class TrafficInterceptor:
    """网络流量拦截器 (借鉴 Vespasian Capture 模块)"""

    def __init__(self, verbose: bool = True):
        self.routes: list[RouteNode] = []
        self.verbose = verbose

    def install(self, page: Page) -> None:
        """安装路由拦截器"""
        page.on("request", self._on_request)
        page.on("response", self._on_response)

    def _on_request(self, request: Request):
        """记录请求 (暂存, 等response再完整记录)"""
        # 只标记, 实际记录在 response 阶段
        pass

    def _on_response(self, response: Response):
        """记录响应"""
        request = response.request
        url = request.url
        resource_type = request.resource_type

        # 跳过静态资源
        if resource_type in ("stylesheet", "font", "image", "media", "manifest"):
            return
        if _is_static_resource(url):
            return

        # 尝试获取响应体
        response_sample = None
        content_type = ""
        try:
            content_type = response.headers.get("content-type", "")
            if "json" in content_type or "xml" in content_type or "text" in content_type:
                body = response.body()
                if len(body) < 50000:  # 跳过超大响应
                    try:
                        if "json" in content_type:
                            response_sample = json.loads(body)
                        else:
                            response_sample = body.decode("utf-8", errors="replace")[:2000]
                    except Exception:
                        response_sample = str(body[:1000])
        except Exception:
            pass

        # 获取请求payload
        request_payload = None
        try:
            if request.post_data:
                post_data = request.post_data
                try:
                    request_payload = json.loads(post_data)
                except Exception:
                    request_payload = post_data[:1000]
        except Exception:
            pass

        route = RouteNode(
            url=url,
            method=request.method,
            status=response.status,
            content_type=content_type,
            request_headers=dict(request.headers),
            request_payload=request_payload,
            response_headers=dict(response.headers),
            response_sample=response_sample,
            response_size=int(response.headers.get("content-length", 0)),
            duration_ms=0,  # Playwright 不直接提供, 需要手动计时
            parent_url=page.url if hasattr(response, 'frame') else "",
            initiator_type=resource_type or "",
        )

        self.routes.append(route)


class NavigationExplorer:
    """导航结构探索器 (BFS 遍历)"""

    def __init__(self, base_url: str, verbose: bool = True):
        self.base_url = base_url.rstrip("/")
        self.verbose = verbose
        self.visited: set[str] = set()
        self.url_graph: dict[str, list[str]] = {}

    def explore(self, page: Page, start_url: str = "",
                max_depth: int = MAX_CRAWL_DEPTH,
                max_pages: int = MAX_PAGES) -> list[str]:
        """
        BFS 遍历: 首页 → 导航链接 → 子页 → 更深层
        :returns: 所有已访问的URL列表
        """
        start_url = start_url or self.base_url
        start_url = start_url.rstrip("/")

        queue: list[tuple[str, int, str]] = [(start_url, 0, "")]
        # (url, depth, parent_url)

        while queue and len(self.visited) < max_pages:
            url, depth, parent = queue.pop(0)

            if url in self.visited:
                continue
            if depth > max_depth:
                continue
            if not _is_same_origin(url, self.base_url):
                continue

            self.visited.add(url)
            if parent:
                self.url_graph.setdefault(parent, []).append(url)

            if self.verbose:
                print(f"  🌐 [Depth {depth}] {url[:100]}")

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                time.sleep(1)
            except Exception as e:
                if self.verbose:
                    print(f"    ⚠ 导航失败: {e}")
                continue

            # 收集本页面的所有链接
            child_links = self._collect_links(page, url)
            for link in child_links:
                if link not in self.visited:
                    queue.append((link, depth + 1, url))

        if self.verbose:
            print(f"  ✅ BFS 完成: 访问 {len(self.visited)} 个页面, "
                  f"深度 {max_depth}")

        return list(self.visited)

    def _collect_links(self, page: Page, current_url: str) -> list[str]:
        """收集页面上的所有同源链接"""
        links = []
        try:
            anchors = page.locator("a[href]").all()
            for a in anchors:
                try:
                    href = a.get_attribute("href")
                    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                        continue

                    full_url = urljoin(current_url, href)
                    # 去掉 fragment
                    full_url = full_url.split("#")[0]

                    if (_is_same_origin(full_url, self.base_url) and
                        full_url not in self.visited and
                        not _is_static_resource(full_url) and
                        _is_page_url(full_url)):
                        links.append(full_url)
                except Exception:
                    continue
        except Exception:
            pass

        # 去重并限制数量
        return list(dict.fromkeys(links))[:30]


class PageSnapshotter:
    """页面快照器"""

    def __init__(self, screenshot_dir: Path, verbose: bool = True):
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose

    def snapshot(self, page: Page, url: str, index: int) -> PageSnapshot:
        """对当前页面做快照"""
        title = page.title()

        # DOM 摘要
        dom_summary = _extract_dom_summary(page)

        # 文本内容
        try:
            text_content = page.inner_text("body")
            text_content = _truncate_text(text_content, 5000)
        except Exception:
            text_content = ""

        # 框架检测
        framework_hints = _detect_framework(page)

        # 交互元素
        elements = _extract_interactive_elements(page)

        # 截图
        screenshot_path = ""
        try:
            fname = f"page_{index:03d}_{hashlib.md5(url.encode()).hexdigest()[:8]}.png"
            spath = self.screenshot_dir / fname
            page.screenshot(path=str(spath), full_page=False)
            screenshot_path = str(spath)
        except Exception as e:
            if self.verbose:
                print(f"    ⚠ 截图失败: {e}")

        snapshot = PageSnapshot(
            url=url,
            title=title,
            dom_summary=dom_summary,
            text_content=text_content,
            interactive_elements=elements,
            screenshot_path=screenshot_path,
            framework_hints=framework_hints,
        )

        if self.verbose:
            print(f"  📸 快照: {title[:60]} | {len(elements)} 个交互元素 | "
                  f"框架: {framework_hints}")

        return snapshot


# ═══════════════════════════════════════════════════════════════
# L1 主入口
# ═══════════════════════════════════════════════════════════════

def run_l1_capture(
    page: Page,
    context: BrowserContext,
    base_url: str,
    output_dir: Path,
    max_depth: int = MAX_CRAWL_DEPTH,
    max_pages: int = MAX_PAGES,
    har_path: str = "",
    verbose: bool = True,
) -> CaptureResult:
    """
    L1 完整流程: 安装拦截器 → BFS遍历 → 逐页快照

    :returns: CaptureResult
    """
    interceptor = TrafficInterceptor(verbose=verbose)
    explorer = NavigationExplorer(base_url, verbose=verbose)
    snapshotter = PageSnapshotter(output_dir / "screenshots", verbose=verbose)

    # Step 1: 安装流量拦截
    interceptor.install(page)

    # Step 2: 导航到首页并启动BFS
    if verbose:
        print(f"\n{'='*60}")
        print(f"L1: 流量与结构捕获 — {base_url}")
        print(f"{'='*60}")

    # 先访问首页
    page.goto(base_url, wait_until="networkidle", timeout=30000)
    time.sleep(2)

    # BFS 遍历
    visited_urls = explorer.explore(page, start_url=base_url,
                                    max_depth=max_depth, max_pages=max_pages)

    # Step 3: 对每个页面做快照 (这里已经访问过了, 但如果BFS只访问了一次,
    #          我们需要重新访问来做快照)
    pages: list[PageSnapshot] = []
    for i, url in enumerate(visited_urls):
        try:
            if page.url != url:
                page.goto(url, wait_until="networkidle", timeout=20000)
                time.sleep(1)
            snapshot = snapshotter.snapshot(page, url, i)
            pages.append(snapshot)
        except Exception as e:
            if verbose:
                print(f"  ⚠ 快照跳过 {url}: {e}")

    # Step 4: 分类统计
    routes = interceptor.routes
    api_routes = [r for r in routes
                  if "json" in r.content_type or "/api/" in r.url.lower()]
    static_routes = [r for r in routes
                     if _is_static_resource(r.url)]

    # Step 5: 保存 HAR (简化版, 完整HAR格式较复杂, Phase 1 用JSON)
    if har_path:
        har_file = Path(har_path)
    else:
        har_file = output_dir / "capture.json"

    har_data = {
        "base_url": base_url,
        "visited_urls": visited_urls,
        "routes": [
            {
                "url": r.url,
                "method": r.method,
                "status": r.status,
                "content_type": r.content_type,
                "response_size": r.response_size,
                "parent_url": r.parent_url,
            }
            for r in routes
        ],
    }
    har_file.write_text(json.dumps(har_data, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    result = CaptureResult(
        base_url=base_url,
        start_url=base_url,
        routes=routes,
        pages=pages,
        url_graph=explorer.url_graph,
        har_path=str(har_file),
        total_requests=len(routes),
        api_requests=len(api_routes),
        static_requests=len(static_routes),
    )

    if verbose:
        print(f"\n  📊 L1 捕获完成:")
        print(f"     页面: {len(pages)}")
        print(f"     总请求: {result.total_requests}")
        print(f"     API请求: {result.api_requests}")
        print(f"     静态资源: {result.static_requests}")

    return result
