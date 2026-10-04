"""上传体积：G6.3 的判据 —— 超过反向代理默认上限的请求必须真的到得了后端。

背景
----
阶段出口门 G6.3 原文：「上传 >1 MB GeoTIFF 不再返回 413」。

413 的唯一来源是 **反向代理**：nginx 的 `client_max_body_size` 默认为 1 MB，而
后端 `runtime.max_upload_mb` 默认为 500 MB。旧仓库的 `nginx.conf` 未设该项，
于是任何超过 1 MB 的上传都在 nginx 层被拒，**根本到不了后端**——后端的上限写得
再对也不生效，容器部署下的大文件上传可用性为零（缺陷 A5）。

本模块因此断言「**接受**」这一侧：处于配置上限之内的大文件必须能走完整条流水线。
「**拒绝**」那一侧（超过配置上限 → 413 + 不留半成品）已由
`backend/src/rschange/tests/test_api.py::TestUploadLimit` 覆盖，此处不重复。

只断言「拒绝」会让「闸门根本不存在」静默通过；只断言「接受」会让「上限被误设成
1 MB」静默通过。两侧合起来才是 G6.3 的完整判据。

与契约测试的分工
----------------
`tests/contract/test_wire_format.py` 关心的是**字段集**，用的是 308 KB 的基线夹具。
体积不是它的判据，故本模块独立成篇。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

#: nginx 的默认请求体上限。A5 缺陷的表现即「所有超过它的上传返回 413」。
NGINX_DEFAULT_BODY_LIMIT = 1024 * 1024

#: 生成影像的边长。取 1050 使**未压缩**的 uint8 单波段 GeoTIFF 必然超过 1 MiB
#: （1050² = 1 102 500 字节），同时把检测耗时控制在可接受范围。
#: 取 1024 不够：1024² = 1 048 576，与上限**恰好相等**，而判定用的是严格大于。
SIDE = 1050

GEO_TRANSFORM = (500000.0, 10.0, 0.0, 4000000.0, 0.0, -10.0)
PROJECTION = "EPSG:32650"


def _synthetic_uint8(shift: int) -> np.ndarray:
    """构造一张带矩形块的 uint8 影像。

    刻意用规则几何而非随机噪声：本模块断言的是**接受性**而非数值，噪声只会让
    检测耗时随机器波动，不给判据增加任何信息。
    """
    array = np.zeros((SIDE, SIDE), dtype=np.uint8)
    array[100:400, 100:400] = 200
    array[600 + shift : 700 + shift, 500:900] = 220
    return array


@pytest.fixture(scope="module")
def large_tiffs(engine_ready: None, tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    """生成两张 >1 MiB 的真实 GeoTIFF，返回其字节内容。

    依赖 `engine_ready`：写盘与后续读盘都经 `_spatial`，引擎不可用时本模块整体
    跳过（与既有约定一致），而不是报一堆无关的导入错误。
    """
    from rschange.spatial import write_raster

    base = tmp_path_factory.mktemp("large-upload")
    contents: dict[str, bytes] = {}
    for name, shift in (("before", 0), ("after", 30)):
        path = base / f"{name}.tif"
        write_raster(path, _synthetic_uint8(shift), GEO_TRANSFORM, PROJECTION)
        contents[name] = path.read_bytes()

    # 自检：夹具若因压缩等原因缩到 1 MiB 以下，本模块的判据就失去意义。
    for name, payload in contents.items():
        assert len(payload) > NGINX_DEFAULT_BODY_LIMIT, (
            f"{name}.tif 仅 {len(payload)} 字节，未超过 nginx 默认上限 "
            f"{NGINX_DEFAULT_BODY_LIMIT}；本用例将无法证明任何事"
        )
    return contents


@pytest.mark.usefixtures("engine_ready")
def test_large_geotiff_is_accepted(
    client: TestClient,
    large_tiffs: dict[str, bytes],
) -> None:
    """>1 MiB 的真实 GeoTIFF 必须走完整条流水线并返回 200。

    若此处得到 413，说明体积闸门用了 1 MB 这一错误上限——那正是 A5 缺陷在
    容器部署下的表现。
    """
    response = client.post(
        "/api/detect",
        files={
            "before": ("before.tif", large_tiffs["before"], "image/tiff"),
            "after": ("after.tif", large_tiffs["after"], "image/tiff"),
        },
    )

    assert response.status_code != 413, (
        f"上传被按体积拒绝（{response.json()}）。"
        f"后端上限由 runtime.max_upload_mb 决定（默认 500 MB），"
        f"{len(large_tiffs['before'])} 字节不应当触发 413。"
    )
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["total_pixels"] == SIDE * SIDE, "响应不是本次上传影像的结果"
    assert body["change_pixels"] >= 0
    assert set(body) >= {"change_pixels", "change_rate", "geojson", "detector"}


@pytest.mark.usefixtures("engine_ready")
def test_body_size_limit_is_not_the_nginx_default(
    client: TestClient,
) -> None:
    """1 MiB 以上、内容不合法的文件必须因**内容**被拒，而非因体积。

    这一条把「体积闸门的上限不是 1 MB」从「某张特定影像能通过」推广到「任何
    超过 1 MB 的输入都不会在体积这一关被拦」。内容不合法的合法结局是 400
    （影像无法打开），断言据此排除 413 即可。
    """
    payload = b"\x00" * (2 * NGINX_DEFAULT_BODY_LIMIT)
    response = client.post(
        "/api/detect",
        files={
            "before": ("broken.tif", payload, "image/tiff"),
            "after": ("broken.tif", payload, "image/tiff"),
        },
    )

    assert response.status_code != 413, "2 MiB 的输入被按体积拒绝，说明上限被误设为 1 MB 量级"
    assert response.status_code == 400, response.text
