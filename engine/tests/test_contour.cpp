/// @file test_contour.cpp
/// @brief 沿像素边界追踪（crack following）：单连通域只出一条闭合外环（D-2）、
///        洞环提取、退化输入的空结果约定（D-7），以及几何面积恒等式。
///
/// 判据刻意不引用被测实现：格点集合、顶点数、有向面积均由测试独立算出，
/// 再与追踪结果比对。「外环被打断成多段弧」会使闭合性断言与集合相等断言
/// 同时失败。
///
/// 几何基准（Phase 2.1 起）
/// ----------------------
/// 环的顶点是**角点格点**，`row ∈ [0, H]`、`col ∈ [0, W]`，不是像素中心。
/// 由此环围出的多边形恰好等于成员像素的并集，故
///
///     有向面积（像素单位） == 成员像素个数
///
/// 是**恒等式**而非近似。这一条是本文件最核心的判据：它把「几何与 area_m2
/// 一致」从声明变成可判定的性质。旧实现取像素中心，外环是内接多边形，几何
/// 面积恒小于像素个数（实测偏差 −2.93 % 至 −31.4 %）。

#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <cstddef>
#include <cstdlib>
#include <set>
#include <utility>
#include <vector>

#include "spatial/contour.hpp"
#include "spatial/region.hpp"

namespace {

using Coord = spatial::PixelCoord;
using Index = std::pair<int, int>;

std::vector<Coord> make_block(int row0, int col0, int rows, int cols) {
    std::vector<Coord> pixels;
    for (int r = row0; r < row0 + rows; ++r) {
        for (int c = col0; c < col0 + cols; ++c) {
            pixels.push_back(Coord{r, c});
        }
    }
    return pixels;
}

/// 跨形：一像素宽的十字，含大量凹角与一步宽的凸出。
std::vector<Coord> make_plus() {
    std::vector<Coord> pixels;
    for (int r = 0; r < 5; ++r) {
        pixels.push_back(Coord{r, 2});
    }
    for (int c = 0; c < 5; ++c) {
        if (c != 2) {
            pixels.push_back(Coord{2, c});
        }
    }
    return pixels;
}

std::set<Index> as_index_set(const std::vector<Coord>& pixels) {
    std::set<Index> result;
    for (const auto& p : pixels) {
        result.insert(Index{p.row, p.col});
    }
    return result;
}

/// 闭合折线有向面积的两倍（鞋带公式），测试侧独立实现。
///
/// 与引擎各自的实现互不引用，故「面积 == 像素数」这一判据不构成自证。
long long area_twice(const std::vector<Coord>& ring) {
    long long sum = 0;
    const std::size_t count = ring.size();
    for (std::size_t i = 0; i < count; ++i) {
        const Coord& a = ring[i];
        const Coord& b = ring[(i + 1) % count];
        sum += (static_cast<long long>(a.col) * b.row) - (static_cast<long long>(b.col) * a.row);
    }
    return sum;
}

/// 环的公共约定。
///
/// * 顶点是角点格点，落在 `[0, max_row] × [0, max_col]` 内；
/// * 首尾不重复，相邻顶点由水平或竖直的直线段相连（段长可为多像素）；
/// * 环上不留共线的冗余顶点 —— 相邻两段方向必须不同；
/// * 有向面积符号按外环/洞环区分，绝对值等于像素数的两倍。
///
/// @param pixel_count 该环所属区域（外环）或所围空洞（洞环）的像素个数
/// @param outer 外环为 true（有向面积为正），洞环为 false
void check_ring_shape(const std::vector<Coord>& ring, int pixel_count, bool outer, int max_row,
                      int max_col) {
    INFO("环顶点数 = " << ring.size());
    REQUIRE(ring.size() >= 3);

    for (const auto& p : ring) {
        CHECK(p.row >= 0);
        CHECK(p.row <= max_row);
        CHECK(p.col >= 0);
        CHECK(p.col <= max_col);
    }

    const std::size_t count = ring.size();
    for (std::size_t i = 0; i < count; ++i) {
        const Coord& previous = ring[(i + count - 1) % count];
        const Coord& current = ring[i];
        const Coord& next = ring[(i + 1) % count];

        CHECK(current != next);
        // 轴对齐：水平段行相同，竖直段列相同，二者必居其一。
        const bool horizontal = current.row == next.row;
        const bool vertical = current.col == next.col;
        CHECK(horizontal != vertical);

        // 共线合并的判据：转入方向与转出方向不得相同。
        const int in_row = current.row - previous.row;
        const int in_col = current.col - previous.col;
        const int out_row = next.row - current.row;
        const int out_col = next.col - current.col;
        CHECK_FALSE((in_row == out_row && in_col == out_col));
    }

    const long long twice = area_twice(ring);
    CHECK(twice != 0);
    CHECK((twice > 0) == outer);
    // 几何面积（像素单位）精确等于像素个数 —— Phase 2.1 的核心恒等式。
    CHECK(std::abs(twice) == 2LL * pixel_count);
}

}  // namespace

