/// @file test_geojson.cpp
/// @brief GeoJSON 导出的归属语义（D-3）与退化几何过滤（D-7），以及像素到
///        地理坐标的换算。

#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include "spatial/geojson.hpp"
#include "spatial/labeling.hpp"
#include "spatial/region.hpp"

namespace {

using Coord = spatial::PixelCoord;
using Json = nlohmann::json;

constexpr double kGeo[6] = {500000.0, 10.0, 0.0, 4000000.0, 0.0, -10.0};
constexpr double kPixelAreaM2 = 100.0;

spatial::Region make_region(int label, const std::vector<Coord>& pixels) {
    spatial::Region region;
    region.label = label;
    region.pixel_count = static_cast<int>(pixels.size());
    region.area_m2 = static_cast<double>(pixels.size()) * kPixelAreaM2;
    region.pixels = pixels;
    return region;
}

std::vector<Coord> make_block(int row0, int col0, int rows, int cols) {
    std::vector<Coord> pixels;
    for (int r = row0; r < row0 + rows; ++r) {
        for (int c = col0; c < col0 + cols; ++c) {
            pixels.push_back(Coord{r, c});
        }
    }
    return pixels;
}

std::vector<Coord> make_block_with_hole(int row0, int col0, int rows, int cols, int hole_row,
                                        int hole_col) {
    auto pixels = make_block(row0, col0, rows, cols);
    std::vector<Coord> kept;
    for (const auto& p : pixels) {
        if (!(p.row == hole_row && p.col == hole_col)) {
            kept.push_back(p);
        }
    }
    return kept;
}

Json parse(const std::string& text) {
    return Json::parse(text);
}

double area_sum(const Json& collection) {
    double total = 0.0;
    for (const auto& feature : collection.at("features")) {
        total += feature.at("properties").at("area_m2").get<double>();
    }
    return total;
}

/// 一条 GeoJSON 环的几何面积（鞋带公式，顶点为 [lon, lat]）。
///
/// 测试侧独立实现，不调用引擎的 `signed_area_twice`。本夹具的几何变换是
/// `(10, -10)` 的均匀缩放，故经纬度平面上的面积与像素平面上的面积只相差
/// 一个 `|10 * -10| = 100` 的因子，可直接与 `area_m2` 比对。
double ring_area(const Json& ring) {
    double sum = 0.0;
    const std::size_t count = ring.size();
    for (std::size_t i = 0; i < count; ++i) {
        const double x0 = ring.at(i).at(0).get<double>();
        const double y0 = ring.at(i).at(1).get<double>();
        const double x1 = ring.at((i + 1) % count).at(0).get<double>();
        const double y1 = ring.at((i + 1) % count).at(1).get<double>();
        sum += (x0 * y1) - (x1 * y0);
    }
    return std::abs(sum) / 2.0;
}

/// Feature 的净几何面积：外环面积减去洞环面积。
double feature_area(const Json& feature) {
    const auto& rings = feature.at("geometry").at("coordinates");
    double total = ring_area(rings.at(0));
    for (std::size_t i = 1; i < rings.size(); ++i) {
        total -= ring_area(rings.at(i));
    }
    return total;
}

/// 几何面积与期望值是否一致。
///
/// 不能用严格相等：顶点是经纬度形式，量级为 5e5 × 4e6，双精度乘积的绝对
/// 误差约 1e-4 m²。容差取「相对 1e-6 + 绝对 1e-2」，对最小区域（500 m²）
/// 仍是 2e-5 的相对量级 —— 远小于任何几何基准偏差（旧基准 ≥ 2.9 %），
/// 故判据不失锐利。
bool area_equals(double actual, double expected) {
    return std::abs(actual - expected) <= (1e-6 * expected) + 1e-2;
}

}  // namespace

// 每个 Region 恰好一个 Feature（D-3）
TEST_CASE("geojson: exactly one Feature per Region (D-3)", "[geojson]") {
    const std::vector<spatial::Region> regions = {make_region(1, make_block(10, 20, 3, 3))};
    const Json collection = parse(spatial::regions_to_geojson(regions, kGeo));

    CHECK(collection.at("type") == "FeatureCollection");
    REQUIRE(collection.at("features").size() == 1);

    const auto& feature = collection.at("features").front();
    CHECK(feature.at("type") == "Feature");
    CHECK(feature.at("geometry").at("type") == "Polygon");
    CHECK(feature.at("properties").at("label") == 1);
    CHECK(feature.at("properties").at("pixel_count") == 9);
    CHECK(feature.at("properties").at("area_m2").get<double>() == 9 * kPixelAreaM2);
}

