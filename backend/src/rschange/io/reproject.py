"""GeoJSON 重投影与影像四角定位。

本模块是 backend 内唯一 `import pyproj` 的地方，职责单一：把引擎产出的**投影
坐标**换算到经纬度，使结果能直接画在前端地图上。

与旧实现的行为差异（两处，均为静默错误修正）
--------------------------------------------

1. **非 Polygon 几何。** 旧实现对 `feature["geometry"]["coordinates"]` 直接执行
   `for i, (x, y) in enumerate(ring)`，即假定那是「Polygon 的环列表」。对
   MultiPolygon（环列表的列表）该解包会抛异常，随后被裸 `except Exception` 吞掉，
   函数返回**完全未变换**的坐标。现改为递归下降：只对叶子层的位置数组施加变换，
   任意嵌套深度的 Polygon / MultiPolygon 处理一致。

2. **异常不再被吞掉。** 旧实现在 CRS 缺失或解析失败时 `return geojson_str`，
   把投影坐标系（米为单位，如 UTM 的 `(500000, 4000000)`）的坐标当作经纬度返回。
   前端据此绘图得到的是一张看似正常、位置却完全错误的地图，且全程无任何报错——
   这是最坏的一类失败。现抛 `CrsError`（HTTP 400）：WKT 来自上传的栅格文件，
   无投影属输入问题。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError as PyprojCrsError

from rschange.errors import CrsError, EngineError

if TYPE_CHECKING:
    from rschange.spatial.raster import GeoTransform

__all__ = ["GEOGRAPHIC_CRS", "image_corners", "reproject_geojson"]

#: 输出坐标系。前端地图库与 GeoJSON 规范（RFC 7946）都要求经纬度，故固定为
#: WGS84，不设为可配置项——多一个配置项就多一种「坐标对不上」的故障形态。
GEOGRAPHIC_CRS: Final[str] = "EPSG:4326"


def _transformer(src_wkt: str, target_crs: str) -> Transformer:
    """构造 源 CRS → 目标 CRS 的变换器。

    `always_xy=True` 强制 **(经度, 纬度)** 轴序。缺了它会落到 CRS 定义本身的轴序
    上：EPSG:4326 的官方轴序是 (纬度, 经度)，于是输出被对调，画面上的表现是
    「整幅图关于对角线镜像翻转」——从数值上很难一眼看出，却会让所有空间分析
    全部错位。
    """
    if not src_wkt.strip():
        raise CrsError(
            f"影像无投影信息（WKT 为空），无法重投影到 {target_crs}",
            public_message="影像缺少坐标系，无法定位到地图",
        )
    try:
        source = CRS.from_wkt(src_wkt)
        return Transformer.from_crs(source, target_crs, always_xy=True)
    except PyprojCrsError as exc:
        raise CrsError(f"坐标系解析失败：{exc}") from exc


def _transform_position(position: list[Any], transformer: Transformer) -> list[Any]:
    """变换单个位置，保留 z 值（若存在）。

    GeoJSON 的位置是 `[x, y]` 或 `[x, y, z]`。z 分量原样透传——CRS 变换不改变
    高程，丢弃它会让三维产出静默降维。
    """
    if len(position) < 2:
        raise CrsError(
            f"GeoJSON 位置元素少于 2 个：{position!r}",
            public_message="GeoJSON 坐标结构异常",
        )
    x, y = transformer.transform(position[0], position[1])
    return [x, y, *position[2:]]


def _walk_coordinates(node: Any, transformer: Transformer) -> Any:
    """递归下降坐标结构，只变换叶子层的位置数组。

    叶子判据是「首元素为数值」——位置数组与环列表、多边形列表的唯一区别就在
    这一层。比按几何类型分支更稳：不需要枚举 Polygon / MultiPolygon /
    GeometryCollection，嵌套深度增加时无需改动。
    """
    if isinstance(node, list):
        if node and isinstance(node[0], (int, float)):
            return _transform_position(node, transformer)
        return [_walk_coordinates(child, transformer) for child in node]
    raise CrsError(
        f"GeoJSON 坐标结构无法识别：{node!r}",
        public_message="GeoJSON 坐标结构异常",
    )


def reproject_geojson(geojson_str: str, src_wkt: str, *, target_crs: str = GEOGRAPHIC_CRS) -> str:
    """把 GeoJSON 中的全部坐标由 `src_wkt` 表示的坐标系变换到 `target_crs`。

    空字符串原样返回：那是「无内容可变换」，属正常情形，不是错误。

    @throws CrsError 源 WKT 为空或无法解析，或几何缺少 `coordinates`
    @throws EngineError 传入的 GeoJSON 无法解析——说明引擎产出了非法 JSON
    """
    if not geojson_str:
        return geojson_str

    transformer = _transformer(src_wkt, target_crs)

    try:
        document: Any = json.loads(geojson_str)
    except json.JSONDecodeError as exc:
        raise EngineError(f"引擎返回的 GeoJSON 无法解析：{exc}") from exc

    if not isinstance(document, dict):
        raise EngineError(f"引擎返回的 GeoJSON 顶层不是对象，实得 {type(document).__name__}")

    for feature in document.get("features", []):
        geometry = feature.get("geometry") or {}
        if "coordinates" not in geometry:
            raise CrsError(
                f"几何缺少 coordinates 字段：{geometry.get('type')!r}",
                public_message="GeoJSON 坐标结构异常",
            )
        geometry["coordinates"] = _walk_coordinates(geometry["coordinates"], transformer)

    return json.dumps(document)


def image_corners(
    geo_transform: GeoTransform,
    width: int,
    height: int,
    src_wkt: str,
    *,
    target_crs: str = GEOGRAPHIC_CRS,
) -> list[list[float]]:
    """影像四角在 `target_crs` 下的坐标，顺序为左上、右上、右下、左下。

    参数是**已校验**的 `Raster.geo_transform` 六元组，故此处不再重复校验长度
    （校验在 `spatial.as_geo`，失败语义见 `docs/contracts.md` §6）。

    列方向的步长用 `width`、行方向的步长用 `height`——两者在非方形影像上不等，
    混淆即越界。§7.3 的「纬度落在行范围内」断言专门守护这一处。
    """
    x0, dx, rx, y0, ry, dy = geo_transform
    corners_source = [
        (x0, y0),
        (x0 + width * dx, y0 + width * ry),
        (x0 + width * dx + height * rx, y0 + width * ry + height * dy),
        (x0 + height * rx, y0 + height * dy),
    ]
    transformer = _transformer(src_wkt, target_crs)
    return [list(transformer.transform(x, y)) for x, y in corners_source]
