/// @file test_pipeline.cpp
/// @brief 冻结夹具上的全链路测试：连通域 → 边界 → GeoJSON。
///
/// 这是 Phase 2 出口门 §7.2 的引擎侧判据。夹具 `change_mask.raw` 由冻结的
/// 参考实现在 `before.tif` / `after.tif` 上做 CVA + Otsu 得到，期望值一并
/// 记录在同目录的 `change_mask.json`，测试直接读该文件，不另抄一份常量。

#include <catch2/catch_test_macros.hpp>

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "fixture.hpp"
#include "spatial/contour.hpp"
#include "spatial/geojson.hpp"
#include "spatial/labeling.hpp"
#include "spatial/region.hpp"

namespace {

using Json = nlohmann::json;

/// §7.2 的验收锚点：旧实现在同一夹具上产出 2 个 Feature、面积合计 1441800。
constexpr int kExpectedFeatureCount = 1;
constexpr double kExpectedAreaM2 = 720900.0;
constexpr int kLegacyFeatureCount = 2;
constexpr double kLegacyAreaM2 = 1441800.0;

void copy_geo(const Json& source, double (&target)[6]) {
    REQUIRE(source.size() == 6);
    for (std::size_t i = 0; i < 6; ++i) {
        target[i] = source.at(i).get<double>();
    }
}

double area_sum(const Json& collection) {
    double total = 0.0;
    for (const auto& feature : collection.at("features")) {
        total += feature.at("properties").at("area_m2").get<double>();
    }
    return total;
}

}  // namespace

// 冻结夹具的全链路结果
TEST_CASE("pipeline: frozen fixture end-to-end result", "[pipeline]") {
    const Json meta = fixture::read_json("change_mask.json");
    const int width = meta.at("width").get<int>();
    const int height = meta.at("height").get<int>();
    const int expected_pixels = meta.at("changed_pixels").get<int>();
    const int expected_components = meta.at("components").get<int>();

    double geo[6] = {};
    copy_geo(meta.at("geo_transform"), geo);

    const std::vector<std::uint8_t> mask = fixture::read_bytes("change_mask.raw");
    REQUIRE(mask.size() == static_cast<std::size_t>(width) * height);

    // --- 连通域 ---
    std::size_t nonzero = 0;
    for (const auto value : mask) {
        if (value != 0) {
            ++nonzero;
        }
    }
    CHECK(nonzero == static_cast<std::size_t>(expected_pixels));

    const auto regions = spatial::extract_regions(mask.data(), width, height, geo);
    REQUIRE(regions.size() == static_cast<std::size_t>(expected_components));

    int pixel_total = 0;
    double area_total = 0.0;
    for (const auto& region : regions) {
        pixel_total += region.pixel_count;
        area_total += region.area_m2;
    }
    CHECK(pixel_total == expected_pixels);
    CHECK(area_total == meta.at("area_m2").get<double>());

    // --- 边界（D-2 的直接证据）---
    // 单连通域必须只追踪出一条闭合外环。旧实现因起点未入 visited、扫描方向
    // 未携带，把同一条边界劈成 2 段互不相接的弧。
    for (const auto& region : regions) {
        const spatial::Boundary boundary = spatial::extract_boundary(region.pixels);
        REQUIRE_FALSE(boundary.outline.empty());
        CHECK(boundary.outline.size() >= 3);
        CHECK(boundary.outline.front() != boundary.outline.back());
        CHECK(boundary.holes.empty());
    }

    // --- GeoJSON（§7.2 判据）---
    const Json collection = Json::parse(spatial::regions_to_geojson(regions, geo));
    const auto& features = collection.at("features");

    CHECK(features.size() == static_cast<std::size_t>(kExpectedFeatureCount));
    CHECK(features.size() != static_cast<std::size_t>(kLegacyFeatureCount));
    CHECK(area_sum(collection) == kExpectedAreaM2);
    CHECK(area_sum(collection) != kLegacyAreaM2);

    // Region 级属性只出现一次：Feature 数与 Region 数相等即为该性质的判据。
    CHECK(features.size() == regions.size());

    for (const auto& feature : features) {
        CHECK(feature.at("geometry").at("type") == "Polygon");
        CHECK(feature.at("properties").at("pixel_count").get<int>() == expected_pixels);
    }
}

// 全链路结果可重复
TEST_CASE("pipeline: end-to-end result is reproducible", "[pipeline]") {
    const Json meta = fixture::read_json("change_mask.json");
    const int width = meta.at("width").get<int>();
    const int height = meta.at("height").get<int>();

    double geo[6] = {};
    copy_geo(meta.at("geo_transform"), geo);

    const std::vector<std::uint8_t> mask = fixture::read_bytes("change_mask.raw");

    const std::string first = spatial::regions_to_geojson(
        spatial::extract_regions(mask.data(), width, height, geo), geo);

    for (int attempt = 0; attempt < 8; ++attempt) {
        const std::string again = spatial::regions_to_geojson(
            spatial::extract_regions(mask.data(), width, height, geo), geo);
        CHECK(again == first);
    }
}