// 多个 Region 时属性不重复计入
TEST_CASE("geojson: properties are not double counted across Regions", "[geojson]") {
    const std::vector<spatial::Region> regions = {
        make_region(1, make_block(10, 20, 3, 3)),
        make_region(2, make_block(40, 60, 4, 5)),
    };
    const Json collection = parse(spatial::regions_to_geojson(regions, kGeo));

    REQUIRE(collection.at("features").size() == 2);
    CHECK(area_sum(collection) == (9.0 + 20.0) * kPixelAreaM2);
}

// 带洞 Region 仍是单 Feature，洞作为内环
TEST_CASE("geojson: a holed Region stays one Feature with the hole as an inner ring", "[geojson]") {
    const std::vector<spatial::Region> regions = {
        make_region(1, make_block_with_hole(0, 0, 5, 5, 2, 2)),
    };
    const Json collection = parse(spatial::regions_to_geojson(regions, kGeo));

    REQUIRE(collection.at("features").size() == 1);
    const auto& coordinates = collection.at("features").front().at("geometry").at("coordinates");
    REQUIRE(coordinates.size() == 2);

    // 面积只按 Region 计一次，与环数无关。
    // 旧实现让每个环各成一个 Feature，并把 Region 级面积复制进去，含 N 条环
    // 的 Region 面积即被计 N 次。
    CHECK(area_sum(collection) == collection.at("features")
                                       .front()
                                       .at("properties")
                                       .at("area_m2")
                                       .get<double>());
}

// 环按 Polygon 约定闭合
TEST_CASE("geojson: rings are closed per the Polygon convention", "[geojson]") {
    const std::vector<spatial::Region> regions = {
        make_region(1, make_block_with_hole(0, 0, 5, 5, 2, 2)),
    };
    const Json collection = parse(spatial::regions_to_geojson(regions, kGeo));
    const auto& rings = collection.at("features").front().at("geometry").at("coordinates");

    for (const auto& ring : rings) {
        REQUIRE(ring.size() >= 4);
        CHECK(ring.front() == ring.back());
    }
}

// 像素坐标换算为经纬度
TEST_CASE("geojson: pixel coordinates are converted to geographic coordinates", "[geojson]") {
    const std::vector<spatial::Region> regions = {make_region(1, make_block(10, 20, 3, 3))};
    const Json collection = parse(spatial::regions_to_geojson(regions, kGeo));

    const auto& ring =
        collection.at("features").front().at("geometry").at("coordinates").front();

    // 仿射变换：lon = gt0 + col*gt1 + row*gt2，lat = gt3 + col*gt4 + row*gt5。
    //
    // 顶点是角点格点：3x3 方块占据像素行 10..12、列 20..22，其边界格点因此
    // 跨行 10..13、列 20..23 —— 比像素下标多一行一列，这正是「格点在像素左上角」
    // 的直接体现。若沿用像素中心，上界会少一列一行。
    const double expected_x_min = kGeo[0] + 20 * kGeo[1];
    const double expected_x_max = kGeo[0] + 23 * kGeo[1];
    const double expected_y_min = kGeo[3] + 13 * kGeo[5];
    const double expected_y_max = kGeo[3] + 10 * kGeo[5];

    double min_x = 1e18;
    double max_x = -1e18;
    double min_y = 1e18;
    double max_y = -1e18;
    for (const auto& point : ring) {
        REQUIRE(point.size() == 2);
        const double x = point.at(0).get<double>();
        const double y = point.at(1).get<double>();
        min_x = std::min(min_x, x);
        max_x = std::max(max_x, x);
        min_y = std::min(min_y, y);
        max_y = std::max(max_y, y);
    }

    CHECK(min_x == expected_x_min);
    CHECK(max_x == expected_x_max);
    CHECK(min_y == expected_y_min);
    CHECK(max_y == expected_y_max);

    // 格点坐标与 geo_transform 一致：格点 (r, c) 的地理位置即 geo[0] + c*gt1
    // 与 geo[3] + r*gt5，故多边形恰好铺满像素 (10..12, 20..22) 的并集。
    CHECK(area_equals(ring_area(ring), 9 * kPixelAreaM2));
}

