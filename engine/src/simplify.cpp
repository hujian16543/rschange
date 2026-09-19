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
/// 本实现采用闭曲线变体：先在环上定出三个由几何决定的锚点，用它把环拆成
/// 三段开曲线，各自跑标准 DP，再按原序合并保留点。锚点只由几何决定，因此
/// 结果只取决于环的形状，与起始像素无关；又因为锚点有三个，任何容差都至少
/// 留下一个三角形近似，也就不需要「简化过度就回退原环」这类破坏单调性的
/// 兜底分支。

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

    const PixelCoord origin = ring[physical(0)];

    // 三个锚点。闭曲线 DP 至少要留下 3 个点，否则结果连多边形都构不成。
    //
    // 只取两个锚点时，容差一旦大到把中间顶点全滤掉，递归里就只剩这两个点；
    // 实现只能回退原环 —— 输出于是随容差**非单调**跳变（实测同一八边形：
    // 容差 1.5 得 4 个点，容差 4.0 反得 8 个点）。改取三个几何上分散的锚点
    // 后，任何容差都至少留下一个三角形近似，回退分支随之消失。
    //
    // 锚点 1 = 逻辑 0 号，即 (row, col) 最小的顶点，与输入起点无关；
    // 锚点 2 = 距锚点 1 最远的顶点；
    // 锚点 3 = 距弦「锚点 1 — 锚点 2」最远的顶点。
    // 三者都只由几何决定，故结果仍与起始像素无关。
    std::size_t second = 1;
    double farthest_squared = -1.0;
    for (std::size_t logical = 1; logical < count; ++logical) {
        const PixelCoord& candidate = ring[physical(logical)];
        const double dr = static_cast<double>(candidate.row) - static_cast<double>(origin.row);
        const double dc = static_cast<double>(candidate.col) - static_cast<double>(origin.col);
        const double squared = (dr * dr) + (dc * dc);
        if (squared > farthest_squared) {
            farthest_squared = squared;
            second = logical;
        }
    }

    std::size_t third = 0;
    double farthest_offset = -1.0;
    for (std::size_t logical = 1; logical < count; ++logical) {
        if (logical == second) {
            continue;
        }
        const double offset =
            distance_to_segment(ring[physical(logical)], origin, ring[physical(second)]);
        if (offset > farthest_offset) {
            farthest_offset = offset;
            third = logical;
        }
    }

    // 三个锚点互不相同，因此结果至少 3 点，不再需要「不足 3 点就回退原环」
    // 那条会破坏单调性的分支。
    const std::size_t low = (second < third) ? second : third;
    const std::size_t high = (second < third) ? third : second;

    std::vector<bool> keep(count, false);
    keep[physical(0)] = true;
    keep[physical(low)] = true;
    keep[physical(high)] = true;

    // 环被三个锚点拆成三段开曲线，各自跑标准 DP。`mark_kept` 只置位不清除，
    // 相邻两段共享的锚点不会被后一段抹掉。
    const auto segment = [&physical](std::size_t from, std::size_t to) {
        std::vector<std::size_t> path;
        path.reserve(to - from + 1);
        for (std::size_t logical = from; logical <= to; ++logical) {
            path.push_back(physical(logical));
        }
        return path;
    };

    mark_kept(ring, segment(0, low), tolerance, keep);
    mark_kept(ring, segment(low, high), tolerance, keep);

    std::vector<std::size_t> closing = segment(high, count - 1);
    closing.push_back(physical(0));
    mark_kept(ring, closing, tolerance, keep);

    // 按原始顺序收集，使输出走向与输入一致
    std::vector<PixelCoord> simplified;
    simplified.reserve(count);
    for (std::size_t i = 0; i < count; ++i) {
        if (keep[i]) {
            simplified.push_back(ring[i]);
        }
    }
    return simplified;
}

}  // namespace spatial
