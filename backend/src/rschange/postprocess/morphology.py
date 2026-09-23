"""形态学后处理：剔除小连通块，再做闭运算。

流程与旧 `detectors/postprocessor.py` 一致：

    4 邻域连通域标记 → 剔除像素数不超过 min_size 的块 → 3x3 闭运算

数值行为保留
------------
下列细节都直接影响输出掩膜的像素数，而 §7.1 的基线锚点包含「变化像素
7209」，故一律不改动：

* 判定是 `counts > min_size`，即**不超过** `min_size` 的块被剔除（边界含在
  剔除侧）；
* `keep[0] = False` 排除背景标签；
* 闭运算结构元边长 3、迭代 1 次。

修正项
------
* 删除调试 `print`。旧实现第 21 行 `print(f"[DEBUG] 后处理前: ...")` 是生产
  代码里的残留（D-2，属《重构方案》§1 点名项）。改为结构化日志，且只在像素数
  真的变化时输出。
* `min_size` 与结构元边长提为构造参数，来源是 `config.postprocess`。旧实现把
  `min_size=30` 写成函数默认值，无法从配置调整。
* 连通性显式声明为 4 邻域。旧实现依赖 `scipy.ndimage.label` 的默认结构（那
  恰好是 4 邻域），但默认值一旦变化，语义会静默改变——而它必须与引擎
  `mask_to_geojson` 的 4 邻域口径一致，否则「后处理保留的块」与「导出为
  Feature 的块」会不是同一批。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np
from scipy.ndimage import binary_closing, generate_binary_structure, label

from rschange.logging import get_logger

if TYPE_CHECKING:
    from numpy.typing import NDArray

__all__ = ["MorphologyPostprocessor"]

_logger = get_logger(__name__)

#: 连通性阶数：1 = 4 邻域（上、下、左、右）。与引擎的连通域口径一致。
_CONNECTIVITY: Final[int] = 1


class MorphologyPostprocessor:
    """剔除小连通块后做闭运算。"""

    name = "morphology"

    def __init__(self, *, min_size: int = 30, structure_size: int = 3) -> None:
        if min_size < 0:
            raise ValueError(f"min_size 必须非负，实得 {min_size}")
        if structure_size < 1:
            raise ValueError(f"structure_size 必须为正，实得 {structure_size}")
        self._min_size = min_size
        self._structure_size = structure_size
        self._structure = np.ones((structure_size, structure_size), dtype=bool)

    @property
    def min_size(self) -> int:
        return self._min_size

    @property
    def structure_size(self) -> int:
        return self._structure_size

    def apply(self, mask: NDArray[np.bool_]) -> NDArray[np.bool_]:
        """清理掩膜。

        @throws ValueError 输入不是 2D
        """
        if mask.ndim != 2:
            raise ValueError(f"掩膜必须是 2D (H, W)，实得 {mask.ndim} 维")

        labelled, _ = label(mask, structure=generate_binary_structure(2, _CONNECTIVITY))

        counts = np.bincount(labelled.ravel())
        keep = counts > self._min_size
        keep[0] = False
        cleaned = keep[labelled]

        cleaned = binary_closing(cleaned, structure=self._structure, iterations=1)

        before = int(mask.sum())
        after = int(cleaned.sum())
        if before != after:
            _logger.info(
                "后处理已剔除非显著块",
                pixels_before=before,
                pixels_after=after,
                removed=before - after,
                min_size=self._min_size,
            )
        return cleaned