// 退化轮廓不产出 Feature（D-7）
TEST_CASE("geojson: degenerate contours produce no Feature (D-7)", "[geojson]") {
    SECTION("成员不足 3 个像素") {
        const std::vector<spatial::Region> regions = {
            make_region(1, {Coord{4, 4}, Coord{4, 5}}),
        };
        const Json collection = parse(spatial::regions_to_geojson(regions, kGeo));
        CHECK(collection.at("features").empty());
    }

    SECTION("一像素宽的细长结构：在像素边界基准下是合法矩形") {
        // Phase 2 的实现在像素中心取样，一像素宽竖条的环全部共线、有向面积为 0，
        // 属 D-7 定义的退化轮廓，必须跳过。改在像素边界取样后它是 1x3 的矩形，
        // 面积恰为 3 个像元 —— 不再是退化几何，必须产出 Feature。
        const std::vector<spatial::Region> regions = {
            make_region(1, {Coord{4, 4}, Coord{5, 4}, Coord{6, 4}}),
            make_region(2, make_block(10, 10, 3, 3)),
        };
        const Json collection = parse(spatial::regions_to_geojson(regions, kGeo));
        REQUIRE(collection.at("features").size() == 2);

        const auto& narrow = collection.at("features").front();
        CHECK(narrow.at("properties").at("label") == 1);
        CHECK(area_equals(feature_area(narrow), 3 * kPixelAreaM2));
    }

    SECTION("退化判据仍然生效：成员数为 1 或 2 的区域一律跳过") {
        const std::vector<spatial::Region> regions = {
            make_region(1, {Coord{4, 4}}),
            make_region(2, {Coord{4, 4}, Coord{5, 4}}),
            make_region(3, make_block(10, 10, 3, 3)),  // 同批次里仍须产出合法几何
        };
        const Json collection = parse(spatial::regions_to_geojson(regions, kGeo));
        REQUIRE(collection.at("features").size() == 1);
        CHECK(collection.at("features").front().at("properties").at("label") == 3);
    }
}

// 几何面积精确等于 area_m2（Phase 2.1 的几何基准）
TEST_CASE("geojson: geometric area equals area_m2 exactly (Phase 2.1 invariant)", "[geojson]") {
    // Phase 2 取像素中心，外环是内接多边形，几何面积恒小于 area_m2（实测基线
    // −2.93 %、多区域 −17.63 %、最小区域 −31.4 %）。改在像素边界取样后两者
    // 相等：环围出的多边形恰好等于成员像素的并集。
    //
    // 覆盖三类几何：实心块、带洞块、凹形（十字）。凹形是关键 —— 内接多边形
    // 在凹角处的缺口最大，正是旧偏差的主要来源。
    const std::size_t tile_pixels = 9;

    SECTION("实心块") {
        const std::vector<spatial::Region> regions = {
            make_region(1, make_block(10, 20, 3, 3)),
        };
        const Json collection = parse(spatial::regions_to_geojson(regions, kGeo));
        REQUIRE(collection.at("features").size() == 1);
        CHECK(area_equals(feature_area(collection.at("features").front()),
                          static_cast<double>(tile_pixels) * kPixelAreaM2));
    }

    SECTION("带洞块：净面积扣除洞环") {
        const std::vector<spatial::Region> regions = {
            make_region(1, make_block_with_hole(0, 0, 5, 5, 2, 2)),
        };
        const Json collection = parse(spatial::regions_to_geojson(regions, kGeo));
        REQUIRE(collection.at("features").size() == 1);
        CHECK(area_equals(feature_area(collection.at("features").front()), 24 * kPixelAreaM2));
    }

    SECTION("凹形（十字）：凹角处不留缺口") {
        std::vector<Coord> plus;
        for (int r = 0; r < 5; ++r) {
            plus.push_back(Coord{r, 2});
        }
        for (int c = 0; c < 5; ++c) {
            if (c != 2) {
                plus.push_back(Coord{2, c});
            }
        }

        const std::vector<spatial::Region> regions = {make_region(1, plus)};
        const Json collection = parse(spatial::regions_to_geojson(regions, kGeo));
        REQUIRE(collection.at("features").size() == 1);
        CHECK(area_equals(feature_area(collection.at("features").front()), 9 * kPixelAreaM2));
    }
}

// 端到端：掩膜经连通域与边界追踪后导出
TEST_CASE("geojson: end to end, mask to regions to traced rings to GeoJSON", "[geojson]") {
    const int width = 32;
    const int height = 32;
    std::vector<std::uint8_t> mask(static_cast<std::size_t>(width) * height, 0);
    for (int r = 6; r < 12; ++r) {
        for (int c = 6; c < 12; ++c) {
            mask[static_cast<std::size_t>(r) * width + c] = 1;
        }
    }

    const auto regions = spatial::extract_regions(mask.data(), width, height, kGeo);
    REQUIRE(regions.size() == 1);

    const Json collection = parse(spatial::regions_to_geojson(regions, kGeo));
    REQUIRE(collection.at("features").size() == 1);
    CHECK(collection.at("features").front().at("properties").at("pixel_count") == 36);
    CHECK(area_sum(collection) == 36 * kPixelAreaM2);
}
