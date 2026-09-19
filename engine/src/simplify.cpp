/// @file simplify.cpp
/// @brief 闭合边界环的 Douglas-Peucker 简化（缺陷 D-8 的修复点）。
///
/// 为什么不能直接套开曲线 DP
/// ------------------------
/// Douglas-Peucker 的递归边界是「弦的两个端点固定不动」。把它用在闭合环上时，
/// 最自然的写法是拿 `ring.front()` 与 `ring.back()` 当端点——但环上本来就没有
/// 「端点」，首尾两点是相邻的。这一写法等于在环上人为挑了一条裂缝：
///
/// * 裂缝处的几何特征被强制保留，哪怕它毫无特殊性；
/// * 同一个形状只要换个起始像素，简化结果就会变，输出不可复现。
///
/// 本实现采用闭曲线变体：先找出距 `ring[0]` 最远的顶点作为**对径锚点**，用它
/// 把环拆成两条开曲线，各自跑标准 DP，再按原序合并保留点。锚点选取与起始
/// 像素无关，因此结果只取决于环的几何形状。

#include "spatial/simplify.hpp"

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace spatial {
namespace {

/// 点到线段 AB 的垂直距离。A 与 B 重合时退化为点到 A 的欧氏距离。
double distance_to_segment(const PixelCoord& p, const PixelCoord& a, const PixelCoord& b) {
    const double dx = static_cast<double>(b.col) - static_cast<double>(a.col);
    const double dy = static_cast<double>(b.row) - static_cast<double>(a.row);
    const double length_squared = (dx * dx) + (dy * dy);

    if (length_squared < 1e-9) {
        const double px = static_cast<double>(p.col) - static_cast<double>(a.col);
        const double py = static_cast<double>(p.row) - static_cast<double>(a.row);
        return std::sqrt((px * px) + (py * py));
    }

    // 叉积给出的平行四边形面积除以底边长，即垂直距离。
    const double cross = (dy * (static_cast<double>(p.col) - static_cast<double>(a.col))) -
                         (dx * (static_cast<double>(p.row) - static_cast<double>(a.row)));
    return std::abs(cross) / std::sqrt(length_squared);
}

/// 沿索引路径跑 Douglas-Peucker，把需要保留的顶点在 `keep` 中置位。
///
/// 只负责「置位」不负责「清除」：调用方先把 `keep` 全置 false 并标记两条开
/// 曲线的端点，递归过程中新增的保留点不会被另一条曲线反向抹掉。
///
/// @param path `ring` 的下标序列，首尾两项视为端点，必被保留
void mark_kept(const std::vector<PixelCoord>& ring, const std::vector<std::size_t>& path,
               double tolerance, std::vector<bool>& keep) {
    if (path.size() < 3) {
        return;  // 相邻两点之间没有可删的东西
    }

    const std::size_t first = path.front();
    const std::size_t last = path.back();

    double farthest = 0.0;
    std::size_t farthest_position = 0;
    bool found = false;

    for (std::size_t k = 1; k + 1 < path.size(); ++k) {
        const double distance = distance_to_segment(ring[path[k]], ring[first], ring[last]);
        if (distance > farthest) {
            farthest = distance;
            farthest_position = k;
            found = true;
        }
    }

    if (!found || farthest <= tolerance) {
        return;  // 全部落在容差内，中间点一律删除
    }

    keep[path[farthest_position]] = true;

    const auto split = static_cast<std::ptrdiff_t>(farthest_position);
    const std::vector<std::size_t> left(path.begin(), path.begin() + split + 1);
    const std::vector<std::size_t> right(path.begin() + split, path.end());
    mark_kept(ring, left, tolerance, keep);
    mark_kept(ring, right, tolerance, keep);
}

}  // namespace

double point_line_distance(const PixelCoord& p, const PixelCoord& a, const PixelCoord& b) noexcept {
    return distance_to_segment(p, a, b);
}

std::vector<PixelCoord> simplify_boundary(const std::vector<PixelCoord>& ring, double tolerance) {
    const std::size_t count = ring.size();
    if (count < 4) {
        return ring;  // 少于 4 点无法在闭合环上做有意义的简化
    }

    // 规范化起点：以 (row, col) 最小的顶点为逻辑 0 号。
    //
    // 这一步是「结果与起始像素无关」的关键。环上本没有端点，输入起点只是
    // 上游追踪恰好选中的位置；若直接以它为锚点参照，同一个形状换个起点就会
    // 得到不同的简化结果。取几何上唯一确定的顶点作参照，逻辑序便不再依赖
    // 输入如何旋转。
    std::size_t canonical = 0;
    for (std::size_t i = 1; i < count; ++i) {
        const bool earlier = (ring[i].row < ring[canonical].row) ||
                             (ring[i].row == ring[canonical].row && ring[i].col < ring[canonical].col);
        if (earlier) {
            canonical = i;
        }
    }

    // 逻辑下标 -> 原始下标
    const auto physical = [canonical, count](std::size_t logical) {
        return (logical + canonical) % count;
    };

    // 对径锚点：逻辑序上距逻辑 0 号最远的顶点
    std::size_t anchor = 0;
    double farthest_squared = -1.0;
    for (std::size_t logical = 1; logical < count; ++logical) {
        const PixelCoord& candidate = ring[physical(logical)];
        const double dr = static_cast<double>(candidate.row) - static_cast<double>(ring[physical(0)].row);
        const double dc = static_cast<double>(candidate.col) - static_cast<double>(ring[physical(0)].col);
        const double squared = (dr * dr) + (dc * dc);
        if (squared > farthest_squared) {
            farthest_squared = squared;
            anchor = logical;
        }
    }

    if (anchor == 0) {
        return ring;  // 全部顶点重合，无从简化
    }

    std::vector<bool> keep(count, false);
    keep[physical(0)] = true;
    keep[physical(anchor)] = true;

    // 第一段：逻辑 0 .. anchor
    std::vector<std::size_t> forward;
    forward.reserve(anchor + 1);
    for (std::size_t logical = 0; logical <= anchor; ++logical) {
        forward.push_back(physical(logical));
    }

    // 第二段：逻辑 anchor .. count-1，再回到逻辑 0
    std::vector<std::size_t> backward;
    backward.reserve(count - anchor + 1);
    for (std::size_t logical = anchor; logical < count; ++logical) {
        backward.push_back(physical(logical));
    }
    backward.push_back(physical(0));

    mark_kept(ring, forward, tolerance, keep);
    mark_kept(ring, backward, tolerance, keep);

    // 按原始顺序收集，使输出走向与输入一致
    std::vector<PixelCoord> simplified;
    simplified.reserve(count);
    for (std::size_t i = 0; i < count; ++i) {
        if (keep[i]) {
            simplified.push_back(ring[i]);
        }
    }

    if (simplified.size() < 3) {
        return ring;  // 简化到不足以构成多边形，回退原环
    }
    return simplified;
}

}  // namespace spatial
