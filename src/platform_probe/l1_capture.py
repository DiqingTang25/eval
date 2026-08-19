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


def _safe_sample(data, max_len: int = 5000):
    """安全截断响应样本用于JSON序列化 — 仅序列化时使用, 不修改原数据"""
    if data is None:
        return None
    if isinstance(data, str):
        return data[:max_len]
    if isinstance(data, (dict, list)):
        s = json.dumps(data, ensure_ascii=False, default=str)
        if len(s) > max_len:
            # 只存keys + preview用于调试, 完整数据在 RouteNode.response_sample
            keys_or_len = list(data.keys())[:20] if isinstance(data, dict) else "list[{}]".format(len(data))
            return {
                "__truncated__": True,
                "__size__": len(s),
                "keys": keys_or_len,
                "preview": s[:500]
            }
        return data
    return str(data)[:max_len]


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
    """
    流量拦截器 — 双模式捕获

    Mode 1 (route): page.route() + route.fetch() — 完整捕获响应体 (P0修复)
    Mode 2 (response): page.on("response") — 轻量级URL记录 (fallback)

    同时捕获 WebSocket 连接和消息。
    """

    def __init__(self, verbose: bool = True):
        self.routes: list[RouteNode] = []
        self.verbose = verbose
        self._page = None
        self._ws_messages: list[dict] = []  # WebSocket消息

    def install(self, page: Page, capture_bodies: bool = False) -> None:
        """
        安装拦截器

        :param capture_bodies: True → page.route() 捕获完整响应体
                              False → page.on("response") 轻量模式
        """
        self._page = page

        if capture_bodies:
            self._install_route_mode(page)
        else:
            self._install_response_mode(page)

        # WebSocket 拦截 (始终启用)
        self._install_ws_intercept(page)

    def _install_route_mode(self, page: Page):
        """P0修复: page.route() 捕获完整响应体 + 请求体

        使用多模式匹配覆盖常见API路径结构, 对匹配的请求:
        1. route.fetch() → 获取完整响应
        2. 解析JSON响应体 → response_sample
        3. 提取请求体 → request_payload
        4. route.fulfill() → 将响应返回浏览器
        """
        if self.verbose:
            print("  📡 拦截模式: route (完整响应体捕获)")

        def handle_route(route):
            try:
                request = route.request
                url = request.url
                rt = request.resource_type

                # 快速跳过: 静态资源
                if rt in ("stylesheet", "font", "image", "media", "manifest"):
                    return route.continue_()
                if _is_static_resource(url) or url.startswith("data:"):
                    return route.continue_()

                # ── API判断 (比之前更全面) ──
                url_lower = url.lower()
                is_api = (
                    # 明确的API路径模式
                    any(kw in url_lower for kw in [
                        "/api/", "/v1/", "/v2/", "/v3/",
                        "/graphql", "/auth/", "/rpc/",
                        "/graph-source", "/careers", "/digital-teacher",
                        "/context", "/events",
                    ]) or
                    # JSON Accept header
                    "json" in (request.headers.get("accept", "") or "") or
                    # 写操作 (POST/PUT/PATCH/DELETE大概率是API)
                    request.method in ("POST", "PUT", "PATCH", "DELETE") or
                    # XHR/fetch 资源类型 (几乎都是API)
                    rt in ("xhr", "fetch")
                )

                if not is_api:
                    return route.continue_()

                # ── 提取请求体 (在fetch之前, 因为fetch可能改变状态) ──
                request_payload = None
                try:
                    pd = request.post_data
                    if pd:
                        try:
                            request_payload = json.loads(pd)
                        except Exception:
                            request_payload = pd[:1000]
                except Exception:
                    pass

                # ── Fetch完整响应 ──
                try:
                    response = route.fetch()
                except Exception as fetch_err:
                    # fetch失败 → 继续原请求 (不阻塞页面)
                    if self.verbose:
                        print(f"    ⚠️ route.fetch失败 {url[:80]}: {fetch_err}")
                    return route.continue_()

                # ── 解析响应体 (多策略: text → JSON, bytes → JSON, body → text) ──
                body = response.body()
                content_type = response.headers.get("content-type", "")
                response_sample = None
                response_size = len(body)
                try:
                    if "json" in content_type and 0 < response_size < 100000:
                        # 优先: response.text() 自动处理编码 (BOM/UTF-8/UTF-16等)
                        text = response.text()
                        if text and text.strip():
                            try:
                                response_sample = json.loads(text)
                            except json.JSONDecodeError:
                                # 回退: bytes直接解析
                                try:
                                    response_sample = json.loads(body)
                                except json.JSONDecodeError:
                                    # 最后: 保存文本前500字符
                                    response_sample = text[:500]
                    elif 0 < response_size < 5000:
                        try:
                            response_sample = response.text()[:2000]
                        except Exception:
                            response_sample = body.decode("utf-8", errors="replace")[:2000]
                except Exception as e:
                    if self.verbose:
                        print(f"    ⚠ body parse err {url[:60]}: {e}")
                    if 0 < response_size < 2000:
                        try:
                            response_sample = body.decode("utf-8", errors="replace")
                        except Exception:
                            pass

                parent_url = ""
                try:
                    if self._page:
                        parent_url = self._page.url
                except Exception:
                    pass

                self.routes.append(RouteNode(
                    url=url, method=request.method,
                    status=response.status,
                    content_type=content_type,
                    request_headers=dict(request.headers),
                    request_payload=request_payload,
                    response_headers=dict(response.headers),
                    response_sample=response_sample,
                    response_size=response_size,
                    duration_ms=0,
                    parent_url=parent_url,
                    initiator_type=rt or "",
                ))

                # 将捕获的响应返回给浏览器
                return route.fulfill(response=response)

            except Exception:
                # 最后防线: 任何未预期的错误都不应阻塞页面
                try:
                    return route.continue_()
                except Exception:
                    pass

        # ── 注册路由模式 (从具体到通用) ──
        # 这些是常见的API URL模式, Playwright在浏览器层过滤
        page.route("**/*api*/**", handle_route)
        page.route("**/*v1*/**", handle_route)
        page.route("**/*v2*/**", handle_route)
        page.route("**/*v3*/**", handle_route)
        page.route("**/graphql**", handle_route)
        page.route("**/auth/**", handle_route)
        # 兜底: 捕获所有XHR/fetch请求 (这些几乎都是API)
        page.route("**/*", lambda route: (
            handle_route(route) if route.request.resource_type in ("xhr", "fetch")
            else route.continue_()
        ))

    def _install_response_mode(self, page: Page):
        """轻量URL记录 + 响应体捕获 (P0修复: response.body() 被动捕获)"""
        if self.verbose:
            print("  📡 拦截模式: response (被动捕获响应体)")

        def on_response(response):
            try:
                request = response.request
                url = request.url
                rt = request.resource_type
                if rt in ("stylesheet", "font", "image", "media", "manifest", "script", "document"):
                    return
                if _is_static_resource(url) or url.startswith("data:"):
                    return

                request_payload = None
                try:
                    pd = request.post_data
                    if pd:
                        try:
                            request_payload = json.loads(pd)
                        except Exception:
                            request_payload = pd[:1000]
                except Exception:
                    pass

                # ── P0修复: 捕获响应体 ──
                content_type = response.headers.get("content-type", "")
                response_sample = None
                response_size = 0
                try:
                    # 对JSON响应尝试读取body
                    if "json" in content_type:
                        body = response.body()
                        response_size = len(body)
                        if response_size < 50000:
                            try:
                                response_sample = json.loads(body)
                            except Exception:
                                if response_size < 2000:
                                    response_sample = body.decode("utf-8", errors="replace")
                    elif response.status in (200, 201) and request.method in ("POST", "PUT", "PATCH"):
                        # 非JSON但可能是API响应 → 小响应体捕获
                        try:
                            body = response.body()
                            if len(body) < 2000:
                                response_sample = body.decode("utf-8", errors="replace")
                                response_size = len(body)
                        except Exception:
                            pass
                except Exception:
                    # response.body() 可能因响应未完成/已消费而失败
                    pass

                parent_url = ""
                try:
                    if self._page:
                        parent_url = self._page.url
                except Exception:
                    pass

                self.routes.append(RouteNode(
                    url=url, method=request.method, status=response.status,
                    content_type=content_type,
                    request_headers={}, request_payload=request_payload,
                    response_headers={}, response_sample=response_sample,
                    response_size=response_size, duration_ms=0,
                    parent_url=parent_url, initiator_type=rt or "",
                ))
            except Exception:
                pass

        page.on("response", on_response)

    def _install_ws_intercept(self, page: Page):
        """WebSocket 拦截 — 记录连接和消息"""
        def on_ws(ws):
            ws_url = ws.url
            if self.verbose:
                print(f"  🔌 WS连接: {ws_url[:100]}")

            self._ws_messages.append({
                "type": "connect", "url": ws_url, "data": None})

            def on_frame_sent(frame):
                payload = frame if isinstance(frame, str) else str(frame)[:2000]
                self._ws_messages.append({
                    "type": "send", "url": ws_url, "data": payload})

            def on_frame_received(frame):
                payload = frame if isinstance(frame, str) else str(frame)[:2000]
                self._ws_messages.append({
                    "type": "recv", "url": ws_url, "data": payload})

            def on_close():
                self._ws_messages.append({
                    "type": "close", "url": ws_url, "data": None})

            ws.on("framesent", on_frame_sent)
            ws.on("framereceived", on_frame_received)
            ws.on("close", on_close)

        try:
            page.on("websocket", on_ws)
        except Exception:
            # 老版本Playwright可能不支持
            if self.verbose:
                print("  ⚠️ WebSocket拦截不支持 (需Playwright ≥1.48)")

    @property
    def ws_endpoints(self) -> list[str]:
        """所有WebSocket连接URL"""
        return list(set(m["url"] for m in self._ws_messages if m["type"] == "connect"))

    @property
    def ws_count(self) -> int:
        return len(self.ws_endpoints)


