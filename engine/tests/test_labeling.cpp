/// @file test_labeling.cpp
/// @brief 连通域提取：标签顺序的确定性（D-6）、4 邻域语义与面积换算。

#include <catch2/catch_test_macros.hpp>

#include <cstddef>
#include <cstdint>
#include <vector>

#include "spatial/labeling.hpp"
#include "spatial/region.hpp"

namespace {

/// 夹具影像的仿射变换：10 m × 10 m 像元，故单像元面积 100 m²。
constexpr double kGeo[6] = {500000.0, 10.0, 0.0, 4000000.0, 0.0, -10.0};
constexpr double kPixelAreaM2 = 100.0;

std::vector<std::uint8_t> make_mask(int width, int height) {
    return std::vector<std::uint8_t>(static_cast<std::size_t>(width) * height, 0);
}

void fill_block(std::vector<std::uint8_t>& mask, int width, int row0, int col0, int rows, int cols) {
    for (int r = row0; r < row0 + rows; ++r) {
        for (int c = col0; c < col0 + cols; ++c) {
            mask[static_cast<std::size_t>(r) * width + c] = 1;
        }
    }
}

void set_pixel(std::vector<std::uint8_t>& mask, int width, int row, int col) {
    mask[static_cast<std::size_t>(row) * width + col] = 1;
}

int min_row_of(const spatial::Region& region) {
    int best = region.pixels.front().row;
    for (const auto& p : region.pixels) {
        best = (p.row < best) ? p.row : best;
    }
    return best;
}

}  // namespace

// 非法输入返回空列表
TEST_CASE("labeling: invalid input yields an empty region list", "[labeling]") {
    const std::vector<std::uint8_t> empty;
    CHECK(spatial::extract_regions(nullptr, 8, 8, kGeo).empty());
    CHECK(spatial::extract_regions(empty.data(), 0, 8, kGeo).empty());
    CHECK(spatial::extract_regions(empty.data(), 8, 0, kGeo).empty());
}

// 单个连通域的像素数与面积
TEST_CASE("labeling: pixel count and area of a single region", "[labeling]") {
    const int width = 16;
    const int height = 16;
    auto mask = make_mask(width, height);
    fill_block(mask, width, 4, 4, 3, 3);

    const auto regions = spatial::extract_regions(mask.data(), width, height, kGeo);
    REQUIRE(regions.size() == 1);

    const auto& region = regions.front();
    CHECK(region.label == 1);
    CHECK(region.pixel_count == 9);
    CHECK(region.pixels.size() == 9);
    CHECK(region.area_m2 == 9 * kPixelAreaM2);
}

// 4 邻域连通：对角相邻属两个区域
TEST_CASE("labeling: diagonal neighbours are two regions under 4-connectivity", "[labeling]") {
    const int width = 8;
    const int height = 8;
    auto mask = make_mask(width, height);
    set_pixel(mask, width, 2, 2);
    set_pixel(mask, width, 3, 3);

    const auto regions = spatial::extract_regions(mask.data(), width, height, kGeo);
    CHECK(regions.size() == 2);
    CHECK(regions[0].pixel_count == 1);
    CHECK(regions[1].pixel_count == 1);
}

// 标签按 raster-scan 首次出现顺序分配（D-6）
TEST_CASE("labeling: labels follow raster-scan first-appearance order (D-6)", "[labeling]") {
    const int width = 64;
    const int height = 64;

    auto mask = make_mask(width, height);
    // 先按容器书写顺序放置靠下的块，再放靠上的块：若实现依赖哈希表迭代序，
    // 结果就可能与 raster-scan 顺序不一致。
    fill_block(mask, width, 40, 40, 3, 3);  // 后出现
    fill_block(mask, width, 5, 5, 3, 3);    // 先出现

    const auto regions = spatial::extract_regions(mask.data(), width, height, kGeo);
    REQUIRE(regions.size() == 2);

    CHECK(regions[0].label == 1);
    CHECK(regions[1].label == 2);
    CHECK(min_row_of(regions[0]) == 5);
    CHECK(min_row_of(regions[1]) == 40);

    // 同一输入重复求解必须逐位一致。
    for (int attempt = 0; attempt < 64; ++attempt) {
        const auto again = spatial::extract_regions(mask.data(), width, height, kGeo);
        REQUIRE(again.size() == regions.size());
        for (std::size_t i = 0; i < again.size(); ++i) {
            CHECK(again[i].label == regions[i].label);
            CHECK(again[i].pixel_count == regions[i].pixel_count);
            CHECK(again[i].pixels == regions[i].pixels);
        }
    }
}

// 区域内的像素按 raster-scan 顺序排列
TEST_CASE("labeling: pixels inside a region follow raster-scan order", "[labeling]") {
    const int width = 32;
    const int height = 32;
    auto mask = make_mask(width, height);
    fill_block(mask, width, 10, 3, 4, 6);

    const auto regions = spatial::extract_regions(mask.data(), width, height, kGeo);
    REQUIRE(regions.size() == 1);
    const auto& pixels = regions.front().pixels;
    REQUIRE(pixels.size() == 24);

    for (std::size_t i = 1; i < pixels.size(); ++i) {
        const bool ordered = (pixels[i - 1].row < pixels[i].row) ||
                             (pixels[i - 1].row == pixels[i].row && pixels[i - 1].col < pixels[i].col);
        CHECK(ordered);
    }
}

// 标签连续编号且像素并集等于掩膜非零集
TEST_CASE("labeling: labels are contiguous and their union equals the mask", "[labeling]") {
    const int width = 24;
    const int height = 24;
    auto mask = make_mask(width, height);
    fill_block(mask, width, 1, 1, 2, 2);
    fill_block(mask, width, 10, 10, 4, 3);
    fill_block(mask, width, 20, 2, 3, 5);

    const auto regions = spatial::extract_regions(mask.data(), width, height, kGeo);
    REQUIRE(regions.size() == 3);

    std::size_t total = 0;
    for (std::size_t i = 0; i < regions.size(); ++i) {
        CHECK(regions[i].label == static_cast<int>(i) + 1);
        CHECK(regions[i].pixel_count == static_cast<int>(regions[i].pixels.size()));
        total += regions[i].pixels.size();
    }
    CHECK(total == 4 + 12 + 15);
}
