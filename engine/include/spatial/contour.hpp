#pragma once

/// @file contour.hpp
/// @brief 区域像素集合 → 有序边界环（Moore 邻域追踪）。

#include <vector>

#include "spatial/export.hpp"
#include "spatial/region.hpp"

namespace spatial {

/// 一个连通域的全部轮廓。
struct Boundary {
    std::vector<PixelCoord> outline;             ///< 外环，非空即为有效轮廓
    std::vector<std::vector<PixelCoord>> holes;  ///< 洞环，每个洞一条
};

/// 用 Moore 邻域追踪提取边界。
///
/// 输出约定
/// --------
/// 每条环 **首尾不重复**（闭合由导出层补上首点），且相邻顶点在 8 邻域内相连。
/// 外环与洞环的绕行方向相反。
///
/// 关于 D-2
/// --------
/// 旧实现的 `trace_ring` 在返回时未把起点写入 `visited`，导致主循环从另一个
/// 未访问的边界像素重新起头，把**同一个连通域**的边界劈成多段弧。修复后的
/// 追踪满足两条不变量：
///   1. 同一个连通域只追踪一次外环（`extract_boundary` 不重复起头）；
///   2. 追踪在回到起点时闭合，`outline` 是一条首尾相接的完整环，中途不断开。
///
/// 洞环取什么像素
/// --------------
/// 内环取**与洞相邻的区域像素**（4 邻域），与外环一律取区域像素的做法一致。
/// 一个像素的洞同样能得出合法内环；若改取洞自身的背景像素，这种洞只有一个
/// 像素，凑不出环，只能被丢弃。
///
/// 边界情形
/// --------
/// 成员像素少于 3 个时返回**默认构造的空 `Boundary`**（`outline` 为空），
/// 不返回含空环的容器——旧实现返回 `{{}}`，语义含糊，属缺陷 D-7。
SPATIAL_API Boundary extract_boundary(const std::vector<PixelCoord>& pixels);

}  // namespace spatial
