"""中间件模块 — CORS + 错误处理 + Basic Auth"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import secrets


def setup_cors(app: FastAPI) -> None:
    """配置 CORS — 生产环境应限制origins"""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def setup_auth(app: FastAPI) -> None:
    """Basic Auth 中间件 — 生产环境最低保护

    仅保护 /api/* 路径。使用 .env 中的 ADMIN_USERNAME/ADMIN_PASSWORD。
    未配置凭据时自动放行（开发模式兼容）。
    """
    from backend.config import settings

    username = settings.admin_username
    password = settings.admin_password

    # 未配置凭据 → 跳过认证（向后兼容）
    if not username or not password:
        return

    import base64

    @app.middleware("http")
    async def basic_auth_middleware(request: Request, call_next):
        # 只保护 API 路径（前端静态文件不受限）
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        # 健康检查/指标端点放行
        if request.url.path in ("/api/health", "/api/metrics"):
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Basic "):
            return JSONResponse(
                status_code=401,
                content={"error": "Authentication required"},
                headers={"WWW-Authenticate": 'Basic realm="Agent Eval"'},
            )

        try:
            credentials = base64.b64decode(auth[6:]).decode("utf-8")
            user, _, pwd = credentials.partition(":")
            if not secrets.compare_digest(user, username) or \
               not secrets.compare_digest(pwd, password):
                raise ValueError("Invalid credentials")
        except Exception:
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid credentials"},
                headers={"WWW-Authenticate": 'Basic realm="Agent Eval"'},
            )

        return await call_next(request)


def setup_error_handlers(app: FastAPI) -> None:
    """全局异常处理"""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail, "status_code": exc.status_code},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc: Exception):
        import traceback
        detail = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": detail, "status_code": 500},
        )
