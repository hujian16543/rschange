"""架构约束。

本模块守护的是**结构性质**，不是行为：分层方向、可插拔（G3.4）、
backend 内不得出现机器本地路径（G3.5）。它们不会因为某个函数改错而失败，
但会在一层层「顺手 import 一下」的累积中被悄悄破坏——而那时再发现，代价是
重新理清依赖图。
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
import sys
from typing import TYPE_CHECKING

import numpy as np
import pytest

from rschange.detectors import registry
from rschange.detectors.base import DetectionResult

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from numpy.typing import NDArray

    from rschange.api.deps import RuntimeContext

#: G3.5 的判据字面串，由两段拼出。
#:
#: 判据是「backend/ 内不得出现该串」，而本文件位于 backend/ 之内：直接写出它，
#: 判据就会判自己失败。T3.2 已在 `spatial/__init__.py` 的 docstring 上踩过同一个
#: 坑，此处显式规避。
_MSYS_TOKEN = "msys" + "64"

#: 机器本地绝对路径的另一半：家目录形式。
_WINDOWS_HOME_TOKEN = "C:" + "/Users"

_SCANNED_SUFFIXES = frozenset({".py", ".toml", ".cfg", ".ini", ".json", ".yaml", ".yml"})


def _backend_files(repo_root: Path) -> list[Path]:
    backend = repo_root / "backend"
    return sorted(
        path for path in backend.rglob("*") if path.is_file() and path.suffix in _SCANNED_SUFFIXES
    )


def test_backend_has_no_machine_local_paths(repo_root: Path) -> None:
    """G3.5：`backend/` 内不得出现 MSYS2 安装目录或家目录绝对路径。

    D-5 的收敛目标：全项目只有 `spatial/loader.py` 解析原生依赖路径，且该路径
    来自配置。旧实现把同一段逻辑复制了四份并各自硬编码。
    """
    offenders: dict[str, list[str]] = {}
    for path in _backend_files(repo_root):
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = [token for token in (_MSYS_TOKEN, _WINDOWS_HOME_TOKEN) if token in text]
        if hits:
            offenders[str(path.relative_to(repo_root))] = hits

    assert offenders == {}, f"发现机器本地路径：{offenders}"


def test_pipeline_import_does_not_load_engine_or_algorithms(repo_root: Path) -> None:
    """G3.4 的结构前提：`import rschange.pipeline` 不拉入引擎，也不拉入任何算法实现。

    在独立进程里验证——本进程早已 import 过这些模块，`sys.modules` 的现状说明
    不了「导入 pipeline 本身会做什么」。
    """
    probe = (
        "import sys, rschange.pipeline;"
        "print('_spatial' in sys.modules,"
        " 'rschange.detectors' in sys.modules,"
        " 'rschange.postprocess' in sys.modules)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(repo_root),
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "False False False", completed.stderr


def _module_level_imports(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def _type_checking_imports(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        is_guard = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )
        if not is_guard:
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.ImportFrom) and child.module:
                found.add(child.module)
            elif isinstance(child, ast.Import):
                found.update(alias.name for alias in child.names)
    return found


def test_pipeline_imports_algorithms_only_for_typing(repo_root: Path) -> None:
    """算法与后处理器的协议只在 `TYPE_CHECKING` 下导入，运行期依赖为零。

    这是「依赖注入是结构性的」这一说法的**可执行**版本：如果哪天有人在模块顶层
    写一句 `from rschange.detectors import registry` 来取默认算法，本用例失败。
    """
    path = repo_root / "backend" / "src" / "rschange" / "pipeline" / "change_detection.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    module_level = _module_level_imports(tree)
    guarded = _type_checking_imports(tree)

    for target in ("rschange.detectors.base", "rschange.postprocess.base"):
        assert target in guarded, f"{target} 应写在 TYPE_CHECKING 之下"
        assert target not in module_level, f"{target} 不得在运行期导入"


def test_lower_layers_do_not_import_upper_layers(repo_root: Path) -> None:
    """分层方向：只允许上层导入下层。

    `config` / `logging` / `errors` 是叶层，`spatial` 只依赖它们；`detectors`、
    `postprocess`、`io` 更在其上；`api` 最外。
    """
    root = repo_root / "backend" / "src" / "rschange"
    forbidden = ("rschange.api", "rschange.pipeline")

    offenders: dict[str, list[str]] = {}
    for layer in (
        "config.py",
        "logging.py",
        "errors.py",
        "spatial",
        "io",
        "postprocess",
        "detectors",
    ):
        target = root / layer
        paths = [target] if target.is_file() else sorted(target.rglob("*.py"))
        for path in paths:
            imported = _imported_rschange_modules(path)
            bad = sorted(
                name
                for name in imported
                if any(name == prefix or name.startswith(f"{prefix}.") for prefix in forbidden)
            )
            if bad:
                offenders[str(path.relative_to(repo_root))] = bad

    assert offenders == {}, f"下层反向导入了上层：{offenders}"


def _imported_rschange_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("rschange"):
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if alias.name.startswith("rschange"))
    return found


def test_leaf_modules_depend_only_on_each_other(repo_root: Path) -> None:
    """叶层之间可以互相依赖，但不得依赖任何更高层。

    `config` 反向导入 `postprocess` 这类写法会让「配置」变成有算法知识的模块，
    进而在测试里连带拉起 numpy 与引擎。
    """
    root = repo_root / "backend" / "src" / "rschange"
    allowed = {"rschange.config", "rschange.logging", "rschange.errors"}

    for name in ("config.py", "logging.py", "errors.py"):
        imported = _imported_rschange_modules(root / name)
        assert imported <= allowed, f"{name} 依赖了非叶层模块：{sorted(imported - allowed)}"


def test_detector_contract_has_no_concrete_dependencies(repo_root: Path) -> None:
    """协议模块不得依赖任何具体实现（那会让新算法不得不先 import 旧算法）。"""
    path = repo_root / "backend" / "src" / "rschange" / "detectors" / "base.py"
    assert _imported_rschange_modules(path) == set()


class _MedianDiffDetector:
    """一个「新算法」：逐像元中位数差超过 50 即判变化。

    它只存在于测试进程里——不新增文件、不改动 `pipeline/`。这正是 G3.4 想要证明
    的性质：新增算法是**注册**动作，不是**修改编排**动作。
    """

    name = "median-diff"

    def detect(self, before: NDArray[np.uint16], after: NDArray[np.uint16]) -> DetectionResult:
        delta = np.abs(after.astype(np.int32) - before.astype(np.int32))
        return DetectionResult(mask=delta.max(axis=0) > 50, threshold=50.0)


@pytest.fixture
def restores_registry() -> Iterator[None]:
    snapshot = dict(registry._REGISTRY)
    try:
        yield
    finally:
        registry._REGISTRY.clear()
        registry._REGISTRY.update(snapshot)


@pytest.mark.usefixtures("engine_ready", "restores_registry")
def test_new_detector_is_pluggable_without_pipeline_change(
    repo_root: Path,
    before_path: Path,
    after_path: Path,
    tmp_path: Path,
    context: RuntimeContext,
) -> None:
    """G3.4：注册一个新算法后，编排层无需任何改动即可使用它。"""
    from rschange.pipeline import DetectionRequest, detect_change

    pipeline_path = repo_root / "backend" / "src" / "rschange" / "pipeline" / "change_detection.py"
    digest_before = hashlib.sha256(pipeline_path.read_bytes()).hexdigest()

    registry.register(_MedianDiffDetector())

    request = DetectionRequest(
        job_id="pluggable",
        before_path=before_path,
        after_path=after_path,
        output_dir=tmp_path / "outputs",
    )
    outcome = detect_change(
        request,
        detector=registry.resolve("median-diff"),
        postprocessor=context.postprocessor,
        settings=context.settings,
    )

    assert outcome.detector == "median-diff"
    assert outcome.threshold == 50.0
    assert "median-diff" in registry.available()

    digest_after = hashlib.sha256(pipeline_path.read_bytes()).hexdigest()
    assert digest_before == digest_after, "新增算法不应改动编排层文件"
