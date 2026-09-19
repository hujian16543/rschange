#!/usr/bin/env python
"""`_spatial` 绑定层契约校验。

职责
----
校验 `docs/contracts.md` 中「可机器判定」的条款：函数签名与返回结构、参数约束、
异常类型、掩膜的类型与布局要求。它以 `scripts/engine_env.py` 加载扩展，因此校验
的是**当前构建产物**，不是源码。

与 `verify_baseline.py` 的分工
-----------------------------
| 脚本                   | 判据范围                                                 |
|------------------------|----------------------------------------------------------|
| `verify_baseline.py`   | 《重构方案》§7.1/§7.2/§7.3 三档验收锚点（算法语义）       |
| `verify_bindings.py`   | 绑定层契约（类型、布局、异常、字段名）；**不含**算法锚点 |

两者刻意不混档：把类型约束塞进 §7.3 会让「验收锚点」与「接口契约」两个不同
的判定基准纠缠在一起。

用法
----
    uv run python scripts/verify_bindings.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

import numpy as np

from engine_env import fixtures_dir, load_config, load_spatial

failures: list[str] = []


def check(ok: bool, what: str, detail: str = "") -> None:
    print(f"  {'OK  ' if ok else 'FAIL'} {what}  {detail}")
    if not ok:
        failures.append(what)


def expect_reject(tag: str, call: Callable[[], Any], expected_type: type[BaseException]) -> None:
    """断言调用被拒绝，且异常类型符合契约。"""
    try:
        call()
    except expected_type as exc:
        check(True, f"{tag} 被拒绝", f"{type(exc).__name__}")
    except Exception as exc:  # noqa: BLE001
        check(False, f"{tag} 被拒绝", f"异常类型不符：{type(exc).__name__}（期望 {expected_type.__name__}）")
    else:
        check(False, f"{tag} 被拒绝", "却成功了——不应静默接受")


def expect_accept(tag: str, call: Callable[[], Any]) -> Any:
    try:
        result = call()
    except Exception as exc:  # noqa: BLE001
        check(False, f"{tag} 被接受", f"却抛了 {type(exc).__name__}: {exc}")
        return None
    check(True, f"{tag} 被接受")
    return result


def main() -> int:
    config = load_config()
    spatial, build_dir = load_spatial(config)
    fixtures = fixtures_dir(config)

    scratch = Path(tempfile.mkdtemp(prefix="rschange_bind_"))

    before = fixtures / "before.tif"
    if not before.is_file():
        raise SystemExit(f"[配置错误] 夹具不存在：{before}")

    # 真实投影与 geo：直接取自夹具，避免自造 WKT（缺 CONVERSION 节点会让 GDAL
    # 每次写入都往 stderr 抛噪声，那是测试数据的问题而非引擎缺陷）。
    _, _, _, _, geo, projection = spatial.read_raster(str(before))

    def roundtrip(mask: np.ndarray, tag: str) -> tuple[Any, ...]:
        path = scratch / f"{tag}.tif"
        spatial.write_raster(str(path), mask, geo, projection)
        return spatial.read_raster(str(path))

    # ------------------------------------------------------------------ 1
    print("== 1. 模块与公开函数 ==")
    check(True, "_spatial 导入成功", f"来自 {build_dir}")
    public = ("read_raster", "write_raster", "mask_to_geojson", "print_gdal_version")
    check(all(hasattr(spatial, name) for name in public), "四个公开函数齐备", ", ".join(public))

    # ------------------------------------------------------------------ 2
    print("== 2. 2D 非方形掩膜写读一致（D-1：旧实现一律写成 W×W）==")
    for height, width in ((100, 200), (200, 100), (64, 512), (37, 131)):
        mask = np.zeros((height, width), dtype=np.uint8)
        mask[3:20, 5:40] = 7
        array, got_w, got_h, bands, _, _ = roundtrip(mask, f"2d_{height}x{width}")
        check(
            (got_w, got_h, bands) == (width, height, 1) and array.shape == (1, height, width),
            f"2D ({height},{width}) 写读一致",
            f"读 w={got_w} h={got_h} bands={bands} shape={array.shape}"
            + ("" if (got_w, got_h) == (width, height) else f"  [旧实现会写成 {width}x{width}]"),
        )
        check(
            int(array[0, 3, 5]) == 7 and int(array[0, 19, 39]) == 7,
            f"2D ({height},{width}) 像素值保持",
            f"(3,5)={int(array[0, 3, 5])} (19,39)={int(array[0, 19, 39])}",
        )

    # ------------------------------------------------------------------ 3
    print("== 3. 3D 掩膜 ==")
    mask3 = np.zeros((3, 120, 80), dtype=np.uint8)
    for band in range(3):
        mask3[band, 10:30, 10:50] = band + 1
    array, got_w, got_h, bands, _, _ = roundtrip(mask3, "3d")
    check(
        (got_w, got_h, bands) == (80, 120, 3) and array.shape == (3, 120, 80),
        "3D (3,120,80) 写读一致",
        f"读 w={got_w} h={got_h} bands={bands} shape={array.shape}",
    )
    check(
        all(int(array[b, 15, 15]) == b + 1 for b in range(3)),
        "各波段像素值独立保持",
        str([int(array[b, 15, 15]) for b in range(3)]),
    )

    # ------------------------------------------------------------------ 4
    print("== 4. 方形掩膜（旧实现恰好正确的形状，作回归保护）==")
    square = np.zeros((256, 256), dtype=np.uint8)
    square[100:160, 100:160] = 1
    array, got_w, got_h, bands, _, _ = roundtrip(square, "square")
    check(
        (got_w, got_h, bands) == (256, 256, 1) and array.shape == (1, 256, 256),
        "方形 256x256 仍正确",
        f"读 w={got_w} h={got_h} shape={array.shape}",
    )

    # ------------------------------------------------------------------ 5
    print("== 5. 参数类错误必须抛 ValueError ==")
    bad_dir = scratch / "bad"
    bad_dir.mkdir(exist_ok=True)
    expect_reject(
        "write_raster 1D 掩膜",
        lambda: spatial.write_raster(str(bad_dir / "a.tif"), np.zeros(64, dtype=np.uint8), geo, projection),
        ValueError,
    )
    expect_reject(
        "write_raster 4D 掩膜",
        lambda: spatial.write_raster(str(bad_dir / "b.tif"), np.zeros((1, 1, 8, 8), dtype=np.uint8), geo, projection),
        ValueError,
    )
    expect_reject(
        "write_raster geo 只有 5 项",
        lambda: spatial.write_raster(str(bad_dir / "c.tif"), np.zeros((8, 8), dtype=np.uint8), geo[:5], projection),
        ValueError,
    )
    expect_reject(
        "mask_to_geojson 3D 掩膜",
        lambda: spatial.mask_to_geojson(np.zeros((3, 8, 8), dtype=np.uint8), geo),
        ValueError,
    )
    expect_reject(
        "mask_to_geojson geo 只有 5 项",
        lambda: spatial.mask_to_geojson(np.zeros((8, 8), dtype=np.uint8), geo[:5]),
        ValueError,
    )

    # ------------------------------------------------------------------ 6
    print("== 6. IO 类错误必须抛 RuntimeError ==")
    expect_reject("read_raster 不存在的文件", lambda: spatial.read_raster(str(scratch / "nope.tif")), RuntimeError)
    expect_reject(
        "write_raster 目标目录不存在",
        lambda: spatial.write_raster(str(scratch / "no_such_dir" / "x.tif"), np.zeros((8, 8), dtype=np.uint8), geo, projection),
        RuntimeError,
    )

    # ------------------------------------------------------------------ 7
    print("== 7. 掩膜参数的类型与布局严格性 ==")
    # nanobind 的 ndarray 转换器默认在直接匹配失败时回退到转换，于是浮点幅度图
    # 会被静默当作掩膜使用（非零即变化像素），产出貌似合理的错误结果。
    # 契约要求显式拒绝，由调用方自行转换。
    mask2d = np.zeros((8, 8), dtype=np.uint8)
    mask2d[2:6, 2:6] = 1
    expect_accept("uint8 C 连续可写数组", lambda: spatial.mask_to_geojson(mask2d, geo))
    expect_accept(
        "uint8 C 连续只读数组（np.frombuffer）",
        lambda: spatial.mask_to_geojson(np.frombuffer(bytes(64), dtype=np.uint8).reshape(8, 8), geo),
    )

    expect_reject("float32 掩膜", lambda: spatial.mask_to_geojson(np.ones((8, 8), dtype=np.float32), geo), TypeError)
    expect_reject("int32 掩膜", lambda: spatial.mask_to_geojson(np.ones((8, 8), dtype=np.int32), geo), TypeError)
    expect_reject("bool 掩膜", lambda: spatial.mask_to_geojson(np.ones((8, 8), dtype=bool), geo), TypeError)
    expect_reject(
        "非 C 连续掩膜（跨步切片）",
        lambda: spatial.mask_to_geojson(np.zeros((16, 16), dtype=np.uint8)[::2, ::2], geo),
        TypeError,
    )
    expect_reject(
        "F 连续掩膜",
        lambda: spatial.mask_to_geojson(np.asfortranarray(mask2d), geo),
        TypeError,
    )
    expect_reject(
        "write_raster 收到 float32 掩膜",
        lambda: spatial.write_raster(str(bad_dir / "d.tif"), np.ones((8, 8), dtype=np.float32), geo, projection),
        TypeError,
    )
    # 退化 3D (1, H, W) 的波段数也是 1，若按「波段数 != 1」判定会被静默压维接受。
    expect_reject(
        "mask_to_geojson 退化 3D (1,H,W)",
        lambda: spatial.mask_to_geojson(np.zeros((1, 8, 8), dtype=np.uint8), geo),
        ValueError,
    )

    # ------------------------------------------------------------------ 8
    print("== 8. read_raster 元数据 ==")
    array, width, height, bands, got_geo, got_projection = spatial.read_raster(str(before))
    check((width, height, bands) == (256, 256, 3), "夹具尺寸 256/256/3", f"{width}/{height}/{bands}")
    check(array.shape == (3, 256, 256), "数组形状 (3,256,256)", str(array.shape))
    check(str(array.dtype) == "uint16", "dtype uint16", str(array.dtype))
    check(list(got_geo) == list(geo), "geo_transform 一致", str(list(got_geo)))
    check("UTM zone 50N" in got_projection, "投影含 UTM zone 50N", got_projection[:46] + "...")

    # ------------------------------------------------------------------ 9
    print("== 9. mask_to_geojson 端到端（冻结变化掩膜）==")
    mask_meta = json.loads((fixtures / "change_mask.json").read_text(encoding="utf-8"))
    mask = np.frombuffer((fixtures / "change_mask.raw").read_bytes(), dtype=np.uint8).reshape(
        mask_meta["height"], mask_meta["width"]
    )
    check(
        int(mask.sum()) == mask_meta["changed_pixels"],
        "掩膜载入正确",
        f"非零像素 {int(mask.sum())}，期望 {mask_meta['changed_pixels']}",
    )

    collection = json.loads(spatial.mask_to_geojson(mask, mask_meta["geo_transform"]))
    features = collection["features"]
    check(len(features) == 1, "Feature 数为 1（旧实现为 2）", f"实得 {len(features)}")

    total = sum(float(f["properties"]["area_m2"]) for f in features)
    check(abs(total - 720900.0) < 1e-6, "面积合计 720900 m²（旧实现为 1441800）", f"实得 {total}")
    check(all(f["geometry"]["type"] == "Polygon" for f in features), "几何类型均为 Polygon")
    check(
        all(
            set(f["properties"]) == {"label", "pixel_count", "area_m2"}
            for f in features
        ),
        "properties 字段名恰为 label / pixel_count / area_m2",
        str(sorted(features[0]["properties"])) if features else "",
    )

    # ------------------------------------------------------------------ 10
    print("== 10. 非方形掩膜的地理坐标范围（H≠W 才暴露尺寸混淆）==")
    # 100 行 × 200 列，区块贴近右边缘。若把 H 与 W 混淆（例如按 W×W 处理），
    # 经纬度换算会越出掩膜真实范围，下方边界断言即可捕获。
    rows, cols = 100, 200
    non_square = np.zeros((rows, cols), dtype=np.uint8)
    non_square[10:31, 150:191] = 1
    non_square_collection = json.loads(spatial.mask_to_geojson(non_square, geo))

    x_min = geo[0]
    x_max = geo[0] + cols * geo[1]
    y_max = geo[3]
    y_min = geo[3] + rows * geo[5]
    coords = [
        point
        for feature in non_square_collection["features"]
        for ring in feature["geometry"]["coordinates"]
        for point in ring
    ]
    xs = [point[0] for point in coords]
    ys = [point[1] for point in coords]

    check(len(non_square_collection["features"]) == 1, "非方形掩膜产出 1 个 Feature", f"实得 {len(non_square_collection['features'])}")
    check(
        x_min <= min(xs) and max(xs) <= x_max,
        f"经度落在列范围 [{x_min:.0f}, {x_max:.0f}] 内",
        f"实得 [{min(xs)}, {max(xs)}]",
    )
    check(
        y_min <= min(ys) and max(ys) <= y_max,
        f"纬度落在行范围 [{y_min:.0f}, {y_max:.0f}] 内（混淆 W/H 必越界）",
        f"实得 [{min(ys)}, {max(ys)}]",
    )

    print()
    print(f"失败项合计 = {len(failures)}  ->  {'通过' if not failures else '不通过'}")
    for item in failures:
        print(f"  - {item}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
