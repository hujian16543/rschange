#!/usr/bin/env python
"""配置一致性校验：分层配置、CMake 预设、本机模板三者必须互相对得上。

为什么需要这个工具
------------------
Phase 2 曾出现一处只有人眼能发现的不一致：`config/local.example.toml` 给出的
示例值写的是 `./engine/build`，而 `config/default.toml` 与 CMake 预设实际指向
`./engine/build/dev-win`。模板是 bootstrap 第 6 步复制生成 `config/local.toml`
的来源，照抄即得一份**错误配置**——症状是 `import _spatial` 失败，但报错信息
指向「模块不存在」，与真正的原因（路径写错）相距很远。

人工核对挡不住这类漂移：默认值、预设、模板分属三个文件，任一处单独改动都
不会触发任何现有门禁。本工具把三者的一致性变成可判定的条目。

判据
----
    1  default.toml 的 engine.build_dir        == 预设 dev-win    的 binaryDir
    2  local.toml   的 engine.build_dir        == 预设 local-win  的 binaryDir（文件存在时）
    3  local.example.toml 给出的 build_dir 示例 == default.toml 的取值
    4  local.example.toml 给出的 fixtures_dir 示例 == default.toml 的取值
    5  default.toml 的 legacy_build_dir / legacy_fixtures_dir 均为空（Phase 2 起）
    6  Windows 上 local.toml 的 engine.runtime_dll_dir 非空（文件存在时）

第 3、4 项是「照抄模板可跑通」的直接判据；第 2、6 项是本机可用性的判据。

用法
----
    uv run python scripts/verify_config.py
    uv run python scripts/verify_config.py --verbose

退出码：0 = 全部通过；1 = 存在不通过项。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
CONFIG_DIR: Final[Path] = REPO_ROOT / "config"
ENGINE_DIR: Final[Path] = REPO_ROOT / "engine"

# 预设文件里 CMake 变量到路径的展开规则。预设文件位于 engine/，故
# `${sourceDir}` 即 engine 目录；展开后统一改写为相对仓库根的形式。
CMAKE_VARIABLES: Final[dict[str, str]] = {"${sourceDir}": "engine"}


@dataclass
class Check:
    group: str
    name: str
    expected: str
    actual: str
    passed: bool
    note: str = ""
    skipped: bool = False


def display_width(text: str) -> int:
    """文本在等宽字体下的显示宽度（中日韩字符占两列）。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def pad(text: str, width: int) -> str:
    """按**显示宽度**补齐到 width 列，并额外留一列间隔。

    按字符数 (f"{text:<n}") 补齐在含中日韩字符时会错位——它们占两列。
    内容超出 width 时截断并加省略号，保证后续列不错位。
    """
    shown = display_width(text)
    if shown <= width:
        return text + " " * (width - shown + 1)

    kept: list[str] = []
    used = 0
    for character in text:
        step = 2 if unicodedata.east_asian_width(character) in "WF" else 1
        if used + step > width - 1:
            break
        kept.append(character)
        used += step
    return "".join(kept) + "…" + " " * max(0, width - used)


def load_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def normalize_repo_path(raw: str) -> str:
    """把绝对路径或相对路径统一成「相对仓库根、以 ./ 开头」的写法。"""
    text = raw.strip()
    if not text:
        return ""
    candidate = Path(text)
    if candidate.is_absolute():
        try:
            return "./" + candidate.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            return candidate.as_posix()
    return "./" + text.lstrip("./") if not text.startswith("./") else text


