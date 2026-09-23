/// @file test_multi_region.cpp
/// @brief 多区域夹具上的顺序、退化剔除与洞环判据。
///
/// 单连通域夹具 `change_mask` 覆盖不到三类语义，故另有 `multi_region_mask`：
///
/// 1. **label 分配顺序（D-6）。** 旧实现用 `std::unordered_map` 分组，迭代序
///    未定义，同一输入在不同标准库实现下会得到不同的 label 顺序。判据是
///    「区域按 raster-scan 首次出现位置排序」——它是几何性质，与容器无关。
/// 2. **一像素宽结构不再是退化几何。** 顶点取像素角点后，`line_e` 这条 1 像素
///    宽的竖条围出的是合法的 1x5 矩形，面积 500 m²，必须产出 Feature。Phase 2
///    取像素中心时它的环全部共线、有向面积为 0，被当作 D-7 退化轮廓跳过。
/// 3. **几何面积与像素数一致。** 每个 Feature 的几何面积（外环减内环）精确等于
///    其 `pixel_count` 乘单像元面积。这是 Phase 2.1 几何基准的直接判据。
/// 4. **洞环。** 带洞区域须产出「一个 Feature + 首环为外环、其余为内环」，
///    而不是把洞单独算成一个 Feature。
///
/// 期望值全部取自 `multi_region_mask.json`，该文件由
/// `scripts/make_multi_region_fixture.py` 依几何定义写出，与引擎实现无关。
///
/// 夹具刻意取 120×64 的**非方形**尺寸：方形影像会让行列互换的错误不可见。

#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <cmath>
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

constexpr double kEpsilon = 1e-9;

/// 夹具的原始内容与元数据。
struct MultiRegion {
    Json meta;
    std::vector<std::uint8_t> mask;
    int width = 0;
    int height = 0;
    double geo[6] = {};
};

MultiRegion load_multi_region() {
    MultiRegion data;
    data.meta = fixture::read_json("multi_region_mask.json");
    data.width = data.meta.at("width").get<int>();
    data.height = data.meta.at("height").get<int>();
    for (std::size_t i = 0; i < 6; ++i) {
        data.geo[i] = data.meta.at("geo_transform").at(i).get<double>();
    }
    data.mask = fixture::read_bytes("multi_region_mask.raw");
    return data;
}

/// 像素序列是否严格按 raster-scan 顺序排列（先行后列，且不重复）。
bool is_raster_scan_ordered(const std::vector<spatial::PixelCoord>& pixels) {
    for (std::size_t i = 1; i < pixels.size(); ++i) {
        const spatial::PixelCoord& previous = pixels[i - 1];
        const spatial::PixelCoord& current = pixels[i];
        const bool ordered = (previous.row < current.row) ||
                             (previous.row == current.row && previous.col < current.col);
        if (!ordered) {
            return false;
        }
    }
    return true;
}

/// 某个区域像素集合的边界，按 label 找。
spatial::Boundary boundary_of_label(const std::vector<spatial::Region>& regions, int label) {
    for (const auto& region : regions) {
        if (region.label == label) {
            return spatial::extract_boundary(region.pixels);
        }
    }
    return {};
}

/// 一条 GeoJSON 环的几何面积（鞋带公式，顶点为 [lon, lat]）；测试侧独立实现。
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

/// 几何面积与期望值是否一致。见 test_geojson.cpp 中同名函数的说明：经纬度
/// 坐标量级为 5e5 × 4e6，双精度乘积的绝对误差约 1e-4 m²，故不能用严格相等。
bool area_equals(double actual, double expected) {
    return std::abs(actual - expected) <= (1e-6 * expected) + 1e-2;
}

}  // namespace

