/// @file test_raster_io.cpp
/// @brief 栅格读写与 GDAL 初始化（缺陷 D-4 的判据）。

#include <catch2/catch_test_macros.hpp>

#include <cstdint>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

#include "fixture.hpp"
#include "internal/gdal_registry.hpp"
#include "spatial/raster.hpp"

namespace {

constexpr int kFixtureWidth = 256;
constexpr int kFixtureHeight = 256;
constexpr int kFixtureBands = 3;

/// 临时输出路径。测试结束即删，避免污染夹具目录。
std::filesystem::path scratch(const std::string& name) {
    return std::filesystem::temp_directory_path() / ("spatial_test_" + name);
}

/// 夹具影像的空间参考，供往返测试复用 —— 自造 WKT 会让 GDAL 报
/// "missing CONVERSION node" 之类的噪声，掩盖真实问题。
struct SpatialReference {
    std::vector<double> geo;
    std::string projection;
};

SpatialReference fixture_reference() {
    const auto raster = spatial::read_raster(fixture::path("before.tif").string());
    return SpatialReference{
        std::vector<double>(raster.geo_transform, raster.geo_transform + 6),
        raster.projection,
    };
}

}  // namespace

TEST_CASE("GDAL 全驱动只注册一次（D-4）", "[raster]") {
    spatial::ensure_gdal_initialized();
    CHECK(spatial::internal::gdal_registration_count() == 1);

    // 幂等：重复调用不得增加注册次数
    spatial::ensure_gdal_initialized();
    spatial::ensure_gdal_initialized();
    CHECK(spatial::internal::gdal_registration_count() == 1);

    // read_raster 内部同样会确保初始化，也不得增加注册次数
    const auto raster = spatial::read_raster(fixture::path("before.tif").string());
    CHECK(raster.band_count == kFixtureBands);
    CHECK(spatial::internal::gdal_registration_count() == 1);
}

TEST_CASE("read_raster 读出夹具元数据", "[raster]") {
    const auto raster = spatial::read_raster(fixture::path("before.tif").string());

    CHECK(raster.width == kFixtureWidth);
    CHECK(raster.height == kFixtureHeight);
    CHECK(raster.band_count == kFixtureBands);
    CHECK(raster.pixels_per_band() == static_cast<std::size_t>(kFixtureWidth) * kFixtureHeight);
    CHECK(raster.pixels.size() == static_cast<std::size_t>(kFixtureWidth) * kFixtureHeight * kFixtureBands);
    CHECK_FALSE(raster.empty());

    const std::vector<double> expected_geo = {500000.0, 10.0, 0.0, 4000000.0, 0.0, -10.0};
    for (std::size_t i = 0; i < expected_geo.size(); ++i) {
        CHECK(raster.geo_transform[i] == expected_geo[i]);
    }
    CHECK(raster.projection.find("UTM zone 50N") != std::string::npos);
}

TEST_CASE("read_raster 对不存在的文件抛 runtime_error", "[raster]") {
    const auto missing = fixture::path("no_such_raster.tif").string();
    CHECK_THROWS_AS(spatial::read_raster(missing), std::runtime_error);
}

TEST_CASE("非方形多波段往返一致", "[raster]") {
    const SpatialReference reference = fixture_reference();
    const double* geo = reference.geo.data();

    const int width = 137;
    const int height = 91;
    const int bands = 3;

    std::vector<std::uint8_t> data(static_cast<std::size_t>(width) * height * bands);
    for (int b = 0; b < bands; ++b) {
        for (int r = 0; r < height; ++r) {
            for (int c = 0; c < width; ++c) {
                const auto offset =
                    (static_cast<std::size_t>(b) * height + static_cast<std::size_t>(r)) * width +
                    static_cast<std::size_t>(c);
                data[offset] = static_cast<std::uint8_t>((b + 1) * 16 + (r % 7) * 3 + (c % 5));
            }
        }
    }

    const auto target = scratch("multi_band.tif");
    spatial::write_raster(target.string(), data.data(), width, height, bands, geo,
                          reference.projection);

    const auto back = spatial::read_raster(target.string());
    CHECK(back.width == width);
    CHECK(back.height == height);
    CHECK(back.band_count == bands);
    REQUIRE(back.pixels.size() == data.size());

    // 引擎的像素缓冲为 uint16，写出的 uint8 会被逐值提升，低位保持不变。
    const std::vector<std::uint16_t> expected(data.begin(), data.end());
    CHECK(back.pixels == expected);

    std::filesystem::remove(target);
}

TEST_CASE("非方形单波段往返保留 H 与 W（D-1 的引擎侧对应）", "[raster]") {
    const SpatialReference reference = fixture_reference();
    const double* geo = reference.geo.data();

    // 旧实现在绑定层把 2D 掩膜的宽度取成 H，落盘即变成 H×H；方形样本掩盖了
    // 这一点。此处用 H != W 且两者都不等于对方，确保尺寸不被互换或复制。
    const int width = 200;
    const int height = 100;

    std::vector<std::uint8_t> data(static_cast<std::size_t>(width) * height, 0);
    data[3 * width + 5] = 7;
    data[(height - 1) * width + (width - 1)] = 9;

    const auto target = scratch("single_band.tif");
    spatial::write_raster(target.string(), data.data(), width, height, 1, geo, reference.projection);

    const auto back = spatial::read_raster(target.string());
    CHECK(back.width == width);
    CHECK(back.height == height);
    CHECK(back.band_count == 1);
    REQUIRE(back.pixels.size() == data.size());
    CHECK(back.pixels[3 * width + 5] == 7);
    CHECK(back.pixels[(height - 1) * width + (width - 1)] == 9);

    std::filesystem::remove(target);
}
