"""检测算法注册表：可插拔的落地机制。

新增一种算法只需两步：

1. 在 `detectors/` 下新建模块，实现 `detectors/base.py` 的 `ChangeDetector` 协议；
2. 在 `detectors/__init__.py` 中导入它并 `register` 一次。

`pipeline/change_detection.py` **不需要**任何改动——这是阶段出口门 G3.4
（可插拔验证）的判据：新增算法后编排层文件的哈希必须不变。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from rschange.errors import UnknownDetectorError

if TYPE_CHECKING:
    from rschange.detectors.base import ChangeDetector

__all__ = ["DEFAULT_DETECTOR", "available", "register", "resolve"]

#: 未显式指定算法时使用的算法名。
DEFAULT_DETECTOR: Final[str] = "cva"

_REGISTRY: Final[dict[str, ChangeDetector]] = {}


def register(detector: ChangeDetector, *, override: bool = False) -> ChangeDetector:
    """注册算法，返回它本身（便于链式使用）。

    重名默认报错而非静默覆盖。两个实现同名时，调用方最终拿到哪一个取决于导入
    顺序，而这类问题在运行时没有任何可观测征兆——报错是唯一能在启动期暴露它的
    方式。

    @throws ValueError 名字已被占用且未指定 `override=True`
    """
    name = detector.name
    if name in _REGISTRY and not override:
        existing = type(_REGISTRY[name]).__name__
        raise ValueError(
            f"检测算法名 {name!r} 已被 {existing} 占用；如需替换请显式传 override=True"
        )
    _REGISTRY[name] = detector
    return detector


def available() -> tuple[str, ...]:
    """已注册的算法名，升序。"""
    return tuple(sorted(_REGISTRY))


def resolve(name: str | None = None) -> ChangeDetector:
    """按名取算法；`name` 为 `None` 时取 `DEFAULT_DETECTOR`。

    @throws UnknownDetectorError 名字未注册
    """
    key = name or DEFAULT_DETECTOR
    try:
        return _REGISTRY[key]
    except KeyError:
        raise UnknownDetectorError(
            f"未注册的检测算法 {key!r}；已注册：{list(available())}",
            public_message=f"不支持的检测算法：{key}",
        ) from None
