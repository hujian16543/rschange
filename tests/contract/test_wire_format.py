"""线格式一致性：真实响应的字段集必须与冻结 schema 逐名相同。

为什么需要这道判据
------------------
`test_field_consistency.py` 核对的是三层**声明**之间的一致性（pydantic 模型、
OpenAPI 产物、前端类型）。三者可以全部一致，而**实际发出去的 JSON** 与它们不同——
只要序列化环节多一个或少一个键（例如某个字段被 `exclude` 掉、某个计算属性被序列化、
或响应模型换了而 schema 未动）。

本模块起真实应用、上传真实夹具、检查真实响应体，把「声明」与「线上形态」接上。
这与 `backend/src/rschange/tests/test_api.py::TestDetectEndpoint` 互补而非重复：
那边断言的是**锚点数值**（7209 / 720900.0 / cva），这边断言的是**字段集**。两者
看的是响应的不同侧面，任一侧漂移都不会被另一侧发现。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi.testclient import TestClient

#: 真实夹具跑出的锚点。取一个即可——它的作用是证明这是真实响应而非桩，
#: 穷举锚点数值属于 test_api.py 的职责。
ANCHOR_CHANGE_PIXELS = 7209


@pytest.fixture(scope="module")
def frozen_schemas(repo_root: Path) -> dict[str, dict[str, object]]:
    """直接从入库产物读取 schema。

    刻意**不**调用应用的 `/openapi.json`：那是被测代码自己产出的文档，用它校验
    自己的响应等于自证。入库文件是独立的一份事实，且已被 `gen_openapi.py --check`
    与 `test_openapi_frozen.py` 证明与当前代码一致。
    """
    artifact = json.loads((repo_root / "docs/api/openapi.json").read_text(encoding="utf-8"))
    schemas = artifact["components"]["schemas"]
    assert isinstance(schemas, dict)
    return schemas


@pytest.fixture
def upload_files(before_path: Path, after_path: Path) -> dict[str, tuple[str, bytes, str]]:
    return {
        "before": ("before.tif", before_path.read_bytes(), "image/tiff"),
        "after": ("after.tif", after_path.read_bytes(), "image/tiff"),
    }


@pytest.mark.usefixtures("engine_ready")
@pytest.mark.baseline
def test_detection_response_matches_frozen_schema(
    client: TestClient,
    frozen_schemas: dict[str, dict[str, object]],
    upload_files: dict[str, tuple[str, bytes, str]],
) -> None:
    """成功响应的键集必须**恰好等于**冻结 schema 的属性集。

    用相等而非包含：多出的键同样有害——前端生成类型里没有它，消费方读不到，
    而契约文档也不再描述真实响应。
    """
    response = client.post("/api/detect", files=upload_files)
    assert response.status_code == 200, response.text
    body = response.json()

    schema = frozen_schemas["DetectionResponse"]
    properties = set(schema["properties"])  # type: ignore[arg-type]

    assert set(body) == properties, (
        "真实响应的字段集与冻结 schema 不一致。\n"
        f"  仅响应有：{sorted(set(body) - properties)}\n"
        f"  仅 schema 有：{sorted(properties - set(body))}"
    )
    assert set(schema.get("required", [])) <= set(body), "schema 标为必填的字段在响应中缺失"
    assert body["change_pixels"] == ANCHOR_CHANGE_PIXELS, "响应不是真实夹具产出的结果"


@pytest.mark.usefixtures("engine_ready")
def test_error_response_matches_frozen_schema(
    client: TestClient,
    frozen_schemas: dict[str, dict[str, object]],
) -> None:
    """错误响应的键集必须恰好等于 `ErrorResponse` 的属性集。

    前端按 `code` 分支，而 `code` 只在这个形状里出现；形状一变，分支即失效。
    取 404 是因为它由框架的 `HTTPException` 处理器产出——不经过 pydantic 校验，
    因此最容易被无意改形。
    """
    response = client.get("/api/image/definitely-absent.png")
    assert response.status_code == 404
    body = response.json()

    properties = set(frozen_schemas["ErrorResponse"]["properties"])  # type: ignore[arg-type]

    assert set(body) == properties, (
        f"错误响应形状与契约不一致：实得 {sorted(body)}，契约要求 {sorted(properties)}"
    )
    assert body["code"] == "http_404"
