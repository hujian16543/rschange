"""rschange · 遥感变化检测后端。

分层与依赖方向
--------------
下列分层自外向内排列，**只允许上层导入下层**；反向导入属结构缺陷：

    api/          HTTP 边界：路由、依赖注入、请求/响应 schema
    pipeline/     用例编排：串联各步骤，不含算法细节
    detectors/    变化检测算法（可插拔，见 detectors/registry.py）
    postprocess/  掩膜后处理（可插拔）
    io/           图像与矢量产物：预览图、重投影
    spatial/      对 C++ 扩展 `_spatial` 的唯一访问点
    config.py     分层配置：default.toml → local.toml → RSCHANGE_* 环境变量
    logging.py    结构化日志
    errors.py     领域异常

依据文档
--------
* 引擎接口契约：`docs/contracts.md`（冻结于 v0.2.1；backend 侧**禁止**改动其签名）
* 算法实现说明：`docs/algorithm.md`
* 分层与迁移依据：《迁移映射与阶段拆解》A.3
"""

from __future__ import annotations

import importlib.metadata

__all__ = ["__version__"]

#: 版本号。**唯一真相源**是 `backend/pyproject.toml` 的 `[project].version`。
#
# 不在此处写字面量：那会构造出第二个真相源，而两者漂移是**静默**的。旧实现正是
# 写字面量，结果停在 `0.3.0` 而仓库已到 `v0.4.0`；该数字还会经
# `api/app.py` 的 `FastAPI(version=...)` 冻入 `docs/api/openapi.json`，使一个
# 错误版本号成为契约产物的一部分。改为读已安装发行版的元数据后，漂移在物理上
# 不可能发生。
#
# 刻意**不**提供 `PackageNotFoundError` 兜底常量：兜底会把「未安装」这一环境
# 缺陷转换成又一个静默的错误版本号，正是本节要消除的东西。缺包时直接抛出，
# 修复动作是 `uv sync --all-packages`。
__version__ = importlib.metadata.version("rschange")
