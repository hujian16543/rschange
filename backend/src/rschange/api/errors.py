"""全局异常处理器。

D7 的收敛点：**「异常不外泄」这条规则只在这里实现一次**。

旧实现（`routers/detection.py:42-43`）：

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

三处问题：

1. **`str(e)` 把内部细节交给调用方**。GDAL 的报错原文含文件系统绝对路径，numpy
   的报错含数组形状与内存布局，pyproj 的报错含 PROJ 数据目录。这些对攻击者是免费
   的侦察信息，对正常用户毫无用处。
2. **`except Exception` 把领域异常一并压成 500**。两期影像尺寸不符、坐标系缺失、
   文件类型不支持，本应各自返回 400/413，前端却无法区分「你传错了」与「服务端
   坏了」，因而无法给出有意义的提示。
3. **每个路由各写一套 try/except**，状态码散落各处；新增异常类型时漏改一处就产生
   不一致的响应形状。

分工
----
`RsChangeError` 的子类自带 `http_status` 与 `to_payload()`（见 `rschange.errors`），
处理器只负责「记日志 + 按类属性映射」。因此新增一种领域异常**不需要**改动本文件。
"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from rschange.errors import RsChangeError
from rschange.logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

__all__ = ["install_exception_handlers"]

_logger = get_logger(__name__)

#: 未预期异常统一回给客户端的描述。**禁止**把它换成异常原文。
_UNEXPECTED_DETAIL = "内部错误"


async def _domain_error(request: Request, exc: Exception) -> JSONResponse:
    """领域异常 → 按 `http_status` / `to_payload()` 映射。

    4xx 记 WARNING（调用方的问题，不需要栈），5xx 记 ERROR 并带栈（服务端的问题，
    必须能定位）。日志里写的是**完整**消息，响应里给的是脱敏后的 `public_message`。
    """
    if not isinstance(exc, RsChangeError):  # pragma: no cover - 由注册条件保证
        return await _unexpected_error(request, exc)

    fields = {
        "method": request.method,
        "path": request.url.path,
        "status": exc.http_status,
        "code": exc.code,
    }
    if exc.http_status >= 500:
        _logger.error(f"领域异常（服务端）：{exc}", **fields)
    else:
        _logger.warning(f"领域异常（调用方）：{exc}", **fields)

    return JSONResponse(status_code=exc.http_status, content=exc.to_payload())


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    """请求体校验失败 → 统一错误形状。

    FastAPI 默认返回 422，`detail` 是**结构化列表**，与本项目其余错误的
    「`detail` 是字符串 + `code` 是错误码」不一致。前端因此得写两套解析。

    本处理器保留 422 状态码（改状态码属契约变更），把结构化细节放进 `errors`，
    同时把 `detail` 归一为字符串——两层信息都在，形状只有一个。
    """
    errors = jsonable_encoder(exc.errors()) if isinstance(exc, RequestValidationError) else []

    _logger.warning(
        f"请求校验失败：{len(errors)} 项",
        method=request.method,
        path=request.url.path,
        errors=errors,
    )

    return JSONResponse(
        status_code=422,
        content={
            "detail": "请求参数不符合要求",
            "code": "request_validation_error",
            "errors": errors,
        },
    )


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """未预期异常 → 500 + 通用描述。

    完整栈**只进日志**。响应体是固定字符串，不含 `str(exc)`、不含类型名、不含
    任何栈帧信息。

    栈以 `traceback` 字段传入，而不是 `_logger.exception()`：后者依赖
    `sys.exc_info()`，即「调用时正处于 except 块中」。这在 Starlette 当前实现里
    成立，但属于框架内部结构，一旦装配方式变化，栈会静默变成 `NoneType: None`
    ——最需要栈的时候恰好没有。显式格式化不依赖任何调用上下文。

    `traceback` 不是 `LogRecord` 的保留属性名，因此不会被 `_sanitize` 改名。

    注册它还有一个作用：即使有人把 FastAPI 的 `debug=True` 打开，本处理器也会
    先接管，不依赖框架的调试响应是否泄露内部信息。
    """
    _logger.error(
        f"未预期异常：{type(exc).__name__}",
        method=request.method,
        path=request.url.path,
        traceback="".join(traceback.format_exception(exc)),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": _UNEXPECTED_DETAIL, "code": "internal_error"},
    )


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    """`HTTPException` → 统一错误形状。

    框架自身也会抛它（405 方法不允许、404 路由不存在），若不接管，这些响应会是
    `{"detail": ...}` 而**没有** `code`，前端仍得写第二套解析。此处补上 `code`，
    状态码与 `headers` 原样保留（`Allow` 等头部不能丢）。

    `code` 取 `http_<状态码>`：这类错误没有领域语义，逐个起名只会维护一张永不
    使用的映射表；而 `code` 的存在价值是「前端有稳定的分支键」，`http_405` 完全
    满足这一点。
    """
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover - 由注册条件保证
        return await _unexpected_error(request, exc)

    detail = exc.detail if isinstance(exc.detail, str) else "请求无法完成"
    _logger.warning(
        f"HTTP {exc.status_code}：{detail}",
        method=request.method,
        path=request.url.path,
        status=exc.status_code,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail, "code": f"http_{exc.status_code}"},
        headers=exc.headers,
    )


def install_exception_handlers(app: FastAPI) -> None:
    """把四个处理器挂到应用上。幂等：重复调用只是覆盖同一批键。"""
    app.add_exception_handler(RsChangeError, _domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected_error)
