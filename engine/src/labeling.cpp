/// @file labeling.cpp
/// @brief Two-Pass 连通域提取。
///
/// 与旧实现的差异
/// --------------
/// * 旧实现把像素按**根标签**塞进 `std::unordered_map<int, Region>`，再遍历该
///   映射给 `label` 赋 1、2、3……。`unordered_map` 的迭代顺序由哈希桶布局
///   决定，标准不保证可重现，于是同一幅影像在不同标准库实现、不同编译选项
///   下会得到不同的 `label` 顺序（D-6）。这会让 GeoJSON 的输出无法逐字节
///   比对。
/// * 现在改为「扫描顺序即首次出现顺序」：Pass 2 沿 raster-scan 走一遍，用
///   一张 `root -> regions 下标` 的槽位表把每个连通域**在其第一个像素处**
///   登记进结果。`regions` 的下标因此由扫描顺序唯一决定，而与任何哈希容器
///   的迭代序无关。

#include "spatial/labeling.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <numeric>
#include <vector>

namespace spatial {
namespace {

/// 并查集：路径压缩 + 以编号小者为根。
class UnionFind {
public:
    explicit UnionFind(std::size_t size) : parent_(size) {
        std::iota(parent_.begin(), parent_.end(), 0);
    }

    int find(int x) {
        int root = x;
        while (parent_[static_cast<std::size_t>(root)] != root) {
            root = parent_[static_cast<std::size_t>(root)];
        }
        // 第二趟把沿途节点直接挂到根上，摊还代价接近常数。
        while (parent_[static_cast<std::size_t>(x)] != root) {
            const int next = parent_[static_cast<std::size_t>(x)];
            parent_[static_cast<std::size_t>(x)] = root;
            x = next;
        }
        return root;
    }

    void unite(int a, int b) {
        const int root_a = find(a);
        const int root_b = find(b);
        if (root_a == root_b) {
            return;
        }
        // 编号小者作根，使等价类的代表元与扫描顺序保持一致。
        const int winner = std::min(root_a, root_b);
        const int loser = std::max(root_a, root_b);
        parent_[static_cast<std::size_t>(loser)] = winner;
    }

private:
    std::vector<int> parent_;
};

}  // namespace

std::vector<Region> extract_regions(const std::uint8_t* mask, int width, int height,
                                    const double geo_transform[6]) {
    if (mask == nullptr || width <= 0 || height <= 0) {
        return {};
    }

    const std::size_t stride = static_cast<std::size_t>(width);
    const std::size_t total = stride * static_cast<std::size_t>(height);

    std::vector<int> labels(total, 0);
    UnionFind equivalences(total);
    int next_label = 1;

    // ------------------------------------------------------------------
    // Pass 1：逐行扫描，只看已扫过的左、上两个邻居，分配临时标签并登记等价关系
    // ------------------------------------------------------------------
    for (int row = 0; row < height; ++row) {
        const std::size_t row_base = static_cast<std::size_t>(row) * stride;
        for (int col = 0; col < width; ++col) {
            const std::size_t index = row_base + static_cast<std::size_t>(col);
            if (mask[index] == 0) {
                continue;
            }

            const int left = (col > 0) ? labels[index - 1] : 0;
            const int top = (row > 0) ? labels[index - stride] : 0;

            if (left == 0 && top == 0) {
                labels[index] = next_label++;
            } else if (left != 0 && top == 0) {
                labels[index] = left;
            } else if (left == 0 && top != 0) {
                labels[index] = top;
            } else {
                equivalences.unite(left, top);
                labels[index] = std::min(left, top);
            }
        }
    }

    // ------------------------------------------------------------------
    // Pass 2：沿同一扫描顺序把像素归入连通域。
    // 连通域首次出现处即登记，故 regions 的下标 = 首次出现顺序。
    // ------------------------------------------------------------------
    std::vector<int> root_slot(total, -1);
    std::vector<Region> regions;

    for (int row = 0; row < height; ++row) {
        const std::size_t row_base = static_cast<std::size_t>(row) * stride;
        for (int col = 0; col < width; ++col) {
            const std::size_t index = row_base + static_cast<std::size_t>(col);
            const int label = labels[index];
            if (label == 0) {
                continue;
            }

            const int root = equivalences.find(label);
            int& slot = root_slot[static_cast<std::size_t>(root)];
            if (slot < 0) {
                slot = static_cast<int>(regions.size());
                regions.emplace_back();
            }
            regions[static_cast<std::size_t>(slot)].pixels.push_back(PixelCoord{row, col});
        }
    }

    // ------------------------------------------------------------------
    // 面积：单像元面积取仿射矩阵左上 2x2 子阵的行列式绝对值。
    // ------------------------------------------------------------------
    const double pixel_area =
        std::abs((geo_transform[1] * geo_transform[5]) - (geo_transform[2] * geo_transform[4]));

    for (std::size_t i = 0; i < regions.size(); ++i) {
        Region& region = regions[i];
        region.label = static_cast<int>(i) + 1;
        region.pixel_count = static_cast<int>(region.pixels.size());
        region.area_m2 = static_cast<double>(region.pixel_count) * pixel_area;
    }

    return regions;
}

}  // namespace spatial
