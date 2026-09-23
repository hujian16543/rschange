"""检测接口的请求与响应模型。

契约地位
--------
`DetectionResponse` 是**跨阶段契约**：Phase 3 冻结后写入 `docs/contracts.md`，
Phase 5 由它生成前端的 TypeScript 类型。字段的增删都须走契约变更流程。

与旧 `schemas/detection.py` 的差异（全部为**新增**，无字段删除）
----------------------------------------------------------------
* `detector` —— 可插拔之后，响应必须回带实际使用的算法名，否则「这份结果是哪个
  算法算的」在事后无从判断。
* `pixel_area_m2` / `changed_area_m2` —— 面积以平方米给出。口径与 GeoJSON 中
  Feature 属性的 `area_m2` 同源（`|dx × dy|`），两者可直接互相核对。
* 移除 `DetectionRequest`：旧的它声明 `before` / `after` 两个字符串路径，但 HTTP
  接口收的是 multipart 文件，该模型从未被任何路由使用。

`status` 字段**保留**。它恒为 `"success"`（错误走 HTTP 状态码与 `ErrorResponse`），
即不携带任何信息；删除它属契约收缩，不是缺陷修复，故留给契约冻结时裁定。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

__all__ = ["DetectionResponse", "ErrorResponse"]

#: OpenAPI 示例：真实夹具（before.tif / after.tif，256×256，UTM 50N）的实测输出。
_EXAMPLE: dict[str, Any] = {
    "change_pixels": 7209,
    "total_pixels": 65536,
    "change_rate": 0.1100006103515625,
    "threshold": 5.916767423962816,
    "detector": "cva",
    "pixel_area_m2": 100.0,
    "changed_area_m2": 720900.0,
    "geojson": '{"type": "FeatureCollection", "features": [...]}',
    "image_before_url": "/api/image/8f3c1d9e_before.png",
    "image_after_url": "/api/image/8f3c1d9e_after.png",
    "image_diff_url": "/api/image/8f3c1d9e_diff.png",
    "image_corners": [
        [117.0, 36.144718],
        [117.028456, 36.144715],
        [117.028448, 36.121634],
        [117.0, 36.121638],
    ],
    "status": "success",
}


class DetectionResponse(BaseModel):
    """一次变化检测的结果。"""

    change_pixels: int = Field(..., ge=0, description="变化像元数（后处理后）")
    total_pixels: int = Field(..., gt=0, description="影像总像元数")
    change_rate: float = Field(..., ge=0, le=1, description="变化像元占比，取值 [0, 1]")
    threshold: float = Field(..., description="检测算法使用的判定阈值")
    detector: str = Field(..., description="实际使用的检测算法名，用于结果追溯")
    pixel_area_m2: float = Field(..., gt=0, description="单像元面积（平方米）")
    changed_area_m2: float = Field(
        ..., ge=0, description="真实变化面积（平方米）= change_pixels × pixel_area_m2"
    )
    geojson: str | None = Field(
        default=None, description="变化区域的 GeoJSON FeatureCollection（坐标已为 WGS84 经纬度）"
    )
    image_before_url: str | None = Field(default=None, description="前一期影像预览图 URL")
    image_after_url: str | None = Field(default=None, description="后一期影像预览图 URL")
    image_diff_url: str | None = Field(default=None, description="变化叠加预览图 URL")
    image_corners: list[list[float]] | None = Field(
        default=None,
        description="影像四角经纬度，顺序为左上、右上、右下、左下，用于地图定位",
    )
    status: str = Field(default="success", description="保留字段，恒为 success")

    model_config = {
        "json_schema_extra": {"example": _EXAMPLE},
    }


class ErrorResponse(BaseModel):
    """错误响应体。

    与 `rschange.errors.RsChangeError.to_payload()` 的输出结构一致：`detail` 为
    **脱敏后**的描述，`code` 为机器可读错误码（供前端分支，不随文案变化）。

    本模型只用于 OpenAPI 文档，不参与序列化——异常响应由 `api/errors.py` 的
    全局处理器直接产出 `JSONResponse`，不经过 pydantic 校验。
    """

    detail: str = Field(..., description="脱敏后的错误描述")
    code: str = Field(..., description="机器可读错误码，见 docs/contracts.md")

    model_config = {
        "json_schema_extra": {
            "example": {"detail": "两期影像的尺寸或波段数不一致", "code": "input_validation_error"}
        }
    }

    @field_validator("code")
    @classmethod
    def _code_is_snake_case(cls, value: str) -> str:
        """错误码必须是 `snake_case`。

        前端按 `code` 分支，一旦混入大写或连字符，同一条分支在不同错误上会失效。
        这是文档模型，校验成本为零，故在定义处拦住。
        """
        if value != value.lower() or not value.replace("_", "").isalnum():
            raise ValueError(f"code 必须是 snake_case，实得 {value!r}")
        return value
