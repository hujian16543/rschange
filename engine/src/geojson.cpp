/// @file geojson.cpp
/// @brief 区域列表 → GeoJSON FeatureCollection（缺陷 D-3、D-7 的修复点）。
///
/// D-3：属性归属
/// -------------
/// 旧实现对**每一条环**各生成一个 Feature，并把 Region 级的 `pixel_count`、
/// `area_m2` 原样复制进每个 Feature 的 properties。一个 Region 若含 N 条环，
/// 它的面积就在输出里出现 N 次。
///
/// 基线样本正好踩中这个坑：单连通域的边界被 D-2 劈成 2 条弧，于是 720900 m²
/// 的真实面积在输出里合计成 1441800 m² —— 虚报整整一倍。
///
/// 修复采用标准 GeoJSON 语义：**一个 Region 一个 Feature**，其 Polygon 以首条
/// 环为外环、其余环为内环，properties 保持 Region 级且只出现一次。
///
/// D-7：退化轮廓
/// -------------
/// 轮廓不足以构成**有效**多边形时跳过该 Region，既不产出 Feature 也不抛异常。
/// 退化含两种情形：顶点少于 3；或顶点全部共线（有向面积为 0）。旧实现在
/// `pixels.size() < 3` 时返回含空环的容器，语义含糊，且没有覆盖共线这一情形——
/// 一像素宽的细长结构会产出面积为 0 的「多边形」，交给 GEOS 直接判 invalid。

#include "spatial/geojson.hpp"

#include <nlohmann/json.hpp>

#include <cstddef>
#include <string>
#include <utility>
#include <vector>

#include "spatial/contour.hpp"
#include "spatial/simplify.hpp"

namespace spatial {
namespace {

using Json = nlohmann::json;

/// 像素坐标 → 地理坐标（经度、纬度）。
std::pair<double, double> pixel_to_geo(int row, int col, const double geo_transform[6]) {
    const double lon = geo_transform[0] + (static_cast<double>(col) * geo_transform[1]) +
                       (static_cast<double>(row) * geo_transform[2]);
    const double lat = geo_transform[3] + (static_cast<double>(col) * geo_transform[4]) +
                       (static_cast<double>(row) * geo_transform[5]);
    return {lon, lat};
}

/// 环 → GeoJSON 坐标数组，并按 Polygon 约定补上闭合点（首点重复一次）。
Json ring_to_coordinates(const std::vector<PixelCoord>& ring, const double geo_transform[6]) {
    Json coordinates = Json::array();
    for (const auto& point : ring) {
        const auto [lon, lat] = pixel_to_geo(point.row, point.col, geo_transform);
        coordinates.push_back(Json::array({lon, lat}));
    }
    // 退化在调用方已经挡掉，此处只负责闭合
    if (!coordinates.empty() && coordinates.front() != coordinates.back()) {
        coordinates.push_back(coordinates.front());
    }
    return coordinates;
}

/// 闭合折线有向面积的两倍（鞋带公式）。
///
/// 顶点为整数像素坐标，故结果必为整数；等于 0 表示所有顶点共线，几何退化。
long long signed_area_twice(const std::vector<PixelCoord>& ring) {
    long long sum = 0;
    const std::size_t count = ring.size();
    for (std::size_t i = 0; i < count; ++i) {
        const PixelCoord& a = ring[i];
        const PixelCoord& b = ring[(i + 1) % count];
        sum += (static_cast<long long>(a.col) * b.row) - (static_cast<long long>(b.col) * a.row);
    }
    return sum;
}

/// 环是否足以构成有效多边形：顶点数够，且不共线。
///
/// 一像素宽的细长结构（例如 3x1 的竖条）按像素中心连成的环全部共线，
/// 有向面积为 0。这类几何不满足 OGC Simple Features 对 Polygon 的要求，
/// 交给 GEOS 会直接判 invalid，因此不进输出。
bool forms_polygon(const std::vector<PixelCoord>& ring) {
    return ring.size() >= 3 && signed_area_twice(ring) != 0;
}

}  // namespace

std::string regions_to_geojson(const std::vector<Region>& regions, const double geo_transform[6],
                               const GeoJsonOptions& options) {
    Json features = Json::array();

    for (const auto& region : regions) {
        const Boundary boundary = extract_boundary(region.pixels);
        if (!forms_polygon(boundary.outline)) {
            continue;  // D-7：轮廓退化，跳过该 Region
        }

        const auto outline = simplify_boundary(boundary.outline, options.simplify_tolerance);
        if (!forms_polygon(outline)) {
            continue;
        }

        Json rings = Json::array();
        rings.push_back(ring_to_coordinates(outline, geo_transform));

        for (const auto& hole : boundary.holes) {
            const auto simplified_hole = simplify_boundary(hole, options.simplify_tolerance);
            if (!forms_polygon(simplified_hole)) {
                continue;
            }
            rings.push_back(ring_to_coordinates(simplified_hole, geo_transform));
        }

        // 每个 Region 恰好产出一个 Feature，属性为 Region 级
        features.push_back(Json{
            {"type", "Feature"},
            {"geometry", Json{{"type", "Polygon"}, {"coordinates", std::move(rings)}}},
            {"properties",
             Json{{"label", region.label},
                  {"pixel_count", region.pixel_count},
                  {"area_m2", region.area_m2}}},
        });
    }

    const Json collection{
        {"type", "FeatureCollection"},
        {"features", std::move(features)},
    };
    return collection.dump();
}

}  // namespace spatial
