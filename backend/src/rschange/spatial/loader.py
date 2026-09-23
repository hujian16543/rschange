"""`_spatial` 扩展的唯一加载点（附录 D-5）。

全项目只有本模块解析 DLL 路径并执行 `import _spatial`。旧实现把这段逻辑复制
了四份（`main.py`、`services/detection.py`、`tests/test_cva.py`、
`tests/test_bindings.py`），且各自硬编码 MSYS2 绝对路径。

判定依据：`grep -rn "msys64" backend/` 结果为空（阶段出口门 G3.5）。

`os.add_dll_directory` 的句柄必须持有
-------------------------------------
该函数返回一个对象，CPython 在它被回收时**会把对应目录从 DLL 搜索路径中摘除**。
丢弃返回值是一个静默失效的陷阱：表现为「有时能导入、有时找不到 DLL」，取决于
GC 时机与进程启动顺序。故句柄统一收集在模块级列表中，生命周期与进程一致。
"""

from __future__ import annotations

import functools
import os
import sys
from typing import Any, Final

from rschange.config import Settings, get_settings
from rschange.errors import ConfigError, EngineLoadError

__all__ = ["EXTENSION_NAME", "load_extension"]

#: Python 扩展模块名（见 `docs/contracts.md` §2）。
EXTENSION_NAME: Final[str] = "_spatial"

#: `os.add_dll_directory` 的返回句柄。丢弃即失效，见模块 docstring。
_DLL_HANDLES: Final[list[Any]] = []


def _missing_runtime_dir_error() -> ConfigError:
    return ConfigError(
        "Windows 下 engine.runtime_dll_dir 为必填项：GDAL 与 MinGW 运行时所在的目录。"
        "请在 config/local.toml 中填写（通常是 <msys2>/mingw64/bin）。",
        public_message="服务端配置错误：引擎运行时目录未设置",
    )


def _invalid_build_dir_error(build_dir: str) -> ConfigError:
    return ConfigError(
        f"engine.build_dir 不是有效目录：{build_dir}",
        public_message="服务端配置错误：引擎构建目录不存在",
    )


def _invalid_runtime_dir_error(dll_dir: str) -> ConfigError:
    return ConfigError(
        f"engine.runtime_dll_dir 不是有效目录：{dll_dir}",
        public_message="服务端配置错误：引擎运行时目录不存在",
    )


@functools.lru_cache(maxsize=1)
def _load_cached(build_dir: str, dll_dir: str, windows: bool) -> Any:
    """加载并缓存扩展模块。

    `lru_cache` 的键取字符串而非 `Path`，避免「同一目录的两种写法」被当成两个
    缓存条目。缓存使 `add_dll_directory` 只执行一次——它的效果是进程级的，
    重复调用只是徒增句柄。

    异常**不**被缓存（`lru_cache` 仅缓存正常返回），因此修好配置后可重试。
    """
    if windows:
        _DLL_HANDLES.append(os.add_dll_directory(dll_dir))
        _DLL_HANDLES.append(os.add_dll_directory(build_dir))

    if build_dir not in sys.path:
        sys.path.insert(0, build_dir)

    try:
        import _spatial  # type: ignore[import-not-found]
    except ImportError as exc:
        raise EngineLoadError(
            f"无法 import {EXTENSION_NAME}（搜索目录：{build_dir}）：{exc}",
            public_message="空间引擎不可用：扩展模块加载失败",
        ) from exc
    return _spatial


def load_extension(settings: Settings | None = None) -> Any:
    """按配置加载 `_spatial` 扩展，返回模块对象。

    参数 `settings` 为 `None` 时取进程级单例；测试可显式传入构造的 `Settings`。

    @throws ConfigError 构建目录不存在，或 Windows 上运行时目录未设置/不存在
    @throws EngineLoadError 扩展无法导入
    """
    resolved = settings if settings is not None else get_settings()

    build_dir = resolved.build_dir
    if not build_dir.is_dir():
        raise _invalid_build_dir_error(str(build_dir))

    windows = os.name == "nt"
    dll_dir = resolved.runtime_dll_dir
    if windows:
        if not resolved.engine.runtime_dll_dir.strip():
            raise _missing_runtime_dir_error()
        if not dll_dir.is_dir():
            raise _invalid_runtime_dir_error(str(dll_dir))

    return _load_cached(str(build_dir), str(dll_dir), windows)