class NavigationExplorer:
    """导航结构探索器 — 支持传统链接 + SPA交互式探索"""

    def __init__(self, base_url: str, verbose: bool = True):
        self.base_url = base_url.rstrip("/")
        self.verbose = verbose
        self.visited: set[str] = set()
        self.url_graph: dict[str, list[str]] = {}

    def explore(self, page: Page, start_url: str = "",
                max_depth: int = MAX_CRAWL_DEPTH,
                max_pages: int = MAX_PAGES,
                snapshotter=None) -> list[str]:
        """BFS + 交互式探索 (P0增强: SPA交互始终执行, 即时截图)"""
        start_url = start_url or self.base_url
        start_url = start_url.rstrip("/")

        # Phase 1: 传统 BFS (链接跟踪)
        link_pages = self._bfs_links(page, start_url, max_depth, max_pages)
        snap_base = len(link_pages)  # SPA snapshots start after BFS pages

        # Phase 2: SPA 交互式探索 (始终执行, 即时截图供L2 DOM fallback)
        if self.verbose:
            print(f"  🔍 传统链接发现 {len(link_pages)} 个页面, 交互探索SPA...")
        spa_pages = self._explore_spa_fast(page, start_url, max_depth=2,
                                           snapshotter=snapshotter,
                                           snapshot_index=snap_base)
        all_pages = list(dict.fromkeys(link_pages + spa_pages))

        if self.verbose:
            print(f"  ✅ 探索完成: {len(all_pages)} 个页面")

        return all_pages

    def _bfs_links(self, page, start_url, max_depth, max_pages):
        """传统 BFS — 跟踪 <a href> 链接"""
        queue: list[tuple[str, int, str]] = [(start_url, 0, "")]
        visited: set[str] = set()

        while queue and len(visited) < max_pages:
            url, depth, parent = queue.pop(0)
            if url in visited or depth > max_depth:
                continue
            if not _is_same_origin(url, self.base_url):
                continue
            visited.add(url)
            if parent:
                self.url_graph.setdefault(parent, []).append(url)
            if self.verbose:
                print(f"  🌐 [D{depth}] {url[:100]}")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
            except Exception as e:
                if self.verbose:
                    print(f"    ⚠ 跳过: {str(e)[:80]}")
                continue

            for link in self._collect_links(page, url):
                if link not in visited:
                    queue.append((link, depth + 1, url))

        return list(visited)

    def _explore_spa_fast(self, page: Page, start_url: str, max_depth: int = 2,
                          snapshotter=None, snapshot_index: int = 0) -> list[str]:
        """快速SPA探索 — 多层卡片点击: Career → Phase/Module → Lesson/Course

        每层点击触发API调用, 配合 route 拦截器捕获响应体。
        SPA页面即时截图 → L2 DOM fallback 可提取 Step 列表。
        """
        discovered: list[str] = []
        clicked: set[str] = set()
        snap_idx = snapshot_index

        # 等待SPA渲染
        time.sleep(3)

        # ── 第一层: Career/Subject 卡片 ──
        level1_selectors = [
            "button.ci-shell-career-card", "[class*='career-card']",
            "[class*='course-card']", "[class*='subject-card']",
            "[class*='category-card']", "[class*='track-card']",
        ]
        discovered, snap_idx = self._click_cards(
            page, level1_selectors, clicked, discovered,
            max_per_level=8, snapshotter=snapshotter, snapshot_index=snap_idx)
        if self.verbose:
            print(f"  🖱️ 第一层: {len([d for d in discovered if '|' in d])} 个SPA页面")

        # ── 第二层: Phase/Module 卡片 (在Career页面内) ──
        if max_depth >= 1:
            time.sleep(2)
            level2_selectors = [
                "[class*='phase-card']", "[class*='module-card']",
                "[class*='phase-item']", "[class*='module-item']",
                "[class*='ant-card']", "[class*='el-card']",
                "[role='tab']", "[class*='nav-item']",
            ]
            discovered, snap_idx = self._click_cards(
                page, level2_selectors, clicked, discovered,
                max_per_level=6, snapshotter=snapshotter, snapshot_index=snap_idx)

        # ── 第三层: Lesson/Step 卡片 (在Phase页面内) ──
        if max_depth >= 2:
            time.sleep(2)
            level3_selectors = [
                "[class*='lesson-card']", "[class*='step-card']",
                "[class*='lesson-item']", "[class*='step-item']",
                "[class*='list-item']", "a[class*='lesson']",
            ]
            discovered, snap_idx = self._click_cards(
                page, level3_selectors, clicked, discovered,
                max_per_level=6, snapshotter=snapshotter, snapshot_index=snap_idx)

        return discovered

    def _click_cards(self, page, selectors, clicked, discovered,
                     max_per_level=8, snapshotter=None, snapshot_index=0) -> tuple:
        """点击匹配选择器的可见卡片, 记录URL/标题变化。有snapshotter时即时截图。

        :returns: (discovered, snapshot_index) — SPA页面即时截图供L2 DOM fallback
        """
        snap_idx = snapshot_index
        for card_sel in selectors:
            if len([d for d in discovered if '|' in d]) >= max_per_level:
                break
            try:
                cards = page.locator(card_sel).all()
                for card in cards:
                    if len([d for d in discovered if '|' in d]) >= max_per_level:
                        break
                    try:
                        if not card.is_visible():
                            continue
                        text = card.inner_text().strip()[:60]
                        if not text or text in clicked:
                            continue
                        clicked.add(text)

                        old_url = page.url
                        old_title = page.title()
                        card.evaluate("el => el.click()")
                        time.sleep(1.5)

                        new_url = page.url
                        new_title = page.title()
                        if new_url != old_url or new_title != old_title:
                            state_key = f"{new_url}|{new_title}"
                            if state_key not in discovered:
                                discovered.append(state_key)
                                # ── 即时截图: SPA内容只在当前页面状态可见 ──
                                if snapshotter:
                                    try:
                                        snap = snapshotter.snapshot(
                                            page, new_url, snap_idx)
                                        snap_idx += 1
                                        if self.verbose:
                                            elements = len(snap.interactive_elements)
                                            print(f"    📸 SPA快照: \"{text[:30]}\" → {new_title[:40]}"
                                                  f" ({elements} elements)")
                                    except Exception:
                                        pass
                    except Exception:
                        continue
            except Exception:
                continue
        return discovered, snap_idx

    def _explore_spa_full(self, page, start_url, max_pages):
        """SPA 交互式探索 (完整版, 保留供后续使用) — 点击导航元素发现新内容"""
        discovered: list[str] = [start_url]
        clicked: set[str] = set()

        # 收集所有可交互的导航元素
        nav_selectors = [
            "nav a", "[class*='menu'] a", "[class*='sidebar'] a",
            "[class*='nav'] a", "[class*='tab']", "[class*='ant-menu-item']",
            "[class*='el-menu-item']", "[role='tab']", "[role='menuitem']",
            "[class*='card']", "[class*='tile']", "[class*='course']",
            "[class*='lesson']", "[class*='phase']", "[class*='module']",
            "button[class*='nav']", "button[class*='menu']",
        ]

        for depth in range(3):  # 最多3轮交互
            if len(discovered) >= max_pages:
                break

            new_found = 0
            for sel in nav_selectors:
                try:
                    elements = page.locator(sel).all()
                    for el in elements[:20]:
                        try:
                            if not el.is_visible():
                                continue
                            text = el.inner_text().strip()[:50]
                            if not text or len(text) < 1:
                                continue

                            # 生成唯一标识避免重复点击
                            import hashlib
                            el_hash = hashlib.md5(
                                f"{text}{el.get_attribute('class') or ''}".encode()
                            ).hexdigest()[:8]
                            if el_hash in clicked:
                                continue
                            clicked.add(el_hash)

                            # 记录当前页面状态
                            current_url = page.url
                            current_title = page.title()

                            # 安全点击
                            try:
                                el.evaluate("el => el.click()")
                                time.sleep(2)
                            except Exception:
                                continue

                            # 检查是否有变化
                            new_url = page.url
                            new_title = page.title()
                            if new_url != current_url or new_title != current_title:
                                state_key = f"{new_url}|{new_title}"
                                if state_key not in discovered:
                                    discovered.append(state_key)
                                    new_found += 1
                                    if self.verbose:
                                        print(f"  🖱️ [SPA] 点击 \"{text[:40]}\" → {new_title[:50]}")

                                    # 递归: 在新页面状态下继续探索
                                    if len(discovered) < max_pages:
                                        sub_links = self._collect_links(page, new_url)
                                        for link in sub_links:
                                            if link not in discovered:
                                                discovered.append(link)

                        except Exception:
                            continue
                except Exception:
                    continue

            if new_found == 0:
                break  # 没有新发现, 停止

        return discovered

    def _collect_links(self, page: Page, current_url: str) -> list[str]:
        """收集页面上所有同源链接 (含 <a href> 和 router-link)"""
        links = []
        try:
            for a in page.locator("a[href]").all():
                try:
                    href = a.get_attribute("href")
                    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                        continue
                    full_url = urljoin(current_url, href).split("#")[0]
                    if (_is_same_origin(full_url, self.base_url) and
                        full_url not in self.visited and
                        not _is_static_resource(full_url)):
                        links.append(full_url)
                except Exception:
                    continue
        except Exception:
            pass
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
    capture_bodies: bool = True,
) -> CaptureResult:
    """
    L1 完整流程: 安装拦截器 → BFS遍历 → 逐页快照

    :param capture_bodies: True → page.route() 完整响应体 + 请求体 (P0默认)
                           False → page.on("response") 被动捕获 (低侵入fallback)
    :returns: CaptureResult
    """
    interceptor = TrafficInterceptor(verbose=verbose)
    explorer = NavigationExplorer(base_url, verbose=verbose)
    snapshotter = PageSnapshotter(output_dir / "screenshots", verbose=verbose)

    # Step 1: 安装流量拦截
    # P0修复: 默认使用 route 模式捕获完整响应体
    # 如遇SPA兼容性问题可改为 capture_bodies=False (response模式也捕获body)
    interceptor.install(page, capture_bodies=capture_bodies)

    # Step 2: 导航到首页并启动BFS (轻量模式)
    if verbose:
        print(f"\n{'='*60}")
        print(f"L1: 流量与结构捕获 — {base_url}")
        print(f"{'='*60}")

    # 设置默认超时 (避免SPA无限等待)
    page.set_default_navigation_timeout(15000)
    page.set_default_timeout(15000)

    # L0已经登录, 页面已在目标位置 — 不重复导航
    current_domain = urlparse(page.url).netloc
    target_domain = urlparse(base_url).netloc
    if current_domain != target_domain:
        try:
            page.goto(base_url, wait_until="domcontentloaded", timeout=20000)
        except Exception:
            pass
    time.sleep(2)

    # BFS 遍历 + 交互探索
    visited_urls = []
    try:
        # P0: SPA即时截图 — snapshotter传入explore, 课程内页DOM被L2 fallback使用
        visited_urls = explorer.explore(page, start_url=base_url,
                                        max_depth=max_depth,
                                        max_pages=max_pages,
                                        snapshotter=snapshotter)
    except Exception as e:
        if verbose:
            print(f"  ⚠️ BFS中止: {str(e)[:100]}")
        visited_urls = [page.url]

    # Step 3: 对每个页面做快照
    pages: list[PageSnapshot] = []
    for i, url in enumerate(visited_urls):
        try:
            if page.url != url:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    pass
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
                "response_sample": _safe_sample(r.response_sample),
                "request_payload": _safe_sample(r.request_payload),
                "parent_url": r.parent_url,
                "initiator_type": r.initiator_type,
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
