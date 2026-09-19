#pragma once

/// @file region.hpp
/// @brief 引擎的基础几何类型：像素坐标与连通区域。

#include <cstddef>
#include <cstdint>
#include <vector>

#include "spatial/export.hpp"

namespace spatial {

/// 栅格像素坐标。
///
/// `row` 向下增长、`col` 向右增长，与 GDAL 的行主序一致。
struct PixelCoord {
    int row = 0;
    int col = 0;

    friend bool operator==(const PixelCoord&, const PixelCoord&) noexcept = default;
};

/// 一个连通的候选变化区域。
///
/// 字段命名约束：面积字段必须是 `area_m2`。旧实现写作 `are_m2`（拼写残缺），
/// 且同一拼写在 GeoJSON `properties` 中又被写成正确的 `area_m2`，两处不一致
/// 属缺陷 D-9，Phase 2 已统一。
struct Region {
    int label = 0;                   ///< 从 1 起编号，按 raster-scan 首次出现顺序分配
    int pixel_count = 0;             ///< 成员像素个数
    double area_m2 = 0.0;            ///< 真实面积 = pixel_count × 单像元面积
    std::vector<PixelCoord> pixels;  ///< 成员像素，raster-scan 顺序
};

}  // namespace spatial

namespace std {

/// `PixelCoord` 的哈希，供 `unordered_set` / `unordered_map` 使用。
///
/// 实现刻意不使用 `row << 32` —— 该表达式在 `size_t` 为 32 位的平台上是
/// 未定义行为。改用可移植的乘法混合。
template <>
struct hash<spatial::PixelCoord> {
    std::size_t operator()(const spatial::PixelCoord& p) const noexcept {
        const std::size_t r = static_cast<std::size_t>(static_cast<std::uint32_t>(p.row));
        const std::size_t c = static_cast<std::size_t>(static_cast<std::uint32_t>(p.col));
        return (r * 1000003U) ^ (c + 0x9E3779B9U + (r << 6) + (r >> 2));
    }
};

}  // namespace std
