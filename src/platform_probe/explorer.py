"""
Platform Explorer 主协调器

五层流水线协调:
  L0: 认证检测与登录
  L1: 流量捕获 + 页面遍历
  L2: 教学结构推断 (Phase 1: 简化版, Phase 2: 完整实现)
  L3: API分类 + Step类型分类
  L4: Schema生成 + 验证 + 脱敏

用法:
  from src.platform_probe.explorer import PlatformExplorer
  explorer = PlatformExplorer(headless=True)
  schema, report = explorer.explore("https://some-platform.com", username="...", password="...")

CLI:
  python -m src.platform_probe --url https://some-platform.com
"""

from __future__ import annotations

import time
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from playwright.sync_api import sync_playwright

from .models import (
    PlatformSchema, ExplorationReport, AuthSchema, SessionState,
    CaptureResult, APICatalog, StepCatalog,
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
        max_depth: int = 3,
        max_pages: int = 50,
        verbose: bool = True,
    ):
        self.headless = headless
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.api_threshold = api_threshold
        self.llm_api_key = llm_api_key
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.verbose = verbose

    def explore(
        self,
        target_url: str,
        username: str = "",
        password: str = "",
    ) -> tuple[PlatformSchema, ExplorationReport, str]:
        """
        执行完整五层探索流水线

        :param target_url: 目标教学平台URL
        :param username: 登录用户名 (可选)
        :param password: 登录密码 (可选)
        :returns: (schema, report, schema_yaml_path)
        """
        start_time = time.time()

        if self.verbose:
            print(f"\n{'='*70}")
            print(f"  Platform Explorer (PX) v0.1 — 通用教学平台探索器")
            print(f"  目标: {target_url}")
            print(f"{'='*70}")

        with sync_playwright() as p:
            # ── 启动浏览器 ──
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()

            try:
                # ═══════════════════════════════════════════════
                # L0: 认证与会话
                # ═══════════════════════════════════════════════
                if self.verbose:
                    print(f"\n── L0: 认证检测 ──")

                # 先访问首页
                page.goto(target_url, wait_until="networkidle", timeout=30000)

                auth_schema, session_state = run_l0_auth(
                    page=page,
                    context=context,
                    base_url=target_url,
                    username=username,
                    password=password,
                    output_dir=self.output_dir,
                    verbose=self.verbose,
                )

                # ═══════════════════════════════════════════════
                # L1: 流量与结构捕获
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

                # ═══════════════════════════════════════════════
                # L2: 教学结构推断 (Phase 1: 简化版, 跳过)
                # ═══════════════════════════════════════════════
                # Phase 2 在此处调用 l2_structure.py
                if self.verbose:
                    print(f"\n── L2: 教学结构推断 (Phase 1 跳过, 使用默认值) ──")

                # ═══════════════════════════════════════════════
                # L3: API分类与推断
                # ═══════════════════════════════════════════════
                api_catalog, step_catalog = run_l3_classify(
                    capture=capture,
                    api_threshold=self.api_threshold,
                    llm_api_key=self.llm_api_key,
                    verbose=self.verbose,
                )

                # ═══════════════════════════════════════════════
                # L4: Schema生成与验证
                # ═══════════════════════════════════════════════
                schema, report, yaml_path = run_l4_schema(
                    target_url=target_url,
                    auth_schema=auth_schema,
                    capture=capture,
                    api_catalog=api_catalog,
                    step_catalog=step_catalog,
                    output_dir=self.output_dir,
                    verbose=self.verbose,
                )

                # 填充耗时
                elapsed = time.time() - start_time
                report.duration_seconds = elapsed

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
