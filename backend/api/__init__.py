"""API 路由聚合 — 增量加载，部分模块缺失不影响"""

from fastapi import APIRouter

api_router = APIRouter(prefix="/api")

# 核心路由 (Phase 2)
from . import dashboard, qa, agents
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(qa.router, prefix="/qa", tags=["QA Pairs"])
api_router.include_router(agents.router, prefix="/agents", tags=["Agents"])

# 扩展路由 (Phase 3-4, 存在即加载)
try:
    from . import tests
    api_router.include_router(tests.router, prefix="/tests", tags=["Tests"])
except ImportError:
    pass

try:
    from . import reports
    api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
except ImportError:
    pass

try:
    from . import web_eval
    api_router.include_router(web_eval.router, prefix="/web-eval", tags=["Web Eval"])
except ImportError:
    pass

try:
    from . import kb
    api_router.include_router(kb.router, prefix="/kb", tags=["Knowledge Base"])
except ImportError:
    pass

try:
    from . import calibration
    api_router.include_router(calibration.router, prefix="/calibration", tags=["Calibration"])
except ImportError:
    pass

try:
    from . import i18n
    api_router.include_router(i18n.router, prefix="/i18n", tags=["i18n"])
except ImportError:
    pass

# v4.0 核心路由 — 平台探索器 (无条件加载, 错误直接暴露)
try:
    from . import explorer
    api_router.include_router(explorer.router, prefix="/explorer", tags=["Explorer"])
except Exception as e:
    import logging
    logging.getLogger(__name__).error(f"Explorer route load failed: {e}")

try:
    from . import settings
    api_router.include_router(settings.router, prefix="/settings", tags=["Settings"])
except Exception as e:
    import logging
    logging.getLogger(__name__).error(f"Settings route load failed: {e}")

# v4.0 Agent C — MCP Server (Schema→Tools)
try:
    from . import mcp
    api_router.include_router(mcp.router, prefix="/mcp", tags=["MCP"])
except Exception as e:
    import logging
    logging.getLogger(__name__).error(f"MCP route load failed: {e}")

# v4.0 Agent C — Health endpoints (4.4 P2, 独立于 dashboard.py)
try:
    from . import health
    api_router.include_router(health.router, prefix="/health", tags=["Health"])
except Exception as e:
    import logging
    logging.getLogger(__name__).error(f"Health route load failed: {e}")
