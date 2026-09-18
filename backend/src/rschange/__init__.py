"""rschange · 遥感变化检测后端。

Phase 1 仅建立包骨架：本模块存在的目的，是让 hatchling 能把
`backend/src/rschange` 识别为可安装包，从而使 uv workspace 的
`uv sync --all-packages` 能解析成员依赖并落盘 uv.lock。

分层实现自 Phase 3 起逐层迁入（见《迁移映射与阶段拆解》）。
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
