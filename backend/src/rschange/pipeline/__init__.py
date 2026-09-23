"""用例编排层。

只做「取输入 → 依次调用各层抽象 → 组装结果」，因此本层：

* **禁止**在运行期 import 具体算法实现（`detectors.*` / `postprocess.*` 的具体
  模块），只依赖它们的协议；协议名也仅用于类型标注，故写在 `if TYPE_CHECKING:`
  之下，使 `import rschange.pipeline` 不会连带拉入任何算法。
* **禁止** import `_spatial`（属 `spatial`）；
* 各步骤实现由 `api/deps.py` 在装配期注入，使测试可整体替换为替身。

旧实现的 `services/detection.py` 把「读栅格、检测、后处理、出图、重投影、
组装 GeoJSON、拼响应」七个步骤塞进单个 114 行函数，且 DLL 路径解析与业务
逻辑交织——本层即该函数的解耦结果。

`import rschange.pipeline` **不**加载 `_spatial` 扩展：本包只 import `spatial`
包本身（空壳，符号按 PEP 562 延迟提供），不取用其中任何符号。
"""

from __future__ import annotations

from rschange.pipeline.change_detection import (
    DetectionOutcome,
    DetectionRequest,
    PreviewImage,
    detect_change,
)

__all__ = [
    "DetectionOutcome",
    "DetectionRequest",
    "PreviewImage",
    "detect_change",
]
