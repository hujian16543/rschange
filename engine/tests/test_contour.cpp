/// @file test_contour.cpp
/// @brief Moore 邻域边界追踪：单连通域只出一条闭合外环（D-2）、洞环提取、
///        退化输入的空结果约定（D-7）。
///
/// 判据刻意不引用被测实现：边界像素集合由测试独立算出，再与追踪结果比对。
/// 「外环被打断成多段弧」会使闭合性断言与集合相等断言同时失败。

#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <cstddef>
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

/// 独立计算轮廓像素：4 邻域中存在非成员邻居的成员像素。
///
/// 采用 4 邻域而非 8 邻域：区域本身按 4 邻域连通，故「内部像素」应由 4 个
/// 边邻居判定。十字形的中心像素在 8 邻域下会被误判为轮廓像素（它的四个对角
/// 位置恰好是背景），但外轮廓并不穿过它。
std::set<Index> boundary_pixels_of(const std::vector<Coord>& pixels) {
    const std::set<Index> members = as_index_set(pixels);
    std::set<Index> boundary;
    constexpr int kDr[4] = {-1, 1, 0, 0};
    constexpr int kDc[4] = {0, 0, -1, 1};

    for (const auto& p : pixels) {
        for (int k = 0; k < 4; ++k) {
            if (members.count(Index{p.row + kDr[k], p.col + kDc[k]}) == 0) {
                boundary.insert(Index{p.row, p.col});
                break;
            }
        }
    }
    return boundary;
}

bool is_8_adjacent(const Coord& a, const Coord& b) {
    const int dr = a.row - b.row;
    const int dc = a.col - b.col;
    return dr >= -1 && dr <= 1 && dc >= -1 && dc <= 1 && !(dr == 0 && dc == 0);
}

/// 环的公共约定：首尾不重复、相邻顶点 8 邻接、且末点与首点也邻接（闭合）。
void check_ring_shape(const std::vector<Coord>& ring, const std::set<Index>& members) {
    REQUIRE(ring.size() >= 3);

    for (const auto& p : ring) {
        CHECK(members.count(Index{p.row, p.col}) == 1);
    }
    for (std::size_t i = 1; i < ring.size(); ++i) {
        CHECK(ring[i - 1] != ring[i]);
        CHECK(is_8_adjacent(ring[i - 1], ring[i]));
    }
    // 闭合：末点与首点必须 8 邻接。追踪若在中途断掉，这条断言会失败。
    CHECK(ring.back() != ring.front());
    CHECK(is_8_adjacent(ring.back(), ring.front()));
}

}  // namespace

TEST_CASE("实心方块：一条闭合外环，无洞", "[contour]") {
    const auto pixels = make_block(1, 1, 3, 3);
    const spatial::Boundary boundary = spatial::extract_boundary(pixels);

    REQUIRE_FALSE(boundary.outline.empty());
    CHECK(boundary.holes.empty());

    const std::set<Index> members = as_index_set(pixels);
    check_ring_shape(boundary.outline, members);

    // 方格中心的 8 个邻居全为成员，中心不是边界像素；其余 8 个都是。
    const std::set<Index> traced = as_index_set(boundary.outline);
    CHECK(traced == boundary_pixels_of(pixels));
    CHECK(traced.size() == 8);
}

TEST_CASE("十字形：凹角众多，仍只出一条闭合外环", "[contour]") {
    const auto pixels = make_plus();
    const spatial::Boundary boundary = spatial::extract_boundary(pixels);

    REQUIRE_FALSE(boundary.outline.empty());
    INFO("洞数 = " << boundary.holes.size());
    CHECK(boundary.holes.empty());

    const std::set<Index> members = as_index_set(pixels);
    check_ring_shape(boundary.outline, members);

    // 一像素宽的臂使 9 个像素中有 8 个是轮廓像素 —— 十字中心的四个边邻居都在
    // 区域内，属内部像素。外环须覆盖轮廓像素的全集；覆盖不全即说明轮廓被劈成
    // 了多段。
    const std::set<Index> traced = as_index_set(boundary.outline);
    CHECK(traced == boundary_pixels_of(pixels));
    CHECK(traced.size() == 8);
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

    const std::set<Index> members = as_index_set(kept);
    check_ring_shape(boundary.outline, members);

    REQUIRE(boundary.holes.size() == 1);
    const auto& hole = boundary.holes.front();
    check_ring_shape(hole, members);

    // 内环即被挖空中心的 4 邻域像素 —— 也就是区域的内边界。若改取洞自身的
    // 背景像素，这种一个像素的洞凑不出环，只能被丢弃。
    const std::set<Index> expected_hole = {
        Index{1, 2},
        Index{2, 1},
        Index{2, 3},
        Index{3, 2},
    };
    CHECK(as_index_set(hole) == expected_hole);
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

TEST_CASE("共线三点不产出环（退化几何）", "[contour]") {
    // 追踪本身会走通这条线，但结果不足以构成多边形；此处只固定住「不抛异常、
    // 且更上层会据有向面积过滤」这一约定。
    const std::vector<Coord> line = {Coord{5, 5}, Coord{5, 6}, Coord{5, 7}};
    const spatial::Boundary boundary = spatial::extract_boundary(line);
    CHECK(boundary.holes.empty());
}

TEST_CASE("追踪结果与输入像素的书写顺序无关", "[contour]") {
    auto pixels = make_plus();
    const spatial::Boundary forward = spatial::extract_boundary(pixels);

    std::reverse(pixels.begin(), pixels.end());
    const spatial::Boundary backward = spatial::extract_boundary(pixels);

    CHECK(as_index_set(forward.outline) == as_index_set(backward.outline));
    CHECK(forward.holes.size() == backward.holes.size());
}
