"""测试支撑。

`make_settings` 存在的唯一理由：`Settings(runtime={...})` 在 mypy 下是类型错误。

pydantic 提供 `dataclass_transform`，类型检查器据此把 `Settings(...)` 的每个字段
当成具名参数（`runtime: RuntimeSettings`），于是传原始 dict 会被判不兼容。运行期
pydantic 当然接受 dict（这正是它合并配置的方式），所以问题只在静态声明层面。

用一个 `**overrides: Any` 的窄口把它表达清楚，好过在每个用例里写
`# type: ignore[arg-type]`——后者会掩盖同一行上真正的问题，而且一旦签名变化就
无人知道这些 ignore 是否还有效。

不用 `Settings.model_validate({...})` 替代：那会**绕过** pydantic-settings 的来源
机制，`config/local.toml` 与 `RSCHANGE_*` 环境变量都不再被读取，于是
`engine.runtime_dll_dir` 为空、`_spatial` 装载失败——测试会以「引擎不可用」的
面貌失败，与真实原因相隔甚远。
"""

from __future__ import annotations

from typing import Any

from rschange.config import Settings

__all__ = ["make_settings"]


def make_settings(**overrides: Any) -> Settings:
    """构造 `Settings`，允许按原始 dict 覆盖任意分组。

    与 `Settings(...)` 语义一致：覆盖值优先于 `local.toml` 与 `default.toml`。
    """
    return Settings(**overrides)
