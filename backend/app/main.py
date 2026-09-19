import os
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.core.config import settings


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)

# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)


# --- Frontend (WebUI) hosting -----------------------------------------------
# 前端构建产物的位置：
#   1. 环境变量 IrsBot_WEBUI_DIR（compose 里指向绑定挂载的 ./frontend/dist）
#   2. 镜像内置的 /app/frontend-dist（构建镜像时 COPY 进去的）
# 两者都不存在时，本段整体跳过 —— 不影响纯 API 使用（如开发时的 5173 dev server）。
WEBUI_DIR = Path(os.getenv("IrsBot_WEBUI_DIR", "/app/frontend-dist"))
WEBUI_INDEX = WEBUI_DIR / "index.html"

if WEBUI_INDEX.exists():
    # 静态资源（/assets/*.js、/assets/*.css）直接由 StaticFiles 提供
    WEBUI_ASSETS = WEBUI_DIR / "assets"
    if WEBUI_ASSETS.exists():
        app.mount("/assets", StaticFiles(directory=WEBUI_ASSETS), name="webui-assets")

    @app.exception_handler(StarletteHTTPException)
    async def spa_fallback(request, exc):
        """SPA 路由回退：前端路由（/chat、/settings…）在服务端没有对应文件，
        需要回退到 index.html 交给前端路由处理，否则刷新页面会 404。

        ⚠️ 必须排除 API 前缀：接口 404 时应返回 JSON 错误，
        若这里也返回 HTML，前端会报 JSON 解析错误，掩盖真实原因。
        """
        if exc.status_code == 404 and not request.url.path.startswith(
            settings.API_V1_STR
        ):
            accept = request.headers.get("accept", "")
            # 只对"想要 HTML"的请求回退；静态资源（图片等）缺失时保持 404
            if "text/html" in accept:
                # no-cache = 每次都向服务器校验（ETag 协商，命中 304 不重复下载）。
                # index.html 引用带哈希的 assets 文件名，若 html 本身被浏览器缓存，
                # 重新构建后会继续加载旧 bundle，用户看不到新版本（本次删除按钮就踩过）。
                return FileResponse(
                    WEBUI_INDEX, headers={"Cache-Control": "no-cache"}
                )
        return await http_exception_handler(request, exc)
