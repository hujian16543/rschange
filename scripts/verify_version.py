#!/usr/bin/env python
"""版本号一致性校验：多个声明点必须同号。

为什么需要这个工具
------------------
版本号在本仓库里出现在四处，且**曾经互不相同**：`backend/pyproject.toml` 写
`0.3.0`、工作区根 `pyproject.toml` 写 `0.1.0`、`frontend/package.json` 写
`0.4.0`，而仓库实际已到 `v0.4.0`。三处同时错，没有任何现有门禁会报错。

后果不是「显示不美观」：`rschange.__version__` 经 `api/app.py` 的
`FastAPI(version=...)` 写进 OpenAPI 文档，再由 T5.1 冻结为
`docs/api/openapi.json` —— 一个错误的版本号就此成为**契约产物的一部分**，
并被 T5.2 的类型生成链路带给前端。

人工核对挡不住这类漂移：四处分属不同技术栈（Python 打包、npm、工作区根），
任一处单独改动都不会触发任何检查。

判据
----
    1  rschange.__version__（取自已安装发行版元数据） == backend/pyproject.toml
    2  frontend/package.json 的 version                == 真相源
    3  工作区根 pyproject.toml 的 version               == 真相源
    4  真相源形如 X.Y.Z（版本号可被各方一致解析）
    5  docs/api/openapi.json 的 info.version           == 真相源（文件存在时）

第 1 项同时充当「元数据是否已随源码刷新」的判据：`uv` 在安装期把版本写进
`dist-info/METADATA`，改完 `backend/pyproject.toml` 而未执行
`uv sync --all-packages` 时，元数据仍是旧值，本项会 FAIL——这正是要拦住的
情形，因为下游的 OpenAPI 会带着旧版本号被生成出来。

用法
----
    uv run python scripts/verify_version.py
    uv run python scripts/verify_version.py --verbose

退出码：0 = 全部通过；1 = 存在不通过项。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any, Final

import rschange
from engine_env import REPO_ROOT
from verify_config import Check, pad

#: 真相源所在文件。改版本号只改这一处。
SOURCE_OF_TRUTH: Final[Path] = REPO_ROOT / "backend" / "pyproject.toml"

#: 其余必须与真相源同号的声明点：`(组号, 说明, 文件路径)`。
#:
#: 元组顺序即解包顺序，注解必须与磁盘上的元素顺序一致——曾把注解写成
#: `(str, Path, str)`，运行期因解包顺序恰好正确而无症状，只有类型检查能发现。
PEER_FILES: Final[tuple[tuple[str, str, Path], ...]] = (
    ("2", "frontend/package.json", REPO_ROOT / "frontend" / "package.json"),
    ("3", "工作区根 pyproject.toml", REPO_ROOT / "pyproject.toml"),
)

#: 契约产物。其 `info.version` 由 `rschange.__version__` 决定。
OPENAPI_FILE: Final[Path] = REPO_ROOT / "docs" / "api" / "openapi.json"

#: 版本号格式。本项目的版本号与阶段号绑定（Phase 1–6 → `0.N.0`；Phase 7 收口 → `1.0.0`），三段式。
VERSION_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d+\.\d+\.\d+$")


def read_toml_version(path: Path, *, workspace_root: bool = False) -> str:
    """取出 `[project].version`。

    `workspace_root` 仅用于错误信息——工作区根与成员包同用一个键名，区分二者
    只是为了让 FAIL 行能指出到底是谁写错了。
    """
    if not path.is_file():
        return "(文件不存在)"
    with path.open("rb") as handle:
        document: dict[str, Any] = tomllib.load(handle)
    value = document.get("project", {}).get("version")
    if value is None:
        return "(未声明 version)"
    del workspace_root  # 键名相同，无需分支处理；形参保留以便调用处自述意图
    return str(value)


def read_package_json_version(path: Path) -> str:
    if not path.is_file():
        return "(文件不存在)"
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    value = document.get("version")
    return "(未声明 version)" if value is None else str(value)


def read_runtime_version() -> str:
    """读 `rschange.__version__`（取自已安装发行版的元数据）。"""
    return rschange.__version__


def read_openapi_version(path: Path) -> str | None:
    """读 `docs/api/openapi.json` 的 `info.version`。文件不存在时返回 None。"""
    if not path.is_file():
        return None
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    value = document.get("info", {}).get("version")
    return None if value is None else str(value)


def collect_checks() -> list[Check]:
    checks: list[Check] = []

    truth = read_toml_version(SOURCE_OF_TRUTH)

    # 1 —— 运行时元数据与真相源一致
    runtime = read_runtime_version()
    checks.append(
        Check(
            "1",
            "rschange.__version__ == backend/pyproject.toml",
            truth,
            runtime,
            runtime == truth,
            note="不一致说明改完 pyproject 未执行 uv sync --all-packages",
        )
    )

    # 2、3 —— 其余声明点与真相源一致
    for group, label, path in PEER_FILES:
        if path.name == "package.json":
            actual = read_package_json_version(path)
        else:
            actual = read_toml_version(path, workspace_root=True)
        checks.append(Check(group, f"{label} version == 真相源", truth, actual, actual == truth))

    # 4 —— 版本号本身可解析
    checks.append(
        Check(
            "4",
            "真相源版本号形如 X.Y.Z",
            "N.N.N",
            truth,
            bool(VERSION_PATTERN.match(truth)),
            note="与阶段号绑定：Phase 1–6 出 v0.N.0；Phase 7 收口出 v1.0.0",
        )
    )

    # 5 —— 契约产物里的版本号与真相源一致
    openapi_version = read_openapi_version(OPENAPI_FILE)
    if openapi_version is None:
        checks.append(
            Check(
                "5",
                "openapi.json info.version == 真相源",
                "—",
                "—",
                True,
                skipped=True,
                note="docs/api/openapi.json 尚未生成（T5.1 之前）",
            )
        )
    else:
        checks.append(
            Check(
                "5",
                "openapi.json info.version == 真相源",
                truth,
                openapi_version,
                openapi_version == truth,
                note="该值经 app.py 的 FastAPI(version=...) 冻入契约产物",
            )
        )

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="版本号一致性校验")
    parser.add_argument("--verbose", action="store_true", help="打印附加信息")
    arguments = parser.parse_args()

    print("版本号一致性校验：backend/pyproject.toml（真相源）· 运行时元数据 · 前端 · 工作区根")
    print("=" * 112)

    checks = collect_checks()

    print(
        pad("组", 5)
        + pad("判定项", 46)
        + pad("期望", 18)
        + pad("实际", 18)
        + pad("结果", 7)
        + "备注"
    )
    print("-" * 112)

    for check in checks:
        result = "SKIP" if check.skipped else ("PASS" if check.passed else "FAIL")
        print(
            pad(check.group, 5)
            + pad(check.name, 46)
            + pad(check.expected, 18)
            + pad(check.actual, 18)
            + pad(result, 7)
            + check.note
        )

    print("-" * 112)

    active = [check for check in checks if not check.skipped]
    failed = [check for check in active if not check.passed]
    print(
        f"判定项 {len(active)} 项（跳过 {len(checks) - len(active)} 项），不通过 {len(failed)} 项"
    )

    if arguments.verbose:
        print(f"\n仓库根：{REPO_ROOT}")
        print(f"真相源：{SOURCE_OF_TRUTH}")

    if failed:
        print("结论：不通过 —— 版本号存在漂移，契约产物会带上错误的版本号")
        return 1

    print("结论：通过 —— 全部声明点同号且与契约产物一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
