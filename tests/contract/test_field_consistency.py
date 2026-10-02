"""三方字段一致性：pydantic 模型 · OpenAPI 产物 · 前端生成的 TypeScript 接口。

为什么需要这道判据
------------------
Phase 5 之后，同一个响应 schema 以三种形态存在：

    1. backend/src/rschange/api/schemas/detection.py   —— 运行期真相（pydantic）
    2. docs/api/openapi.json                           —— 冻结的机器可读契约
    3. frontend/src/api/generated/data-contracts.ts    —— 前端所见的类型

1 → 2 由 `gen_openapi.py` 保证，2 → 3 由 `gen-api-types.sh` 保证，两段各有一条
链路。但**没有人检查 1 与 3 是否仍然一致**：只要两段各自「看起来跑过」，中间任何
一步忘记执行，前端就会拿着过时的类型去解析真实响应。

`test_openapi_frozen.py` 只守住 1 → 2 这一段。本模块补上 1 ↔ 3 的**端到端**核对，
使「忘记重新生成前端类型」不再是一种静默失败。

解析方式
--------
不引入 TypeScript 解析器：生成文件的形态由生成器模板完全决定（两空格缩进、
`export interface X {` 起、单独一行的 `}` 止），逐行解析足够且不引入依赖。
若某天生成器换了模板，本模块会以「字段集为空」的形式立刻失败——这是可接受的
失败模式，比悄悄解析出错误结果好。
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import pytest

from rschange.api.schemas.detection import DetectionResponse, ErrorResponse

if TYPE_CHECKING:
    from pathlib import Path

#: 与 `scripts/gen-api-types.sh` 的产物路径一致。
GENERATED_TS_REL = "frontend/src/api/generated/data-contracts.ts"

#: 生成器中 `export interface X {` 那一行。
_INTERFACE_START = re.compile(r"^export interface (\w+) \{$")

#: 接口体内的一行字段：两空格缩进 + 字段名 + 可选的 `?` + 冒号。
_FIELD_LINE = re.compile(r"^ {2}(\w+)(\?)?:")

#: 本阶段的契约基线：成功响应的字段个数（v0.5.0 由 13 收缩为 12）。
EXPECTED_DETECTION_FIELD_COUNT = 12


def parse_generated_interfaces(path: Path) -> dict[str, dict[str, bool]]:
    """解析生成文件里的接口声明。

    @returns `{接口名: {字段名: 是否可选}}`
    """
    interfaces: dict[str, dict[str, bool]] = {}
    current: str | None = None

    for line in path.read_text(encoding="utf-8").splitlines():
        if current is None:
            match = _INTERFACE_START.match(line)
            if match is not None:
                current = match.group(1)
                interfaces[current] = {}
            continue

        if line == "}":
            current = None
            continue

        field = _FIELD_LINE.match(line)
        if field is not None:
            interfaces[current][field.group(1)] = field.group(2) == "?"

    return interfaces


@pytest.fixture(scope="module")
def openapi_schema(repo_root: Path) -> dict[str, object]:
    """冻结契约里 `#/components/schemas` 一节。"""
    document = json.loads((repo_root / "docs/api/openapi.json").read_text(encoding="utf-8"))
    schemas = document["components"]["schemas"]
    assert isinstance(schemas, dict)
    return schemas


@pytest.fixture(scope="module")
def generated_interfaces(repo_root: Path) -> dict[str, dict[str, bool]]:
    """前端生成文件里的接口。"""
    interfaces = parse_generated_interfaces(repo_root / GENERATED_TS_REL)
    assert interfaces, (
        f"未从 {GENERATED_TS_REL} 解析出任何接口——生成器模板可能已变化。\n"
        "修复：bash scripts/gen-api-types.sh（并检查 tests/contract 的解析规则）"
    )
    return interfaces


def test_detection_response_field_sets_are_identical(
    openapi_schema: dict[str, object],
    generated_interfaces: dict[str, dict[str, bool]],
) -> None:
    """三层的 `DetectionResponse` 字段集必须逐名相同。"""
    pydantic_fields = set(DetectionResponse.model_fields)

    schema = openapi_schema["DetectionResponse"]
    assert isinstance(schema, dict)
    openapi_fields = set(schema["properties"])

    ts_fields = set(generated_interfaces["DetectionResponse"])

    assert pydantic_fields == openapi_fields, (
        "pydantic 模型与 OpenAPI 产物字段集不一致——"
        "契约产物未随后端定义更新。修复：uv run python scripts/gen_openapi.py"
    )
    assert pydantic_fields == ts_fields, (
        "pydantic 模型与前端生成类型字段集不一致——"
        "前端类型未随契约产物更新。修复：bash scripts/gen-api-types.sh"
    )


def test_detection_response_field_count(openapi_schema: dict[str, object]) -> None:
    """字段个数锁死为本阶段基线，防止无声的增删。"""
    schema = openapi_schema["DetectionResponse"]
    assert isinstance(schema, dict)

    count = len(schema["properties"])
    assert count == EXPECTED_DETECTION_FIELD_COUNT, (
        f"成功响应字段数由 {EXPECTED_DETECTION_FIELD_COUNT} 变为 {count}。\n"
        "契约变更须走 docs/contracts.md §8 流程，并同步更新本基线与 docs/contracts.md §9.3。"
    )


def test_status_is_absent_from_every_layer(
    openapi_schema: dict[str, object],
    generated_interfaces: dict[str, dict[str, bool]],
) -> None:
    """`status` 必须三层皆无。

    v0.5.0 的契约收缩：该字段恒为 `"success"`，不携带信息。移除后若被任何一层
    无声恢复，本判据失败——这正是「删字段比加字段更容易被回退」的防线。
    """
    schema = openapi_schema["DetectionResponse"]
    assert isinstance(schema, dict)

    assert "status" not in DetectionResponse.model_fields, "status 回到了 pydantic 模型"
    assert "status" not in schema["properties"], "status 回到了 OpenAPI 产物"
    assert "status" not in generated_interfaces["DetectionResponse"], "status 回到了前端类型"


def test_optionality_agrees_between_pydantic_and_typescript(
    generated_interfaces: dict[str, dict[str, bool]],
) -> None:
    """「pydantic 视为必填」必须对应「TS 不带 `?`」，反之亦然。

    这条比字段名一致性更严格：字段名相同而可空性不同，前端仍会在编译期放行一个
    运行期必然取到 `undefined` 的访问。
    """
    pydantic_optional = {
        name for name, field in DetectionResponse.model_fields.items() if not field.is_required()
    }
    ts_optional = {
        name for name, optional in generated_interfaces["DetectionResponse"].items() if optional
    }

    assert pydantic_optional == ts_optional, (
        "必填性与前端类型不一致。\n"
        f"  pydantic 视为可选：{sorted(pydantic_optional)}\n"
        f"  前端标记为可选：  {sorted(ts_optional)}"
    )


def test_error_response_agrees(
    openapi_schema: dict[str, object],
    generated_interfaces: dict[str, dict[str, bool]],
) -> None:
    """`ErrorResponse` 同样三层一致。它是前端按 `code` 分支的唯一依据。"""
    schema = openapi_schema["ErrorResponse"]
    assert isinstance(schema, dict)

    pydantic_fields = set(ErrorResponse.model_fields)
    assert pydantic_fields == set(schema["properties"])
    assert pydantic_fields == set(generated_interfaces["ErrorResponse"])
    assert pydantic_fields == {"detail", "code"}
