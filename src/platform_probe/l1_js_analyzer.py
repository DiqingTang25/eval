"""
L1.6: JS Bundle 逆向分析器

借鉴: Vespasian (JS static analysis + sourcemap recovery)
      A2A论文 (LLM分析JS源码变量名/路由片段 — 前提是拿到JS内容)
      WALT (从JS提取可参数化URL)

能力:
  1. 下载页面引用的所有 JS 文件
  2. 正则提取 API 路径 (URL strings, fetch/XHR calls, route defs)
  3. SourceMap 下载 + 还原 (minified → readable)
  4. 输出: 发现的隐藏API路径列表
"""

from __future__ import annotations

import json
import re
import hashlib
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from playwright.sync_api import Page

from .models import RouteNode

# ── API路径提取正则 ──
API_PATH_PATTERNS = [
    # fetch/axios/$.ajax calls
    re.compile(r'''(?:fetch|axios\.(?:get|post|put|delete|patch)|\.ajax)\s*\(\s*["']([^"']*api[^"']*)["']''', re.IGNORECASE),
    # URL strings containing /api/, /v1/, /v2/, /graphql
    re.compile(r'''["']((?:https?:)?//[^"']*(?:/api/|/v[12]/|/graphql|/rpc/|/rest/)[^"']*)["']''', re.IGNORECASE),
    # React Router paths
    re.compile(r'''path\s*:\s*["'](/[^"']*(?:api|phase|lesson|course|quiz|auth|user)[^"']*)["']''', re.IGNORECASE),
    # Vue Router paths
    re.compile(r'''{?\s*path\s*:\s*["'](/[^"']+)["']'''),
    # Next.js API routes
    re.compile(r'''["']/api/[^"']+["']'''),
    # Generic URL patterns with IDs
    re.compile(r'''["'](/[a-z-]+/\$\{[a-zA-Z]+\}|/[a-z-]+/:[\w]+)["']'''),
    # baseURL / API_BASE assignments
    re.compile(r'''(?:baseURL|API_BASE|apiUrl|apiPrefix)\s*[:=]\s*["']([^"']+)["']''', re.IGNORECASE),
    # WebSocket URLs
    re.compile(r'''["'](wss?://[^"']+)["']'''),
]

# ── 非API路径过滤 ──
NON_API_PATTERNS = [
    r'\.js', r'\.css', r'\.png', r'\.jpg', r'\.svg', r'\.woff',
    r'\.map$', r'node_modules', r'cdnjs', r'google-analytics',
    r'gtag', r'facebook', r'/_next/static', r'/__next',
]


def _is_api_candidate(url: str) -> bool:
    """判断URL是否可能是API端点"""
    if not url or len(url) < 3:
        return False
    for pattern in NON_API_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return False
    return True


