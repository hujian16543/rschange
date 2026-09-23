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
/// 直接把环的首尾当作端点，等于人为在环上挑选了一条「裂缝」——该处的几何
/// 特征会被强制保留，而同一形状换个起始像素就会得到不同结果。
///
/// 本实现分两步消掉这个人为痕迹：
///
/// 1. **规范化起点**。以 `(row, col)` 最小的顶点为逻辑 0 号。环上本没有
///    端点，输入起点只是上游追踪恰好选中的位置；取几何上唯一确定的顶点
///    作参照，逻辑序便不再依赖输入如何旋转。
/// 2. **三锚点切分**。取「逻辑 0 号」「距它最远的顶点」「距前两点连成的弦
///    最远的顶点」共三个锚点，把环拆成三条开曲线各自简化，再按原序合并。
///
/// 由此结果只取决于环的几何形状，与起始像素无关。三个锚点必然保留，故结果
/// 恒不少于 3 点，且容差增大时顶点数单调不增。
///
/// 容差为零
/// --------
/// `tolerance <= 0` 时**不简化**，原样返回。Douglas-Peucker 在容差 0 下本应
/// 只删除与弦严格共线的顶点，但顶点落在弦上的判定是浮点距离比较，直角阶梯的
/// 角点完全可能被判为距离 0 而被删除——那会改变几何面积。既然「容差 0」的
/// 语义价值在于**面积精确守恒**（几何面积 == 像素个数 × 单像元面积），此处
/// 直接短路，让该性质由构造保证而非由浮点巧合保证。
///
/// @param ring 闭合环，首尾不重复
/// @param tolerance 容差（像素）。0 表示不简化；正容差建议取 1.0–2.0，越大顶点越少
/// @return 简化后的环，顶点保持输入顺序，不少于 3 点；输入少于 4 点或容差非正时原样返回
SPATIAL_API std::vector<PixelCoord> simplify_boundary(const std::vector<PixelCoord>& ring,
                                                      double tolerance);

}  // namespace spatial
