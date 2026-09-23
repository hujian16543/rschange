"""掩膜后处理层（可插拔）。

结构与 `detectors/` 对称：协议定义在 `base.py`，具体实现各自独立成模块。
差异在于本层**没有**注册表——当前只有一个内置实现，为单一实现维护索引表
只是多一层间接。出现第二个实现时再引入。

两条硬约束：

* 参数（最小连通面积、结构元尺寸）必须来自 `config.postprocess`，禁止写死在
  实现内部——旧实现的 `min_size=30` 是函数默认值，无法从配置调整。
* **禁止**残留任何调试输出（旧实现 `detectors/postprocessor.py` 第 21 行的
  `print` 属缺陷 D-2）。日志一律走 `rschange.logging`。
"""

from __future__ import annotations

from rschange.postprocess.base import MaskPostprocessor
from rschange.postprocess.morphology import MorphologyPostprocessor

__all__ = ["MaskPostprocessor", "MorphologyPostprocessor"]
