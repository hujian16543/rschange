#!/usr/bin/env python
"""引擎定位与环境装载（供 scripts/ 下的验证工具共用）。

职责
----
把「按分层配置找到 `_spatial` 扩展、并让它的原生依赖可被解析」这件事收敛到
一处。`verify_baseline.py`（黄金基线门）与 `verify_bindings.py`（绑定契约）
都用它，避免两份配置优先级语义各自漂移。

配置优先级
----------
    RSCHANGE_<SECTION>__<KEY>  >  config/local.toml  >  config/default.toml

相对路径一律按**仓库根**解析，因此脚本可在任意工作目录下执行。
"""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict[str, Any]:
    """合并 default.toml、local.toml 与环境变量覆盖。"""
    config: dict[str, Any] = {}
    for name in ("default.toml", "local.toml"):
        path = REPO_ROOT / "config" / name
        if path.is_file():
            with path.open("rb") as handle:
                config = _deep_merge(config, tomllib.load(handle))

    prefix = "RSCHANGE_"
    for env_key, raw in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        parts = env_key[len(prefix) :].split("__")
        if len(parts) != 2:
            continue
        section, key = parts[0].lower(), parts[1].lower()
        value: Any = raw
        lowered = raw.lower()
        if lowered in ("true", "false"):
            value = lowered == "true"
        else:
            try:
                value = int(raw)
            except ValueError:
                pass
        config.setdefault(section, {})[key] = value

    return config


def resolve_path(raw: str) -> Path:
    """相对路径按仓库根解析；空字符串返回仓库根。"""
    if not raw:
        return REPO_ROOT
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def load_spatial(config: dict[str, Any]) -> tuple[Any, Path]:
    """按配置定位并加载 `_spatial` 扩展。

    返回 (模块, 扩展所在目录)。Windows 下先把原生依赖目录登记进 DLL 搜索路径：
    GDAL 与 MinGW 运行时都在 MSYS2 的 bin 里，PE 加载器不会自己去那里找。
    """
    engine = config.get("engine", {})
    dll_dir = resolve_path(str(engine.get("runtime_dll_dir") or ""))
    build_dir = resolve_path(str(engine.get("build_dir") or ""))

    if not build_dir.is_dir():
        raise SystemExit(
            f"[配置错误] engine.build_dir 不存在：{build_dir}\n"
            f"  请检查 config/local.toml 与 engine/CMakePresets.json 是否一致。"
        )

    if os.name == "nt":
        if dll_dir.is_dir():
            os.add_dll_directory(str(dll_dir))
        else:
            print(f"[警告] engine.runtime_dll_dir 不是有效目录，已跳过：{dll_dir}")
        os.add_dll_directory(str(build_dir))

    if str(build_dir) not in sys.path:
        sys.path.insert(0, str(build_dir))

    try:
        import _spatial  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            f"[加载失败] 无法 import _spatial（目录：{build_dir}）\n  原因：{exc}"
        ) from exc

    return _spatial, build_dir


def load_engine() -> tuple[Any, Path, dict[str, Any]]:
    """一次取到 (扩展模块, 扩展目录, 配置)。"""
    config = load_config()
    spatial, build_dir = load_spatial(config)
    return spatial, build_dir, config


def fixtures_dir(config: dict[str, Any]) -> Path:
    """黄金基线夹具目录（baseline.fixtures_dir）。"""
    return resolve_path(str(config.get("baseline", {}).get("fixtures_dir") or ""))
