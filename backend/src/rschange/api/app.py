"""应用工厂。

应用实例由 `create_app()` 产出，**不是**模块级单例。理由是可测试性：模块级
单例在导入时就把真实算法与真实引擎接上，测试要替换依赖只能打桩；工厂则把
装配结果作为参数收进来（`api/deps.py` 的 `RuntimeContext`），测试可以构造自己的
上下文并得到一个完全隔离的应用。

启动方式
--------
开发（自动重载）：

    uv run uvicorn --factory rschange.api.app:create_app --reload

直接运行：

    uv run python -m rschange.api.app

旧实现是 `main.py` 里的模块级 `app = FastAPI(...)`，且 `if __name__ == "__main__"`
里用字符串 `"main:app"` 启动——该字符串只在工作目录恰为 `src/backend` 时可解析。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rschange import __version__
from rschange.api.deps import STATE_ATTR, RuntimeContext, build_context
from rschange.api.errors import install_exception_handlers
from rschange.api.routers.detection import router as detection_router
from rschange.logging import configure_logging, get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from contextlib import AbstractAsyncContextManager

    from rschange.config import Settings

__all__ = ["API_PREFIX", "create_app", "main"]

#: 所有业务路由的挂载前缀。
API_PREFIX = "/api"

_logger = get_logger(__name__)


def _configure_logging_once(settings: Settings) -> None:
    """按配置装配根记录器，但**不覆盖**已存在的处理器。

    「已有处理器就跳过」不是省事，而是一条明确边界：本函数只在进程边界负责
    **没有**装配过日志的场景（`python -m rschange.api.app`）。ASGI 服务器
    （uvicorn `--log-config`）、容器运行时、pytest 的 `caplog` 都各自有日志装配，
    强行覆盖会把它们的输出吞掉——表现为「日志文件里什么都没有」或「用例里
    `caplog` 永远为空」。
    """
    if logging.getLogger().handlers:
        return
    configure_logging(level=settings.logging.level, format=settings.logging.format)


def _lifespan(
    context: RuntimeContext,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """构造 lifespan：启动时确保数据目录存在。

    目录创建放在这里而不是每次请求里：`uploads/` 与 `outputs/` 是**部署期**
    资源，请求期内反复 `mkdir` 只是把一次性的装配成本摊到每个请求上。
    """

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        for directory in (context.settings.uploads_dir, context.settings.outputs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        _logger.info(
            "应用启动",
            version=__version__,
            data_dir=str(context.settings.data_dir),
            detector=context.detector.name,
            postprocessor=context.postprocessor.name,
            allowed_origins=list(context.settings.runtime.allowed_origins),
        )
        yield
        _logger.info("应用停止")

    return lifespan


def create_app(*, context: RuntimeContext | None = None) -> FastAPI:
    """构造应用实例。

    参数
    ----
    context
        运行时上下文（配置 + 算法 + 后处理器）。为 `None` 时按
        `api/deps.build_context()` 装配默认实现。

    测试替换依赖的方式：

        create_app(context=RuntimeContext(settings, StubDetector(), StubPostprocessor()))
    """
    resolved = context if context is not None else build_context()

    _configure_logging_once(resolved.settings)

    app = FastAPI(
        title="遥感变化检测平台",
        description="基于 CVA 的两期影像变化检测服务。检测算法可插拔，引擎为 C++ 扩展 `_spatial`。",
        version=__version__,
        lifespan=_lifespan(resolved),
    )

    # 装配结果放在 app.state 上，路由经 api/deps.get_context 取用。
    setattr(app.state, STATE_ATTR, resolved)

    install_exception_handlers(app)

    # D1 修正：旧实现是 allow_origins=["*"] 与 allow_credentials=True 并存。
    # 浏览器规范禁止该组合，结果是白名单**实际失效**——任何来源都能通过，
    # 只是浏览器会拒绝携带凭据的响应。现逐条列出前端来源（由配置校验保证不含
    # "*"），并显式关闭凭据：本服务不使用 Cookie 会话，关闭它可消除一类 CSRF
    # 面；将来真要用 Cookie，须同时把 allowed_origins 收窄到确切域名。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.settings.runtime.allowed_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(detection_router, prefix=API_PREFIX, tags=["Detection"])

    @app.get("/", summary="服务信息", tags=["Meta"])
    async def root() -> dict[str, str]:
        return {"message": "遥感变化检测平台 API", "version": __version__}

    return app


def main() -> None:
    """命令行入口：按配置启动 uvicorn。"""
    import uvicorn

    context = build_context()
    settings = context.settings
    _logger.info(
        "准备启动",
        host=settings.runtime.host,
        port=settings.runtime.port,
        log_level=settings.logging.level,
    )
    uvicorn.run(
        "rschange.api.app:create_app",
        factory=True,
        host=settings.runtime.host,
        port=settings.runtime.port,
    )


if __name__ == "__main__":
    main()
