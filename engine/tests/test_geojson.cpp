/// @file test_geojson.cpp
/// @brief GeoJSON 导出的归属语义（D-3）与退化几何过滤（D-7），以及像素到
///        地理坐标的换算。

#include <catch2/catch_test_macros.hpp>

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

}  // namespace

TEST_CASE("每个 Region 恰好一个 Feature（D-3）", "[geojson]") {
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

TEST_CASE("多个 Region 时属性不重复计入", "[geojson]") {
    const std::vector<spatial::Region> regions = {
        make_region(1, make_block(10, 20, 3, 3)),
        make_region(2, make_block(40, 60, 4, 5)),
    };
    const Json collection = parse(spatial::regions_to_geojson(regions, kGeo));

    REQUIRE(collection.at("features").size() == 2);
    CHECK(area_sum(collection) == (9.0 + 20.0) * kPixelAreaM2);
}

TEST_CASE("带洞 Region 仍是单 Feature，洞作为内环", "[geojson]") {
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

TEST_CASE("环按 Polygon 约定闭合", "[geojson]") {
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

TEST_CASE("像素坐标换算为经纬度", "[geojson]") {
    const std::vector<spatial::Region> regions = {make_region(1, make_block(10, 20, 3, 3))};
    const Json collection = parse(spatial::regions_to_geojson(regions, kGeo));

    const auto& ring =
        collection.at("features").front().at("geometry").at("coordinates").front();

    // 仿射变换：lon = gt0 + col*gt1 + row*gt2，lat = gt3 + col*gt4 + row*gt5。
    const double expected_x_min = kGeo[0] + 20 * kGeo[1];
    const double expected_x_max = kGeo[0] + 22 * kGeo[1];
    const double expected_y_min = kGeo[3] + 12 * kGeo[5];
    const double expected_y_max = kGeo[3] + 10 * kGeo[5];

    for (const auto& point : ring) {
        REQUIRE(point.size() == 2);
        const double x = point.at(0).get<double>();
        const double y = point.at(1).get<double>();
        CHECK(x >= expected_x_min);
        CHECK(x <= expected_x_max);
        CHECK(y >= expected_y_min);
        CHECK(y <= expected_y_max);
    }
}

TEST_CASE("退化轮廓不产出 Feature（D-7）", "[geojson]") {
    SECTION("成员不足 3 个像素") {
        const std::vector<spatial::Region> regions = {
            make_region(1, {Coord{4, 4}, Coord{4, 5}}),
        };
        const Json collection = parse(spatial::regions_to_geojson(regions, kGeo));
        CHECK(collection.at("features").empty());
    }

    SECTION("一像素宽的细长结构：顶点共线，有向面积为 0") {
        const std::vector<spatial::Region> regions = {
            make_region(1, {Coord{4, 4}, Coord{5, 4}, Coord{6, 4}}),
            make_region(2, make_block(10, 10, 3, 3)),  // 同批次里仍须产出合法几何
        };
        const Json collection = parse(spatial::regions_to_geojson(regions, kGeo));
        REQUIRE(collection.at("features").size() == 1);
        CHECK(collection.at("features").front().at("properties").at("label") == 2);
    }
}

TEST_CASE("端到端：掩膜经连通域与边界追踪后导出", "[geojson]") {
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
