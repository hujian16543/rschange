"""契约漂移：入库的 OpenAPI 产物必须与当前后端定义一致。

这道判据的意义
--------------
`docs/contracts.md` §9 是人读的契约，`api/schemas/detection.py` 是运行期实现，
二者之间没有机械约束。`docs/api/openapi.json` 是二者的机器可读交集，本模块守护
它**不落后于代码**。

它与 `scripts/gen_openapi.py --check` 是同一判据的两处入口，刻意如此：
`--check` 供人在交付前手动执行，本模块让它在 `pytest` 中**自动**执行。只有前者时，
「忘了跑」就等于没有门禁；只有后者时，交付前无法单独确认。

实现上以子进程调用脚本而非导入它，理由同样是判据完整性：被判定的应当是
**文档里写的那条命令**及其退出码，而不是某个内部函数的返回值。
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

#: 契约产物的仓库相对路径。
OPENAPI_REL = "docs/api/openapi.json"

#: 子进程的 stdio 编码，显式固定为 UTF-8。
#:
#: 脚本以中文输出，而 Windows 上子进程的 stdio 编码取自进程 locale：GitHub 托管
#: runner 是 `en-US`（ANSI 代码页 1252），stdout 为管道时 `print()` 一遇中文即报
#: `UnicodeEncodeError`，退出码变成 1——一条**编码崩溃**会被误读成「契约漂移」。
#: 本机是中文 Windows（ACP=936），能表示中文，故此缺陷只在 CI 上暴露。
#:
#: 因此不依赖环境 locale：子进程经 `PYTHONUTF8=1` 开 PEP 540 UTF-8 模式，父进程
#: 按同一编码解码。`errors="replace"` 是兜底——即便将来某个子进程输出非 UTF-8
#: 字节，也只降级为替换字符，不会把一条通过的判据变成解码异常。
_STDIO_ENCODING = "utf-8"


def _child_env() -> dict[str, str]:
    """子进程环境：在继承当前环境的基础上强制 UTF-8 stdio。

    `PYTHONIOENCODING` 被**移除**而非保留：它的优先级高于 UTF-8 模式，若父进程
    或开发者 shell 设过它，子进程的 stdio 编码会被改回去，本判据随即重新变成
    「结果取决于环境」。判据的可复现性由本函数独占决定。
    """
    env = {key: value for key, value in os.environ.items() if key != "PYTHONIOENCODING"}
    env["PYTHONUTF8"] = "1"
    return env


def test_openapi_artifact_matches_backend(repo_root: Path) -> None:
    """重新生成并与入库产物逐字节比对。"""
    script = repo_root / "scripts" / "gen_openapi.py"

    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding=_STDIO_ENCODING,
        errors="replace",
        env=_child_env(),
        check=False,
    )

    assert result.returncode == 0, (
        f"契约漂移：{OPENAPI_REL} 与后端定义不一致。\n"
        "含义：后端响应字段/类型变了，但契约产物没有重新生成，前端类型因此也是过时的。\n"
        "修复：uv run python scripts/gen_openapi.py && bash scripts/gen-api-types.sh\n\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )


def test_openapi_artifact_is_committed(repo_root: Path) -> None:
    """产物必须存在且非空。

    单独成一条而非并入上一条：上一条在产物**缺失**时也会失败，但失败信息指向
    「不一致」，掩盖了真实原因（文件根本不存在）。分开后「缺文件」有专属判据。
    """
    artifact = repo_root / OPENAPI_REL

    assert artifact.is_file(), (
        f"契约产物不存在：{OPENAPI_REL}\n修复：uv run python scripts/gen_openapi.py"
    )
    assert artifact.stat().st_size > 0, f"契约产物为空：{OPENAPI_REL}"
