"""
pytest 通用配置 + Playwright fixtures

用法:
    pytest tests/                          # 全部测试（需要浏览器）
    pytest tests/ -m "not browser"         # 仅逻辑测试（无浏览器）
    pytest tests/ -m browser              # 仅浏览器测试
    pytest tests/ --headed                # 有头模式调试
"""

import os
import sys
import pytest
from pathlib import Path

# 确保项目根在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

# 加载 .env
from dotenv import load_dotenv
load_dotenv()


# ── 命令行选项 ──────────────────────────────────

def pytest_addoption(parser):
    parser.addoption("--headed", action="store_true", default=False,
                     help="Run browser tests in headed mode")
    parser.addoption("--slow", action="store_true", default=False,
                     help="Include slow tests (full conversation flow)")


# ── Markers ─────────────────────────────────────

pytest_plugins = []
# 注册自定义 markers（pyproject.toml 不存在，用 conftest 注册）
def pytest_configure(config):
    config.addinivalue_line("markers", "browser: tests requiring a real browser")
    config.addinivalue_line("markers", "slow: slow integration tests")
    config.addinivalue_line("markers", "llm: tests requiring LLM API calls")


# ── Playwright fixtures ─────────────────────────

@pytest.fixture(scope="session")
def playwright_browser(request):
    """会话级浏览器实例（复用，加速测试）"""
    from playwright.sync_api import sync_playwright

    headed = request.config.getoption("--headed", default=False)
    proxy = None
    if os.getenv("PLAYWRIGHT_PROXY"):
        proxy = {"server": os.getenv("PLAYWRIGHT_PROXY")}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed, proxy=proxy)
        yield browser
        browser.close()


@pytest.fixture
def page(playwright_browser):
    """每个测试一个独立页面（隔离状态）"""
    context = playwright_browser.new_context(
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    )
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture
def platform_url():
    """被测平台 URL (自主学习平台)"""
    return os.getenv("PLATFORM_URL", "http://124.174.108.70")


@pytest.fixture
def api_key():
    """DeepSeek API Key"""
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        pytest.skip("OPENAI_API_KEY 未设置")
    return key


@pytest.fixture
def evaluator(api_key):
    """Evaluator 实例"""
    from src.evaluator import Evaluator
    return Evaluator(api_key, config={
        "use_embedding": True,
        "use_structure": True,
        "use_boundary": True,
    })


@pytest.fixture
def boundary_detector(api_key):
    """BoundaryDetector 实例"""
    from src.boundary_detector import BoundaryDetector
    return BoundaryDetector(api_key)