TEST_CASE("实心方块：一条闭合外环，无洞", "[contour]") {
    const auto pixels = make_block(1, 1, 3, 3);
    const spatial::Boundary boundary = spatial::extract_boundary(pixels);

    REQUIRE_FALSE(boundary.outline.empty());
    CHECK(boundary.holes.empty());

    // 3x3 方块（行 1..3、列 1..3）的边界即格点矩形 (1,1)-(1,4)-(4,4)-(4,1)。
    check_ring_shape(boundary.outline, 9, true, 4, 4);

    const std::set<Index> expected = {Index{1, 1}, Index{1, 4}, Index{4, 4}, Index{4, 1}};
    CHECK(as_index_set(boundary.outline) == expected);
}

TEST_CASE("十字形：凹角众多，仍只出一条闭合外环", "[contour]") {
    const auto pixels = make_plus();
    const spatial::Boundary boundary = spatial::extract_boundary(pixels);

    REQUIRE_FALSE(boundary.outline.empty());
    INFO("洞数 = " << boundary.holes.size());
    CHECK(boundary.holes.empty());

    // 一像素宽的臂使外环在格点层面成为 12 顶点的正交多边形；面积仍恰为 9。
    check_ring_shape(boundary.outline, 9, true, 5, 5);
    CHECK(boundary.outline.size() == 12);

    const std::set<Index> expected = {
        Index{0, 2}, Index{0, 3}, Index{2, 3}, Index{2, 5}, Index{3, 5}, Index{3, 3},
        Index{5, 3}, Index{5, 2}, Index{3, 2}, Index{3, 0}, Index{2, 0}, Index{2, 2},
    };
    CHECK(as_index_set(boundary.outline) == expected);
}

TEST_CASE("带洞方块：外环一条、洞环一条", "[contour]") {
    auto pixels = make_block(0, 0, 5, 5);
    // 挖掉中心 (2, 2)
    std::vector<Coord> kept;
    for (const auto& p : pixels) {
        if (!(p.row == 2 && p.col == 2)) {
            kept.push_back(p);
        }
    }

    const spatial::Boundary boundary = spatial::extract_boundary(kept);
    REQUIRE_FALSE(boundary.outline.empty());

    // 外环围住整个 5x5，有向面积 == 2 * 25。
    check_ring_shape(boundary.outline, 25, true, 5, 5);
    CHECK(as_index_set(boundary.outline) ==
          std::set<Index>{Index{0, 0}, Index{0, 5}, Index{5, 5}, Index{5, 0}});

    REQUIRE(boundary.holes.size() == 1);
    const auto& hole = boundary.holes.front();

    // 洞环是围绕 (2, 2) 的那个格点方形，方向与外环相反，有向面积 == −2 * 1。
    // 它由边图分解直接得到，不需要对背景做洪泛搜索；一像素的洞同样是合法内环。
    check_ring_shape(hole, 1, false, 5, 5);
    CHECK(as_index_set(hole) ==
          std::set<Index>{Index{2, 2}, Index{2, 3}, Index{3, 3}, Index{3, 2}});

    // 净面积（外环 + 洞环）== 2 * 实际像素数，即 5x5 减去被挖的 1 个。
    CHECK(area_twice(boundary.outline) + area_twice(hole) == 2LL * 24);
}

TEST_CASE("成员不足 3 个像素：返回空 Boundary（D-7）", "[contour]") {
    const spatial::Boundary single = spatial::extract_boundary({Coord{3, 3}});
    CHECK(single.outline.empty());
    CHECK(single.holes.empty());

    const spatial::Boundary pair = spatial::extract_boundary({Coord{3, 3}, Coord{3, 4}});
    CHECK(pair.outline.empty());
    CHECK(pair.holes.empty());

    const spatial::Boundary none = spatial::extract_boundary({});
    CHECK(none.outline.empty());
    CHECK(none.holes.empty());
}

TEST_CASE("三点共线的成员：沿像素边界追踪仍产出合法矩形", "[contour]") {
    // Phase 2 的实现在像素中心取样，共线像素连成的环有向面积为 0，被判为退化。
    // 改在像素边界取样后，一行三像素围出的是 1 像素高的矩形，面积恰为 3 ——
    // 它不是退化几何，不应被剔除。
    const std::vector<Coord> line = {Coord{5, 5}, Coord{5, 6}, Coord{5, 7}};
    const spatial::Boundary boundary = spatial::extract_boundary(line);

    REQUIRE_FALSE(boundary.outline.empty());
    CHECK(boundary.holes.empty());
    check_ring_shape(boundary.outline, 3, true, 6, 8);
    CHECK(as_index_set(boundary.outline) ==
          std::set<Index>{Index{5, 5}, Index{5, 8}, Index{6, 8}, Index{6, 5}});
}

TEST_CASE("追踪结果与输入像素的书写顺序无关", "[contour]") {
    auto pixels = make_plus();
    const spatial::Boundary forward = spatial::extract_boundary(pixels);

    std::reverse(pixels.begin(), pixels.end());
    const spatial::Boundary backward = spatial::extract_boundary(pixels);

    CHECK(as_index_set(forward.outline) == as_index_set(backward.outline));
    CHECK(forward.holes.size() == backward.holes.size());
}
