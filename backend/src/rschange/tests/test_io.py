"""`io/` 层：GeoJSON 重投影与预览图渲染。

本模块的用例**不依赖引擎**：重投影只处理字符串，渲染只处理数组。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest
from PIL import Image
from pyproj import CRS, Transformer

from rschange.errors import CrsError, EngineError, InputValidationError
from rschange.io import GEOGRAPHIC_CRS, image_corners, reproject_geojson, save_rgb_png
from rschange.io.preview import RGB_BANDS, stretch_percentiles

if TYPE_CHECKING:
    from pathlib import Path

    from numpy.typing import NDArray

#: 夹具使用的投影：UTM 50N，中央经线 117°E。
UTM_50N_WKT = (
    'PROJCS["WGS 84 / UTM zone 50N",GEOGCS["WGS 84",DATUM["WGS_1984",'
    'SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],'
    'UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],'
    'PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",117],'
    'PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],'
    'PARAMETER["false_northing",0],UNIT["metre",1]]'
)

GEO = (500000.0, 10.0, 0.0, 4000000.0, 0.0, -10.0)


def _collection(*geometries: dict[str, Any]) -> str:
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {}, "geometry": geometry}
                for geometry in geometries
            ],
        }
    )


def _positions(geojson_text: str) -> NDArray[np.float64]:
    document = json.loads(geojson_text)
    collected: list[list[float]] = []

    def walk(node: object) -> None:
        if isinstance(node, list) and node and isinstance(node[0], (int, float)):
            collected.append(node)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    for feature in document["features"]:
        walk(feature["geometry"]["coordinates"])
    return np.array(collected, dtype=np.float64)


class TestReprojectGeoJson:
    def test_empty_string_is_returned_as_is(self) -> None:
        assert reproject_geojson("", UTM_50N_WKT) == ""

    def test_output_crs_is_wgs84(self) -> None:
        assert GEOGRAPHIC_CRS == "EPSG:4326"

    def test_polygon_is_projected_to_lon_lat(self) -> None:
        polygon = {
            "type": "Polygon",
            "coordinates": [
                [
                    [500000.0, 4000000.0],
                    [500100.0, 4000000.0],
                    [500100.0, 3999900.0],
                    [500000.0, 4000000.0],
                ]
            ],
        }
        positions = _positions(reproject_geojson(_collection(polygon), UTM_50N_WKT))

        assert positions.shape[1] == 2
        # UTM 50N 的 x=500000 即中央经线 117°E；y=4000000 约在 36.1°N。
        assert 116.9 < positions[:, 0].min() <= positions[:, 0].max() < 117.2
        assert 36.0 < positions[:, 1].min() <= positions[:, 1].max() < 36.3

    def test_multipolygon_is_transformed(self) -> None:
        """旧实现对 MultiPolygon 解包失败，随后被裸 `except` 吞掉，返回未变换的坐标。"""
        multipolygon = {
            "type": "MultiPolygon",
            "coordinates": [
                [[[500000.0, 4000000.0], [500100.0, 4000000.0], [500100.0, 3999900.0]]],
                [[[500200.0, 3999800.0], [500300.0, 3999800.0], [500300.0, 3999700.0]]],
            ],
        }
        positions = _positions(reproject_geojson(_collection(multipolygon), UTM_50N_WKT))
        assert len(positions) == 6
        assert positions[:, 0].max() < 1000.0, "未变换的坐标会是 500000 量级"
        assert positions[:, 0].min() > 100.0

    def test_z_component_is_preserved(self) -> None:
        point = {"type": "Point", "coordinates": [500000.0, 4000000.0, 123.0]}
        position = json.loads(reproject_geojson(_collection(point), UTM_50N_WKT))["features"][0][
            "geometry"
        ]["coordinates"]
        assert len(position) == 3
        assert position[2] == 123.0

    def test_missing_crs_raises_400(self) -> None:
        """旧实现在此返回未重投影的坐标，前端画出一张位置全错的地图且无报错。"""
        polygon = {"type": "Polygon", "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]]}
        with pytest.raises(CrsError) as caught:
            reproject_geojson(_collection(polygon), "   ")
        assert caught.value.http_status == 400

    def test_unparsable_crs_raises_400(self) -> None:
        polygon = {"type": "Polygon", "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]]}
        with pytest.raises(CrsError):
            reproject_geojson(_collection(polygon), "NOT A CRS AT ALL")

    def test_invalid_json_raises_engine_error(self) -> None:
        with pytest.raises(EngineError) as caught:
            reproject_geojson("{not json", UTM_50N_WKT)
        assert caught.value.http_status == 500

    def test_geometry_without_coordinates_raises(self) -> None:
        broken = _collection({"type": "GeometryCollection", "geometries": []})
        with pytest.raises(CrsError):
            reproject_geojson(broken, UTM_50N_WKT)


class TestImageCorners:
    def test_returns_four_corners_clockwise_from_upper_left(self) -> None:
        corners = image_corners(GEO, 48, 32, UTM_50N_WKT)
        assert len(corners) == 4
        # 左上与右上同纬度；左下与右下同纬度；上排纬度高于下排。
        assert corners[0][1] == pytest.approx(corners[1][1])
        assert corners[2][1] == pytest.approx(corners[3][1])
        assert corners[0][1] > corners[2][1]

    def test_width_and_height_are_not_swapped(self) -> None:
        """非方形影像才能暴露 W/H 混淆；方形会把两者变成同一个值。"""
        width, height = 48, 32
        corners = image_corners(GEO, width, height, UTM_50N_WKT)
        transformer = Transformer.from_crs(CRS.from_wkt(UTM_50N_WKT), "EPSG:4326", always_xy=True)
        expected = [
            list(transformer.transform(x, y))
            for x, y in (
                (GEO[0], GEO[3]),
                (GEO[0] + width * GEO[1], GEO[3] + width * GEO[4]),
                (
                    GEO[0] + width * GEO[1] + height * GEO[2],
                    GEO[3] + width * GEO[4] + height * GEO[5],
                ),
                (GEO[0] + height * GEO[2], GEO[3] + height * GEO[5]),
            )
        ]
        assert np.allclose(np.array(corners), np.array(expected), atol=1e-9)

    def test_axis_order_is_lon_lat(self) -> None:
        """`always_xy=True` 保证输出是 (经度, 纬度)。

        缺了它会落到 EPSG:4326 的官方轴序 (纬度, 经度)，表现为整幅图关于对角线
        镜像翻转——数值上看不出明显异常。
        """
        corners = image_corners(GEO, 256, 256, UTM_50N_WKT)
        for lon, lat in corners:
            assert 116.0 < lon < 118.0
            assert 35.0 < lat < 37.0

    def test_missing_crs_raises_400(self) -> None:
        with pytest.raises(CrsError) as caught:
            image_corners(GEO, 4, 4, "")
        assert caught.value.http_status == 400


class TestStretch:
    def test_percentile_stretch_spans_full_range(self) -> None:
        band = np.linspace(0.0, 1000.0, 1000).astype(np.float32).reshape(40, 25)
        stretched = stretch_percentiles(band)
        assert stretched.dtype == np.float32
        assert stretched.min() == pytest.approx(0.0, abs=1.0)
        assert stretched.max() == pytest.approx(255.0, abs=1.0)

    def test_constant_band_does_not_divide_by_zero(self) -> None:
        stretched = stretch_percentiles(np.full((4, 4), 7.0, dtype=np.float32))
        assert np.isfinite(stretched).all()


class TestSaveRgbPng:
    def test_three_band_array_becomes_rgb_png(self, tmp_path: Path) -> None:
        array = np.zeros((3, 8, 8), dtype=np.uint16)
        array[0] = 100
        array[1] = 200
        path = save_rgb_png(array, tmp_path / "rgb.png")

        assert path.exists()
        with Image.open(path) as image:
            assert image.mode == "RGB"
            assert image.size == (8, 8)

    def test_single_band_array_is_replicated(self, tmp_path: Path) -> None:
        """旧实现 `arr[:3]` 对单波段得到 (1, H, W)，随后抛与真实原因无关的报错。"""
        single = np.full((1, 8, 8), 100, dtype=np.uint16)
        path = save_rgb_png(single, tmp_path / "gray.png")
        with Image.open(path) as image:
            assert image.mode == "RGB"

    def test_two_band_array_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(InputValidationError) as caught:
            save_rgb_png(np.zeros((2, 8, 8), dtype=np.uint16), tmp_path / "two.png")
        assert caught.value.http_status == 400

    @pytest.mark.parametrize("ndim", [1, 2, 4])
    def test_non_3d_rejected(self, tmp_path: Path, ndim: int) -> None:
        array = np.zeros((8,) * ndim, dtype=np.uint16)
        with pytest.raises(InputValidationError, match="3D"):
            save_rgb_png(array, tmp_path / f"bad{ndim}.png")

    def test_mask_shape_mismatch_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(InputValidationError, match="掩膜形状"):
            save_rgb_png(
                np.zeros((3, 8, 8), dtype=np.uint16),
                tmp_path / "bad.png",
                mask=np.zeros((4, 4), dtype=bool),
            )

    def test_mask_overlay_is_opaque_red(self, tmp_path: Path) -> None:
        """掩膜处为纯红：`putalpha(mask)` 整体覆盖了构造时的 alpha=100。

        `alpha=100` 实际是无效参数。改成真半透明会让输出图肉眼可见地变化，属产品
        决策而非缺陷修复，故本用例把**当前行为**钉住，避免无声漂移。
        """
        array = np.full((3, 8, 8), 500, dtype=np.uint16)
        mask = np.zeros((8, 8), dtype=bool)
        mask[2:6, 2:6] = True
        path = save_rgb_png(array, tmp_path / "overlay.png", mask=mask)

        with Image.open(path) as image:
            pixels = np.array(image)
        assert tuple(pixels[4, 4]) == (255, 0, 0), "掩膜内应为纯红"
        assert tuple(pixels[0, 0]) != (255, 0, 0), "掩膜外不应为纯红"

    def test_constant_image_writes_file(self, tmp_path: Path) -> None:
        path = save_rgb_png(np.full((3, 8, 8), 7, dtype=np.uint16), tmp_path / "const.png")
        assert path.stat().st_size > 0
        assert RGB_BANDS == 3