def comment_example(path: Path, key: str) -> str | None:
    """从模板文件的注释行里取出示例值：`# key = "value"`。"""
    if not path.is_file():
        return None
    pattern = re.compile(rf'^\s*#\s*{re.escape(key)}\s*=\s*"([^"]*)"', re.MULTILINE)
    match = pattern.search(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def preset_binary_dir(preset_file: Path, preset_name: str) -> str | None:
    """解析某个 configure preset 最终生效的 binaryDir（含 inherits 链与变量展开）。"""
    if not preset_file.is_file():
        return None

    document = json.loads(preset_file.read_text(encoding="utf-8"))
    by_name = {
        preset["name"]: preset
        for preset in document.get("configurePresets", [])
        if isinstance(preset, dict) and "name" in preset
    }

    # 沿 inherits 链从具体到抽象走一遍，最具体处若定义了 binaryDir 即生效。
    chain: list[dict[str, Any]] = []
    current: str | None = preset_name
    while current and current in by_name:
        chain.append(by_name[current])
        parent = by_name[current].get("inherits")
        current = parent[0] if isinstance(parent, list) and parent else parent

    template = next((node["binaryDir"] for node in chain if "binaryDir" in node), None)
    if template is None:
        return None

    expanded = template.replace("${presetName}", preset_name)
    for variable, replacement in CMAKE_VARIABLES.items():
        expanded = expanded.replace(variable, replacement)
    return normalize_repo_path(expanded)


def engine_value(config: dict[str, Any], key: str, default: str = "") -> str:
    return str(config.get("engine", {}).get(key, default) or "")


def baseline_value(config: dict[str, Any], key: str) -> str:
    return str(config.get("baseline", {}).get(key, "") or "")


def collect_checks() -> list[Check]:
    checks: list[Check] = []

    default_toml = load_toml(CONFIG_DIR / "default.toml")
    local_toml = load_toml(CONFIG_DIR / "local.toml")
    presets = ENGINE_DIR / "CMakePresets.json"
    user_presets = ENGINE_DIR / "CMakeUserPresets.json"
    example = CONFIG_DIR / "local.example.toml"

    default_build_dir = normalize_repo_path(engine_value(default_toml, "build_dir"))
    default_fixtures = normalize_repo_path(baseline_value(default_toml, "fixtures_dir"))

    # 1 —— 入库默认值与入库预设一致
    expected = preset_binary_dir(presets, "dev-win") or "(预设未定义)"
    checks.append(
        Check(
            "1",
            "default.toml build_dir == 预设 dev-win",
            expected,
            default_build_dir,
            expected == default_build_dir,
            note="presets 的 base 用 `${sourceDir}/build/${presetName}` 推导",
        )
    )

    # 2 —— 本机配置与本机预设一致（文件不存在时跳过）
    local_build_dir = normalize_repo_path(engine_value(local_toml, "build_dir"))
    local_preset_dir = preset_binary_dir(user_presets, "local-win")
    if not local_toml:
        checks.append(
            Check(
                "2",
                "local.toml build_dir == 预设 local-win",
                "—",
                "—",
                True,
                skipped=True,
                note="config/local.toml 不存在（未执行 bootstrap）",
            )
        )
    elif local_preset_dir is None:
        checks.append(
            Check(
                "2",
                "local.toml build_dir == 预设 local-win",
                "—",
                str(local_build_dir),
                True,
                skipped=True,
                note="engine/CMakeUserPresets.json 无 local-win 预设，无法对照",
            )
        )
    else:
        # 本机 local.toml 允许省略 build_dir（回落到 default.toml 的值）
        effective = local_build_dir or default_build_dir
        checks.append(
            Check(
                "2",
                "local.toml build_dir == 预设 local-win",
                local_preset_dir,
                effective,
                local_preset_dir == effective,
                note="本机预设的 binaryDir 必须与实际产物目录相同",
            )
        )

    # 3 —— 模板给出的 build_dir 示例照抄即正确
    example_build_dir = comment_example(example, "build_dir")
    checks.append(
        Check(
            "3",
            "模板 build_dir 示例 == default.toml",
            default_build_dir,
            normalize_repo_path(example_build_dir) if example_build_dir else "(模板未给示例)",
            normalize_repo_path(example_build_dir or "") == default_build_dir,
            note="bootstrap 第 6 步直接复制模板；示例值错即产出错误配置",
        )
    )

    # 4 —— 模板给出的 fixtures_dir 示例同理
    example_fixtures = comment_example(example, "fixtures_dir")
    checks.append(
        Check(
            "4",
            "模板 fixtures_dir 示例 == default.toml",
            default_fixtures,
            normalize_repo_path(example_fixtures) if example_fixtures else "(模板未给示例)",
            normalize_repo_path(example_fixtures or "") == default_fixtures,
            note="同上",
        )
    )

    # 5 —— Phase 2 起 legacy_* 必须为空
    legacy = {
        "legacy_build_dir": baseline_value(default_toml, "legacy_build_dir"),
        "legacy_fixtures_dir": baseline_value(default_toml, "legacy_fixtures_dir"),
    }
    offenders = {key: value for key, value in legacy.items() if value}
    checks.append(
        Check(
            "5",
            "default.toml legacy_* 均为空",
            "两项均空",
            "两项均空" if not offenders else str(offenders),
            not offenders,
            note="仅 Phase 1 使用；Phase 2 完成引擎搬迁后必须清空",
        )
    )

    # 6 —— Windows 上 runtime_dll_dir 必填
    dll_dir = engine_value(local_toml, "runtime_dll_dir")
    if sys.platform != "win32":
        checks.append(
            Check(
                "6",
                "local.toml runtime_dll_dir 非空",
                "—",
                "—",
                True,
                skipped=True,
                note="非 Windows 平台留空，由动态链接器提供",
            )
        )
    elif not local_toml:
        checks.append(
            Check(
                "6",
                "local.toml runtime_dll_dir 非空",
                "—",
                "—",
                True,
                skipped=True,
                note="config/local.toml 不存在（未执行 bootstrap）",
            )
        )
    else:
        checks.append(
            Check(
                "6",
                "local.toml runtime_dll_dir 非空",
                "非空绝对路径",
                dll_dir or "(空)",
                bool(dll_dir),
                note="空则 import _spatial 找不到 libgdal-*.dll",
            )
        )

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="配置一致性校验")
    parser.add_argument("--verbose", action="store_true", help="打印附加信息")
    arguments = parser.parse_args()

    print("配置一致性校验：config/default.toml · config/local.example.toml · CMake 预设")
    print("=" * 112)

    checks = collect_checks()

    print(
        pad("组", 5)
        + pad("判定项", 44)
        + pad("期望", 32)
        + pad("实际", 32)
        + pad("结果", 7)
        + "备注"
    )
    print("-" * 112)

    for check in checks:
        result = "SKIP" if check.skipped else ("PASS" if check.passed else "FAIL")
        print(
            pad(check.group, 5)
            + pad(check.name, 44)
            + pad(check.expected, 32)
            + pad(check.actual, 32)
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
        print(f"预设文件：{ENGINE_DIR / 'CMakePresets.json'}")
        print(f"本机预设：{ENGINE_DIR / 'CMakeUserPresets.json'}")

    if failed:
        print("结论：不通过 —— 配置之间存在不一致，照抄模板可能产出不可用配置")
        return 1

    print("结论：通过 —— 分层配置、CMake 预设与本机模板互相一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
