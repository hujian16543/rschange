#pragma once

/// @file geojson.hpp
/// @brief 区域列表 → GeoJSON FeatureCollection。

#include <string>
#include <vector>

#include "spatial/export.hpp"
#include "spatial/region.hpp"

namespace spatial {

/// GeoJSON 导出选项。
struct GeoJsonOptions {
    double simplify_tolerance = 2.0;  ///< Douglas-Peucker 容差，像素单位
};

/// 区域列表 → GeoJSON `FeatureCollection` 字符串。
///
/// 归属语义（D-3）
/// --------------
/// **每个 `Region` 恰好产出一个 `Feature`。** 该 Feature 的 Polygon 以第一条
/// 环为外环、其余环为洞环；`properties` 是 Region 级的，不随环数重复。
///
/// 旧实现让每个环各自成为一个 Feature，并把 Region 级的 `pixel_count` /
/// `area_m2` 复制进每一个环的属性里。一个 Region 若含 N 条环，其面积就被
/// 重复计 N 次——基线样本（单连通域被劈成 2 段弧）实测面积合计
/// `1441800 m²`，是真实值 `720900 m²` 的 2 倍。
///
/// 跳过规则（D-7）
/// --------------
/// 轮廓退化（顶点少于 3、或简化后不足以构成多边形）的区域直接跳过，
/// **不产出** Feature，也不抛异常。
///
/// @throws std::runtime_error 仅在 JSON 序列化本身失败时抛出
SPATIAL_API std::string regions_to_geojson(const std::vector<Region>& regions,
                                           const double geo_transform[6],
                                           const GeoJsonOptions& options = {});

}  // namespace spatial
