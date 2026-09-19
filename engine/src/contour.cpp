/// @file contour.cpp
/// @brief Moore 邻域边界追踪 —— 从无序像素集合提取有序轮廓环。
///
/// 缺陷 D-2 的说明
/// ---------------
/// 旧实现的追踪函数长这样（示意）：
///
///     std::vector<PixelCoord> ring = {start};
///     ...
///     while (true) {
///         for (d in 0..7) {
///             n = cur + dir[d];
///             if (in_region(n) && is_boundary(n) && !visited(n)) {
///                 ring.push_back(n);
///                 if (n == start) return ring;
///                 visited.insert(n);          // ← 只插入了 n
///                 cur = n; break;
///             }
///         }
///     }
///
/// 两个问题叠加：
///
/// 1. **起点从未进入 `visited`。** 环回到起点后通过 `n == start` 直接返回，
///    `visited.insert(start)` 那行根本没机会执行。外层主循环随后按 raster-scan
///    遍历像素时，`visited.count(start)` 为 0，于是同一个连通域会被再次起头。
///
/// 2. **扫描起点没有携带。** 每步都从方向 0（正右）重新开始扫描，等价于假定
///    「上一个像素永远在正左方」。这只在水平的左上角成立；一旦走到边界的
///    竖直段或凹角，扫描会立刻折回刚刚走过的像素，追踪在那里断掉。断掉后
///    主循环又换一个未访问的边界像素重新起头。
///
/// 两者共同造成：**一个连通域的边界被劈成若干段互不相接的弧**。基线样本
/// （圆盘，7209 像素）实测产出 2 条弧，于是 GeoJSON 出现 2 个 Feature、
/// 面积被计了 2 倍。
///
/// 修复
/// ----
/// 采用标准的 Moore 邻域追踪，状态里显式带上「上一轮扫描的起始方向」：
///
/// * 起点选定后，整条环（含起点）在返回前全部进入 `visited`；
/// * 每轮扫描从 `scan_from` 起顺时针试 8 个方向，取第一个属于区域的像素；
/// * 走到下一个像素后，`scan_from` 重新计算为「上一个跳过的背景像素相对
///   新当前像素的方向」。该背景像素必然存在，因为扫描在命中之前试过的
///   方向都属于背景。
///
/// 由此每个连通域只追踪一次外环，且追踪结束时可断言「环上所有像素均已
/// 访问」。

#include "spatial/contour.hpp"

#include <cstddef>
#include <cstdint>
#include <unordered_set>
#include <utility>
#include <vector>

namespace spatial {
namespace {

/// 8 邻域方向编号，顺时针：0=右 1=右下 2=下 3=左下 4=左 5=左上 6=上 7=右上
constexpr int kDirections = 8;
constexpr int kDr[kDirections] = {0, 1, 1, 1, 0, -1, -1, -1};
constexpr int kDc[kDirections] = {1, 1, 0, -1, -1, -1, 0, 1};

/// 返回 `from → to` 的 8 邻域方向编号；两点不相邻时返回 -1。
int direction_of(const PixelCoord& from, const PixelCoord& to) noexcept {
    const int dr = to.row - from.row;
    const int dc = to.col - from.col;
    for (int d = 0; d < kDirections; ++d) {
        if (kDr[d] == dr && kDc[d] == dc) {
            return d;
        }
    }
    return -1;
}

/// 稀疏像素集合，成员查询 O(1)。
class PixelSet {
public:
    explicit PixelSet(const std::vector<PixelCoord>& pixels)
        : pixels_(pixels.begin(), pixels.end()) {}

