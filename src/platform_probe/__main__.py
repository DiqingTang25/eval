"""
Platform Explorer CLI 入口

用法:
  # 基础探索
  python -m src.platform_probe --url https://teaching-platform.com

  # 带认证
  python -m src.platform_probe --url https://teaching-platform.com \\
      --username student001 --password 123456

  # 高级选项
  python -m src.platform_probe --url https://teaching-platform.com \\
      --headless --max-depth 4 --max-pages 100 --output ./my_output

  # 输出到指定路径 (对接后续测评)
  python -m src.platform_probe --url https://teaching-platform.com \\
      --output data/platform_schemas/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .explorer import PlatformExplorer, DEFAULT_OUTPUT_DIR


def main():
    parser = argparse.ArgumentParser(
        description="Platform Explorer (PX) — 通用教学平台探索器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m src.platform_probe --url https://example.com
  python -m src.platform_probe --url https://example.com -u admin -p secret
  python -m src.platform_probe --url https://example.com --headed --max-depth 5
        """,
    )
    parser.add_argument("--url", required=True, help="目标教学平台URL")
    parser.add_argument("-u", "--username", default="", help="登录用户名")
    parser.add_argument("-p", "--password", default="", help="登录密码")
    parser.add_argument("--headless", action="store_true", default=True,
                        help="无头模式 (默认)")
    parser.add_argument("--headed", action="store_true",
                        help="显示浏览器窗口 (调试用)")
    parser.add_argument("--max-depth", type=int, default=3,
                        help="BFS最大深度 (默认3)")
    parser.add_argument("--max-pages", type=int, default=50,
                        help="最大访问页面数 (默认50)")
    parser.add_argument("--api-threshold", type=float, default=0.50,
                        help="API分类阈值 (默认0.50)")
    parser.add_argument("--llm-api-key", default="",
                        help="LLM API Key (用于Phase 2端点枚举)")
    parser.add_argument("--output", "-o", default="",
                        help="输出目录 (默认 output/platform_probe/)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="静默模式")

    args = parser.parse_args()

    # 输出目录
    output_dir = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR

    # 无头模式: --headed 覆盖 --headless
    headless = not args.headed

    print(f"🚀 Platform Explorer (PX) v0.1")
    print(f"   目标: {args.url}")
    print(f"   模式: {'无头' if headless else '可见'}")
    print(f"   深度: {args.max_depth}, 最大页面: {args.max_pages}")
    print()

    explorer = PlatformExplorer(
        headless=headless,
        output_dir=output_dir,
        api_threshold=args.api_threshold,
        llm_api_key=args.llm_api_key,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        verbose=not args.quiet,
    )

    try:
        schema, report, yaml_path = explorer.explore(
            target_url=args.url,
            username=args.username,
            password=args.password,
        )

        print(f"\n✅ 探索成功!")
        print(f"   Schema: {yaml_path}")
        print(f"   报告: {output_dir / 'exploration_report.md'}")
        print(f"   置信度: {report.confidence.overall:.0%}")
        print(f"   API端点: {report.api_endpoints_found}")
        print(f"   Step: {report.steps_found}")

        if report.warnings:
            print(f"\n⚠️ 警告 ({len(report.warnings)}条):")
            for w in report.warnings:
                print(f"   - {w}")

        if report.recommendations:
            print(f"\n💡 建议:")
            for r in report.recommendations:
                print(f"   - {r}")

        return 0

    except Exception as e:
        print(f"\n❌ 探索失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
