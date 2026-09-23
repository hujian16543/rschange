"""CVA（Change Vector Analysis）变化检测。

算法
----
对每个像元计算两期影像在多波段空间中的欧氏距离：

    magnitude(r, c) = ‖ after[:, r, c] − before[:, r, c] ‖₂

再对 magnitude 图用 Otsu 方法求阈值，得到二值变化掩膜。

数值行为与 Phase 2 基线逐位一致
-------------------------------
本文件是旧 `detectors/cva.py` 的重构版，**刻意保留**了原直方图与 Otsu 的
实现路径，没有替换成 `np.histogram` 或 `skimage.filters.threshold_otsu`。

原因：黄金基线锚点钉住了本夹具上的阈值 `5.9168` 与变化像素数 `7209/65536`。
阈值来自「等宽分箱 + 箱中心作为候选阈值 + 严格大于取最大类间方差」这一具体
组合；换实现若在箱边界归并或并列最大方差的取舍上有任何差异，锚点即漂移，
而漂移会被记成回归缺陷——排查成本远高于保留原实现。

唯一的修正：常量输入（`magnitude` 全为同一值）在旧实现里会因 `bin_width == 0`
产生 `0/0`，随后 `astype(np.int64)` 的行为未定义。这里显式处理为「全部样本
落入首箱」，此时 Otsu 无可用切分点，返回 0.0，掩膜全 False。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

from rschange.detectors.base import DetectionResult
from rschange.errors import InputValidationError

if TYPE_CHECKING:
    from numpy.typing import NDArray

__all__ = ["HISTOGRAM_BINS", "CvaDetector", "histogram", "otsu_threshold"]

#: 直方图分箱数。与旧实现一致；改动会移动阈值锚点。
HISTOGRAM_BINS: Final[int] = 256


def histogram(
    data: NDArray[np.float64], bins: int = HISTOGRAM_BINS
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """等宽直方图，返回 `(箱中心, 计数)`。

    越界值一律并入首尾箱（`np.clip`），这与 `np.histogram` 在边界上的处理
    不完全相同，而该差异是 Otsu 结果的一部分，故不使用后者。
    """
    vmin = float(data.min())
    vmax = float(data.max())

    if not (vmax > vmin):  # 常量图，或 data 为空导致 min/max 无意义
        centers = np.full(bins, vmin, dtype=np.float64)
        counts = np.zeros(bins, dtype=np.float64)
        counts[0] = float(data.size)
        return centers, counts

    edges = np.linspace(vmin, vmax, bins + 1)
    width = edges[1] - edges[0]
    indices = np.clip(((data - vmin) / width).astype(np.int64), 0, bins - 1)
    counts = np.bincount(indices.ravel(), minlength=bins).astype(np.float64)
    centers = (edges[:-1] + edges[1:]) / 2
    return centers.astype(np.float64), counts


def otsu_threshold(magnitude: NDArray[np.float64]) -> float:
    """Otsu 二分类阈值：最大化类间方差。

    逐个候选阈值把样本切成 `≤ t` 与 `> t` 两类，取类间方差最大者的箱中心。
    实现沿用原逐箱累加路径，见模块 docstring。
    """
    centers, counts = histogram(magnitude)
    total = float(counts.sum())
    if total <= 0:
        return 0.0

    sum_all = float((centers * counts).sum())
    weight_back = 0.0
    sum_back = 0.0
    best_variance = 0.0
    best_threshold = 0.0

    for index in range(counts.size):
        weight_back += counts[index]
        if weight_back == 0.0:
            continue
        weight_fore = total - weight_back
        if weight_fore == 0.0:
            break

        sum_back += centers[index] * counts[index]
        mean_back = sum_back / weight_back
        mean_fore = (sum_all - sum_back) / weight_fore
        variance = weight_back * weight_fore * (mean_back - mean_fore) ** 2
        if variance > best_variance:
            best_variance = variance
            best_threshold = float(centers[index])

    return best_threshold


class CvaDetector:
    """欧氏距离 + Otsu 阈值的 CVA 检测器。"""

    name = "cva"

    def detect(self, before: NDArray[np.uint16], after: NDArray[np.uint16]) -> DetectionResult:
        """计算两期影像的变化掩膜。

        @throws InputValidationError 两期影像形状不一致
        """
        if before.shape != after.shape:
            raise InputValidationError(
                f"两期影像形状不一致：before {before.shape}，after {after.shape}",
                public_message="两期影像的尺寸或波段数不一致",
            )
        if before.ndim != 3:
            raise InputValidationError(
                f"影像必须是 (bands, height, width) 的 3D 数组，实得 {before.ndim} 维",
                public_message="影像维度不符合要求",
            )

        delta = after.astype(np.float64) - before.astype(np.float64)
        magnitude = np.sqrt(np.sum(delta**2, axis=0))
        threshold = otsu_threshold(magnitude)
        return DetectionResult(mask=magnitude > threshold, threshold=threshold)
