"""对 C++ 扩展 `_spatial` 的唯一访问点（附录 D-5）。

全项目**只有** `spatial/loader.py` 解析 DLL 路径并执行 `import _spatial`。
其余模块一律 `from rschange.spatial import read_raster`，永不接触路径。

旧实现把同一段 DLL 路径逻辑复制了四份（`main.py`、`services/detection.py`、
`tests/test_cva.py`、`tests/test_bindings.py`），且各自硬编码 MSYS2 绝对路径。

判定依据：`grep -rn "msys64" backend/` 结果为空（阶段出口门 G3.5）。

按需加载
--------
子模块用 PEP 562 的模块级 `__getattr__` 延迟导入：`import rschange.spatial`
本身**不**触发引擎加载，只有取用 `read_raster` 等符号时才加载。这使引擎尚未
构建的环境仍能导入本包——例如只跑配置校验或 API schema 快照的测试。

符号归属：`loader` 提供 `load_extension`，其余来自 `raster`。
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from rschange.spatial.loader import load_extension
    from rschange.spatial.raster import (
        Raster,
        as_geo,
        as_mask,
        gdal_version,
        mask_to_geojson,
        read_raster,
        write_raster,
    )

__all__ = [
    "Raster",
    "as_geo",
    "as_mask",
    "gdal_version",
    "load_extension",
    "mask_to_geojson",
    "read_raster",
    "write_raster",
]

#: 符号名 → 提供它的子模块名。
_LAZY_SOURCES: Final[dict[str, str]] = {
    "load_extension": "loader",
    "Raster": "raster",
    "as_geo": "raster",
    "as_mask": "raster",
    "gdal_version": "raster",
    "mask_to_geojson": "raster",
    "read_raster": "raster",
    "write_raster": "raster",
}


def __getattr__(name: str) -> Any:
    module_name = _LAZY_SOURCES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(f"{__name__}.{module_name}")
    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted(set(__all__) | set(globals()))
