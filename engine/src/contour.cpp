/// @file contour.cpp
/// @brief 沿像素边界追踪（crack following）—— 从无序像素集合提取有序轮廓环。
///
/// 几何基准的变更（Phase 2.1）
/// --------------------------
/// Phase 2 的实现在**像素中心**取样：环的顶点是边界像素的中心。由此外环是
/// 区域的内接多边形，几何面积恒小于真实面积，且偏差随区域变小而放大
/// （实测基线 −2.93 %、多区域 −17.63 %、最小区域 −31.4 %）。
///
/// 本实现改在**像素边界**上取样：顶点是角点格点 `(r, c)`，`r ∈ [0, H]`、
/// `c ∈ [0, W]`，环沿相邻像素之间的「缝」行进。于是环围出的多边形恰好等于
/// 成员像素的并集：几何面积（像素单位）**精确等于像素个数**，乘以单像元面积
/// 即 `area_m2`。角点格点 `(r, c)` 的地理位置正是像素 `(r, c)` 的角，与
/// GDAL 的地理变换约定（`geo[0], geo[3]` 是左上角像素的左上角）一致，故这也
/// 与 GDAL 栅格转多边形的语义对齐。
///
/// 缺陷 D-2 的说明（Phase 2 已修复，此处保留结论）
/// ----------------------------------------------
/// 旧实现的 `trace_ring` 未把起点写入 `visited`，且每步都从方向 0 重新扫描，
/// 等价于假定「上一个像素永远在正左方」。两者叠加使**一个连通域的边界被劈成
/// 若干段互不相接的弧**：基线样本（圆盘，7209 像素）实测产出 2 条弧，于是
/// GeoJSON 出现 2 个 Feature、面积被计了 2 倍。
///
/// 本实现不再依赖 `visited`，也不再逐像素扫描方向：轮廓是边图分解的结果，
/// 「同一连通域只出一条外环」是图的性质，而不是扫描顺序的巧合。
///
/// 算法
/// ----
/// 1. **建边图。** 成员像素朝向背景的每条边转成一条**有向**单位边，方向取
///    「区域恒在行进方向右侧」：
///
///    | 暴露边 | 条件 | 有向边 | 方向 |
///    |---|---|---|---|
///    | 上边 | `(r−1, c) ∉ R` | `(r, c) → (r, c+1)` | 东 |
///    | 右边 | `(r, c+1) ∉ R` | `(r, c+1) → (r+1, c+1)` | 南 |
///    | 下边 | `(r+1, c) ∉ R` | `(r+1, c+1) → (r+1, c)` | 西 |
///    | 左边 | `(r, c−1) ∉ R` | `(r+1, c) → (r, c)` | 北 |
///
///    每条边恰由一侧的成员像素产生，故**每个节点的出度等于入度**，取值 0/2/4。
/// 2. **行走。** 每个节点在「到达方向」基础上按**逆时针优先**选下一条未使用的
///    边：直行 → 逆时针 90° → 180° → 顺时针 90°。出度为 1 时选择唯一；
///    出度为 2 只发生在区域于某个角点上自我相切的「夹点」，此时该规则把两条
///    边界并成一条环，与「一个 4 连通域只产出**一条**外环」的约定一致。
/// 3. **合并共线。** 同向的连续步长合并，只保留转折点。不做这一步，环上会为
///    每个边界像素留一个顶点，顶点数膨胀且毫无信息。
/// 4. **分类。** 区域恒在行进方向右侧 ⇒ 外环在 `(行, 列)` 平面上顺时针、
///    有向面积为正；洞环反向、有向面积为负。取有向面积最大的正环为外环，
///    负环为洞环。
///
/// 洞不再需要单独的洪泛搜索：洞的边界本来就是这个边图里与外环不相接的另一
/// 条独立环。旧实现的 `find_holes` + `pixels_around` 因而整体删除。

