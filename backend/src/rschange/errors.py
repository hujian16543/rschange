"""领域异常。

设计约束
--------
对外回给客户端的描述**必须**取 `public_message`，不得使用 `str(exc)`。

旧实现（`routers/detection.py`）写的是：

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

`str(e)` 把内部细节直接交给调用方：GDAL 的报错原文含文件系统绝对路径，
numpy 的报错含数组形状与内存布局，pyproj 的报错含 PROJ 数据目录。这些对
攻击者是免费的侦察信息，对正常用户毫无用处。

因此每个异常承载两层信息：

* 构造时的 `message` —— 完整信息，**只**进日志；
* `public_message` —— 脱敏描述，可回给客户端。

HTTP 状态码由类属性 `http_status` 给出，由 `api/errors.py` 的全局处理器统一
映射，避免每个路由各写一套 `try/except` 与状态码。
"""

from __future__ import annotations

from typing import ClassVar

__all__ = [
    "ConfigError",
    "EngineError",
    "EngineLoadError",
    "InputValidationError",
    "ProcessingError",
    "RasterReadError",
    "RasterWriteError",
    "RsChangeError",
    "UnsupportedFormatError",
]


class RsChangeError(Exception):
    """所有领域异常的基类。

    子类通过覆写三个类属性定制对外行为：

    * `http_status` —— 映射到的 HTTP 状态码；
    * `code` —— 机器可读的错误码，供前端分支，不随文案变化；
    * `default_public_message` —— 未显式给出 `public_message` 时的脱敏描述。
    """

    http_status: ClassVar[int] = 500
    code: ClassVar[str] = "internal_error"
    default_public_message: ClassVar[str] = "内部错误"

    def __init__(self, message: str, *, public_message: str | None = None) -> None:
        super().__init__(message)
        self.public_message: str = (
            public_message if public_message is not None else self.default_public_message
        )

    def to_payload(self) -> dict[str, str]:
        """构造回给客户端的响应体。

        键名 `detail` 与 FastAPI 的 `HTTPException` 保持一致，使前端只须处理
        一种错误响应形状；`code` 为新增的机器可读字段。
        """
        return {"detail": self.public_message, "code": self.code}

    def __str__(self) -> str:
        return super().__str__()


class ConfigError(RsChangeError):
    """配置缺失或不合法。属部署期错误，与请求无关。"""

    code: ClassVar[str] = "config_error"
    default_public_message: ClassVar[str] = "服务端配置错误"


class EngineError(RsChangeError):
    """引擎层错误的基类。"""

    code: ClassVar[str] = "engine_error"
    default_public_message: ClassVar[str] = "空间引擎错误"


class EngineLoadError(EngineError):
    """`_spatial` 扩展或其原生依赖无法加载。"""

    code: ClassVar[str] = "engine_load_error"
    default_public_message: ClassVar[str] = "空间引擎不可用"


class RasterReadError(EngineError):
    """栅格读取失败。

    归为 400 而非 500：最常见的成因是调用方给出了不存在、损坏或格式不受支持
    的文件，属输入问题。
    """

    http_status: ClassVar[int] = 400
    code: ClassVar[str] = "raster_read_error"
    default_public_message: ClassVar[str] = "影像读取失败：文件不存在、损坏或格式不受支持"


class RasterWriteError(EngineError):
    """结果栅格写出失败。属服务端问题。"""

    code: ClassVar[str] = "raster_write_error"
    default_public_message: ClassVar[str] = "结果写出失败"


class UnsupportedFormatError(RsChangeError):
    """上传文件的扩展名不在白名单内。"""

    http_status: ClassVar[int] = 400
    code: ClassVar[str] = "unsupported_format"
    default_public_message: ClassVar[str] = "不支持的文件类型"


class InputValidationError(RsChangeError):
    """输入满足文件格式要求，但不满足业务约束。

    例：两期影像尺寸不一致、波段数少于三、像元量纲无法比较。
    """

    http_status: ClassVar[int] = 400
    code: ClassVar[str] = "input_validation_error"
    default_public_message: ClassVar[str] = "输入影像不满足要求"


class ProcessingError(RsChangeError):
    """处理流程中出现未预期的失败。"""

    code: ClassVar[str] = "processing_error"
    default_public_message: ClassVar[str] = "处理失败"
