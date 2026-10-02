#!/usr/bin/env python
"""冻结 HTTP 接口契约的机器可读形态：`docs/api/openapi.json`。

为什么需要这个工具
------------------
`docs/contracts.md` §9 是**人读**的契约，`api/schemas/detection.py` 是**运行期**
的实现，二者之间没有任何机械约束：改了一个字段而忘了改另一个（或忘了改前端类型），
在运行期不会报错，只会让前端在某次请求后拿到一个它不认识的响应。

本脚本把契约固化成一份可 diff 的产物，使「契约变了但没人同步」这件事变成一次
**可见的文本差异**。它是 Phase 5 出口门 G5.2 的载体：故意改一个响应字段而不重新
生成，`--check` 必须变红；不红就说明契约未真正生效。

产物与机器本地配置无关
----------------------
生成过程显式注入桩检测器与桩后处理器，**不执行任何算法**；文档内容只由路由签名
与 pydantic 模型决定。因此产物与 `config/local.toml`、`RSCHANGE_*` 环境变量、
`_spatial` 扩展是否可用均无关，可在任意机器上逐字节复现。

输出确定性
----------
`sort_keys=True`、`indent=2`、`ensure_ascii=False`，换行固定为 LF，且以换行结尾。
键序在 JSON 中无语义，固定它只为让「重新生成 = 零 diff」成为一个可靠判据；
换行固定为 LF 则使同一份代码在 Windows 与 Linux 上产出的文件**逐字节相同**——
`--check` 比对的是字节而不是文本，因此 Windows 的换行翻译无法把漂移藏起来。

用法
----
    uv run python scripts/gen_openapi.py            # 生成/覆盖入库产物
    uv run python scripts/gen_openapi.py --check    # 只校验，不写入（漂移检测）

退出码：0 = 通过；1 = `--check` 发现漂移，或产物缺失。
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    from rschange.api.deps import RuntimeContext
    from rschange.detectors.base import DetectionResult

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
OUTPUT: Final[Path] = REPO_ROOT / "docs" / "api" / "openapi.json"

#: 差异输出上限。漂移往往只是几行，但字段重排会放大成全文件差异，
#: 全部打印只会把关键信息挤出屏幕。
_MAX_DIFF_LINES: Final[int] = 60

_INDENT: Final[int] = 2

#: 产物换行符，显式固定为 LF。`Path.write_text()` 默认会把 `\n` 翻译成平台换行符，
#: 在 Windows 上生成 CRLF 文件：同一份代码产出的字节因平台而异，与本文档「跨平台
#: 逐字节复现」的声明矛盾，sha256 也因此不能作为判据。写盘时显式指定即可消除。
_NEWLINE: Final[str] = "\n"


class _SchemaOnlyDetector:
    """只为产出契约文档而存在的检测器桩。

    生成 OpenAPI 不需要任何算法——文档由路由签名与 pydantic 模型决定。用一个
    一旦被调用就报错的桩，好过接上真实 CVA：后者会把「生成契约」与 numpy 计算
    绑在一起，而这个脚本的价值恰恰在于不依赖那些东西就能复现契约。
    """

    name = "schema-only"

    def detect(self, before: NDArray[np.uint16], after: NDArray[np.uint16]) -> DetectionResult:
        del before, after
        raise NotImplementedError("生成契约文档不应执行检测")


class _SchemaOnlyPostprocessor:
    """同上的后处理器桩。"""

    name = "schema-only"

    def apply(self, mask: NDArray[np.bool_]) -> NDArray[np.bool_]:
        del mask
        raise NotImplementedError("生成契约文档不应执行后处理")


def _schema_only_context() -> RuntimeContext:
    """构造注入桩实现的运行时上下文。

    只用 `Settings()` 的默认装载链（`config/default.toml` → `config/local.toml`
    → 环境变量）：CORS 白名单等字段会被读取，但它们**不出现在** OpenAPI 文档里，
    故不破坏产物的可复现性。
    """
    from rschange.api.deps import RuntimeContext as Context
    from rschange.config import Settings

    return Context(
        settings=Settings(),
        detector=_SchemaOnlyDetector(),
        postprocessor=_SchemaOnlyPostprocessor(),
    )


def render() -> str:
    """产出契约文档的规范文本形态。"""
    from rschange.api.app import create_app

    document: dict[str, Any] = create_app(context=_schema_only_context()).openapi()
    return json.dumps(document, ensure_ascii=False, indent=_INDENT, sort_keys=True) + "\n"


def _unified_diff(expected: str, actual: str) -> str:
    lines = list(
        difflib.unified_diff(
            actual.splitlines(keepends=True),
            expected.splitlines(keepends=True),
            fromfile="docs/api/openapi.json（入库）",
            tofile="重新生成（当前代码）",
            n=2,
        )
    )
    if len(lines) > _MAX_DIFF_LINES:
        omitted = len(lines) - _MAX_DIFF_LINES
        lines = lines[:_MAX_DIFF_LINES]
        lines.append(f"...（另有 {omitted} 行差异未显示）\n")
    return "".join(lines)


def check() -> int:
    """比对**字节**而非文本。

    `read_text()` 会做通用换行翻译（CRLF → LF），若用它比对，一份被 Windows 工具
    写成 CRLF 的产物会被判为「与代码一致」——漂移被悄悄藏起来。本判据的全部价值
    在于「不一样就说不一样」，故下沉到字节层。
    """
    expected = render().encode("utf-8")

    if not OUTPUT.is_file():
        print(f"[FAIL] 契约产物不存在：{OUTPUT}")
        print("       修复：uv run python scripts/gen_openapi.py")
        return 1

    actual = OUTPUT.read_bytes()
    if actual == expected:
        print(f"[PASS] 契约产物与当前代码一致：{OUTPUT.relative_to(REPO_ROOT).as_posix()}")
        return 0

    print("[FAIL] 契约漂移：后端定义与入库的契约产物不一致")
    print("       这意味着契约变了但没有人重新生成产物——前端类型也会因此过时。")
    if b"\r\n" in actual and b"\r\n" not in expected:
        print()
        print("       提示：产物含 CRLF 换行。写盘固定用 LF，出现 CRLF 说明该文件是被")
        print("       别的工具写过的（旧版生成器、Windows 编辑器），应重新生成。")
    print()
    print(_unified_diff(expected.decode("utf-8"), actual.decode("utf-8")), end="")
    print()
    print("       修复：uv run python scripts/gen_openapi.py（并同步前端类型）")
    return 1


def generate() -> int:
    text = render()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8", newline=_NEWLINE)
    print(
        f"[OK] 已写入 {OUTPUT.relative_to(REPO_ROOT).as_posix()}"
        f"（{len(text.encode('utf-8'))} 字节 / {len(text)} 字符）"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="冻结/校验 HTTP 接口契约文档")
    parser.add_argument(
        "--check",
        action="store_true",
        help="只校验入库产物是否与当前代码一致，不写入（漂移检测，G5.2 载体）",
    )
    arguments = parser.parse_args()

    return check() if arguments.check else generate()


if __name__ == "__main__":
    sys.exit(main())