#include "spatial/contour.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace spatial {
namespace {

/// 4 个边方向：0=东 1=南 2=西 3=北。在 `(行, 列)` 平面上该序即顺时针。
constexpr int kSides = 4;
constexpr int kDr[kSides] = {0, 1, 0, -1};
constexpr int kDc[kSides] = {1, 0, -1, 0};

/// 角点格点按 `(行, 列)` 字典序排列。
///
/// 用有序容器而非哈希容器，是为了让「从哪条边开始行走」成为**几何决定的**
/// 量：输出因而与标准库实现、平台都无关。旧实现用 `unordered_map` 分组，迭代
/// 序未定义，正是缺陷 D-6。
struct NodeOrder {
    [[nodiscard]] bool operator()(const PixelCoord& a, const PixelCoord& b) const noexcept {
        return (a.row != b.row) ? (a.row < b.row) : (a.col < b.col);
    }
};

/// 节点 → 方向位掩码。
using NodeMap = std::map<PixelCoord, std::uint8_t, NodeOrder>;

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

[[nodiscard]] constexpr std::uint8_t bit_of(int side) noexcept {
    return static_cast<std::uint8_t>(1U << side);
}

/// 成员像素的暴露边 → 有向单位边图（区域恒在行进方向右侧）。
NodeMap build_boundary_edges(const std::vector<PixelCoord>& pixels) {
    const PixelSet region(pixels);
    NodeMap outgoing;

    const auto add = [&outgoing](int row, int col, int side) {
        outgoing[PixelCoord{row, col}] = static_cast<std::uint8_t>(
            outgoing[PixelCoord{row, col}] | bit_of(side));
    };

    for (const auto& pixel : pixels) {
        const int row = pixel.row;
        const int col = pixel.col;
        if (!region.contains(row - 1, col)) {
            add(row, col, 0);  // 上边 → 东
        }
        if (!region.contains(row, col + 1)) {
            add(row, col + 1, 1);  // 右边 → 南
        }
        if (!region.contains(row + 1, col)) {
            add(row + 1, col + 1, 2);  // 下边 → 西
        }
        if (!region.contains(row, col - 1)) {
            add(row + 1, col, 3);  // 左边 → 北
        }
    }
    return outgoing;
}

/// 在 `node` 处、以 `arrived_by` 为到达方向，挑下一条**未使用**的边。
///
/// 试探顺序为「直行 → 逆时针 90°(turn=3) → 180°(turn=2) → 顺时针 90°(turn=1)」。
/// 每个节点的出度恒等于入度；出度为 1 时该顺序只是重述「唯一的那条边」，
/// 出度为 2（夹点）时先取逆时针 90° 的分支，把两条边界并成一条环。
///
/// @return 方向编号；无可用边返回 -1
int pick_next(const NodeMap& outgoing, const NodeMap& consumed, const PixelCoord& node,
              int arrived_by) noexcept {
    constexpr int kTryOrder[kSides] = {0, 3, 2, 1};

    const auto candidates = outgoing.find(node);
    if (candidates == outgoing.end()) {
        return -1;
    }

    const auto used = consumed.find(node);
    const std::uint8_t used_mask = (used == consumed.end()) ? 0U : used->second;

    for (const int turn : kTryOrder) {
        const int side = (arrived_by + turn) % kSides;
        const std::uint8_t bit = bit_of(side);
        if ((candidates->second & bit) != 0 && (used_mask & bit) == 0) {
            return side;
        }
    }
    return -1;
}

/// 标记边 `(node, side)` 已使用。
void consume(NodeMap& consumed, const PixelCoord& node, int side) {
    consumed[node] = static_cast<std::uint8_t>(consumed[node] | bit_of(side));
}

/// 沿边图行走到回到起始边为止，返回环的顶点序列（首尾不重复）。
///
/// @param start_side 起始边的方向
/// @param step_limit 步数上界；边的总数加一即可，超出即说明边图异常
std::vector<PixelCoord> trace_ring(const NodeMap& outgoing, NodeMap& consumed,
                                   const PixelCoord& start, int start_side,
                                   std::size_t step_limit) {
    std::vector<PixelCoord> ring;
    PixelCoord node = start;
    int side = start_side;

    for (std::size_t step = 0; step < step_limit; ++step) {
        consume(consumed, node, side);
        ring.push_back(node);

        const PixelCoord arrival{node.row + kDr[side], node.col + kDc[side]};
        const int next = pick_next(outgoing, consumed, arrival, side);
        if (next < 0) {
            break;  // 边图不闭合，返回已得部分
        }
        if (arrival == start && next == start_side) {
            break;  // 回到起始边，环闭合
        }
        node = arrival;
        side = next;
    }

    return ring;
}

/// 合并同向共线的连续步长，只保留转折点。
///
/// 顶点用 `(行, 列)` 的整数差判断方向，不引入浮点误差。环首尾相接，故下标取
/// 模。全部顶点共线时（退化输入）返回空。
std::vector<PixelCoord> merge_collinear(const std::vector<PixelCoord>& ring) {
    const std::size_t count = ring.size();
    if (count < 3) {
        return ring;
    }

    std::vector<PixelCoord> kept;
    kept.reserve(count);
    for (std::size_t i = 0; i < count; ++i) {
        const PixelCoord& previous = ring[(i + count - 1) % count];
        const PixelCoord& current = ring[i];
        const PixelCoord& next = ring[(i + 1) % count];

        const int in_row = current.row - previous.row;
        const int in_col = current.col - previous.col;
        const int out_row = next.row - current.row;
        const int out_col = next.col - current.col;

        if (in_row != out_row || in_col != out_col) {
            kept.push_back(current);
        }
    }
    return kept;
}

/// 闭合折线有向面积的两倍（鞋带公式）。顶点为整数角点格点，故结果必为整数。
///
/// 区域恒在行进方向右侧 ⇒ 外环在 `(行, 列)` 平面上顺时针，此值为**正**；
/// 洞环反向，此值为**负**。这同时是外环与洞环的判别依据。
long long signed_area_twice(const std::vector<PixelCoord>& ring) {
    long long sum = 0;
    const std::size_t count = ring.size();
    for (std::size_t i = 0; i < count; ++i) {
        const PixelCoord& a = ring[i];
        const PixelCoord& b = ring[(i + 1) % count];
        sum += (static_cast<long long>(a.col) * b.row) - (static_cast<long long>(b.col) * a.row);
    }
    return sum;
}

/// 环上 `(行, 列)` 最小的顶点，用作环的规范代表，使环之间的顺序与行走起点无关。
const PixelCoord& canonical_node(const std::vector<PixelCoord>& ring) {
    std::size_t best = 0;
    for (std::size_t i = 1; i < ring.size(); ++i) {
        if (NodeOrder{}(ring[i], ring[best])) {
            best = i;
        }
    }
    return ring[best];
}

}  // namespace

