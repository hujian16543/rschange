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

import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

#: 契约产物的仓库相对路径。
OPENAPI_REL = "docs/api/openapi.json"


def test_openapi_artifact_matches_backend(repo_root: Path) -> None:
    """重新生成并与入库产物逐字节比对。"""
    script = repo_root / "scripts" / "gen_openapi.py"

    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        cwd=repo_root,
        capture_output=True,
        text=True,
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
