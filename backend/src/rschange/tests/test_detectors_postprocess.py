"""检测算法与后处理。

CVA 的数值用例分两类：

* **引擎无关**的合成数组用例（构造已知的双峰幅度图），任何环境都能跑；
* **基线锚点**用例依赖真实夹具与 `_spatial`，标 `baseline` 并依赖 `engine_ready`。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from rschange.detectors import registry
from rschange.detectors.base import ChangeDetector, DetectionResult
from rschange.detectors.cva import HISTOGRAM_BINS, CvaDetector, histogram, otsu_threshold
from rschange.errors import InputValidationError, UnknownDetectorError
from rschange.postprocess import MaskPostprocessor, MorphologyPostprocessor

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from numpy.typing import NDArray


class _ProbeDetector:
    """最简实现：把两期影像的不等位置当作变化。协议只要求形状对得上。"""

    name = "probe"

    def detect(self, before: NDArray[np.uint16], after: NDArray[np.uint16]) -> DetectionResult:
        return DetectionResult(mask=(before != after), threshold=None)


@pytest.fixture
def restores_registry() -> Iterator[None]:
    """注册表是模块级全局；用例改动它之后必须还原，否则会污染后续用例。

    这里直接用私有 `_REGISTRY` 快照，而不是为测试新增公开的 `unregister`——
    公开 API 的每一寸都要长期维护，而测试的还原需求是局部的。
    """
    snapshot = dict(registry._REGISTRY)
    try:
        yield
    finally:
        registry._REGISTRY.clear()
        registry._REGISTRY.update(snapshot)


class TestRegistry:
    def test_builtin_algorithm_is_prenegistered(self) -> None:
        """导入包即完成注册，调用方无需记得先 import 什么。"""
        assert registry.available() == ("cva",)
        assert registry.DEFAULT_DETECTOR == "cva"

    def test_resolve_default_and_by_name(self) -> None:
        assert isinstance(registry.resolve(), CvaDetector)
        assert isinstance(registry.resolve("cva"), CvaDetector)

    def test_unknown_name_raises_with_400(self) -> None:
        with pytest.raises(UnknownDetectorError) as caught:
            registry.resolve("does-not-exist")
        assert caught.value.http_status == 400
        assert "does-not-exist" in caught.value.public_message

    def test_duplicate_registration_rejected(self, restores_registry: None) -> None:
        """重名静默覆盖会让「最终生效的是哪一个」取决于导入顺序，且无任何征兆。"""
        with pytest.raises(ValueError, match="已被"):
            registry.register(CvaDetector())

    def test_override_registration_allowed(self, restores_registry: None) -> None:
        replacement = _ProbeDetector()
        replacement.name = "cva"
        assert registry.register(replacement, override=True) is replacement
        assert registry.resolve("cva") is replacement

    def test_new_algorithm_joins_registry(self, restores_registry: None) -> None:
        registry.register(_ProbeDetector())
        assert registry.available() == ("cva", "probe")
        assert isinstance(registry.resolve("probe"), _ProbeDetector)

    def test_protocol_is_structural(self) -> None:
        """不继承任何东西也该被接受——这是降低「写一个新算法」门槛的关键。"""
        assert isinstance(_ProbeDetector(), ChangeDetector)
        assert isinstance(CvaDetector(), ChangeDetector)


class TestHistogram:
    def test_counts_sum_to_size(self) -> None:
        data = np.linspace(0.0, 100.0, 1000).reshape(40, 25)
        centers, counts = histogram(data)
        assert len(counts) == HISTOGRAM_BINS
        assert len(centers) == HISTOGRAM_BINS
        assert counts.sum() == data.size

    def test_extreme_values_land_in_end_bins(self) -> None:
        """极值分别落入首箱与末箱。

        箱边界由数据自身的最小/最大值决定，故「越界」只可能发生在上界：
        `(max - min) / width` 恰好等于箱数，直接取整会得到 `bins` 这一越界下标，
        被 `np.clip` 折回 `bins - 1`。这一处细节属于 Otsu 结果的一部分，不能用
        `np.histogram` 替换——那会把最大值归入另一个箱。
        """
        _, counts = histogram(np.array([[0.0, 10.0, -5.0, 20.0]]))
        assert counts[0] == 1  # 最小值 -5.0
        assert counts[-1] == 1  # 最大值 20.0
        assert counts.sum() == 4
        assert counts[1:-1].sum() == 2  # 0.0 与 10.0 落在中间

    def test_constant_input_does_not_divide_by_zero(self) -> None:
        """旧实现在 `bin_width == 0` 时产生 0/0，随后 `astype(int64)` 行为未定义。"""
        centers, counts = histogram(np.full((4, 4), 7.0))
        assert counts.sum() == 16
        assert counts[0] == 16
        assert np.all(centers == 7.0)


class TestOtsu:
    def test_constant_input_returns_zero(self) -> None:
        assert otsu_threshold(np.full((8, 8), 3.0)) == 0.0

    def test_bimodal_input_splits_between_the_modes(self) -> None:
        magnitude = np.concatenate([np.zeros(500), np.full(500, 300.0)]).reshape(25, 40)
        threshold = otsu_threshold(magnitude)
        assert 0.0 < threshold < 300.0


class TestCvaDetector:
    def test_known_bimodal_magnitude(self) -> None:
        """纯合成、引擎无关：2×2 的已知变化块。"""
        before = np.zeros((3, 4, 4), dtype=np.uint16)
        after = np.zeros((3, 4, 4), dtype=np.uint16)
        after[:, 1:3, 1:3] = 200

        result = CvaDetector().detect(before, after)
        assert result.changed_pixels == 4
        assert result.total_pixels == 16
        assert result.mask[1, 1] and result.mask[2, 2]
        assert not result.mask[0, 0]
        assert result.mask.dtype == np.bool_
        assert result.threshold is not None and result.threshold > 0.0

    def test_identical_images_produce_empty_mask(self) -> None:
        array = np.full((3, 8, 8), 42, dtype=np.uint16)
        result = CvaDetector().detect(array, array.copy())
        assert result.changed_pixels == 0
        assert result.change_rate == 0.0

    def test_change_rate_is_consistent(self) -> None:
        before = np.zeros((1, 10, 10), dtype=np.uint16)
        after = np.zeros((1, 10, 10), dtype=np.uint16)
        after[:, :5, :] = 200
        result = CvaDetector().detect(before, after)
        assert result.change_rate == result.changed_pixels / result.total_pixels

    def test_shape_mismatch_rejected(self) -> None:
        before = np.zeros((3, 8, 8), dtype=np.uint16)
        after = np.zeros((3, 8, 4), dtype=np.uint16)
        with pytest.raises(InputValidationError) as caught:
            CvaDetector().detect(before, after)
        assert caught.value.http_status == 400
        assert "尺寸或波段数不一致" in caught.value.public_message

    @pytest.mark.parametrize("ndim", [1, 2])
    def test_non_3d_input_rejected(self, ndim: int) -> None:
        array = np.zeros((8,) * ndim, dtype=np.uint16)
        with pytest.raises(InputValidationError, match="3D"):
            CvaDetector().detect(array, array)


class TestDetectionResult:
    def test_empty_mask_has_zero_rate(self) -> None:
        result = DetectionResult(mask=np.zeros((4, 4), dtype=bool))
        assert result.changed_pixels == 0
        assert result.change_rate == 0.0
        assert result.threshold is None


class TestMorphology:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(MorphologyPostprocessor(), MaskPostprocessor)

    def test_small_blobs_are_removed(self) -> None:
        """判定是「严格大于 min_size」：不超过该值的块被剔除。"""
        mask = np.zeros((10, 10), dtype=bool)
        mask[0:1, 0:5] = True  # 5 像素的小块
        mask[4:9, 4:9] = True  # 25 像素的大块

        cleaned = MorphologyPostprocessor(min_size=10, structure_size=1).apply(mask)
        assert int(cleaned.sum()) == 25
        assert not cleaned[0, :5].any()
        assert cleaned[4:9, 4:9].all()

    def test_min_size_zero_with_unit_structure_is_identity(self) -> None:
        mask = np.zeros((8, 8), dtype=bool)
        mask[2:4, 2:4] = True
        cleaned = MorphologyPostprocessor(min_size=0, structure_size=1).apply(mask)
        assert np.array_equal(cleaned, mask)

    def test_closing_fills_single_pixel_gap(self) -> None:
        mask = np.zeros((7, 7), dtype=bool)
        mask[2:5, 2:5] = True
        mask[3, 3] = False  # 内部单像素空洞
        cleaned = MorphologyPostprocessor(min_size=0, structure_size=3).apply(mask)
        assert bool(cleaned[3, 3])

    def test_background_label_is_excluded(self) -> None:
        """`keep[0] = False`：标签 0 是背景，不代表任何连通块。"""
        cleaned = MorphologyPostprocessor(min_size=0, structure_size=1).apply(
            np.zeros((4, 4), dtype=bool)
        )
        assert not cleaned.any()

    def test_shape_is_preserved(self) -> None:
        mask = np.zeros((32, 48), dtype=bool)
        mask[10:20, 10:20] = True
        assert MorphologyPostprocessor().apply(mask).shape == (32, 48)

    def test_non_2d_rejected(self) -> None:
        with pytest.raises(ValueError, match="2D"):
            MorphologyPostprocessor().apply(np.zeros((1, 4, 4), dtype=bool))

    @pytest.mark.parametrize(
        ("min_size", "structure_size"),
        [(-1, 3), (0, 0), (0, -3)],
        ids=["min-负", "struct-0", "struct-负"],
    )
    def test_invalid_parameters_rejected(self, min_size: int, structure_size: int) -> None:
        with pytest.raises(ValueError):
            MorphologyPostprocessor(min_size=min_size, structure_size=structure_size)


@pytest.mark.baseline
class TestBaselineAnchors:
    """§7.1 的 CVA 不变量。漂移即回归缺陷。"""

    @pytest.mark.usefixtures("engine_ready")
    def test_fixture_threshold_and_pixel_count(self, before_path: Path, after_path: Path) -> None:
        from rschange.spatial import read_raster

        before = read_raster(before_path)
        after = read_raster(after_path)
        result = CvaDetector().detect(before.array, after.array)

        assert before.array.shape == (3, 256, 256)
        assert before.array.dtype == np.uint16
        assert abs((result.threshold or 0.0) - 5.9168) <= 1e-4
        assert result.changed_pixels == 7209
        assert result.total_pixels == 65536

    @pytest.mark.usefixtures("engine_ready")
    def test_postprocess_is_identity_on_fixture(self, before_path: Path, after_path: Path) -> None:
        """`EXPECTED_CHANGED_RAW` 与 `EXPECTED_CHANGED_CLEAN` 同为 7209。"""
        from rschange.spatial import read_raster

        before = read_raster(before_path)
        after = read_raster(after_path)
        result = CvaDetector().detect(before.array, after.array)
        cleaned = MorphologyPostprocessor(min_size=30, structure_size=3).apply(result.mask)
        assert int(cleaned.sum()) == 7209
