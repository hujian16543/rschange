#!/usr/bin/env python
"""生成多区域冻结夹具 `multi_region_mask.raw` 与 `multi_region_mask.json`。

用途
----
基线夹具 `change_mask.raw` 只有**一个**连通域，因此无法覆盖两类语义：

1. `extract_regions` 的 label 分配顺序（缺陷 D-6：旧实现用 `unordered_map`
   分组，迭代序未定义，跨平台结果不同）；
2. 多区域时的「Feature 数 == 连通域数」「每个 Region 恰好一个 Feature」，
   以及退化区域被剔除后 label 出现缺口的行为（缺陷 D-7）。

本脚本产出一份**几何完全人工指定**的掩膜，同时把逐区域的期望值写进 JSON。
期望值来自几何定义本身，不来自任何引擎实现，因此可作为独立对照基准。

夹具布局（宽 120、高 64，刻意取非方形）
--------------------------------------
| 编号 | 名称   | 几何                        | 像素 | 首次出现       |
|------|--------|-----------------------------|------|----------------|
| 1    | blob_a | 行 4..13, 列 6..15          | 100  | (4, 6)         |
| 2    | blob_b | 行 6..15, 列 40..59         | 200  | (6, 40)        |
| 3    | blob_f | 行 26..30, 列 8..14         | 35   | (26, 8)        |
| 4    | blob_c | 行 26..31, 列 96..118       | 138  | (26, 96)       |
| 5    | ring_d | 行 40..53, 列 20..34 挖洞   | 185  | (40, 20)       |
| 6    | line_e | 行 56..60, 列 100 (1 像素宽) | 5    | (56, 100)      |

**各区域像素数必须两两不同。** 判定顺序时用的观测值是「Feature 的像素数序列」，
若两个区域像素数相同，交换它们的位置不会改变该序列，判据随之失效。生成脚本
与验收工具都会对这一点显式断言，避免夹具被改动后判据悄悄退化。

两处刻意设计
------------
* **blob_f 与 blob_c 的首次出现位于同一行 26。** 这使顺序不能只按行号判定，
  必须真正按 raster-scan 的 (行, 列) 字典序 —— 列 8 的 blob_f 先于列 96 的
  blob_c。若实现退回 `unordered_map` 迭代序，此判据随即失败。
* **line_e 是一像素宽的竖条。** 按像素中心连成的环全部共线、有向面积为 0，
  属 D-7 定义的退化轮廓，`regions_to_geojson` 必须跳过它。于是本夹具上
  `Feature 数 = 连通域数 - 退化区域数 = 6 - 1 = 5`，且 label 序列为
  `1,2,3,4,5`（被剔除的 label 6 留下一个末端缺口）。
  与之对照，ring_d 的洞**不**产生额外 Feature —— 洞是同一个 Feature 的内环。

用法
----
    uv run python scripts/make_multi_region_fixture.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "engine" / "tests" / "fixtures"

WIDTH = 120
HEIGHT = 64

# 与基线夹具保持同一套坐标参数，便于两个夹具互相印证。
GEO_TRANSFORM = [500000.0, 10.0, 0.0, 4000000.0, 0.0, -10.0]
PIXEL_AREA_M2 = abs(GEO_TRANSFORM[1] * GEO_TRANSFORM[5])
SIMPLIFY_TOLERANCE = 2.0  # GeoJsonOptions 的默认值

Rect = tuple[int, int, int, int]  # (row0, row1, col0, col1)，闭区间

LAYOUT: list[dict[str, object]] = [
    {"name": "blob_a", "kind": "solid", "rect": (4, 13, 6, 15)},
    {"name": "blob_b", "kind": "solid", "rect": (6, 15, 40, 59)},
    {"name": "blob_f", "kind": "solid", "rect": (26, 30, 8, 14)},
    {"name": "blob_c", "kind": "solid", "rect": (26, 31, 96, 118)},
    {
        "name": "ring_d",
        "kind": "ring",
        "rect": (40, 53, 20, 34),
        "hole": (45, 49, 25, 29),
    },
    {"name": "line_e", "kind": "degenerate_line", "rect": (56, 60, 100, 100)},
]


def painted_cells(entry: dict[str, object]) -> list[tuple[int, int]]:
    """列出该区域实际着色的像素，按 raster-scan 顺序。"""
    row0, row1, col0, col1 = entry["rect"]  # type: ignore[misc]
    hole = entry.get("hole")
    cells: list[tuple[int, int]] = []
    for row in range(row0, row1 + 1):
        for col in range(col0, col1 + 1):
            if hole is not None:
                hr0, hr1, hc0, hc1 = hole  # type: ignore[misc]
                if hr0 <= row <= hr1 and hc0 <= col <= hc1:
                    continue
            cells.append((row, col))
    return cells


def main() -> int:
    mask = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    regions: list[dict[str, object]] = []

    painted = [(entry, painted_cells(entry)) for entry in LAYOUT]

    # label 按各区域首次出现的 raster-scan 位置 (行, 列) 排序 —— 这正是引擎
    # 承诺的顺序。此处独立排序，而非按 LAYOUT 的书写顺序。
    ordered = sorted(painted, key=lambda item: item[1][0])

    for label, (entry, cells) in enumerate(ordered, start=1):
        for row, col in cells:
            mask[row, col] = 1
        first_row, first_col = cells[0]
        regions.append(
            {
                "label": label,
                "name": entry["name"],
                "kind": entry["kind"],
                "first_row": first_row,
                "first_col": first_col,
                "first_index": first_row * WIDTH + first_col,
                "pixel_count": len(cells),
                "holes": 1 if entry["kind"] == "ring" else 0,
                "expected_feature": entry["kind"] != "degenerate_line",
            }
        )

    degenerate = [r for r in regions if not r["expected_feature"]]
    with_feature = [r for r in regions if r["expected_feature"]]

    changed_pixels = int(mask.sum())
    expected_pixels_in_features = sum(int(r["pixel_count"]) for r in with_feature)

    # 一致性自检：布局定义与落盘内容必须互相对应，避免手写布局出错。
    assert changed_pixels == sum(int(r["pixel_count"]) for r in regions), "着色像素数与布局不符"
    assert len(regions) == len(LAYOUT), "区域数与布局不符"
    assert mask.dtype == np.uint8

    # 判定顺序所用的观测值是「Feature 的像素数序列」。两个区域像素数相同即
    # 交换位置后观测值不变，判据失效，故此处直接拒绝这种布局。
    counts_seen = [int(r["pixel_count"]) for r in regions]
    assert len(set(counts_seen)) == len(counts_seen), f"各区域像素数必须两两不同，实得 {counts_seen}"

    meta = {
        "width": WIDTH,
        "height": HEIGHT,
        "dtype": "uint8",
        "provenance": (
            "由 scripts/make_multi_region_fixture.py 依 LAYOUT 人工指定几何生成。"
            "期望值来自几何定义本身，与任何引擎实现无关，故可作独立对照基准。"
        ),
        "geo_transform": GEO_TRANSFORM,
        "pixel_area_m2": PIXEL_AREA_M2,
        "simplify_tolerance": SIMPLIFY_TOLERANCE,
        "changed_pixels": changed_pixels,
        "components": len(regions),
        "degenerate_components": len(degenerate),
        "expected_feature_count": len(with_feature),
        "expected_pixels_in_features": expected_pixels_in_features,
        "expected_area_m2": expected_pixels_in_features * PIXEL_AREA_M2,
        "expected_holes_total": sum(int(r["holes"]) for r in with_feature),
        "note": (
            "label 顺序必须等于各区域首次出现位置 (first_row, first_col) 的字典序。"
            "blob_f 与 blob_c 首次出现同行，故顺序由列号决定：blob_f 在前。"
            "line_e 为退化轮廓，必须被剔除，因此 Feature 数为 "
            f"{len(with_feature)} 而连通域数为 {len(regions)}。"
        ),
        "regions": regions,
    }

    FIXTURES.mkdir(parents=True, exist_ok=True)
    raw_path = FIXTURES / "multi_region_mask.raw"
    json_path = FIXTURES / "multi_region_mask.json"

    raw_path.write_bytes(mask.tobytes(order="C"))
    json_path.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"[写入] {raw_path}  ({raw_path.stat().st_size} 字节)")
    print(f"[写入] {json_path}")
    print(f"       连通域 {len(regions)} 个 / 退化 {len(degenerate)} 个 / Feature {len(with_feature)} 个")
    print(f"       着色像素 {changed_pixels} / 计入 Feature 的像素 {expected_pixels_in_features}")
    for entry in regions:
        mark = "产出 Feature" if entry["expected_feature"] else "剔除（退化）"
        print(
            f"       label={entry['label']}  {entry['name']:<7} "
            f"首像素=({entry['first_row']},{entry['first_col']})  "
            f"{entry['pixel_count']:>4} px  洞={entry['holes']}  {mark}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
