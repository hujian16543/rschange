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
    /// Douglas-Peucker 容差，像素单位。
    ///
    /// 默认 **0.0，即不简化**。轮廓在追踪阶段已合并共线步长，容差 0 下导出
    /// 的几何面积（像素单位）精确等于 `pixel_count`，乘单像元面积即 `area_m2`。
    /// 取正容差会换取更少的顶点，代价是几何面积不再等于 `area_m2`（实测圆盘
    /// 容差 1.0 时面积偏 +0.19 %，小区域偏差更大），故面积统计必须以
    /// `properties.area_m2` 为准。
    double simplify_tolerance = 0.0;
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
/// 几何基准（Phase 2.1）
/// -------------------
/// 多边形顶点是**像素角点**而非像素中心，故几何恰好铺满成员像素。`area_m2`
/// 仍是面积的权威值；容差 0 时两者在数值上一致（差异仅来自浮点表示）。
///
/// 跳过规则（D-7）
/// --------------
/// 轮廓退化的区域直接跳过，**不产出** Feature，也不抛异常。退化含两种情形：
///
/// * 顶点少于 3，无法构成多边形；
/// * 顶点全部共线（有向面积为 0）。
///
/// 自 Phase 2.1 起顶点取像素角点，一像素宽的细长结构（例如 1×5 的竖条）会
/// 得到合法的 1×5 矩形，**不再**属于退化情形；余下的退化来源是成员少于 3 个
/// 像素的区域（轮廓层即返回空环）。
///
/// 由此保证：输出的每一条几何都是合法的非退化多边形。
///
/// @throws std::runtime_error 仅在 JSON 序列化本身失败时抛出
SPATIAL_API std::string regions_to_geojson(const std::vector<Region>& regions,
                                           const double geo_transform[6],
                                           const GeoJsonOptions& options = {});

}  // namespace spatial
