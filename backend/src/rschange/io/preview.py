"""预览图渲染。

把 `spatial.read_raster` 的 `(bands, height, width) uint16` 数组渲染为 PNG，
可选叠加变化掩膜。旧实现在 `services/detection.py` 的 `_save_rgb_png`。

波段数
------
旧实现的波段假设是隐含的：`rgb = arr[:3]` 对单波段影像得到 `(1, H, W)`，随后
`Image.fromarray(..., mode="RGB")` 抛出与真实原因无关的报错（像素数与模式不匹配）。
现按波段数分支：1 波段复制为三通道，≥3 波段取前三，2 波段明确拒绝——两个通道
既拼不出彩色，也没法解释成灰度，静默取前两个只会产出偏色的图。

保持不变的两处（**有意**）
--------------------------
* **拉伸口径**：2 / 98 分位线性拉伸到 0–255，`hi - lo < 1e-6` 时令 `hi = lo + 1`
  以避免除零。该项直接决定输出像素值，改动会让所有历史预览图不可比。
* **掩膜叠加方式**：`Image.new("RGBA", size, (255, 0, 0, 100))` 的初始 alpha 随后
  被 `putalpha(mask)` **整体覆盖**，因此实际效果是「掩膜处不透明纯红」，而不是
  半透明叠加——`alpha=100` 是无效参数。把它改成真正的半透明会让输出图肉眼
  可见地变化，那属于产品决策而非缺陷修复，故保留原样并在此记录。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

import numpy as np
from PIL import Image

from rschange.errors import InputValidationError, RasterWriteError

if TYPE_CHECKING:
    from numpy.typing import NDArray

__all__ = ["RGB_BANDS", "save_rgb_png", "stretch_percentiles"]

#: 彩色预览的通道数。
RGB_BANDS: Final[int] = 3

#: 拉伸分位点 (低, 高)。与旧实现一致。
_STRETCH_LOW: Final[float] = 2.0
_STRETCH_HIGH: Final[float] = 98.0

#: 动态范围下限。低于它即视为常数图，直接抬高上限避免除零。
_MIN_DYNAMIC_RANGE: Final[float] = 1e-6

#: 掩膜叠加色。
_OVERLAY_RGB: Final[tuple[int, int, int]] = (255, 0, 0)


def stretch_percentiles(band: NDArray[np.float32]) -> NDArray[np.float32]:
    """单波段 2–98 分位线性拉伸到 0–255。

    返回值 dtype 与输入一致（`float32`）。中间运算落在 `float64` 上再赋值回
    `float32` 数组，与旧实现逐位一致。
    """
    low = np.percentile(band, _STRETCH_LOW)
    high = np.percentile(band, _STRETCH_HIGH)
    if high - low < _MIN_DYNAMIC_RANGE:
        high = low + 1
    # 显式标注：numpy 的标量-数组类型提升无法在存根里精确表达，`np.clip` 在此
    # 被推断为 `Any`。标注保留真实返回类型，避免整个函数的输出退化成 Any。
    stretched: NDArray[np.float32] = np.clip((band - low) / (high - low) * 255, 0, 255).astype(
        np.float32
    )
    return stretched


def _to_rgb(array: NDArray[np.uint16]) -> NDArray[np.float32]:
    """取前三通道，1 波段则复制为三通道。

    @throws InputValidationError 数组不是 3D，或波段数为 2
    """
    if array.ndim != 3:
        raise InputValidationError(
            f"影像必须是 (bands, height, width) 的 3D 数组，实得 {array.ndim} 维",
            public_message="影像维度不符合要求",
        )

    bands = int(array.shape[0])
    if bands == 1:
        channels = np.repeat(array, RGB_BANDS, axis=0)
    elif bands >= RGB_BANDS:
        channels = array[:RGB_BANDS]
    else:
        raise InputValidationError(
            f"预览渲染需要 1 或 ≥{RGB_BANDS} 个波段，实得 {bands} 个",
            public_message="影像波段数不足，无法生成彩色预览",
        )
    return channels.astype(np.float32)


def save_rgb_png(
    array: NDArray[np.uint16],
    path: str | Path,
    *,
    mask: NDArray[np.bool_] | None = None,
) -> Path:
    """把影像渲染为 PNG 写出，返回实际写入的路径。

    父目录**必须**已存在，本函数不创建目录——与引擎 `write_raster` 的约定一致
    （`docs/contracts.md` §3.3），目录创建由编排层统一负责。

    @throws InputValidationError 数组不是 3D、波段数为 2，或掩膜形状与影像不符
    @throws RasterWriteError 目标路径不可写
    """
    channels = _to_rgb(array)
    height, width = int(channels.shape[1]), int(channels.shape[2])

    if mask is not None and mask.shape != (height, width):
        raise InputValidationError(
            f"掩膜形状 {mask.shape} 与影像 {(height, width)} 不符",
            public_message="掩膜与影像尺寸不一致",
        )

    rgb = np.empty_like(channels)
    for index in range(RGB_BANDS):
        rgb[index] = stretch_percentiles(channels[index])

    image = Image.fromarray(np.transpose(rgb, (1, 2, 0)).astype(np.uint8))

    if mask is not None:
        overlay = Image.new("RGBA", image.size, (*_OVERLAY_RGB, 100))
        image = image.convert("RGBA")
        mask_image = Image.fromarray((mask * 255).astype(np.uint8))
        mask_image = mask_image.resize(image.size, Image.Resampling.NEAREST)
        overlay.putalpha(mask_image)
        image = Image.alpha_composite(image, overlay)
        image = image.convert("RGB")

    try:
        image.save(str(path), format="PNG")
    except OSError as exc:
        raise RasterWriteError(f"预览图写出失败 {path}：{exc}") from exc
    return Path(path)
