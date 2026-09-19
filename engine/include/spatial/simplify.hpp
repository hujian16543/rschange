#pragma once

/// @file simplify.hpp
/// @brief 闭合边界环的 Douglas-Peucker 简化。

#include <vector>

#include "spatial/export.hpp"
#include "spatial/region.hpp"

namespace spatial {

/// 点到线段 AB 的垂直距离（像素单位）。
///
/// 退化情形：A 与 B 重合时返回点到 A 的欧氏距离。
SPATIAL_API double point_line_distance(const PixelCoord& p, const PixelCoord& a,
                                       const PixelCoord& b) noexcept;

/// 闭曲线 Douglas-Peucker 简化。
///
/// 关于 D-8
/// --------
/// Douglas-Peucker 本是**开曲线**算法，其递归边界要求两个端点固定不动。
/// 直接把环的首尾当作端点，等于人为在环上挑选了一条"裂缝"——该处的几何
/// 特征会被强制保留，而同一形状换个起始像素就会得到不同结果。
///
/// 本实现采用闭曲线变体：先取距 `ring[0]` 最远的顶点作为对径锚点，把环拆成
/// 两条开曲线各自简化，再按原序合并。这样结果与起始像素的选择无关。
///
/// @param ring 闭合环，首尾不重复
/// @param tolerance 容差（像素）。建议取 1.0–2.0
/// @return 简化后的环，首尾不重复，顶点数不少于 3；输入少于 4 点时原样返回
SPATIAL_API std::vector<PixelCoord> simplify_boundary(const std::vector<PixelCoord>& ring,
                                                      double tolerance);

}  // namespace spatial