TEST_CASE("多区域夹具：每个区域按 raster-scan 首次出现位置编号", "[multi_region]") {
    const MultiRegion f = load_multi_region();
    REQUIRE(f.mask.size() == static_cast<std::size_t>(f.width) * f.height);

    // 夹具自检：元数据与落盘掩膜必须一致，否则后续判据的前提不成立。
    std::size_t nonzero = 0;
    for (const auto value : f.mask) {
        if (value != 0) {
            ++nonzero;
        }
    }
    CHECK(nonzero == static_cast<std::size_t>(f.meta.at("changed_pixels").get<int>()));

    const auto regions = spatial::extract_regions(f.mask.data(), f.width, f.height, f.geo);
    const Json& meta_regions = f.meta.at("regions");
    REQUIRE(regions.size() == meta_regions.size());

    const double pixel_area = f.meta.at("pixel_area_m2").get<double>();

    for (std::size_t index = 0; index < regions.size(); ++index) {
        const spatial::Region& region = regions[index];
        const Json& expected = meta_regions.at(index);

        REQUIRE_FALSE(region.pixels.empty());
        CHECK(region.label == expected.at("label").get<int>());
        CHECK(region.pixel_count == expected.at("pixel_count").get<int>());
        CHECK(region.area_m2 == expected.at("pixel_count").get<double>() * pixel_area);

        // 区域成员按 raster-scan 排列，故首个成员即首次出现位置。
        CHECK(is_raster_scan_ordered(region.pixels));
        CHECK(region.pixels.front().row == expected.at("first_row").get<int>());
        CHECK(region.pixels.front().col == expected.at("first_col").get<int>());
    }

    // 顺序判据的核心：首个成员在整幅影像中的行主序下标必须严格递增。
    // 该性质不依赖任何容器的迭代序，正是 D-6 的修复目标。
    int previous_index = -1;
    for (const auto& region : regions) {
        const int index = (region.pixels.front().row * f.width) + region.pixels.front().col;
        CHECK(index > previous_index);
        previous_index = index;
    }

    // 同行不同列的情形：blob_f 与 blob_c 的首次出现都在第 26 行，
    // 故顺序必须由列号决定。若实现退回哈希迭代序，此处会翻转。
    CHECK(regions[2].pixels.front().row == regions[3].pixels.front().row);
    CHECK(regions[2].pixels.front().col < regions[3].pixels.front().col);
}

TEST_CASE("多区域夹具：一个 Region 一个 Feature，几何面积与像素数一致", "[multi_region]") {
    const MultiRegion f = load_multi_region();
    const auto regions = spatial::extract_regions(f.mask.data(), f.width, f.height, f.geo);

    const Json collection = Json::parse(spatial::regions_to_geojson(regions, f.geo));
    const auto& features = collection.at("features");

    const Json& meta_regions = f.meta.at("regions");
    std::vector<int> kept_labels;
    std::vector<int> kept_counts;
    for (const auto& expected : meta_regions) {
        REQUIRE(expected.at("expected_feature").get<bool>());
        kept_labels.push_back(expected.at("label").get<int>());
        kept_counts.push_back(expected.at("pixel_count").get<int>());
    }

    // 顶点取像素角点后本夹具没有退化项，故 Feature 数等于连通域数。
    REQUIRE(features.size() == regions.size());
    REQUIRE(features.size() == f.meta.at("expected_feature_count").get<std::size_t>());
    CHECK(f.meta.at("degenerate_components").get<int>() == 0);

    const double pixel_area = f.meta.at("pixel_area_m2").get<double>();
    for (std::size_t index = 0; index < features.size(); ++index) {
        CHECK(features.at(index).at("properties").at("label").get<int>() == kept_labels[index]);
        CHECK(features.at(index).at("properties").at("pixel_count").get<int>() ==
              kept_counts[index]);

        // 几何面积 == 像素数 × 单像元面积。旧基准（像素中心）下本夹具的几何
        // 面积合计比上报值小 17.63 %；`line_e` 更是被整条剔除。
        CHECK(area_equals(feature_area(features.at(index)), kept_counts[index] * pixel_area));
    }

    // 一像素宽结构的轮廓是 4 顶点的矩形，不再是共线退化几何。
    for (const auto& expected : meta_regions) {
        if (expected.at("name").get<std::string>() != "line_e") {
            continue;
        }
        const spatial::Boundary boundary =
            boundary_of_label(regions, expected.at("label").get<int>());
        REQUIRE(boundary.outline.size() == 4);
        CHECK(boundary.outline.front() != boundary.outline.back());
        CHECK(boundary.holes.empty());
    }
}

