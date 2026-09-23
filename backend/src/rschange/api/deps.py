"""依赖注入的装配点。

本模块是「协议」与「实现」唯一的接合处。`pipeline` 只认 `ChangeDetector` 与
`MaskPostprocessor` 两个协议，**具体是哪种实现、参数取多少，全部在这里决定**——
这样 `pipeline/change_detection.py` 才可以对 `detectors/` 与 `postprocess/` 保持
运行期零依赖（阶段出口门 G3.4 的结构前提）。

替换实现的方式
--------------
`create_app()` 把装配结果存进 `app.state`。测试要换掉算法或后处理器时，直接构造
自己的 `RuntimeContext` 传给 `create_app()`：

    app = create_app(context=RuntimeContext(settings, StubDetector(), StubPostprocessor()))

不需要打桩、不需要改环境变量、不会触及 `_spatial` 扩展。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from fastapi import Request

from rschange.config import Settings, get_settings
from rschange.detectors import registry
from rschange.postprocess import MorphologyPostprocessor

if TYPE_CHECKING:
    from rschange.detectors.base import ChangeDetector
    from rschange.postprocess.base import MaskPostprocessor

__all__ = ["STATE_ATTR", "RuntimeContext", "build_context", "get_context"]

#: `app.state` 上的属性名。
STATE_ATTR = "rschange"


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    """一个应用实例的全部可替换依赖。"""

    settings: Settings
    """配置。路径解析、CORS 白名单、上传上限都取自它。"""

    detector: ChangeDetector
    """检测算法。默认由注册表给出（`cva`）。"""

    postprocessor: MaskPostprocessor
    """掩膜后处理器。默认参数的来源是 `config.postprocess`。"""


def build_context(
    settings: Settings | None = None,
    *,
    detector: ChangeDetector | None = None,
    postprocessor: MaskPostprocessor | None = None,
) -> RuntimeContext:
    """按配置装配默认依赖；显式传入的实现优先。

    显式参数优先于配置：测试与将来的多算法接口都从这条路径进来，无需改动装配
    逻辑本身。
    """
    resolved = settings if settings is not None else get_settings()

    if postprocessor is None:
        postprocessor = MorphologyPostprocessor(
            min_size=resolved.postprocess.min_size,
            structure_size=resolved.postprocess.structure_size,
        )

    return RuntimeContext(
        settings=resolved,
        detector=detector if detector is not None else registry.resolve(),
        postprocessor=postprocessor,
    )


def get_context(request: Request) -> RuntimeContext:
    """FastAPI 依赖：取出当前应用实例的运行时上下文。

    @throws RuntimeError 应用未经 `create_app()` 装配（属装配期缺陷，不是请求问题）
    """
    context = getattr(request.app.state, STATE_ATTR, None)
    if context is None:
        raise RuntimeError(f"应用状态缺少 {STATE_ATTR!r}：必须经 api.app.create_app() 创建应用实例")
    return cast("RuntimeContext", context)