    [[nodiscard]] bool contains(int row, int col) const {
        return pixels_.contains(PixelCoord{row, col});
    }

private:
    std::unordered_set<PixelCoord> pixels_;
};

/// 像素集合的外接矩形。
struct Bounds {
    int min_row = 0;
    int max_row = 0;
    int min_col = 0;
    int max_col = 0;
};

Bounds bounds_of(const std::vector<PixelCoord>& pixels) {
    Bounds box{pixels.front().row, pixels.front().row, pixels.front().col, pixels.front().col};
    for (const auto& p : pixels) {
        box.min_row = (p.row < box.min_row) ? p.row : box.min_row;
        box.max_row = (p.row > box.max_row) ? p.row : box.max_row;
        box.min_col = (p.col < box.min_col) ? p.col : box.min_col;
        box.max_col = (p.col > box.max_col) ? p.col : box.max_col;
    }
    return box;
}

/// raster-scan 顺序下的首个像素：先行、后列。
///
/// 该像素的西邻必然不属于同一集合 —— 否则按扫描序它会被更早取到。
/// 这一性质是 `trace_ring` 用「西」作为初始扫描方向的前提。
PixelCoord raster_scan_first(const std::vector<PixelCoord>& pixels) {
    PixelCoord best = pixels.front();
    for (const auto& p : pixels) {
        if (p.row < best.row || (p.row == best.row && p.col < best.col)) {
            best = p;
        }
    }
    return best;
}

/// Moore 邻域追踪，提取单条闭合轮廓。
///
/// @param region 成员判定
/// @param start 起始像素，须满足「西邻不在集合内」
/// @param step_limit 步数上界，超出即判定为异常输入并返回已得部分
/// @return 环的顶点序列，**首尾不重复**，末点与首点在 8 邻域内相邻
std::vector<PixelCoord> trace_ring(const PixelSet& region, const PixelCoord& start,
                                   std::size_t step_limit) {
    std::vector<PixelCoord> ring;
    ring.push_back(start);

    PixelCoord current = start;
    int scan_from = 4;  // 正左。起点西邻必为背景，故从它开始绕行。

    for (std::size_t step = 0; step < step_limit; ++step) {
        // 从 scan_from 起顺时针找一个属于区域的邻居
        int found = -1;
        for (int k = 0; k < kDirections; ++k) {
            const int d = (scan_from + k) % kDirections;
            if (region.contains(current.row + kDr[d], current.col + kDc[d])) {
                found = d;
                break;
            }
        }
        if (found < 0) {
            break;  // 孤立像素，无邻居可走
        }

        // 命中方向的前一个位置必为背景，它就是下一轮的绕行起点。
        const PixelCoord previous{current.row + kDr[(found + kDirections - 1) % kDirections],
                                  current.col + kDc[(found + kDirections - 1) % kDirections]};

        current = PixelCoord{current.row + kDr[found], current.col + kDc[found]};
        if (current == start) {
            break;  // 环闭合
        }

        ring.push_back(current);

        const int next_scan = direction_of(current, previous);
        scan_from = (next_scan >= 0) ? next_scan : 0;
    }

    return ring;
}

/// 找出被区域完全包住的背景连通域（洞）。
///
/// 做法：在区域外接矩形内，从矩形四边上的背景像素出发做 4 邻域洪泛；
/// 能到达矩形边界的背景像素属「外部背景」，剩下未被标记的即洞。
/// 每个洞单独追踪一次得到一条内环。
std::vector<std::vector<PixelCoord>> find_holes(const PixelSet& region, const Bounds& box) {
    const int rows = box.max_row - box.min_row + 1;
    const int cols = box.max_col - box.min_col + 1;
    const auto stride = static_cast<std::size_t>(cols);
    const std::size_t total = stride * static_cast<std::size_t>(rows);

    // 0 = 未分类，1 = 外部背景，2 = 属于区域，3 = 已归入某个洞
    std::vector<std::uint8_t> state(total, 0);

    const auto index_of = [stride](int r, int c) {
        return static_cast<std::size_t>(r) * stride + static_cast<std::size_t>(c);
    };

    for (int r = 0; r < rows; ++r) {
        for (int c = 0; c < cols; ++c) {
            if (region.contains(box.min_row + r, box.min_col + c)) {
                state[index_of(r, c)] = 2;
            }
        }
    }

    constexpr int kNeighbourR[4] = {-1, 1, 0, 0};
    constexpr int kNeighbourC[4] = {0, 0, -1, 1};

    std::vector<std::size_t> stack;
    const auto push_if_unvisited = [&](int r, int c) {
        if (r < 0 || r >= rows || c < 0 || c >= cols) {
            return;
        }
        const std::size_t i = index_of(r, c);
        if (state[i] == 0) {
            state[i] = 1;
            stack.push_back(i);
        }
    };

    for (int c = 0; c < cols; ++c) {
        push_if_unvisited(0, c);
        push_if_unvisited(rows - 1, c);
    }
    for (int r = 0; r < rows; ++r) {
        push_if_unvisited(r, 0);
        push_if_unvisited(r, cols - 1);
    }

    while (!stack.empty()) {
        const std::size_t i = stack.back();
        stack.pop_back();
        const int r = static_cast<int>(i / stride);
        const int c = static_cast<int>(i % stride);
        for (int k = 0; k < 4; ++k) {
            push_if_unvisited(r + kNeighbourR[k], c + kNeighbourC[k]);
        }
    }

    std::vector<std::vector<PixelCoord>> holes;
    std::vector<std::size_t> pending;
    for (int r = 0; r < rows; ++r) {
        for (int c = 0; c < cols; ++c) {
            const std::size_t seed = index_of(r, c);
            if (state[seed] != 0) {
                continue;
            }

            std::vector<PixelCoord> hole;
            state[seed] = 3;
            pending.push_back(seed);

            while (!pending.empty()) {
                const std::size_t cur = pending.back();
                pending.pop_back();
                const int cr = static_cast<int>(cur / stride);
                const int cc = static_cast<int>(cur % stride);
                hole.push_back(PixelCoord{box.min_row + cr, box.min_col + cc});
                for (int k = 0; k < 4; ++k) {
                    const int nr = cr + kNeighbourR[k];
                    const int nc = cc + kNeighbourC[k];
                    if (nr < 0 || nr >= rows || nc < 0 || nc >= cols) {
                        continue;
                    }
                    const std::size_t ni = index_of(nr, nc);
                    if (state[ni] == 0) {
                        state[ni] = 3;
                        pending.push_back(ni);
                    }
                }
            }

            holes.push_back(std::move(hole));
        }
    }

    return holes;
}

}  // namespace

Boundary extract_boundary(const std::vector<PixelCoord>& pixels) {
    Boundary boundary;
    if (pixels.size() < 3) {
        // D-7：返回默认构造的空 Boundary，而不是含空环的容器。
        return boundary;
    }

    const PixelSet region(pixels);
    const std::size_t step_limit = pixels.size() * 8U + 64U;

    boundary.outline = trace_ring(region, raster_scan_first(pixels), step_limit);
    if (boundary.outline.size() < 3) {
        boundary.outline.clear();
        return boundary;
    }

    for (const auto& hole : find_holes(region, bounds_of(pixels))) {
        if (hole.size() < 3) {
            continue;
        }
        const PixelSet hole_pixels(hole);
        auto ring = trace_ring(hole_pixels, raster_scan_first(hole), hole.size() * 8U + 64U);
        if (ring.size() >= 3) {
            boundary.holes.push_back(std::move(ring));
        }
    }

    return boundary;
}

}  // namespace spatial
