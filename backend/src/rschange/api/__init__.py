"""HTTP 边界层。

职责：路由声明、请求解析、依赖注入、响应序列化。
禁止：业务编排（属 `pipeline`）、算法细节（属 `detectors` / `postprocess`）、
直接接触 `_spatial`（属 `spatial`）。

应用实例由 `api/app.py` 的 `create_app()` 工厂产出，而非模块级单例——
测试因此可以注入替身依赖，无需启动真实引擎。

模块分工
--------
* `app.py` —— `create_app()` 工厂；CORS、路由挂载、lifespan
* `deps.py` —— 依赖装配点（`RuntimeContext` / `build_context` / `get_context`）；
  这是「协议」与「实现」唯一的接合处
* `errors.py` —— 全局异常处理器；「异常不外泄」（D7）只在这一处实现
* `routers/` —— 路由声明
* `schemas/` —— 请求与响应模型（跨阶段契约）

本包的 `__init__` **不**导入 `app.py`：那样会让 `import rschange.api` 连带装配
算法与引擎，破坏「按需加载」。
"""

from __future__ import annotations

__all__: list[str] = []
