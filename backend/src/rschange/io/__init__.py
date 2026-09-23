"""图像与矢量产物层：预览图渲染、GeoJSON 重投影。

包名与标准库 `io` 同名，这是**有意**保留的命名（与《重构方案》目录结构一致）。
Python 3 使用绝对导入，故本包内写 `from io import BytesIO` 仍解析到标准库，
不会冲突。但包内**禁止**写 `from . import io` 这类相对导入，以免遮蔽标准库。

本层是 backend 内 `import PIL` 与 `import pyproj` 的唯一位置。两个依赖都不涉及
原生 DLL 的目录解析，故不受附录 D-5 的约束——D-5 只针对 `_spatial` 的装载。
"""

from __future__ import annotations

from rschange.io.preview import save_rgb_png, stretch_percentiles
from rschange.io.reproject import GEOGRAPHIC_CRS, image_corners, reproject_geojson

__all__ = [
    "GEOGRAPHIC_CRS",
    "image_corners",
    "reproject_geojson",
    "save_rgb_png",
    "stretch_percentiles",
]
