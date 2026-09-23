"""HTTP 边界层。

职责：路由声明、请求解析、依赖注入、响应序列化。
禁止：业务编排（属 `pipeline`）、算法细节（属 `detectors` / `postprocess`）、
直接接触 `_spatial`（属 `spatial`）。

应用实例由 `api/app.py` 的 `create_app()` 工厂产出，而非模块级单例——
测试因此可以注入替身依赖，无需启动真实引擎。
"""
