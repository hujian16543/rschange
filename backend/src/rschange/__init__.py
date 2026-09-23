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

__all__ = ["__version__"]

__version__ = "0.3.0"
