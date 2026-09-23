"""掩膜后处理的协议。

与 `detectors/base.py` 同构，但这里只有协议、没有注册表：后处理当前只有一个
内置实现，为单一实现维护索引表只是多一层间接。出现第二个实现时再引入对称的
`registry.py`。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

__all__ = ["MaskPostprocessor"]


@runtime_checkable
class MaskPostprocessor(Protocol):
    """掩膜后处理器协议。

    实现约定：

    * `name` 唯一，用于日志与诊断。
    * `apply` 是纯函数，入参与返回值都是 `(height, width)` 的 `bool` 数组。
    * 参数由**构造期**注入（来源是配置）。不放进 `apply` 的签名——否则每个
      调用点都要各自从配置里取一遍参数，注入点一多，配置就形同虚设。
    """

    name: str

    def apply(self, mask: NDArray[np.bool_]) -> NDArray[np.bool_]: ...