Boundary extract_boundary(const std::vector<PixelCoord>& pixels) {
    Boundary boundary;
    if (pixels.size() < 3) {
        // D-7 的尺寸下限，与几何取样基准无关，Phase 2.1 未改动：
        // 成员少于 3 个像素的区域不产出轮廓。
        return boundary;
    }

    const NodeMap outgoing = build_boundary_edges(pixels);

    std::size_t edge_count = 0;
    for (const auto& [node, mask] : outgoing) {
        for (int side = 0; side < kSides; ++side) {
            if ((mask & bit_of(side)) != 0) {
                ++edge_count;
            }
        }
    }

    // 每条边恰用一次。起始边按 `(行, 列)` 字典序取，故环的分解结果可复现。
    NodeMap consumed;
    std::vector<std::vector<PixelCoord>> cycles;

    for (const auto& [node, mask] : outgoing) {
        for (int side = 0; side < kSides; ++side) {
            const std::uint8_t bit = bit_of(side);
            if ((mask & bit) == 0) {
                continue;
            }
            const auto used = consumed.find(node);
            if (used != consumed.end() && (used->second & bit) != 0) {
                continue;
            }

            auto ring = trace_ring(outgoing, consumed, node, side, edge_count + 1U);
            ring = merge_collinear(ring);
            if (ring.size() >= 3) {
                cycles.push_back(std::move(ring));
            }
        }
    }

    // 外环：有向面积最大的正环。
    std::size_t outline_index = cycles.size();
    long long outline_area = 0;
    for (std::size_t i = 0; i < cycles.size(); ++i) {
        const long long area = signed_area_twice(cycles[i]);
        if (area > outline_area) {
            outline_area = area;
            outline_index = i;
        }
    }
    if (outline_index == cycles.size()) {
        return boundary;  // 无正面积环：输入不构成闭合边界
    }

    // 洞环：有向面积为负的其余环。正面积的其余环说明输入不是单一 4 连通域，
    // 此时按 `canonical_node` 保留最大的那一条作外环、其余丢弃 —— 与旧实现
    // 「只追踪一条外环」的退化行为一致，不把多余的几何塞进洞的位置。
    std::vector<std::vector<PixelCoord>> holes;
    for (std::size_t i = 0; i < cycles.size(); ++i) {
        if (i == outline_index || signed_area_twice(cycles[i]) >= 0) {
            continue;
        }
        holes.push_back(std::move(cycles[i]));
    }

    // 洞之间按规范顶点排序，使洞环顺序只取决于几何，不取决于行走起点。
    std::sort(holes.begin(), holes.end(), [](const std::vector<PixelCoord>& a,
                                             const std::vector<PixelCoord>& b) {
        return NodeOrder{}(canonical_node(a), canonical_node(b));
    });

    boundary.outline = std::move(cycles[outline_index]);
    boundary.holes = std::move(holes);
    return boundary;
}

}  // namespace spatial
