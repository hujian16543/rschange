#pragma once

/// @file labeling.hpp
/// @brief 二值掩膜 → 连通区域列表。

#include <cstdint>
#include <vector>

#include "spatial/export.hpp"
#include "spatial/region.hpp"

namespace spatial {

/// Two-Pass 连通域提取（4 邻域连通）。
///
/// 输入约定
/// --------
/// `mask` 为行主序、长度 `width * height` 的 0/非 0 掩膜；0 表示背景。
///
/// 输出约定
/// --------
/// 返回的 `Region` 按 **raster-scan 首次出现顺序**排列，`label` 从 1 起递增。
/// 该顺序与容器的迭代序无关，因此在任何平台、任何标准库实现下都产生相同结果
/// （旧实现用 `std::unordered_map` 分组，迭代序未定义，属缺陷 D-6）。
///
/// 边界情形
/// --------
/// `mask == nullptr` 或尺寸非正时返回空列表。
SPATIAL_API std::vector<Region> extract_regions(const std::uint8_t* mask, int width, int height,
                                                const double geo_transform[6]);

}  // namespace spatial
