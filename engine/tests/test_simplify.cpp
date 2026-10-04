/// @file test_simplify.cpp
/// @brief 闭曲线 Douglas-Peucker：结果与起始像素无关（D-8），以及点到线段的
///        退化距离。
///
/// 判据形式
/// --------
/// 环本无端点，输入起点只是上游追踪恰好选中的位置。因此「同一形状换起点得到
/// 同一结果」不能靠逐位比较原始输出，而须先把结果规范化到几何上唯一确定的
/// 起点（`(row, col)` 最小的顶点），再比较序列。

#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <vector>

#include "spatial/region.hpp"
#include "spatial/simplify.hpp"

namespace {

using Coord = spatial::PixelCoord;

/// 顶点均在格点上、相邻边方向各不相同的非凸环（八边形）。
std::vector<Coord> make_octagon() {
    return {
        Coord{0, 1}, Coord{0, 2}, Coord{1, 3}, Coord{2, 3},
        Coord{3, 2}, Coord{3, 1}, Coord{2, 0}, Coord{1, 0},
    };
}

/// 正交阶梯环：相邻边方向两两不同，模拟 crack following 的输出形状。
///
/// 这类环是「容差 0 必须短路」的动机所在：它的角点全是直角，用浮点垂直距离
/// 判定「是否落在弦上」时，角点完全可能被判为距离 0 而被删掉，几何随之改变。
std::vector<Coord> make_stairs() {
    return {
        Coord{0, 0}, Coord{0, 3}, Coord{1, 3}, Coord{1, 1},
        Coord{2, 1}, Coord{2, 4}, Coord{3, 4}, Coord{3, 0},
    };
}

std::vector<Coord> rotate_ring(const std::vector<Coord>& ring, std::size_t offset) {
    std::vector<Coord> result;
    result.reserve(ring.size());
    for (std::size_t i = 0; i < ring.size(); ++i) {
        result.push_back(ring[(offset + i) % ring.size()]);
    }
    return result;
}

/// 把环旋转到「(row, col) 最小顶点」居首，使逻辑序只依赖几何形状。
std::vector<Coord> normalize_ring(const std::vector<Coord>& ring) {
    if (ring.empty()) {
        return ring;
    }
    std::size_t best = 0;
    for (std::size_t i = 1; i < ring.size(); ++i) {
        const bool smaller = (ring[i].row < ring[best].row) ||
                             (ring[i].row == ring[best].row && ring[i].col < ring[best].col);
        if (smaller) {
            best = i;
        }
    }
    return rotate_ring(ring, best);
}

bool contains(const std::vector<Coord>& ring, const Coord& target) {
    for (const auto& p : ring) {
        if (p == target) {
            return true;
        }
    }
    return false;
}

/// result 是否为 ring 的子序列（两者都已规范化到同一起点）。
bool is_subsequence(const std::vector<Coord>& result, const std::vector<Coord>& ring) {
    std::size_t cursor = 0;
    for (const auto& p : result) {
        while (cursor < ring.size() && !(ring[cursor] == p)) {
            ++cursor;
        }
        if (cursor == ring.size()) {
            return false;
        }
        ++cursor;
    }
    return true;
}

}  // namespace

// 点在字面为点退化的线段上：返回欧氏距离
TEST_CASE("simplify: point-to-degenerate-segment distance is euclidean", "[simplify]") {
    const Coord p{0, 4};
    const Coord a{3, 0};
    // 欧氏距离：根号下 (0-3)^2 + (4-0)^2 = 5
    CHECK(spatial::point_line_distance(p, a, a) == 5.0);
}

// 点到水平线段的垂距
TEST_CASE("simplify: perpendicular distance to a horizontal segment", "[simplify]") {
    const Coord a{2, 0};
    const Coord b{2, 6};
    CHECK(spatial::point_line_distance(Coord{5, 3}, a, b) == 3.0);
    CHECK(spatial::point_line_distance(Coord{2, 3}, a, b) == 0.0);
}

// 输入少于 4 点时原样返回
TEST_CASE("simplify: fewer than 4 points are returned unchanged", "[simplify]") {
    const std::vector<Coord> three = {Coord{0, 0}, Coord{0, 3}, Coord{3, 0}};
    CHECK(spatial::simplify_boundary(three, 2.0) == three);

    const std::vector<Coord> two = {Coord{0, 0}, Coord{0, 3}};
    CHECK(spatial::simplify_boundary(two, 2.0) == two);
}

// 容差非正时不简化：顶点原样保留
TEST_CASE("simplify: non-positive tolerance keeps every vertex", "[simplify]") {
    const auto ring = make_stairs();
    REQUIRE(ring.size() == 8);

    for (const double tolerance : {0.0, -0.5, -1.0}) {
        INFO("容差 = " << tolerance);
        CHECK(spatial::simplify_boundary(ring, tolerance) == ring);
    }

    // 对照：正容差才真的简化。容差 0 的语义价值不在「删得少」，而在
    // 「几何面积精确守恒」—— 由短路保证，而非由浮点比较的巧合保证。
    CHECK(spatial::simplify_boundary(ring, 1.0).size() < ring.size());
}

// 简化结果只取输入顶点且保持循环顺序
TEST_CASE("simplify: result is a subsequence in cyclic order", "[simplify]") {
    const auto ring = make_octagon();
    const auto simplified = normalize_ring(spatial::simplify_boundary(ring, 1.0));

    REQUIRE(simplified.size() >= 3);
    for (const auto& p : simplified) {
        CHECK(contains(ring, p));
    }
    CHECK(is_subsequence(simplified, normalize_ring(ring)));
}

// 容差越大顶点数不增
TEST_CASE("simplify: vertex count is non-increasing in tolerance", "[simplify]") {
    const auto ring = make_octagon();
    const std::size_t count_small = spatial::simplify_boundary(ring, 0.5).size();
    const std::size_t count_mid = spatial::simplify_boundary(ring, 1.5).size();
    const std::size_t count_large = spatial::simplify_boundary(ring, 4.0).size();

    CHECK(count_mid <= count_small);
    CHECK(count_large <= count_mid);
}

// 结果与起始像素无关（D-8）
TEST_CASE("simplify: result is independent of the start vertex (D-8)", "[simplify]") {
    const auto ring = make_octagon();
    const std::vector<double> tolerances = {0.5, 1.0, 2.0, 3.0};

    for (const double tolerance : tolerances) {
        const auto baseline = normalize_ring(spatial::simplify_boundary(ring, tolerance));
        REQUIRE(baseline.size() >= 3);

        // 逐一旋转起点：结果必须与基准逐点一致。
        // 旧实现把环的首尾当作 Douglas-Peucker 的固定端点，等价于在环上人为
        // 挑了一条「裂缝」，起点一变结果就变。
        for (std::size_t offset = 1; offset < ring.size(); ++offset) {
            const auto rotated = rotate_ring(ring, offset);
            const auto candidate = normalize_ring(spatial::simplify_boundary(rotated, tolerance));
            INFO("容差 " << tolerance << "，旋转偏移 " << offset);
            CHECK(candidate == baseline);
        }
    }
}

// 反转绕行方向得到同一顶点集合
TEST_CASE("simplify: reversing winding yields the same vertex set", "[simplify]") {
    const auto ring = make_octagon();
    std::vector<Coord> reversed(ring.rbegin(), ring.rend());

    const auto forward = spatial::simplify_boundary(ring, 1.0);
    const auto backward = spatial::simplify_boundary(reversed, 1.0);

    REQUIRE(forward.size() == backward.size());
    for (const auto& p : forward) {
        CHECK(contains(backward, p));
    }
}
