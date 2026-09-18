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

用法
----
    uv run python scripts/verify_baseline.py --phase 1
    uv run python scripts/verify_baseline.py --phase 2 --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

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
# §7.2 现状值（旧引擎的实际输出，均为缺陷产物）
LEGACY_FEATURE_COUNT: Final = 2
LEGACY_AREA_SUM: Final = 1441800.0
# §7.2 修复目标
TARGET_FEATURE_COUNT: Final = 1
TARGET_AREA_SUM: Final = 720900.0


# ============================================================================
# 配置载入
# ============================================================================


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict[str, Any]:
    """优先级：RSCHANGE_<SECTION>__<KEY> > config/local.toml > config/default.toml"""
    config: dict[str, Any] = {}
    for name in ("default.toml", "local.toml"):
        path = REPO_ROOT / "config" / name
        if path.is_file():
            with path.open("rb") as handle:
                config = _deep_merge(config, tomllib.load(handle))

    prefix = "RSCHANGE_"
    for env_key, raw in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        parts = env_key[len(prefix) :].split("__")
        if len(parts) != 2:
            continue
        section, key = parts[0].lower(), parts[1].lower()
        value: Any = raw
        lowered = raw.lower()
        if lowered in ("true", "false"):
            value = lowered == "true"
        else:
            try:
                value = int(raw)
            except ValueError:
                pass
        config.setdefault(section, {})[key] = value

    return config


def resolve_path(raw: str) -> Path:
    """相对路径按仓库根解析；空字符串返回仓库根。"""
    if not raw:
        return REPO_ROOT
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def load_spatial(config: dict[str, Any]) -> tuple[Any, Path]:
    """按配置定位并加载 _spatial 扩展。"""
    engine = config.get("engine", {})
    dll_dir = resolve_path(str(engine.get("runtime_dll_dir") or ""))
    build_dir = resolve_path(str(engine.get("build_dir") or ""))

    if not build_dir.is_dir():
        raise SystemExit(
            f"[配置错误] engine.build_dir 不存在：{build_dir}\n"
            "  请检查 config/local.toml。Phase 1 应指向旧仓库的 build 目录。"
        )

    if os.name == "nt":
        if dll_dir.is_dir():
            os.add_dll_directory(str(dll_dir))
        else:
            print(f"[警告] engine.runtime_dll_dir 不是有效目录，已跳过：{dll_dir}")
        os.add_dll_directory(str(build_dir))

    if str(build_dir) not in sys.path:
        sys.path.insert(0, str(build_dir))

    try:
        import _spatial  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            f"[加载失败] 无法 import _spatial（目录：{build_dir}）\n  原因：{exc}"
        ) from exc

    return _spatial, build_dir


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


