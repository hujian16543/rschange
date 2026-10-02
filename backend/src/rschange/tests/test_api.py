"""HTTP 边界：路由、错误映射、目录穿越、CORS、体积上限。

异常映射的用例各自构造一个只替换算法的应用（`create_app(context=...)`），
因此不需要打桩框架、也不需要启动真实服务的其他部分。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar

import numpy as np
import pytest
from fastapi.testclient import TestClient

import rschange
from rschange.api.app import create_app
from rschange.api.deps import RuntimeContext
from rschange.api.routers.detection import _artifact_path
from rschange.config import Settings
from rschange.detectors import registry
from rschange.detectors.base import DetectionResult
from rschange.errors import InputValidationError
from rschange.postprocess import MorphologyPostprocessor
from rschange.tests.support import make_settings

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from numpy.typing import NDArray

#: 泄漏探针。刻意**不用** Windows 家目录形式的路径——`test_architecture.py` 会扫描
#: `backend/` 内是否出现那类字面串，探针若写成那种形式会自己触发门禁。
_LEAK_CANARY = "LEAK-CANARY-DO-NOT-EMIT"
_LEAK_PATH = "/internal/secret/engine.so"


@pytest.fixture
def upload_files(
    before_path: Path, after_path: Path
) -> Callable[[], dict[str, tuple[str, bytes, str]]]:
    def _make() -> dict[str, tuple[str, bytes, str]]:
        return {
            "before": ("before.tif", before_path.read_bytes(), "image/tiff"),
            "after": ("after.tif", after_path.read_bytes(), "image/tiff"),
        }

    return _make


def _client_for(
    settings: Settings, detector: object, postprocessor: object | None = None
) -> TestClient:
    context = RuntimeContext(
        settings,
        detector,  # type: ignore[arg-type]
        postprocessor or MorphologyPostprocessor(),  # type: ignore[arg-type]
    )
    return TestClient(create_app(context=context), raise_server_exceptions=False)


# ------------------------------------------------------------------ 应用工厂
class TestAppFactory:
    def test_no_module_level_singleton(self) -> None:
        """模块级单例会在导入期就接上真实算法，使测试只能打桩。"""
        import rschange.api.app as app_module

        assert not hasattr(app_module, "app")

    def test_openapi_exposes_contract_fields(self, client: TestClient) -> None:
        schema = client.get("/openapi.json").json()
        assert "/api/detect" in schema["paths"]
        properties = schema["components"]["schemas"]["DetectionResponse"]["properties"]
        assert {"detector", "pixel_area_m2", "changed_area_m2"} <= set(properties)

    def test_root_reports_version(self, client: TestClient) -> None:
        """`/` 上报的版本号必须等于包版本，**不写字面量**。

        写死版本号会凭空造出第二个声明点：此处曾停在 `"0.3.0"` 而仓库已到
        `v0.4.0`，且没有任何门禁会因此报错。断言「等于 `rschange.__version__`」
        保住原意（端点确实上报了版本）并消除漂移；该值的单一真相源由
        `scripts/verify_version.py` 守护。
        """
        assert client.get("/").json()["version"] == rschange.__version__


# ------------------------------------------------------------------ CORS
class TestCors:
    """D1：`allow_origins=["*"]` 与 `allow_credentials=True` 并存会使白名单失效。"""

    def test_listed_origin_is_allowed(self, client: TestClient) -> None:
        response = client.get("/", headers={"Origin": "http://localhost:5173"})
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"

    def test_foreign_origin_is_not_allowed(self, client: TestClient) -> None:
        response = client.get("/", headers={"Origin": "http://evil.example"})
        assert response.headers.get("access-control-allow-origin") is None

    def test_credentials_header_absent(self, client: TestClient) -> None:
        response = client.get("/", headers={"Origin": "http://localhost:5173"})
        assert response.headers.get("access-control-allow-credentials") is None


# ------------------------------------------------------------------ 静态产物
class TestArtifactPaths:
    """目录穿越：旧代码 `os.path.join(UPLOAD_DIR, filename)` 会被绝对路径丢弃基目录。"""

    HOSTILE: ClassVar[list[str]] = [
        "../config/local.toml",
        "../../pyproject.toml",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "..\\config\\local.toml",
        "..",
        ".",
        "",
        "sub/../../pyproject.toml",
        ".hidden",
    ]

    @pytest.mark.parametrize("name", HOSTILE)
    def test_hostile_names_are_rejected(self, name: str, context: RuntimeContext) -> None:
        assert _artifact_path(name, context) is None

    @pytest.mark.parametrize(
        "probe",
        ["/api/image/..%2F..%2Fpyproject.toml", "/api/image/%2Fetc%2Fpasswd", "/api/image/.."],
    )
    def test_http_probes_return_404(self, client: TestClient, probe: str) -> None:
        response = client.get(probe)
        assert response.status_code == 404
        assert b"dependency-groups" not in response.content


# ------------------------------------------------------------------ 错误映射
class TestErrorMapping:
    def test_unsupported_extension(self, client: TestClient) -> None:
        response = client.post(
            "/api/detect",
            files={
                "before": ("a.exe", b"MZ", "application/octet-stream"),
                "after": ("b.tif", b"x", "image/tiff"),
            },
        )
        assert response.status_code == 400
        assert response.json()["code"] == "unsupported_format"

    def test_missing_file_field(self, client: TestClient) -> None:
        response = client.post("/api/detect")
        assert response.status_code == 422
        payload = response.json()
        assert payload["code"] == "request_validation_error"
        assert isinstance(payload["detail"], str)
        assert "errors" in payload

    def test_method_not_allowed_gets_code(self, client: TestClient) -> None:
        response = client.get("/api/detect")
        assert response.status_code == 405
        assert response.json()["code"] == "http_405"

    def test_unknown_image_returns_404_with_code(self, client: TestClient) -> None:
        response = client.get("/api/image/not-a-real-file.png")
        assert response.status_code == 404
        assert response.json()["code"] == "http_404"


class TestUploadLimit:
    """旧实现声明了 500 MB 上限却从未校验，边读边写盘。"""

    @pytest.fixture
    def tiny_client(self, tmp_path: Path) -> TestClient:
        settings = make_settings(
            runtime={
                "data_dir": str(tmp_path / "data"),
                "max_upload_mb": 1,
                "allowed_origins": ["http://localhost:5173"],
            }
        )
        return TestClient(
            create_app(
                context=RuntimeContext(settings, registry.resolve(), MorphologyPostprocessor())
            )
        )

    def test_oversized_upload_is_rejected(self, tiny_client: TestClient, tmp_path: Path) -> None:
        payload = b"\x00" * (2 * 1024 * 1024)
        response = tiny_client.post(
            "/api/detect",
            files={
                "before": ("big.tif", payload, "image/tiff"),
                "after": ("big.tif", payload, "image/tiff"),
            },
        )
        assert response.status_code == 413
        assert response.json()["code"] == "upload_too_large"

    def test_no_partial_file_left_behind(self, tiny_client: TestClient, tmp_path: Path) -> None:
        payload = b"\x00" * (2 * 1024 * 1024)
        tiny_client.post(
            "/api/detect",
            files={
                "before": ("big.tif", payload, "image/tiff"),
                "after": ("big.tif", payload, "image/tiff"),
            },
        )
        uploads = tmp_path / "data" / "uploads"
        leftovers = sorted(uploads.glob("*.tif")) if uploads.exists() else []
        assert leftovers == [], [path.name for path in leftovers]


class TestExceptionLeakage:
    """D7：`str(exc)` 不得进入响应体。"""

    def test_unexpected_exception_is_redacted(self, settings: Settings, upload_files) -> None:
        class ExplodingDetector:
            name = "exploding"

            def detect(
                self, before: NDArray[np.uint16], after: NDArray[np.uint16]
            ) -> DetectionResult:
                raise RuntimeError(f"{_LEAK_CANARY} {_LEAK_PATH}")

        client = _client_for(settings, ExplodingDetector())
        response = client.post("/api/detect", files=upload_files())

        assert response.status_code == 500
        assert response.json() == {"detail": "内部错误", "code": "internal_error"}
        assert _LEAK_CANARY not in response.text
        assert "secret" not in response.text
        assert "Traceback" not in response.text

    def test_domain_exception_returns_public_message_only(
        self, settings: Settings, upload_files
    ) -> None:
        """领域异常必须映射到自己的状态码，而不是被统一压成 500。"""

        class FailingDetector:
            name = "failing"

            def detect(
                self, before: NDArray[np.uint16], after: NDArray[np.uint16]
            ) -> DetectionResult:
                raise InputValidationError(
                    f"{_LEAK_CANARY} 内部形状 {before.shape}",
                    public_message="两期影像的尺寸或波段数不一致",
                )

        client = _client_for(settings, FailingDetector())
        response = client.post("/api/detect", files=upload_files())

        assert response.status_code == 400
        payload = response.json()
        assert payload == {
            "detail": "两期影像的尺寸或波段数不一致",
            "code": "input_validation_error",
        }
        assert _LEAK_CANARY not in response.text


# ------------------------------------------------------------------ 主流程
@pytest.mark.usefixtures("engine_ready")
@pytest.mark.baseline
class TestDetectEndpoint:
    def test_returns_baseline_numbers(self, client: TestClient, upload_files) -> None:
        response = client.post("/api/detect", files=upload_files())
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["change_pixels"] == 7209
        assert body["total_pixels"] == 65536
        assert abs(body["threshold"] - 5.9168) <= 1e-4
        assert body["detector"] == "cva"
        assert body["pixel_area_m2"] == pytest.approx(100.0)
        assert body["changed_area_m2"] == pytest.approx(720900.0)
        assert body["change_rate"] == pytest.approx(7209 / 65536)
        assert len(body["image_corners"]) == 4

    def test_geojson_area_matches_changed_area(self, client: TestClient, upload_files) -> None:
        body = client.post("/api/detect", files=upload_files()).json()
        document = json.loads(body["geojson"])
        area_sum = sum(feature["properties"]["area_m2"] for feature in document["features"])
        assert area_sum == pytest.approx(body["changed_area_m2"], abs=1e-6)

    @pytest.mark.parametrize(
        ("field", "kind"),
        [("image_before_url", "before"), ("image_after_url", "after"), ("image_diff_url", "diff")],
    )
    def test_preview_urls_are_served_as_png(
        self, client: TestClient, upload_files, field: str, kind: str
    ) -> None:
        body = client.post("/api/detect", files=upload_files()).json()
        response = client.get(body[field])

        assert response.status_code == 200
        assert response.content[:8] == b"\x89PNG\r\n\x1a\n", f"{kind} 不是 PNG"
