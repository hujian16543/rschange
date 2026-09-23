"""变化检测算法的协议与结果类型。

本模块只声明契约，不含任何算法。协议用 `Protocol` 而非抽象基类：算法实现
不需要继承任何东西，只要形状对得上即可被注册表接受——这降低了「写一个新
算法」的门槛，也让第三方实现不必依赖本包的类层次。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

__all__ = ["ChangeDetector", "DetectionResult"]


@dataclass(frozen=True, slots=True)
class DetectionResult:
    """一次变化检测的结果。"""

    mask: NDArray[np.bool_]
    """变化掩膜，shape `(height, width)`，`True` 表示该像元判定为变化。"""

    threshold: float | None = None
    """算法使用的判定阈值。无阈值语义的算法（如分类器式）填 `None`。"""

    @property
    def changed_pixels(self) -> int:
        return int(self.mask.sum())

    @property
    def total_pixels(self) -> int:
        return int(self.mask.size)

    @property
    def change_rate(self) -> float:
        """变化像素占比。空掩膜返回 0.0。"""
        total = self.total_pixels
        return self.changed_pixels / total if total > 0 else 0.0


@runtime_checkable
class ChangeDetector(Protocol):
    """变化检测算法协议。

    实现约定：

    * `name` 唯一，用于注册表索引与日志字段。重名注册会被拒绝。
    * `detect` 是**纯函数**：同样的输入必得同样的输出，不读写外部状态。
      后处理、写盘、出图、重投影都不属本层职责——它们分别在 `postprocess`、
      `io` 中，由 `pipeline` 串联。
    * 入参是 `(bands, height, width)` 的 `uint16` 数组，与
      `spatial.read_raster` 的返回一致；返回值中的掩膜是 `(height, width)` 的
      `bool` 数组。波段数由实现自行解释，但**必须**接受 3 波段输入。
    """

    name: str

    def detect(self, before: NDArray[np.uint16], after: NDArray[np.uint16]) -> DetectionResult: ...