class JSBundleAnalyzer:
    """JS Bundle 下载 + 静态分析"""

    def __init__(self, output_dir: Path, verbose: bool = True):
        self.output_dir = Path(output_dir) / "js_bundles"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose
        self._js_cache: dict[str, str] = {}  # url → content

    def analyze(self, page: Page, base_url: str) -> dict:
        """
        完整分析流程: 收集URL → 下载 → 提取路径 → SourceMap
        :returns: {api_paths, js_files, sourcemaps, stats}
        """
        # Step 1: 收集页面上的JS文件URL
        js_urls = self._collect_js_urls(page, base_url)
        if self.verbose:
            print(f"\n── L1.6: JS Bundle 逆向 ({len(js_urls)} 个JS文件) ──")

        # Step 2: 下载所有JS文件
        downloaded = 0
        for url in js_urls:
            content = self._download_js(url)
            if content:
                self._js_cache[url] = content
                downloaded += 1

        if self.verbose:
            print(f"  📥 下载: {downloaded}/{len(js_urls)} 个JS文件")

        # Step 3: 从JS内容提取API路径
        api_paths = set()
        for url, content in self._js_cache.items():
            paths = self._extract_api_paths(content)
            for p in paths:
                full_url = urljoin(base_url, p) if not p.startswith("http") else p
                if _is_api_candidate(full_url):
                    api_paths.add(full_url)

        if self.verbose:
            print(f"  🔍 提取API路径: {len(api_paths)} 个候选")

        # Step 4: SourceMap还原 (尝试)
        sourcemaps = {}
        for url in js_urls:
            if url.endswith('.js') and not url.endswith('.min.js'):
                sm = self._try_sourcemap(url)
                if sm:
                    sourcemaps[url] = sm

        if self.verbose and sourcemaps:
            print(f"  🗺️ SourceMap还原: {len(sourcemaps)} 个文件")

        # Step 5: 保存JS文件到磁盘
        for url, content in self._js_cache.items():
            fname = hashlib.md5(url.encode()).hexdigest()[:12] + '.js'
            (self.output_dir / fname).write_text(content, encoding='utf-8', errors='replace')

        return {
            "api_paths": sorted(api_paths),
            "js_files": len(self._js_cache),
            "sourcemaps": len(sourcemaps),
            "total_size_bytes": sum(len(c) for c in self._js_cache.values()),
        }

    def _collect_js_urls(self, page: Page, base_url: str) -> list[str]:
        """收集页面中所有 <script src> 和动态import的URL"""
        urls = set()

        # 1. <script src="..."> 标签
        scripts = page.locator("script[src]").all()
        for s in scripts:
            try:
                src = s.get_attribute("src")
                if src:
                    full = urljoin(base_url, src)
                    if _is_same_origin(full, base_url):
                        urls.add(full)
            except Exception:
                continue

        # 2. 从page.content()中提取
        try:
            html = page.content()
            # <script src="...">
            for m in re.finditer(r'<script[^>]+src="([^"]+)"', html):
                full = urljoin(base_url, m.group(1))
                if _is_same_origin(full, base_url):
                    urls.add(full)
            # import("...") 动态导入
            for m in re.finditer(r'import\s*\(\s*"([^"]+)"\s*\)', html):
                full = urljoin(base_url, m.group(1))
                if _is_same_origin(full, base_url):
                    urls.add(full)
        except Exception:
            pass

        return sorted(urls)

    def _download_js(self, url: str) -> Optional[str]:
        """下载JS文件内容"""
        try:
            resp = requests.get(url, timeout=15, headers={
                'Accept': 'text/javascript, application/javascript, */*',
                'User-Agent': 'Mozilla/5.0 (compatible; PlatformExplorer/1.0)',
            })
            if resp.status_code == 200 and len(resp.text) > 50:
                return resp.text
        except Exception:
            pass
        return None

    def _extract_api_paths(self, js_content: str) -> set[str]:
        """从JS内容中正则提取API路径"""
        paths = set()

        # 策略: 精确匹配 template literal 中的API路径
        # `${BASE}/auth/login` → /auth/login
        tmpl_pattern = re.compile(r'`\$\{[^}]*\}(/[^`]{2,80})`')
        for match in tmpl_pattern.finditer(js_content):
            path = match.group(1).strip()
            if self._is_valid_path(path):
                paths.add(path)

        # 策略: 直接字符串中的路径
        # "/api/v1/courses" or '/api/v1/courses'
        str_pattern = re.compile(r'''["']((?:/api/|/v[12]/|/auth/|/graphql|/courses?/|/lessons?/|/steps?/|/phase|/quiz|/chat|/agent|/login|/logout|/token|/user|/profile|/search|/knowledge)[^"'\s]{0,80})["']''', re.IGNORECASE)
        for match in str_pattern.finditer(js_content):
            path = match.group(1).strip()
            if self._is_valid_path(path):
                paths.add(path)

        # 策略: fetch/xhr 调用 (提取模板字符串中的URL片段)
        fetch_pattern = re.compile(r'''fetch\s*\(\s*`\$\{[^}]*\}(/[^`]{3,80})`\s*[,\)]''')
        for match in fetch_pattern.finditer(js_content):
            path = match.group(1).strip()
            if self._is_valid_path(path):
                paths.add(path)

        return paths

    @staticmethod
    def _is_valid_path(path: str) -> bool:
        """过滤无效的路径片段"""
        if not path or len(path) < 2 or len(path) > 120:
            return False
        # 不能包含JS关键字/语法
        invalid_chars = [';', ' ', '=', '{', '}', '(', ')', ':', '??', '=>', 'function']
        for c in invalid_chars:
            if c in path:
                return False
        # 必须以 / 开头且不含空格
        if not path.startswith('/'):
            return False
        return True

    def _try_sourcemap(self, js_url: str) -> Optional[dict]:
        """尝试下载SourceMap"""
        # 策略1: JS文件末尾的 sourceMappingURL
        if js_url in self._js_cache:
            content = self._js_cache[js_url]
            m = re.search(r'//# sourceMappingURL=(\S+)', content[-1000:])
            if m:
                map_url = urljoin(js_url, m.group(1))
                map_content = self._download_js(map_url)
                if map_content:
                    try:
                        sm = json.loads(map_content)
                        return {
                            "map_url": map_url,
                            "sources": sm.get("sources", [])[:20],
                            "source_count": len(sm.get("sources", [])),
                        }
                    except Exception:
                        pass

        # 策略2: 直接加 .map 后缀
        map_url = js_url + '.map'
        map_content = self._download_js(map_url)
        if map_content:
            try:
                sm = json.loads(map_content)
                return {
                    "map_url": map_url,
                    "sources": sm.get("sources", [])[:20],
                    "source_count": len(sm.get("sources", [])),
                }
            except Exception:
                pass

        return None


def _is_same_origin(url: str, base_url: str) -> bool:
    """检查是否同源"""
    try:
        t, b = urlparse(url), urlparse(base_url)
        return t.netloc == b.netloc and t.scheme == b.scheme
    except Exception:
        return False


def run_js_analysis(page: Page, base_url: str, output_dir: Path,
                    verbose: bool = True) -> dict:
    """L1.6 主入口"""
    analyzer = JSBundleAnalyzer(output_dir=output_dir, verbose=verbose)
    return analyzer.analyze(page, base_url)
