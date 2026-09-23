#!/usr/bin/env python
"""rschange 黄金基线校验工具。

职责
----
一条命令输出《重构方案》§7.1 / §7.2 / §7.3 三组判定的通过情况，任一项不符合
预期即以非零码退出（供 CI 使用）。

设计原则
--------
1. **禁止用被测代码自证。**
   本脚本内置一份「冻结参考实现」（FROZEN REFERENCE v0），与 backend 的
   rschange 包完全独立。连通域个数另用 scipy 独立计算，作为 C++ 引擎输出的
   对照基准。这样 rschange 的改动不会悄悄改变基线。
2. **打印实际值，不只打印结论。**
   每项均输出「期望 / 实际 / 判定」，便于人工复核，避免黑箱通过。
3. **期望状态由 --phase 决定。**
   Phase 1：缺陷尚未修复，故 §7.2 / §7.3 **必须失败**——失败才是正确结果。
   Phase 2 起：缺陷已修复，三项必须全部通过。
   注意：`--phase 1` 只对**旧引擎的构建产物**有意义，须把 config 的
   `engine.build_dir` 指回旧仓库的 build 目录。Phase 1 的判定结果已归档在
   `docs/verification/phase-1.md`。

夹具
----
| 夹具                       | 覆盖判据                                                     |
|----------------------------|--------------------------------------------------------------|
| `change_mask.{raw,json}`   | §7.1 不变量、§7.2 缺陷基线、§7.3 语义断言（单连通域）        |
| `multi_region_mask.{raw,json}` | §7.3 的 label 分配顺序、多区域「一个 Region 一个 Feature」、几何面积一致性、洞环合法性 |

`multi_region_mask` 的期望值由几何定义直接写出（`scripts/make_multi_region_fixture.py`），
连通域个数与首次出现顺序另由 scipy 独立计算，构成「几何定义 ↔ scipy ↔ 引擎」三方对照。

用法
----
    uv run python scripts/verify_baseline.py --phase 2
    uv run python scripts/verify_baseline.py --phase 2 --verbose
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from dataclasses import dataclass
from typing import Any, Final

import numpy as np

# scripts/ 就在脚本自身目录下（sys.path[0]），直接导入即可。
from engine_env import REPO_ROOT, fixtures_dir, load_config, load_spatial

# ============================================================================
# 冻结参考实现 FROZEN REFERENCE v0
#
# 来源：旧仓库 src/backend/detectors/cva.py 与 postprocessor.py 的算法语义，
#      逐行对齐（含 Otsu 直方图分箱方式与后处理顺序）。
# 纪律：本区块不得随 backend 的重构而改动。若确需修改，必须走
#      「更新 baseline.md → 重跑三方对照 → 记录修订理由」流程。
# ============================================================================


def frozen_otsu(data: np.ndarray, bins: int = 256) -> float:
    """Otsu 阈值：手动直方图 + 最大化类间方差。"""
    vmin = float(data.min())
    vmax = float(data.max())
    if vmax <= vmin:
        return vmin

    edges = np.linspace(vmin, vmax, bins + 1)
    width = edges[1] - edges[0]
    indices = np.clip(((data - vmin) / width).astype(np.int64), 0, bins - 1)
    counts = np.bincount(indices.ravel(), minlength=bins).astype(np.float64)
    centers = (edges[:-1] + edges[1:]) / 2.0

    total = counts.sum()
    if total == 0:
        return 0.0

    sum_all = float((centers * counts).sum())
    w_b = 0.0
    sum_b = 0.0
    best = 0.0
    max_variance = 0.0

    for i in range(bins):
        w_b += counts[i]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += centers[i] * counts[i]
        mean_b = sum_b / w_b
        mean_f = (sum_all - sum_b) / w_f
        variance = w_b * w_f * (mean_b - mean_f) ** 2
        if variance > max_variance:
            max_variance = variance
            best = float(centers[i])

    return best


def frozen_cva(before: np.ndarray, after: np.ndarray) -> tuple[float, np.ndarray]:
    """CVA：多维欧氏距离 + Otsu 二值化。"""
    delta = after.astype(np.float64) - before.astype(np.float64)
    magnitude = np.sqrt(np.sum(delta**2, axis=0))
    threshold = frozen_otsu(magnitude)
    return threshold, magnitude > threshold


def frozen_postprocess(mask: np.ndarray, min_size: int = 30) -> np.ndarray:
    """后处理：连通域过滤（>min_size）+ 3x3 闭运算。"""
    from scipy import ndimage

    label_mask, _ = ndimage.label(mask)
    counts = np.bincount(label_mask.ravel())
    keep = counts > min_size
    keep[0] = 0
    clean = keep[label_mask]
    return ndimage.binary_closing(clean, structure=np.ones((3, 3)), iterations=1)


# ============================================================================
# 冻结基线常量
# ============================================================================

EXPECTED_SHAPE: Final = (3, 256, 256)
EXPECTED_DTYPE: Final = "uint16"
EXPECTED_GEO: Final = [500000.0, 10.0, 0.0, 4000000.0, 0.0, -10.0]
EXPECTED_PROJ_MARKER: Final = "UTM zone 50N"
EXPECTED_THRESHOLD: Final = 5.9168
THRESHOLD_TOL: Final = 1e-4
EXPECTED_CHANGED_RAW: Final = 7209
EXPECTED_CHANGED_CLEAN: Final = 7209
TOTAL_PIXELS: Final = 256 * 256
PIXEL_AREA_M2: Final = 100.0  # |10 * -10|
EXPECTED_TRUE_AREA: Final = 720900.0
RATE_TOL: Final = 1e-6
AREA_TOL: Final = 1e-6
# 几何面积（shapely 由经纬度坐标算出）与上报面积的相对偏差上限，百分比为单位。
#
# 顶点取像素角点，故两者应恒等，残余偏差只来自浮点表示：坐标量级为
# 5e5 × 4e6，双精度乘积的绝对误差约 1e-4 m²。取 1e-6 % 已远超该量级，
# 同时远小于旧基准的偏差（>= 2.93 %），故判据仍能捕捉几何基准回退。
GEOMETRY_TOL_PERCENT: Final = 1e-6
# §7.2 现状值（旧引擎的实际输出，均为缺陷产物）
LEGACY_FEATURE_COUNT: Final = 2
LEGACY_AREA_SUM: Final = 1441800.0
# §7.2 修复目标
TARGET_FEATURE_COUNT: Final = 1
TARGET_AREA_SUM: Final = 720900.0


# ============================================================================
# 配置载入
#
# 分层配置的合并、相对路径解析、`_spatial` 的定位与加载，统一由
# scripts/engine_env.py 提供（verify_bindings.py 也用同一份），
# 避免两处配置优先级语义各自漂移。
# ============================================================================


# ============================================================================
# 判定框架
# ============================================================================


@dataclass
class Check:
    group: str
    name: str
    expected: str
    actual: str
    passed: bool
    skipped: bool = False
    note: str = ""


def fmt(value: Any, digits: int = 4) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(fmt(v, digits) for v in value) + "]"
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="rschange 黄金基线校验")
    parser.add_argument(
        "--phase",
        type=int,
        default=1,
        help="期望状态所对应的阶段号：1 = 缺陷未修复（§7.2/7.3 应失败）；>=2 = 全部应通过",
    )
    parser.add_argument("--verbose", action="store_true", help="额外打印原始 GeoJSON")
    args = parser.parse_args()

    config = load_config()
    spatial, build_dir = load_spatial(config)

    fixtures = fixtures_dir(config)
    before_path = fixtures / "before.tif"
    after_path = fixtures / "after.tif"

    for path in (before_path, after_path):
        if not path.is_file():
            raise SystemExit(f"[配置错误] fixture 不存在：{path}")

    checks: list[Check] = []
    add = checks.append

    def record(group: str, name: str, expected: Any, actual: Any, passed: bool) -> None:
        add(Check(group, name, fmt(expected), fmt(actual), passed))

    # -------------------------------------------------------------- 输入影像
    before, width, height, bands, geo, proj = spatial.read_raster(str(before_path))
    after, *_rest = spatial.read_raster(str(after_path))

    record("7.1", "影像形状", EXPECTED_SHAPE, before.shape, tuple(before.shape) == EXPECTED_SHAPE)
    record("7.1", "影像 dtype", EXPECTED_DTYPE, before.dtype, str(before.dtype) == EXPECTED_DTYPE)
    record(
        "7.1",
        "geo_transform",
        EXPECTED_GEO,
        geo,
        len(geo) == 6 and all(abs(a - b) < 1e-9 for a, b in zip(geo, EXPECTED_GEO, strict=True)),
    )
    record(
        "7.1",
        "投影含标记",
        EXPECTED_PROJ_MARKER,
        EXPECTED_PROJ_MARKER in str(proj),
        EXPECTED_PROJ_MARKER in str(proj),
    )
    add(
        Check(
            "7.1",
            "宽/高/波段",
            "256/256/3",
            f"{width}/{height}/{bands}",
            (width, height, bands) == (256, 256, 3),
        )
    )

    # -------------------------------------------------------------- 算法链路
    threshold, change_mask = frozen_cva(before, after)
    clean_mask = frozen_postprocess(change_mask)

    raw_changed = int(change_mask.sum())
    clean_changed = int(clean_mask.sum())

    record(
        "7.1",
        "Otsu 阈值",
        EXPECTED_THRESHOLD,
        threshold,
        abs(threshold - EXPECTED_THRESHOLD) <= THRESHOLD_TOL,
    )
    record(
        "7.1",
        "变化像素（原始）",
        EXPECTED_CHANGED_RAW,
        raw_changed,
        raw_changed == EXPECTED_CHANGED_RAW,
    )
    record(
        "7.1",
        "变化像素（后处理后）",
        EXPECTED_CHANGED_CLEAN,
        clean_changed,
        clean_changed == EXPECTED_CHANGED_CLEAN,
    )
    expected_rate = EXPECTED_CHANGED_CLEAN / TOTAL_PIXELS
    actual_rate = clean_changed / TOTAL_PIXELS
    add(
        Check(
            "7.1",
            "变化率",
            fmt(expected_rate, 6),
            fmt(actual_rate, 6),
            abs(actual_rate - expected_rate) <= RATE_TOL,
        )
    )
    add(
        Check(
            "7.1",
            "真实变化面积 m²",
            fmt(EXPECTED_TRUE_AREA, 1),
            fmt(clean_changed * PIXEL_AREA_M2, 1),
            abs(clean_changed * PIXEL_AREA_M2 - EXPECTED_TRUE_AREA) <= AREA_TOL,
        )
    )

    # ------------------------------------------------- 独立对照：连通域个数
    from scipy import ndimage

    _labeled, n_components = ndimage.label(clean_mask)

    # -------------------------------------------------------------- 矢量输出
    clean_u8 = clean_mask.astype(np.uint8)
    geojson_raw = spatial.mask_to_geojson(clean_u8, geo)
    features = json.loads(geojson_raw).get("features", [])
    n_features = len(features)
    area_sum = sum(float(f.get("properties", {}).get("area_m2", 0.0)) for f in features)

    if args.verbose:
        print("\n--- 原始 GeoJSON（源坐标系）---")
        print(json.dumps(json.loads(geojson_raw), ensure_ascii=False, indent=2))

    # ------------------------------------------------- 不变量：矢量输出结构
    # 「每个环首尾闭合」在旧引擎上已成立（它输出的是两段闭合弧，而非开口折线），
    # 因此属于不变量，归 §7.1。它不是修复带来的语义改进——
    # 归入 §7.3 会把「修复前的正确行为」误判为「缺陷基线」，属分类错误。
    ring_closed = True
    for feature in features:
        for ring in feature.get("geometry", {}).get("coordinates", []):
            if len(ring) < 4 or list(ring[0]) != list(ring[-1]):
                ring_closed = False
    record("7.1", "每个环首尾闭合", True, ring_closed, ring_closed)

    # -------------------------------------------------------------- §7.2 缺陷
    add(
        Check(
            "7.2",
            "GeoJSON Feature 个数",
            str(TARGET_FEATURE_COUNT),
            str(n_features),
            n_features == TARGET_FEATURE_COUNT,
            note=f"旧引擎实际输出 {LEGACY_FEATURE_COUNT}（缺陷：单连通域被劈成多段弧）",
        )
    )
    add(
        Check(
            "7.2",
            "属性面积合计 m²",
            fmt(TARGET_AREA_SUM, 1),
            fmt(area_sum, 1),
            abs(area_sum - TARGET_AREA_SUM) <= AREA_TOL,
            note=f"旧引擎实际输出 {LEGACY_AREA_SUM:.1f}（缺陷：面积重复计 2 倍）",
        )
    )

    # -------------------------------------------------------------- §7.3 语义
    add(
        Check(
            "7.3",
            "Feature 数 == 连通域个数",
            str(n_components),
            str(n_features),
            n_features == n_components,
            note="连通域个数由 scipy 独立计算，不依赖被测代码",
        )
    )
    expected_area_sem = clean_changed * PIXEL_AREA_M2
    add(
        Check(
            "7.3",
            "面积合计 == 像素数 × 单像元面积",
            fmt(expected_area_sem, 1),
            fmt(area_sum, 1),
            abs(area_sum - expected_area_sem) <= AREA_TOL,
        )
    )

    # ================================================= 多区域夹具（§7.3 判据）
    # 单连通域夹具覆盖不到两类语义：label 分配顺序（D-6）、多区域时的
    # 「一个 Region 一个 Feature」与几何面积一致性。故另取一份几何完全
    # 人工指定的夹具，其期望值写在同名 JSON 里，来自几何定义本身。
    multi_raw_path = fixtures / "multi_region_mask.raw"
    multi_meta_path = fixtures / "multi_region_mask.json"
    for path in (multi_raw_path, multi_meta_path):
        if not path.is_file():
            raise SystemExit(
                f"[配置错误] 多区域夹具不存在：{path}\n"
                "  该夹具承载 §7.3 的顺序与几何合法性判据，必须存在。\n"
                "  生成方式：uv run python scripts/make_multi_region_fixture.py"
            )

    multi_meta = json.loads(multi_meta_path.read_text(encoding="utf-8"))
    multi_width = int(multi_meta["width"])
    multi_height = int(multi_meta["height"])
    multi_mask = np.frombuffer(multi_raw_path.read_bytes(), dtype=np.uint8).reshape(
        multi_height, multi_width
    )

    # 连通域个数与「首次出现顺序」全部由 scipy 独立计算，不依赖被测代码：
    # 逐像素按行主序扫描，记录各连通域首次出现的位置，再按该位置排序。
    multi_labeled, multi_components = ndimage.label(multi_mask)
    multi_flat = multi_labeled.ravel()
    first_seen: dict[int, int] = {}
    for position in np.flatnonzero(multi_flat):
        first_seen.setdefault(int(multi_flat[position]), int(position))
    scan_order = sorted(first_seen, key=lambda label: first_seen[label])
    scipy_counts = [int((multi_labeled == label).sum()) for label in scan_order]

    meta_regions = multi_meta["regions"]
    meta_counts = [int(region["pixel_count"]) for region in meta_regions]
    kept_labels = [int(r["label"]) for r in meta_regions if r["expected_feature"]]
    dropped_counts = [int(r["pixel_count"]) for r in meta_regions if not r["expected_feature"]]

    # 用「像素数序列」比对顺序的前提是各区域像素数互不相同，否则序列相等
    # 不足以判定顺序相同。此处显式断言，避免夹具被改动后判据悄悄失效。
    if len(set(meta_counts)) != len(meta_counts):
        raise SystemExit("[夹具错误] 多区域夹具存在像素数相同的区域，无法据像素数序列判定顺序")

    # 三方对照：几何定义（元数据）↔ scipy ↔ 引擎。
    add(
        Check(
            "7.3",
            "夹具元数据顺序 == scipy 首次出现顺序",
            fmt(meta_counts),
            fmt(scipy_counts),
            meta_counts == scipy_counts,
            note="元数据由几何定义直接写出，与任何实现无关",
        )
    )

    multi_geojson = spatial.mask_to_geojson(multi_mask, multi_meta["geo_transform"])
    multi_features = json.loads(multi_geojson).get("features", [])
    engine_labels = [int(f["properties"]["label"]) for f in multi_features]
    engine_counts = [int(f["properties"]["pixel_count"]) for f in multi_features]
    expected_counts = [c for c in scipy_counts if c not in dropped_counts]

    add(
        Check(
            "7.3",
            "多区域 label 序列（与几何定义一致）",
            fmt(kept_labels),
            fmt(engine_labels),
            engine_labels == kept_labels,
            note=(
                f"连通域 {multi_components} 个，退化项 {len(dropped_counts)} 个"
                "（Phase 2.1 起一像素宽结构也是合法矩形，故无退化项）"
            ),
        )
    )
    add(
        Check(
            "7.3",
            "多区域 Feature 顺序 == scipy 顺序",
            fmt(expected_counts),
            fmt(engine_counts),
            engine_counts == expected_counts,
            note="期望顺序为各连通域首次出现的 raster-scan 位置序；旧实现用 unordered_map 分组，迭代序未定义（D-6）",
        )
    )

    # ------------------------------------------------- 几何合法性（GEOS 判定）
    # 引擎自己的 `forms_polygon` 只判「顶点数够且不共线」，那是 GEOS 要求的
    # 必要条件而非充分条件。真正的判据是让 GEOS 解析一遍：合法、不自交、
    # 面积为正、环的类型正确。
    try:
        from shapely.geometry import LineString
        from shapely.geometry import shape as shapely_shape
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            f"[依赖缺失] 几何合法性判据需要 shapely。\n  安装：uv sync --group dev\n  原因：{exc}"
        ) from exc

    audit_targets: list[tuple[str, list[dict[str, Any]]]] = [
        ("基线", features),
        ("多区域", multi_features),
    ]
    total_features = sum(len(items) for _, items in audit_targets)
    violations: list[str] = []
    hole_total = 0
    geometry_area = 0.0

    for tag, items in audit_targets:
        for position, feature in enumerate(items):
            label = feature.get("properties", {}).get("label", position)
            rings = feature.get("geometry", {}).get("coordinates", [])
            polygon = shapely_shape(feature["geometry"])
            hole_total += len(rings) - 1
            geometry_area += float(polygon.area)

            if polygon.geom_type != "Polygon":
                violations.append(f"{tag}[{label}] 类型为 {polygon.geom_type}")
            if not polygon.is_valid:
                violations.append(f"{tag}[{label}] GEOS 判 invalid")
            if polygon.area <= 0:
                violations.append(f"{tag}[{label}] 面积非正")
            for ring_index, ring in enumerate(rings):
                if not LineString(ring).is_simple:
                    violations.append(f"{tag}[{label}] 第 {ring_index} 环自交")

    reported_area = area_sum + sum(float(f["properties"]["area_m2"]) for f in multi_features)
    deviation = (geometry_area - reported_area) / reported_area * 100.0 if reported_area else 0.0

    add(
        Check(
            "7.3",
            "多边形可被 GEOS 解析且不自交",
            f"全部合法（{total_features} 个）",
            f"{total_features - len(violations)}/{total_features} 合法",
            not violations,
            note=(
                f"洞环合计 {hole_total} 个；几何面积合计 {fmt(geometry_area, 1)} m²，"
                f"上报面积合计 {fmt(reported_area, 1)} m²，偏差 {deviation:.2f}%"
                "（顶点取像素角点，故几何面积应等于 area_m2）"
                + ("；" + "；".join(violations[:3]) if violations else "")
            ),
        )
    )

    # ---------------------------------------------- 几何面积与上报面积一致
    #
    # Phase 2 的实现在像素中心取样，外环是内接多边形，几何面积恒**小于**
    # 上报的 area_m2 —— 偏差随区域变小而放大（实测基线 −2.93 %、多区域
    # −17.63 %、最小区域 −31.4 %）。Phase 2.1 改在像素边界取样后两者恒等。
    #
    # 本判据把「几何与 area_m2 一致」从文档声明变成可判定的性质：偏差一旦
    # 显著偏离 0（尤其回到负值），即说明追踪基准回退到像素中心。
    add(
        Check(
            "7.3",
            "几何面积 == 上报面积（像素角点基准）",
            f"偏差 0.00%（{fmt(reported_area, 1)} m²）",
            f"偏差 {deviation:.2f}%（{fmt(geometry_area, 1)} m²）",
            abs(deviation) <= GEOMETRY_TOL_PERCENT,
            note="几何面积由 shapely 独立算出，不依赖被测代码；差值为浮点表示级",
        )
    )

    # ============================================================ 输出
    phase = args.phase
    print()
    print("=" * 112)
    print(f"rschange 黄金基线校验  ·  仓库根 {REPO_ROOT}")
    print(f"引擎目录 {build_dir}")
    print(
        f"期望模式 {'Phase 1：§7.1 应通过，§7.2/7.3 应失败' if phase <= 1 else 'Phase 2+：全部应通过'}"
    )
    print("=" * 112)

    def pad(text: str, width: int) -> str:
        """按终端显示宽度左对齐补齐：CJK 字符占两列，超宽则截断。"""
        clipped = text
        display = 0
        for index, char in enumerate(text):
            display += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
            if display > width:
                clipped = text[:index]
                break
        return clipped + " " * max(0, width - display)

    print(
        pad("组", 5)
        + pad("判定项", 40)
        + pad("期望", 30)
        + pad("实际", 30)
        + pad("结果", 7)
        + "备注"
    )
    print("-" * 112)

    for check in checks:
        result = "SKIP" if check.skipped else ("PASS" if check.passed else "FAIL")
        print(
            pad(check.group, 5)
            + pad(check.name, 40)
            + pad(check.expected, 30)
            + pad(check.actual, 30)
            + pad(result, 7)
            + check.note
        )
    print("-" * 112)

    # 期望达成度：Phase 1 要求 §7.2/§7.3 失败；Phase >=2 要求全部通过
    def group_status(group: str) -> tuple[int, int]:
        items = [c for c in checks if c.group == group and not c.skipped]
        ok = sum(1 for c in items if c.passed)
        return ok, len(items)

    for group, label in (
        ("7.1", "§7.1 不变量"),
        ("7.2", "§7.2 缺陷基线"),
        ("7.3", "§7.3 语义断言"),
    ):
        ok, total = group_status(group)
        print(f"  {label:<18} {ok}/{total} 通过")

    ok71, total71 = group_status("7.1")
    ok72, total72 = group_status("7.2")
    ok73, total73 = group_status("7.3")

    if phase <= 1:
        satisfied = ok71 == total71 and ok72 == 0 and ok73 == 0
        expectation = "§7.1 全通过 且 §7.2/§7.3 全失败"
    else:
        satisfied = ok71 == total71 and ok72 == total72 and ok73 == total73
        expectation = "三项全部通过"

    print()
    print(f"期望：{expectation}")
    print(
        f"结论：{'通过 —— Phase ' + str(phase) + ' 预期状态已达成' if satisfied else '不通过 —— 与 Phase ' + str(phase) + ' 预期不符'}"
    )
    print()

    return 0 if satisfied else 1


if __name__ == "__main__":
    sys.exit(main())
