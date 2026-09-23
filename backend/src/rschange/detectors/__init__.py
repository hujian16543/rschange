"""变化检测算法层（可插拔）。

新增一种检测算法只需两步：

1. 实现 `detectors/base.py` 中 `ChangeDetector` 协议规定的接口；
2. 在 `detectors/registry.py` 注册。

**禁止**为此修改 `pipeline/change_detection.py`。该约束由「可插拔验证」用例
守护（阶段出口门 G3.4）：新增算法后，编排层文件的哈希必须不变。

注册时机
--------
内置算法在**本模块**（包的 `__init__`）里注册，而不是散在各自算法模块的
导入副作用里。Python 导入 `rschange.detectors.registry` 这类子模块时必先执行
父包的 `__init__`，因此无论调用方从哪条路径进来，「注册表已装好内置算法」
这一前提都成立——不需要调用方记得先 import 什么。
"""

from __future__ import annotations

from rschange.detectors import registry
from rschange.detectors.base import ChangeDetector, DetectionResult
from rschange.detectors.cva import CvaDetector

__all__ = ["ChangeDetector", "CvaDetector", "DetectionResult", "registry"]

registry.register(CvaDetector())