TEST_CASE("多区域夹具：带洞区域产出一个 Feature 与一条内环", "[multi_region]") {
    const MultiRegion f = load_multi_region();
    const auto regions = spatial::extract_regions(f.mask.data(), f.width, f.height, f.geo);

    const Json& meta_regions = f.meta.at("regions");
    int holed_label = -1;
    int holed_count = 0;
    for (const auto& expected : meta_regions) {
        if (expected.at("holes").get<int>() > 0) {
            holed_label = expected.at("label").get<int>();
            holed_count = expected.at("pixel_count").get<int>();
        }
    }
    REQUIRE(holed_label > 0);

    const spatial::Boundary boundary = boundary_of_label(regions, holed_label);
    CHECK(boundary.outline.size() >= 3);
    CHECK(boundary.holes.size() == 1);

    const Json collection = Json::parse(spatial::regions_to_geojson(regions, f.geo));
    int matched_features = 0;
    for (const auto& feature : collection.at("features")) {
        if (feature.at("properties").at("label").get<int>() != holed_label) {
            continue;
        }
        ++matched_features;
        // 首环为外环、其余为内环：环数 = 1 + 洞数。
        CHECK(feature.at("geometry").at("coordinates").size() == 2);
        CHECK(feature.at("properties").at("pixel_count").get<int>() == holed_count);
    }
    CHECK(matched_features == 1);
}

TEST_CASE("多区域夹具：非方形影像的行列不得互换", "[multi_region]") {
    const MultiRegion f = load_multi_region();
    const auto regions = spatial::extract_regions(f.mask.data(), f.width, f.height, f.geo);
    const Json collection = Json::parse(spatial::regions_to_geojson(regions, f.geo));

    // 经纬度由 geo_transform 与像素行列唯一决定：
    //   lon = 500000 + col * 10   /   lat = 4000000 - row * 10
    // 下面四个极值把「哪一维是行、哪一维是列」钉死。若把 120×64 当作 64×120
    // 解析，这些数值会整体错位。
    double min_lon = 1e18;
    double max_lon = -1e18;
    double min_lat = 1e18;
    double max_lat = -1e18;
    for (const auto& feature : collection.at("features")) {
        for (const auto& ring : feature.at("geometry").at("coordinates")) {
            for (const auto& point : ring) {
                const double lon = point.at(0).get<double>();
                const double lat = point.at(1).get<double>();
                min_lon = std::min(min_lon, lon);
                max_lon = std::max(max_lon, lon);
                min_lat = std::min(min_lat, lat);
                max_lat = std::max(max_lat, lat);
            }
        }
    }

    // 顶点取像素角点，故极值格点比像素下标各多一行一列。四个极值分别来自：
    // 最左格点列 6（blob_a 的列 6..15）、最右格点列 119（blob_c 的列 96..118）、
    // 最上格点行 4（blob_a 的行 4..13）、最下格点行 61（line_e 的行 56..60）。
    //
    // `line_e` 在 Phase 2 被当作退化轮廓整条剔除，故当时的最下行来自 ring_d
    // （行 53）；新基准下它参与输出，极值也随之改变 —— 这几条断言因此同时
    // 钉住了「几何基准」与「行列不互换」两件事。
    CHECK(min_lon == 500000.0 + 6.0 * 10.0);    // blob_a 最左格点列 6
    CHECK(max_lon == 500000.0 + 119.0 * 10.0);  // blob_c 最右格点列 119
    CHECK(max_lat == 4000000.0 - 4.0 * 10.0);   // blob_a 最上格点行 4
    CHECK(min_lat == 4000000.0 - 61.0 * 10.0);  // line_e 最下格点行 61

    for (const auto& feature : collection.at("features")) {
        for (const auto& ring : feature.at("geometry").at("coordinates")) {
            CHECK(ring.size() >= 4);
            CHECK(ring.front() == ring.back());
        }
    }
}

TEST_CASE("多区域夹具：输出在重复调用间逐字节一致", "[multi_region]") {
    const MultiRegion f = load_multi_region();
    const auto regions = spatial::extract_regions(f.mask.data(), f.width, f.height, f.geo);
    const std::string first = spatial::regions_to_geojson(regions, f.geo);

    for (int attempt = 0; attempt < 8; ++attempt) {
        const auto again = spatial::extract_regions(f.mask.data(), f.width, f.height, f.geo);
        CHECK(spatial::regions_to_geojson(again, f.geo) == first);
    }
}