def main() -> int:  # noqa: C901
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

    baseline_cfg = config.get("baseline", {})
    fixtures_dir = resolve_path(str(baseline_cfg.get("fixtures_dir") or ""))
    before_path = fixtures_dir / "before.tif"
    after_path = fixtures_dir / "after.tif"

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
    add(Check("7.1", "宽/高/波段", "256/256/3", f"{width}/{height}/{bands}",
              (width, height, bands) == (256, 256, 3)))

    # -------------------------------------------------------------- 算法链路
    threshold, change_mask = frozen_cva(before, after)
    clean_mask = frozen_postprocess(change_mask)

    raw_changed = int(change_mask.sum())
    clean_changed = int(clean_mask.sum())

    record("7.1", "Otsu 阈值", EXPECTED_THRESHOLD, threshold,
           abs(threshold - EXPECTED_THRESHOLD) <= THRESHOLD_TOL)
    record("7.1", "变化像素（原始）", EXPECTED_CHANGED_RAW, raw_changed,
           raw_changed == EXPECTED_CHANGED_RAW)
    record("7.1", "变化像素（后处理后）", EXPECTED_CHANGED_CLEAN, clean_changed,
           clean_changed == EXPECTED_CHANGED_CLEAN)
    expected_rate = EXPECTED_CHANGED_CLEAN / TOTAL_PIXELS
    actual_rate = clean_changed / TOTAL_PIXELS
    add(Check("7.1", "变化率", fmt(expected_rate, 6), fmt(actual_rate, 6),
              abs(actual_rate - expected_rate) <= RATE_TOL))
    add(Check("7.1", "真实变化面积 m²", fmt(EXPECTED_TRUE_AREA, 1),
              fmt(clean_changed * PIXEL_AREA_M2, 1),
              abs(clean_changed * PIXEL_AREA_M2 - EXPECTED_TRUE_AREA) <= AREA_TOL))

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
    add(Check("7.2", "GeoJSON Feature 个数", str(TARGET_FEATURE_COUNT), str(n_features),
              n_features == TARGET_FEATURE_COUNT,
              note=f"旧引擎实际输出 {LEGACY_FEATURE_COUNT}（缺陷：单连通域被劈成多段弧）"))
    add(Check("7.2", "属性面积合计 m²", fmt(TARGET_AREA_SUM, 1), fmt(area_sum, 1),
              abs(area_sum - TARGET_AREA_SUM) <= AREA_TOL,
              note=f"旧引擎实际输出 {LEGACY_AREA_SUM:.1f}（缺陷：面积重复计 2 倍）"))

    # -------------------------------------------------------------- §7.3 语义
    add(Check("7.3", "Feature 数 == 连通域个数",
              str(n_components), str(n_features),
              n_features == n_components,
              note="连通域个数由 scipy 独立计算，不依赖被测代码"))
    expected_area_sem = clean_changed * PIXEL_AREA_M2
    add(Check("7.3", "面积合计 == 像素数 × 单像元面积",
              fmt(expected_area_sem, 1), fmt(area_sum, 1),
              abs(area_sum - expected_area_sem) <= AREA_TOL))
    add(Check("7.3", "多区域 label 分配顺序确定", "—", "—", False, skipped=True,
              note="当前 fixture 为单连通域，无法覆盖；Phase 2 补多区域样本后启用"))
    add(Check("7.3", "多边形可被 GEOS 解析且不自交", "—", "—", False, skipped=True,
              note="需 shapely，Phase 2 引入后启用；环闭合本身已归入 §7.1 不变量"))

    # ============================================================ 输出
    phase = args.phase
    print()
    print("=" * 108)
    print(f"rschange 黄金基线校验  ·  仓库根 {REPO_ROOT}")
    print(f"引擎目录 {build_dir}")
    print(f"期望模式 {'Phase 1：§7.1 应通过，§7.2/7.3 应失败' if phase <= 1 else 'Phase 2+：全部应通过'}")
    print("=" * 108)
    print(f"{'组':<5}{'判定项':<38}{'期望':<26}{'实际':<26}{'结果':<6}备注")
    print("-" * 108)

    for check in checks:
        if check.skipped:
            result = "SKIP"
        else:
            result = "PASS" if check.passed else "FAIL"
        name = check.name[:36]
        exp = check.expected[:24]
        act = check.actual[:24]
        print(f"{check.group:<5}{name:<38}{exp:<26}{act:<26}{result:<6}{check.note}")
    print("-" * 108)

    # 期望达成度：Phase 1 要求 §7.2/§7.3 失败；Phase >=2 要求全部通过
    def group_status(group: str) -> tuple[int, int]:
        items = [c for c in checks if c.group == group and not c.skipped]
        ok = sum(1 for c in items if c.passed)
        return ok, len(items)

    for group, label in (("7.1", "§7.1 不变量"), ("7.2", "§7.2 缺陷基线"), ("7.3", "§7.3 语义断言")):
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
    print(f"结论：{'通过 —— Phase ' + str(phase) + ' 预期状态已达成' if satisfied else '不通过 —— 与 Phase ' + str(phase) + ' 预期不符'}")
    print()

    return 0 if satisfied else 1


if __name__ == "__main__":
    sys.exit(main())
