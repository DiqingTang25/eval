#!/usr/bin/env python3
"""
AI Agent 全自动化测评系统 v3.4

评测流程: 问题生成 → 浏览器操控Agent → 追问 → 6维度评分 + 边界检测 → 报告

支持: Platform Agent (HiAgent API) / WebTest Agent (Playwright网站测试)

用法:
    python main.py                        # 默认运行测评
    python main.py dashboard              # 启动监控面板
    python main.py dashboard --port 8080  # 指定端口
"""

import os
import sys
import argparse
from dotenv import load_dotenv

load_dotenv()


def cmd_run():
    """运行测评"""
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ 请在 .env 中设置 OPENAI_API_KEY")
        sys.exit(1)

    from src.test_runner import TestRunner

    print("🤖 AI Agent 自动化测评系统 v3.4")
    runner = TestRunner()
    runner.run_all()


def cmd_dashboard(port: int = 8000):
    """启动监控面板"""
    import uvicorn
    print(f"🚀 监控面板: http://localhost:{port}")
    uvicorn.run("dashboard.app:app", host="0.0.0.0", port=port, reload=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Agent 自动化测评系统 v3.4")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run", help="运行测评")

    dash = sub.add_parser("dashboard", help="启动监控面板")
    dash.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()

    if args.command == "dashboard":
        cmd_dashboard(args.port)
    else:
        cmd_run()
