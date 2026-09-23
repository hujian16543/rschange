"""pytest 公共夹具。

约定
----
* 需要真实 `_spatial` 扩展的用例依赖 `engine_ready`；引擎不可用时**跳过**而不是
  报错——配置、schema、重投影的用例在引擎未构建的环境里也应当能跑。
* 配置一律用 `Settings(...)` 显式构造，指向 `tmp_path`。不要动 `config/local.toml`，
  也不要用 `get_settings()`：它是进程级单例，用例之间会互相污染。
* 应用实例一律经 `create_app(context=...)` 得到。`api.app` 没有模块级单例正是为了
  这一点。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi.testclient import TestClient

    from rschange.api.deps import RuntimeContext
    from rschange.config import Settings

#: 仓库根。tests → rschange → src → backend → 仓库根。
REPO_ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def fixtures_dir(repo_root: Path) -> Path:
    """黄金基线夹具目录（before.tif / after.tif）。"""
    return repo_root / "engine" / "tests" / "fixtures"


@pytest.fixture(scope="session")
def before_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "before.tif"


@pytest.fixture(scope="session")
def after_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "after.tif"


@pytest.fixture(scope="session")
def engine_ready() -> None:
    """确保 `_spatial` 可加载；不可用则跳过整个用例。"""
    from rschange.errors import RsChangeError
    from rschange.spatial import load_extension

    try:
        load_extension()
    except RsChangeError as exc:  # pragma: no cover - 取决于本机环境
        pytest.skip(f"空间引擎不可用：{exc}")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """指向临时目录的配置。

    只覆盖 `data_dir`：其余字段沿用 `config/default.toml` 与 `config/local.toml`，
    这样用例同时也在守护「入库默认值 + 本机覆盖值都可以被解析」这一事实。
    `runtime_dll_dir` 必须来自 `local.toml`，否则 `_spatial` 装载失败。
    """
    from rschange.tests.support import make_settings

    return make_settings(
        runtime={
            "data_dir": str(tmp_path / "data"),
            "allowed_origins": ["http://localhost:5173"],
        }
    )


@pytest.fixture
def context(settings: Settings) -> RuntimeContext:
    """默认装配（真实 CVA + Morphology）。不触发引擎加载。"""
    from rschange.api.deps import build_context

    return build_context(settings)


@pytest.fixture
def client(context: RuntimeContext) -> Iterator[TestClient]:
    """真实装配的测试客户端。lifespan 由 `with` 触发，故数据目录会被创建。"""
    from fastapi.testclient import TestClient

    from rschange.api.app import create_app

    with TestClient(create_app(context=context)) as test_client:
        yield test_client
