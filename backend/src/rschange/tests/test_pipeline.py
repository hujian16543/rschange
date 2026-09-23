"""编排层：七步流程的集成与基线锚点。

流程用例都经 `detect_change(...)` 走完整链路（读栅格 → 检测 → 后处理 → 出图 →
矢量化/重投影 → 组装）。依赖由 `context` 夹具显式注入，故这些用例**不依赖**
`api/` 层。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import numpy as np
import pytest

from rschange.detectors.base import DetectionResult
from rschange.errors import InputValidationError, ProcessingError
from rschange.pipeline import DetectionRequest, detect_change

if TYPE_CHECKING:
    from pathlib import Path

    from numpy.typing import NDArray

    from rschange.api.deps import RuntimeContext


@pytest.fixture
def request_for(tmp_path: Path):
    """按 路径对 构造请求，输出目录落在 tmp_path 下。"""

    def _make(before: Path, after: Path, job_id: str = "job") -> DetectionRequest:
        return DetectionRequest(
            job_id=job_id,
            before_path=before,
            after_path=after,
            output_dir=tmp_path / "outputs",
        )

    return _make


def _run(request: DetectionRequest, context: RuntimeContext):
    return detect_change(
        request,
        detector=context.detector,
        postprocessor=context.postprocessor,
        settings=context.settings,
    )


def _write_pair(
    tmp_path: Path,
    before_mask: NDArray[np.uint8],
    after_mask: NDArray[np.uint8],
    geo: tuple[float, float, float, float, float, float],
    projection: str,
) -> tuple[Path, Path]:
    from rschange.spatial import write_raster

    before = tmp_path / "syn_before.tif"
    after = tmp_path / "syn_after.tif"
    write_raster(before, before_mask, geo, projection)
    write_raster(after, after_mask, geo, projection)
    return before, after


@pytest.mark.baseline
@pytest.mark.usefixtures("engine_ready")
class TestFixtureAnchors:
    """真实夹具上的端到端锚点。任何一项漂移都记回归缺陷。"""

    def test_outcome_matches_baseline(
        self, before_path: Path, after_path: Path, request_for, context: RuntimeContext
    ) -> None:
        outcome = _run(request_for(before_path, after_path, "anchors"), context)

        assert outcome.detector == "cva"
        assert abs(outcome.threshold - 5.9168) <= 1e-4
        assert outcome.change_pixels == 7209
        assert outcome.total_pixels == 65536
        assert outcome.change_rate == pytest.approx(7209 / 65536)
        assert outcome.pixel_area_m2 == pytest.approx(100.0)
        assert outcome.changed_area_m2 == pytest.approx(720900.0)
        assert outcome.mask.shape == (256, 256)

    def test_geojson_area_matches_pixel_area(
        self, before_path: Path, after_path: Path, request_for, context: RuntimeContext
    ) -> None:
        """§7.3 语义断言：属性面积合计 == 像元数 × 单像元面积。"""
        outcome = _run(request_for(before_path, after_path, "areas"), context)
        document = json.loads(outcome.geojson)

        assert document["type"] == "FeatureCollection"
        area_sum = sum(feature["properties"]["area_m2"] for feature in document["features"])
        assert area_sum == pytest.approx(outcome.changed_area_m2, abs=1e-6)

    def test_geojson_coordinates_are_geographic(
        self, before_path: Path, after_path: Path, request_for, context: RuntimeContext
    ) -> None:
        outcome = _run(request_for(before_path, after_path, "coords"), context)
        document = json.loads(outcome.geojson)
        positions = np.array(
            [
                position
                for feature in document["features"]
                for ring in feature["geometry"]["coordinates"]
                for position in ring
            ]
        )
        assert positions[:, 0].min() > 116.0 and positions[:, 0].max() < 118.0
        assert positions[:, 1].min() > 35.0 and positions[:, 1].max() < 37.0

    def test_three_previews_are_written(
        self, before_path: Path, after_path: Path, request_for, context: RuntimeContext
    ) -> None:
        outcome = _run(request_for(before_path, after_path, "previews"), context)
        assert [preview.kind for preview in outcome.previews] == ["before", "after", "diff"]
        for preview in outcome.previews:
            assert preview.path.name.startswith("previews_")
            assert preview.path.stat().st_size > 1000

    def test_corners_bracket_the_image(
        self, before_path: Path, after_path: Path, request_for, context: RuntimeContext
    ) -> None:
        outcome = _run(request_for(before_path, after_path, "corners"), context)
        corners = outcome.image_corners
        assert len(corners) == 4
        assert corners[0][1] > corners[2][1]


@pytest.mark.usefixtures("engine_ready")
class TestNonSquareImage:
    """方形影像会让 `width == height`，把 W/H 混淆长期掩盖。"""

    H = 32
    W = 48
    GEO = (500000.0, 10.0, 0.0, 4000000.0, 0.0, -10.0)

    def _pair(self, tmp_path: Path, projection: str) -> tuple[Path, Path]:
        before = np.zeros((self.H, self.W), dtype=np.uint8)
        after = np.zeros((self.H, self.W), dtype=np.uint8)
        after[8:20, 10:30] = 200
        return _write_pair(tmp_path, before, after, self.GEO, projection)

    def test_change_area_is_pixel_count_times_pixel_area(
        self, tmp_path: Path, request_for, context: RuntimeContext, before_path: Path
    ) -> None:
        from rschange.spatial import read_raster

        projection = read_raster(before_path).projection
        before, after = self._pair(tmp_path, projection)
        outcome = _run(request_for(before, after, "nonsquare"), context)

        assert outcome.change_pixels == 12 * 20
        assert outcome.pixel_area_m2 == pytest.approx(100.0)
        assert outcome.changed_area_m2 == pytest.approx(12 * 20 * 100.0)

    def test_corners_use_width_for_columns(
        self, tmp_path: Path, request_for, context: RuntimeContext, before_path: Path
    ) -> None:
        from rschange.spatial import read_raster

        projection = read_raster(before_path).projection
        before, after = self._pair(tmp_path, projection)
        outcome = _run(request_for(before, after, "nonsquare"), context)

        # 右上角对应 x = x0 + width * dx = 500000 + 480
        upper_right_lon = outcome.image_corners[1][0]
        assert upper_right_lon > outcome.image_corners[0][0]
        # 若误用 height 走列，位移会变成 320 而非 480，经度增量随之偏小。
        increment = upper_right_lon - outcome.image_corners[0][0]
        assert increment > 0.005


@pytest.mark.usefixtures("engine_ready")
class TestValidation:
    def test_shape_mismatch_rejected(
        self, tmp_path: Path, request_for, context: RuntimeContext, before_path: Path
    ) -> None:
        """夹具是 3 波段，合成的单波段影像与之形状不同。"""
        from rschange.spatial import read_raster, write_raster

        source = read_raster(before_path)
        mask = np.zeros((source.height, source.width), dtype=np.uint8)
        other = tmp_path / "single_band.tif"
        write_raster(other, mask, source.geo_transform, source.projection)

        with pytest.raises(InputValidationError) as caught:
            _run(request_for(before_path, other, "mismatch"), context)
        assert "尺寸或波段数不一致" in caught.value.public_message

    def test_geotransform_mismatch_rejected(
        self, tmp_path: Path, request_for, context: RuntimeContext, before_path: Path
    ) -> None:
        """旧实现静默沿用前一期地理参考，对两幅定位不同的影像做逐像元比较。

        两侧都用合成的单波段影像：形状必须一致，否则会先撞上形状检查，测不到
        地理变换这一条。
        """
        from rschange.spatial import read_raster, write_raster

        source = read_raster(before_path)
        mask = np.zeros((source.height, source.width), dtype=np.uint8)
        geo = source.geo_transform
        shifted = (geo[0], geo[1], geo[2], geo[3] - 1000.0, geo[4], geo[5])

        base = tmp_path / "base.tif"
        displaced = tmp_path / "displaced.tif"
        write_raster(base, mask, geo, source.projection)
        write_raster(displaced, mask, shifted, source.projection)

        with pytest.raises(InputValidationError) as caught:
            _run(request_for(base, displaced, "geoshift"), context)
        assert "地理定位" in caught.value.public_message

    def test_projection_mismatch_rejected(
        self, tmp_path: Path, request_for, context: RuntimeContext, before_path: Path
    ) -> None:
        """地理变换一致、仅投影不同——必须在这一条上失败。"""
        from rschange.spatial import read_raster, write_raster

        source = read_raster(before_path)
        mask = np.zeros((source.height, source.width), dtype=np.uint8)

        base = tmp_path / "with_crs.tif"
        without_crs = tmp_path / "no_crs.tif"
        write_raster(base, mask, source.geo_transform, source.projection)
        write_raster(without_crs, mask, source.geo_transform, "")

        with pytest.raises(InputValidationError) as caught:
            _run(request_for(base, without_crs, "projmismatch"), context)
        assert "坐标系不一致" in caught.value.public_message


@pytest.mark.usefixtures("engine_ready")
class TestInjection:
    """依赖注入是编排层可测试、可插拔的前提。"""

    def test_stub_detector_overrides_cva(
        self, before_path: Path, after_path: Path, request_for, context: RuntimeContext
    ) -> None:
        class EmptyDetector:
            name = "empty"

            def detect(
                self, before: NDArray[np.uint16], after: NDArray[np.uint16]
            ) -> DetectionResult:
                return DetectionResult(mask=np.zeros(after.shape[1:], dtype=bool), threshold=None)

        outcome = detect_change(
            request_for(before_path, after_path, "stub"),
            detector=EmptyDetector(),
            postprocessor=context.postprocessor,
            settings=context.settings,
        )
        assert outcome.detector == "empty"
        assert outcome.change_pixels == 0
        assert outcome.changed_area_m2 == 0.0

    def test_postprocessor_shape_violation_raises_processing_error(
        self, before_path: Path, after_path: Path, request_for, context: RuntimeContext
    ) -> None:
        """`MaskPostprocessor` 的保形约定此前只是文档语句，现在是断言。"""

        class Reshaper:
            name = "reshaper"

            def apply(self, mask: NDArray[np.bool_]) -> NDArray[np.bool_]:
                return mask[: mask.shape[0] // 2, :]

        with pytest.raises(ProcessingError) as caught:
            detect_change(
                request_for(before_path, after_path, "reshape"),
                detector=context.detector,
                postprocessor=Reshaper(),
                settings=context.settings,
            )
        assert caught.value.http_status == 500

    def test_postprocessor_min_size_comes_from_configuration(
        self, before_path: Path, after_path: Path, request_for, context: RuntimeContext
    ) -> None:
        """`min_size` 提为构造参数后，配置真的能改变结果。"""
        from rschange.postprocess import MorphologyPostprocessor

        outcome = detect_change(
            request_for(before_path, after_path, "aggressive"),
            detector=context.detector,
            postprocessor=MorphologyPostprocessor(min_size=10**9, structure_size=3),
            settings=context.settings,
        )
        assert outcome.change_pixels == 0
