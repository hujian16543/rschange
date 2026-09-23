"""`_spatial` 的 Python 侧封装。

`_spatial` 的四个函数是**裸接口**：元组返回、无类型、错误只有 `RuntimeError`
与 `ValueError`。本模块是它们在 backend 内的唯一访问入口，承担三件事：

1. **消掉位置解包。** 旧代码同时存在两种解包写法：

       before, w, h, bands, geo, proj = _spatial.read_raster(path)
       before, *_, geo, proj = _spatial.read_raster(path)

   后者把中间字段整体丢弃，字段顺序一旦变化不会有任何提示。`Raster` 用具名
   字段取而代之。

2. **映射异常。** 引擎的 `RuntimeError` 含绝对路径与 GDAL 原文，只能进日志；
   对外由 `RasterReadError` 的 `public_message` 承担。

3. **统一入参准备。** 引擎声明 `noconvert()`，即不做隐式转换，调用方必须
   自行准备 `uint8` + C 连续的掩膜。`as_mask` 是那个「自行准备」的唯一实现。

引擎契约见 `docs/contracts.md` §3、§4；本模块**禁止**改变其语义（例如擅自
接受 `bool` 以外的 dtype，或对 `geo` 做单位换算）。
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, cast

import numpy as np

from rschange.config import Settings
from rschange.errors import EngineLoadError, RasterReadError, RasterWriteError
from rschange.spatial.loader import load_extension

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from numpy.typing import NDArray

__all__ = [
    "GEO_TRANSFORM_LENGTH",
    "Raster",
    "as_geo",
    "as_mask",
    "gdal_version",
    "mask_to_geojson",
    "read_raster",
    "write_raster",
]

#: `geo_transform` 的元素个数（GDAL 固定六参数）。
GEO_TRANSFORM_LENGTH: Final[int] = 6

#: GDAL 六参数仿射变换，顺序 (x0, dx, rx, y0, ry, dy)。
GeoTransform = tuple[float, float, float, float, float, float]


@dataclass(frozen=True, slots=True)
class Raster:
    """一期影像及其地理参考。

    字段的排列顺序**刻意不同于** `_spatial.read_raster` 的返回顺序：具名访问
    是唯一推荐方式，本类不承诺位置解包可用。
    """

    array: NDArray[np.uint16]
    """影像数组，shape `(bands, height, width)`，dtype `uint16`。

    像素缓冲的所有权随数组移交，这里持有的是引擎交出的同一块内存（零拷贝）。
    因此**禁止**在持有期间重新读取同一路径到同一缓冲的假设下原地改写。
    """

    width: int
    """像素列数。"""

    height: int
    """像素行数。"""

    bands: int
    """波段数。"""

    geo_transform: GeoTransform
    """GDAL 六参数。顶点换算见 `docs/contracts.md` §5。"""

    projection: str
    """完整 WKT；影像无投影时为空字符串。"""

    @property
    def pixel_area(self) -> float:
        """单像元面积，与 CRS 的长度单位同量纲（投影坐标下为平方米）。

        取 `abs(dx × dy)`，与 `docs/contracts.md` §5 对 `area_m2` 的定义一致。
        """
        return abs(self.geo_transform[1] * self.geo_transform[5])

    @property
    def shape(self) -> tuple[int, int, int]:
        """`(bands, height, width)`，与 `array.shape` 相同但无需触发导入。"""
        return (self.bands, self.height, self.width)


def as_mask(array: NDArray[Any]) -> NDArray[np.uint8]:
    """把布尔或 `uint8` 掩膜规范成引擎要求的形态。

    引擎的掩膜参数声明为 `uint8` + C 连续 + 不做隐式转换。本函数输出满足前
    两项；第三项意味着**必须**经由此处转换，不能把原始数组直接递过去。

    `bool` 是唯一被额外接受的输入：CVA 的自然输出就是布尔掩膜，要求每个调用点
    各写一次 `astype(np.uint8)` 只会制造重复。其余 dtype 一律拒绝——若放行浮点，
    `mask_to_geojson(magnitude, geo)` 这类漏掉二值化的错误不会报错，引擎会把每个
    非零像素当作变化像素并静默返回错误结果（见 `docs/contracts.md` §4）。

    @throws TypeError 输入既非 `bool` 也非 `uint8`
    """
    if array.dtype == np.bool_:
        return np.ascontiguousarray(array, dtype=np.uint8)
    if array.dtype != np.uint8:
        raise TypeError(f"掩膜必须是 bool 或 uint8，实得 {array.dtype}")
    return np.ascontiguousarray(array)


def as_geo(geo_transform: Sequence[float]) -> GeoTransform:
    """规范成引擎接受的六元素浮点元组。

    长度错误在此拦截并保留 `ValueError` 语义（与 `docs/contracts.md` §6 一致），
    但消息由本层给出，指向调用方传了什么，而不是让 nanobind 报
    「参数类型不匹配」——那会把长度问题误报成类型问题。

    @throws ValueError 元素个数不是 6
    """
    values = tuple(float(value) for value in geo_transform)
    if len(values) != GEO_TRANSFORM_LENGTH:
        raise ValueError(
            f"geo_transform 必须是 {GEO_TRANSFORM_LENGTH} 个浮点数，实得 {len(values)} 个"
        )
    return cast("GeoTransform", values)


def read_raster(path: str | Path, settings: Settings | None = None) -> Raster:
    """读取 GeoTIFF 的全部波段。

    @throws RasterReadError 文件不存在、损坏或格式不受支持
    """
    extension = load_extension(settings)
    try:
        array, width, height, bands, geo, projection = extension.read_raster(str(path))
    except RuntimeError as exc:
        raise RasterReadError(f"读取栅格失败 {path}：{exc}") from exc

    return Raster(
        array=array,
        width=int(width),
        height=int(height),
        bands=int(bands),
        geo_transform=as_geo(geo),
        projection=str(projection),
    )


def write_raster(
    path: str | Path,
    mask: NDArray[Any],
    geo_transform: Sequence[float],
    projection: str,
    settings: Settings | None = None,
) -> None:
    """把 `uint8` 掩膜写成 GeoTIFF。

    父目录**必须**已存在，引擎不创建目录（`docs/contracts.md` §3.3）。

    @throws RasterWriteError 目标不可创建
    @throws TypeError 掩膜 dtype 不是 `bool` / `uint8`
    @throws ValueError `geo_transform` 长度不是 6
    """
    extension = load_extension(settings)
    prepared = as_mask(mask)
    try:
        extension.write_raster(str(path), prepared, list(as_geo(geo_transform)), projection)
    except RuntimeError as exc:
        raise RasterWriteError(f"写出栅格失败 {path}：{exc}") from exc


def mask_to_geojson(
    mask: NDArray[Any],
    geo_transform: Sequence[float],
    settings: Settings | None = None,
) -> str:
    """把 2D 掩膜转成 GeoJSON `FeatureCollection` 字符串。

    掩膜**必须**为 2D；3D 输入（含退化的 `(1, H, W)`）由引擎抛 `ValueError`。

    @throws ValueError 掩膜维度不是 2，或 `geo_transform` 长度不是 6
    @throws TypeError 掩膜 dtype 不是 `bool` / `uint8`
    """
    extension = load_extension(settings)
    prepared = as_mask(mask)
    return str(extension.mask_to_geojson(prepared, list(as_geo(geo_transform))))


#: 取 GDAL 版本的子进程脚本。
#:
#: 为什么必须走子进程：`_spatial` 由 MSYS2 的 MinGW 工具链编译，持有**它自己
#: 那一套** C 运行时的 `stdout`；CPython 由 MSVC 编译，用的是另一套 CRT。两套
#: CRT 各有独立的文件描述符表，因此 `os.dup2(..., 1)` 只重定向 Python 侧，引擎
#: 的输出不受影响。实测：本进程内用 `dup2` 重定向并补 `fflush`（ucrtbase 与
#: msvcrt 都试过），捕获结果恒为空字符串；且 `contextlib.redirect_stdout` 更弱
#: ——它只替换 `sys.stdout` 对象，连描述符都没碰。
#:
#: 子进程的 fd 1 由操作系统在创建时直接指向管道，与任何 CRT 无关，故可靠。
#: 代价是启动一个解释器（约 0.1 s），仅用于诊断，可接受。
_GDAL_VERSION_PROBE: Final[str] = (
    "from rschange.spatial import load_extension; load_extension().print_gdal_version()"
)


def gdal_version(*, timeout_s: float = 60.0) -> str:
    """取底层 GDAL 版本号。

    在独立进程中运行引擎的 `print_gdal_version()`（理由见 `_GDAL_VERSION_PROBE`），
    返回其标准输出去除首尾空白后的内容。使用**子进程自身的默认配置**装载引擎，
    因此不接受 `settings` 参数。

    返回值形如 `GDAL Version: GDAL 3.12.3 "Chicoutimi", released 2026/03/17`。

    @throws EngineLoadError 子进程启动失败、超时，或引擎在子进程中装载失败
    """
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _GDAL_VERSION_PROBE],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EngineLoadError(f"GDAL 版本探测失败：{exc}") from exc

    if completed.returncode != 0:
        raise EngineLoadError(
            f"GDAL 版本探测子进程退出码 {completed.returncode}：{completed.stderr.strip()}",
            public_message="空间引擎不可用：版本探测失败",
        )
    return completed.stdout.strip()
