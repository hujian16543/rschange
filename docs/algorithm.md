# 空间引擎算法层

本文档说明 `engine/` 中空间算法的实现、每个环节的输入输出契约，以及关键设计决策的
成因。目标读者是需要在 Phase 3 之后接入 `rschange` backend 的开发者，或需要复核算法
语义的验收方。

表述采用声明式：**必须 / 禁止 / 应当**。

---

## 0. 范围与归属

算法链路被一道明确边界切成两段，边界即 `_spatial` 扩展的 Python 接口。

```
┌────────────────────────── Python 侧（backend，Phase 3）──────────────────────────┐
│                                                                                  │
│   before.tif ─┐                                                                  │
│               ├─► CVA（多维欧氏距离）─► 幅度图 ─► Otsu 阈值 ─► 二值掩膜            │
│   after.tif  ─┘                                    │                             │
│                                                     │ 后处理：连通域过滤 + 闭运算   │
│                                                     ▼                             │
└─────────────────────────────────────────────────────┼────────────────────────────┘
                                                      │  uint8 掩膜 (H, W)
                        ┌─────────────────────────────┼─────────────────────────┐
                        │        C++ 引擎（Phase 2）   ▼                         │
                        │                                                       │
                        │  extract_regions ──► extract_boundary ──►      simplify_boundary
                        │   (连通域标记)        (边界追踪)        (闭曲线 DP)
                        │        │                  │                  │        │
                        │        └──────────────────┴──────────────────┘        │
                        │                       ▼                               │
                        │              regions_to_geojson                       │
                        │                       │                               │
                        └───────────────────────┼───────────────────────────────┘
                                                ▼
                                     GeoJSON FeatureCollection
```

**必须**遵守：

* C++ 引擎**不得**包含阈值分割。其输入是**已二值化**的 `uint8` 掩膜，不接受浮点
  幅度图。该约束由绑定层的 `nb::noconvert()` 强制（见 §7）。
* `backend` **禁止**改 `_spatial` 的函数签名。依赖方向固定为
  `backend → _spatial → libspatial → GDAL`。

**归属表**

| 环节 | 实现位置 | 状态 |
|---|---|---|
| 栅格读取 | `engine/src/raster_io.cpp` | 已实现 |
| CVA（多维欧氏距离） | Python，冻结参考实现 | 待迁入 `backend`（Phase 3） |
| Otsu 阈值 | Python，冻结参考实现 | 待迁入 `backend`（Phase 3） |
| 后处理（连通域过滤 + 闭运算） | Python（scipy） | 待迁入 `backend`（Phase 3） |
| 连通域标记 | `engine/src/labeling.cpp` | 已实现 |
| 边界追踪 | `engine/src/contour.cpp` | 已实现 |
| 环简化 | `engine/src/simplify.cpp` | 已实现 |
| GeoJSON 组装 | `engine/src/geojson.cpp` | 已实现 |

---

## 1. 数据模型

`engine/include/spatial/region.hpp`

```cpp
/// 栅格像素坐标。
///
/// `row` 向下增长、`col` 向右增长，与 GDAL 的行主序一致。
struct PixelCoord {
    int row = 0;
    int col = 0;

    friend bool operator==(const PixelCoord&, const PixelCoord&) noexcept = default;
};

/// 一个连通的候选变化区域。
///
/// 字段命名约束：面积字段必须是 `area_m2`。旧实现写作 `are_m2`（拼写残缺），
/// 且同一拼写在 GeoJSON `properties` 中又被写成正确的 `area_m2`，两处不一致
/// 属缺陷 D-9，Phase 2 已统一。
struct Region {
    int label = 0;                   ///< 从 1 起编号，按 raster-scan 首次出现顺序分配
    int pixel_count = 0;             ///< 成员像素个数
    double area_m2 = 0.0;            ///< 真实面积 = pixel_count × 单像元面积
    std::vector<PixelCoord> pixels;  ///< 成员像素，raster-scan 顺序
};
```

`PixelCoord` 的哈希**应当**可移植。禁止写 `row << 32`——该表达式在 `size_t` 为
32 位的平台上是未定义行为：

```cpp
template <>
struct hash<spatial::PixelCoord> {
    std::size_t operator()(const spatial::PixelCoord& p) const noexcept {
        const std::size_t r = static_cast<std::size_t>(static_cast<std::uint32_t>(p.row));
        const std::size_t c = static_cast<std::size_t>(static_cast<std::uint32_t>(p.col));
        return (r * 1000003U) ^ (c + 0x9E3779B9U + (r << 6) + (r >> 2));
    }
};
```

轮廓容器 `engine/include/spatial/contour.hpp`：

```cpp
/// 一个连通域的全部轮廓。
struct Boundary {
    std::vector<PixelCoord> outline;             ///< 外环，非空即为有效轮廓
    std::vector<std::vector<PixelCoord>> holes;  ///< 洞环，每个洞一条
};
```

**顶点约定**（Phase 2.1 起）：每条环**首尾不重复**（闭合由导出层补上首点）；顶点是
**像素角点格点** `(r, c)`，`row ∈ [0, H]`、`col ∈ [0, W]`，即像素 `(r, c)` 的左上角；
相邻顶点由水平或竖直的直线段相连，段长可为多个像素；环上不留共线的冗余顶点。

外环有向面积为**正**、洞环为**负**，符号相反既是判别依据，也保证导出到经纬度后外环
为逆时针，符合 RFC 7946 对 Polygon 外环方向的要求。

---

## 2. 环节一：Two-Pass 连通域标记

`engine/src/labeling.cpp`

### 2.1 为什么不能用 `unordered_map` 分组

旧实现把像素按**根标签**塞进 `std::unordered_map<int, Region>`，再遍历该映射给
`label` 赋 1、2、3……。`unordered_map` 的迭代顺序由哈希桶布局决定，标准不保证可重现，
于是同一幅影像在不同标准库实现、不同编译选项下会得到不同的 `label` 顺序（**D-6**）。
后果是 GeoJSON 输出无法逐字节比对。

现行实现改为「**扫描顺序即首次出现顺序**」：Pass 2 沿 raster-scan 走一遍，用一张
`root → regions 下标` 的槽位表把每个连通域**在其第一个像素处**登记进结果。`regions`
的下标因此由扫描顺序唯一决定，与任何哈希容器的迭代序无关。

### 2.2 并查集

```cpp
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
```

「编号小者作根」不是随意选择：它保证等价类代表元与扫描顺序一致，这是后面
`root_slot` 槽位表能稳定工作的前提。

### 2.3 主体

```cpp
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
```

**邻接定义**：只看左、上两个邻居 ⇒ **4 邻域连通**。若需 8 邻域，须同时在 Pass 1 检查
左上、右上两个对角邻居，并同步修改 `contour.cpp` 的边界定义——两处必须一致。

**面积权威值**：`area_m2 = pixel_count × |det(左上 2×2 仿射子阵)|`。该值是面积的权威
来源；几何面积（由环的鞋带公式算得）可能更小，理由见 §5。

---

## 3. 环节二：沿像素边界追踪（crack following）

`engine/src/contour.cpp`

### 3.1 缺陷 D-2 的形态

旧实现的追踪函数存在两个叠加问题：

```cpp
// 旧实现（示意）
std::vector<PixelCoord> ring = {start};
while (true) {
    for (d in 0..7) {
        n = cur + dir[d];
        if (in_region(n) && is_boundary(n) && !visited(n)) {
            ring.push_back(n);
            if (n == start) return ring;
            visited.insert(n);          // ← 只插入了 n
            cur = n; break;
        }
    }
}
```

1. **起点从未进入 `visited`。** 环回到起点后通过 `n == start` 直接返回，
   `visited.insert(start)` 那行根本没机会执行。外层主循环随后按 raster-scan 遍历像素
   时，`visited.count(start)` 为 0，同一个连通域会被再次起头。
2. **扫描起点没有携带。** 每步都从方向 0（正右）重新开始扫描，等价于假定「上一个像素
   永远在正左方」。这只在水平的左上角成立；一旦走到边界的竖直段或凹角，扫描会立刻折回
   刚刚走过的像素，追踪在那里断掉。

两者共同造成**一个连通域的边界被劈成若干段互不相接的弧**。基线样本（圆盘，7209 像素）
实测产出 2 条弧，于是 GeoJSON 出现 2 个 Feature、面积被计了 2 倍。

### 3.2 几何基准的变更：像素中心 → 像素角点

Phase 2 的实现在**像素中心**取样：环的顶点是边界像素的中心。由此外环是区域的**内接**
多边形，几何面积恒小于真实面积，且偏差随区域变小而放大：

| 样本 | 上报面积 | 几何面积 | 偏差 |
|---|---|---|---|
| `change_mask`（7209 像素，单区域） | 720 900 m² | 699 800 m² | −2.93 % |
| `multi_region_mask` | 65 800 m² | 54 200 m² | −17.63 % |
| 其中最小的区域（35 像素） | 3 500 m² | 2 400 m² | −31.4 % |

Phase 2.1 改在**像素边界**上取样：环沿相邻像素之间的「缝」行进，顶点是角点格点
`(r, c)`，`r ∈ [0, H]`、`c ∈ [0, W]`。于是环围出的多边形恰好等于成员像素的并集：

    几何面积（像素单位） == 成员像素个数

这使几何面积与 `area_m2` 恒等（偏差仅来自浮点表示），并与 GDAL 栅格转多边形的语义
对齐——`geo[0]`、`geo[3]` 是左上角像素的左上角，与格点 `(0, 0)` 重合。

**这一变更同时改变了「退化几何」的判定。** 一像素宽的细长结构在像素中心基准下顶点
全部共线、有向面积为 0，被当作退化轮廓剔除；在像素角点基准下它是**合法的矩形**，
必须产出 Feature。`multi_region_mask` 夹具的 `line_e` 正是这种情形，该夹具的 Feature
数因此由 5 变为 6（见 §9）。

### 3.3 建边图

追踪不再是「逐像素扫描邻居」，而是**把边界表示成图再分解**。

Phase 2 曾在 Moore 追踪上补一个 `scan_from` 状态把 D-2 修好（成因见 §3.1）。Phase 2.1
换掉了这个思路：它不修补扫描顺序，而是让「一个连通域只产出一条外环」成为**图的性质**。

成员像素朝向背景的每条边转成一条**有向**单位边，方向取「区域恒在行进方向右侧」：

```cpp
/// 4 个边方向：0=东 1=南 2=西 3=北。在 `(行, 列)` 平面上该序即顺时针。
constexpr int kSides = 4;
constexpr int kDr[kSides] = {0, 1, 0, -1};
constexpr int kDc[kSides] = {1, 0, -1, 0};

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
```

| 暴露边 | 条件 | 有向边 | 方向 |
|---|---|---|---|
| 上边 | `(r−1, c) ∉ R` | `(r, c) → (r, c+1)` | 东 |
| 右边 | `(r, c+1) ∉ R` | `(r, c+1) → (r+1, c+1)` | 南 |
| 下边 | `(r+1, c) ∉ R` | `(r+1, c+1) → (r+1, c)` | 西 |
| 左边 | `(r, c−1) ∉ R` | `(r+1, c) → (r, c)` | 北 |

每条边恰由一侧的成员像素产生，故**每个节点的出度等于入度**，取值 0 / 2 / 4。这一性质
是「每条边恰用一次即可分解为环」的前提。

节点容器用**有序** `std::map` 而非哈希容器：起始边按 `(行, 列)` 字典序取，输出因而与
标准库实现、平台都无关。旧实现用 `unordered_map` 分组，迭代序未定义，正是缺陷 **D-6**。

```cpp
/// 角点格点按 `(行, 列)` 字典序排列。
///
/// 用有序容器而非哈希容器，是为了让「从哪条边开始行走」成为**几何决定的**量。
struct NodeOrder {
    [[nodiscard]] bool operator()(const PixelCoord& a, const PixelCoord& b) const noexcept {
        return (a.row != b.row) ? (a.row < b.row) : (a.col < b.col);
    }
};

/// 节点 → 方向位掩码。
using NodeMap = std::map<PixelCoord, std::uint8_t, NodeOrder>;
```

### 3.4 行走：逆时针优先与夹点

每个节点在「到达方向」基础上按**逆时针优先**选下一条未使用的边：直行 → 逆时针 90° →
180° → 顺时针 90°。

```cpp
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
```

**出度为 1** 时选择唯一，没有自由度。**出度为 2** 只发生在区域于某个角点上自我相切的
情形（「夹点」）：该角点关联两条边界，逆时针优先规则把它们并成一条环。这与「一个
4 连通域只产出一条外环」的约定一致。这种环在该角点上自我相切，不满足 OGC Simple
Features 对简单环的要求，是**已知限制**；旧 Moore 实现同样会产生自相切的环，故不是回归。

```cpp
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
```

**本实现不依赖 `visited` 集合**，也不携带「上一次扫描方向」——旧实现在这两处各有一个
缺陷（见 §3.1）。这里「一个连通域只出一条外环」由图的构造保证，而不是扫描顺序的巧合。

边图分解得到的是**逐像素**的顶点序列（每个格点一个顶点），合并共线是下一步。

### 3.5 合并共线

同向的连续步长合并，只保留转折点。不做这一步，环上会为每个边界像素留一个顶点，顶点数
膨胀且毫无信息。

```cpp
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
```

判据用**整数差**而非浮点夹角：步长与方向都是整数，比较精确且无平台差异。

合并后环的顶点数等于**转折点数**。例如 3×3 实心方块的边界有 12 个格点，合并后只剩 4 个
角点；一像素宽竖条（1×5）也从 12 个格点合并为 4 个角点。环上因此**不留共线的冗余
顶点**——这条性质由 `engine/tests/test_contour.cpp` 的 `check_ring_shape` 逐点断言。

### 3.6 环的分类：外环与洞环

边图分解可能产出多条环：外环，以及每个洞各一条环。分类依据是**有向面积的符号**。

```cpp
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
```

**洞不再需要单独的洪泛搜索。** 洞的边界本来就是这个边图里与外环不相接的另一条独立环
——洞是被区域包围住的背景，四周都是成员像素，那些像素朝向背景的边自然连成一条闭环。
因此 `find_holes` 与 `pixels_around` 两个函数**整体删除**：

* 旧 `find_holes` 在区域外接矩形内对背景做洪泛，把「能到达矩形边界」的像素判为外部
  背景，其余判为洞。它需要一份与外接矩形同尺寸的状态数组，且必须按行、按列分别列举
  边界作为洪泛种子。这些复杂度在边图表示下全部消失。
* 旧 `pixels_around` 取「与洞 4 邻接的区域像素」作为内环输入，是对「洞用背景像素表示」
  这一选择的补偿（采样一致 + 让一像素的洞也能凑出环）。新实现直接得到洞的格点环，
  该补偿随之作废。

由此「一像素的洞凑不出环」这个问题从根上消失：一像素的洞围出的正是 4 个格点构成的
单位正方形，有向面积为 −2，是合法内环。

洞环之间按**规范顶点**排序，使洞环顺序只取决于几何，不取决于行走起点：

```cpp
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
```

### 3.7 入口与退化处理

```cpp
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
```

**输入约定**：期望输入是**单一 4 连通分量**（`extract_regions` 即如此调用）。若传入多个
不相接的分量，只有有向面积最大的那一条外环被返回，其余被丢弃。

**边界情形**：成员像素少于 3 个时返回**默认构造的空 `Boundary`**（`outline` 为空），
不返回含空环的容器——旧实现返回 `{{}}`，语义含糊，属缺陷 **D-7**。该尺寸下限是独立于
几何取样基准的约定，Phase 2.1 未改动。

**退化几何只剩一种**：成员像素少于 3 个。像素角点基准下，任何不少于 3 个像素的 4 连通
分量都能围出正面积的合法环 —— 包括一像素宽的细长结构。

---

## 4. 环节三：闭曲线 Douglas-Peucker 简化

`engine/src/simplify.cpp`

### 4.1 为什么不能直接套开曲线 DP

Douglas-Peucker 的递归边界是「弦的两个端点固定不动」。把它用在闭合环上时，最自然的
写法是拿 `ring.front()` 与 `ring.back()` 当端点——但环上本来就没有「端点」，首尾两点
是相邻的。这一写法等于在环上人为挑了一条裂缝：

* 裂缝处的几何特征被强制保留，哪怕它毫无特殊性；
* 同一个形状只要换个起始像素，简化结果就会变，输出不可复现。

### 4.2 两处消痕

**（1）规范化起点。** 以 `(row, col)` 最小的顶点为逻辑 0 号。环上本没有端点，输入起点
只是上游追踪恰好选中的位置。

```cpp
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
```

**（2）三锚点切分。** 取三个由几何决定的锚点，把环拆成三段开曲线，各自跑标准 DP。

```cpp
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
```

### 4.3 三段递归与合并

```cpp
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
```

递归内核刻意做成「只置位、不清除」：

```cpp
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
```

距离度量（点到线段，不是点到直线）：

```cpp
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
```

### 4.4 保证

* 结果只取决于环的**几何形状**，与起始像素无关。
* 三个锚点必然保留 ⇒ 结果恒不少于 3 点。
* 容差增大时顶点数**单调不增**（回退分支已消除）。
* **容差非正时不简化，原样返回。**

最后一条是 Phase 2.1 新增的，其语义价值在**面积精确守恒**：

```cpp
std::vector<PixelCoord> simplify_boundary(const std::vector<PixelCoord>& ring, double tolerance) {
    const std::size_t count = ring.size();
    if (count < 4) {
        return ring;  // 少于 4 点无法在闭合环上做有意义的简化
    }
    if (tolerance <= 0.0) {
        // 容差 0 的语义是「面积精确守恒」，见头文件。此处短路而非交给浮点
        // 距离比较：顶点恰好落在弦上时距离为 0，会被判为可删，几何随之改变。
        return ring;
    }
    // ... 规范化起点 → 三锚点切分 → 三段递归
}
```

Douglas-Peucker 在容差 0 下本应只删除与弦**严格共线**的顶点，但「顶点落在弦上」的判定
是浮点垂直距离比较（`distance_to_segment`），正交阶梯的角点完全可能被判为距离 0 而被
删除——那会改变几何面积。既然容差 0 的用途正是让几何面积等于 `area_m2`（§5.4），此处
直接短路，让该性质**由构造保证**，而不是由浮点比较的巧合保证。

| 性质 | 旧实现 | 现行实现 |
|---|---|---|
| 与起始像素无关 | ✗ | ✓ |
| 顶点数下限 3 | ✗ | ✓ |
| 容差单调性 | ✗（实测 1.5→4 点、4.0→8 点） | ✓ |
| 容差 0 时面积精确守恒 | ✗（浮点比较，可能删掉角点） | ✓（短路返回） |

---

## 5. 环节四：GeoJSON 组装

`engine/src/geojson.cpp`

### 5.1 缺陷 D-3：属性归属

旧实现对**每一条环**各生成一个 Feature，并把 Region 级的 `pixel_count`、`area_m2`
原样复制进每个 Feature 的 properties。一个 Region 若含 N 条环，它的面积就在输出里
出现 N 次。

基线样本正好踩中这个坑：单连通域的边界被 **D-2** 劈成 2 条弧，于是 720900 m² 的真实
面积在输出里合计成 1441800 m²——虚报整整一倍。

修复采用标准 GeoJSON 语义：**一个 Region 一个 Feature**，其 Polygon 以首条环为外环、
其余环为内环，properties 保持 Region 级且只出现一次。

### 5.2 退化轮廓的判定

判据建立在 `signed_area_twice`（鞋带公式）之上，其实现与符号约定见 §3.6：

```cpp
/// 闭合折线有向面积的两倍（鞋带公式）。
///
/// 顶点为整数角点格点，故结果必为整数；等于 0 表示所有顶点共线，几何退化。
long long signed_area_twice(const std::vector<PixelCoord>& ring);

/// 环是否足以构成有效多边形：顶点数够，且不共线。
///
/// 顶点取像素角点后，「一像素宽的细长结构」不再落入此处：它围出的是合法矩形。
/// 余下的退化来源是成员少于 3 个像素的区域 —— 轮廓层即返回空环，被第一条判据
/// 挡下。第二条判据（共线）因此是**防御性**的：它拦住任何意外产出零面积环的
/// 情形，而不是在描述一类已知输入。
bool forms_polygon(const std::vector<PixelCoord>& ring) {
    return ring.size() >= 3 && signed_area_twice(ring) != 0;
}
```

两道判据都必须保留：

1. 顶点少于 3，无法构成多边形；
2. 顶点全部共线（有向面积为 0）——这类几何不满足 OGC Simple Features 对 Polygon 的
   要求，交给 GEOS 会直接判 invalid。

旧实现只覆盖了第 1 种，第 2 种会产出面积为 0 的「多边形」，交给 GEOS 直接判 invalid。

**Phase 2.1 起第 2 种不再由已知输入触发**：像素角点基准下，任何不少于 3 个像素的 4 连通
分量都能围出正面积的环（§3.7）。保留该判据是因为「输出必须是合法非退化多边形」这一约定
不应依赖上游恰好只给出良态输入。

判定在**简化前后各做一次**——`extract_boundary` 之后一次、`simplify_boundary` 之后一次。
后者不可省：取正容差时简化可能把环压成共线（见 §4.4），此时必须放弃整个 Region，而不是
输出零面积几何。

### 5.3 主体

```cpp
/// 像素坐标 → 地理坐标（经度、纬度）。
std::pair<double, double> pixel_to_geo(int row, int col, const double geo_transform[6]) {
    const double lon = geo_transform[0] + (static_cast<double>(col) * geo_transform[1]) +
                       (static_cast<double>(row) * geo_transform[2]);
    const double lat = geo_transform[3] + (static_cast<double>(col) * geo_transform[4]) +
                       (static_cast<double>(row) * geo_transform[5]);
    return {lon, lat};
}

/// 环 → GeoJSON 坐标数组，并按 Polygon 约定补上闭合点（首点重复一次）。
Json ring_to_coordinates(const std::vector<PixelCoord>& ring, const double geo_transform[6]) {
    Json coordinates = Json::array();
    for (const auto& point : ring) {
        const auto [lon, lat] = pixel_to_geo(point.row, point.col, geo_transform);
        coordinates.push_back(Json::array({lon, lat}));
    }
    // 退化在调用方已经挡掉，此处只负责闭合
    if (!coordinates.empty() && coordinates.front() != coordinates.back()) {
        coordinates.push_back(coordinates.front());
    }
    return coordinates;
}

std::string regions_to_geojson(const std::vector<Region>& regions, const double geo_transform[6],
                               const GeoJsonOptions& options) {
    Json features = Json::array();

    for (const auto& region : regions) {
        const Boundary boundary = extract_boundary(region.pixels);
        if (!forms_polygon(boundary.outline)) {
            continue;  // D-7：轮廓退化，跳过该 Region
        }

        const auto outline = simplify_boundary(boundary.outline, options.simplify_tolerance);
        if (!forms_polygon(outline)) {
            continue;
        }

        Json rings = Json::array();
        rings.push_back(ring_to_coordinates(outline, geo_transform));

        for (const auto& hole : boundary.holes) {
            const auto simplified_hole = simplify_boundary(hole, options.simplify_tolerance);
            if (!forms_polygon(simplified_hole)) {
                continue;
            }
            rings.push_back(ring_to_coordinates(simplified_hole, geo_transform));
        }

        // 每个 Region 恰好产出一个 Feature，属性为 Region 级
        features.push_back(Json{
            {"type", "Feature"},
            {"geometry", Json{{"type", "Polygon"}, {"coordinates", std::move(rings)}}},
            {"properties",
             Json{{"label", region.label},
                  {"pixel_count", region.pixel_count},
                  {"area_m2", region.area_m2}}},
        });
    }

    const Json collection{
        {"type", "FeatureCollection"},
        {"features", std::move(features)},
    };
    return collection.dump();
}
```

**`properties` 字段名恰好三个**，禁止增删改名：`label` / `pixel_count` / `area_m2`。
旧实现在引擎内部把面积字段写成 `are_m2`（拼写残缺），却在 GeoJSON 里写成正确的
`area_m2`，两处不一致属缺陷 **D-9**。

### 5.4 面积约定

几何顶点取**像素角点**，环围出的多边形恰好等于成员像素的并集，因此

    几何面积（像素单位） == 成员像素个数

容差取默认值 0（不简化）时，几何面积与 `area_m2` **恒等**，偏差只来自浮点表示：

| 样本 | 上报面积合计 | 几何面积合计 | 偏差 |
|---|---|---|---|
| `change_mask`（7209 像素，单区域） | 720 900 m² | 720 900 m² | 0.00 % |
| `multi_region_mask`（6 连通域，6 个产出 Feature） | 66 300 m² | 66 300 m² | 0.00 % |

`scripts/verify_baseline.py` 的 §7.3 设有判据「几何面积 == 上报面积（像素角点基准）」，
偏差上限 `1e-6 %`。几何面积由 `shapely` 独立算出，不依赖被测代码。

**取正容差时的约定**：简化会打破上述恒等（实测圆盘容差 1.0 时几何面积偏 +0.19 %，小区域
偏差更大）。此时 **`area_m2` 是面积的权威值**，面积统计、报表、阈值判断必须取
`properties.area_m2`；几何面积只可用于显示与叠加。

#### 已裁定的行为变更（Phase 2.1）

Phase 2 取**像素中心**，故外环是**内接**多边形：一个 n×n 实心方块的外环面积是
`(n−1)²` 像素单位，而 `area_m2` 是 `n² × 单像元面积`。偏差随区域变小而放大——区域越小，
「四角各内缩半个像素」占周长的比重越大：

| 样本 | 上报面积合计 | 几何面积合计 | 偏差 |
|---|---|---|---|
| `change_mask`（7209 像素，单区域） | 720 900 m² | 699 800 m² | −2.93 % |
| `multi_region_mask` | 65 800 m² | 54 200 m² | −17.63 % |
| 其中最小的区域（35 像素） | 3 500 m² | 2 400 m² | −31.4 % |

「是否改为沿像素边界追踪」曾列为**待裁定**事项。该项已裁定为**执行**，并在 Phase 2.1
落地（实现见 §3.2）。变更的连带后果：

* 退化剔除只剩「成员少于 3 个像素」（§3.7 / §5.2）；
* `multi_region_mask` 夹具的 `line_e`（1 像素宽竖条）由「被剔除」变为「产出 Feature」，
  该夹具的 Feature 数由 5 变为 6，label 序列由 `1,2,3,4,5` 变为 `1,2,3,4,5,6`；
* 默认简化容差由 `2.0` 改为 `0.0`（§4.4）。

---

## 6. 绑定层入口

`engine/bindings/module.cpp`

绑定层**只做类型转换与参数校验，不含任何算法**。出现多分支业务逻辑即为越界——它应当
下沉到引擎的 `src/`。

```cpp
/// 掩膜的维度描述。
///
/// `dims` 记录原始维度数，`bands == 1` 表示单波段。两者都需要：2D `(H, W)` 与
/// 退化 3D `(1, H, W)` 的 `bands` 同为 1，只有 `dims` 能区分。
struct MaskShape {
    int dims = 0;
    int bands = 1;
    int height = 0;
    int width = 0;
};

using Uint8Mask = nb::ndarray<nb::numpy, std::uint8_t, nb::c_contig, nb::ro>;

/// 解析掩膜形状为 (bands, height, width)。
///
/// @throws std::invalid_argument 维度既不是 2 也不是 3
MaskShape parse_mask_shape(const Uint8Mask& mask) {
    const std::size_t ndim = mask.ndim();
    if (ndim == 2) {
        return MaskShape{2, 1, static_cast<int>(mask.shape(0)), static_cast<int>(mask.shape(1))};
    }
    if (ndim == 3) {
        return MaskShape{3, static_cast<int>(mask.shape(0)), static_cast<int>(mask.shape(1)),
                         static_cast<int>(mask.shape(2))};
    }
    throw std::invalid_argument("掩膜必须是 2D (H, W) 或 3D (B, H, W) 的 uint8 数组，实得 " +
                                std::to_string(ndim) + " 维");
}
```

### 6.1 缺陷 D-1：2D 掩膜的尺寸解析

旧实现写的是：

```cpp
int b = mask.ndim() == 3 ? static_cast<int>(mask.shape(0)) : 1;
int h = mask.shape(1);
int w = mask.shape(2);          // 2D 输入时越界
```

nanobind 的 ndarray 把 shape 与 strides 存放在**同一块**连续内存里（shape 在前、
strides 紧随其后）。因此对 2D 数组取 `shape(2)` 并不会越界崩溃，而是静默读到
`strides[0]`——它的值等于列数。于是 `h` 与 `w` 同时被写成该值，任何 2D 掩膜都被当作
`W × W` 落盘。

**这个错误长期不可见，因为基线样本是 256×256 的方形影像**，`H == W` 时错误恰好被
掩盖。非方形输入（如 100×200）才会暴露。测试必须含非方形样本。

### 6.2 严格模式：禁止隐式转换

nanobind 的 ndarray 转换器在直接匹配失败时**默认回退到转换**：dtype 不符就转型复制，
布局不符就拷成 C 连续。这带来一个静默出错的路径：

```python
mask_to_geojson(magnitude, geo)   # magnitude 是 CVA 的浮点幅度图
```

调用方漏掉二值化时，引擎不会报错，而是把每个非零像素当作变化像素，返回一份貌似合理的
错误结果。浮点值还会被截断（300.0 → 44，仍非零）。

因此两个掩膜参数**必须**加 `nb::noconvert()`：

```cpp
    m.def(
        "mask_to_geojson",
        [](const Uint8Mask& mask, const std::vector<double>& geo) {
            // 判据取 `dims != 2` 而非 `bands != 1`：退化 3D `(1, H, W)` 的
            // bands 也是 1，按后者会被静默当作 2D 接受，与本函数声明的
            // 「只接受 2D」矛盾。
            const MaskShape shape = parse_mask_shape(mask);
            if (shape.dims != 2) {
                throw std::invalid_argument(
                    "mask_to_geojson 只接受 2D (H, W) 的 uint8 掩膜，实得 3D (B, H, W)");
            }

            double transform[6] = {};
            parse_geo_transform(geo, transform);

            const auto regions =
                spatial::extract_regions(mask.data(), shape.width, shape.height, transform);
            return spatial::regions_to_geojson(regions, transform);
        },
        nb::arg("mask").noconvert(), nb::arg("geo"),
        "2D 变化掩膜 -> GeoJSON FeatureCollection 字符串");
```

`Uint8Mask` 带 `nb::ro` 的理由：引擎只读取掩膜，但取的是 `const std::uint8_t*`；而
nanobind 对非 const 标量的 `ndarray` 默认走 `cfg.ro == false` 分支，会在转换期直接拒绝
只读数组。显式标注后，读写数组与只读数组都接受，`np.frombuffer(...)` 等常见来源不再
被拒。

---

## 7. 上游：CVA / Otsu（Python 侧）

该段当前以**冻结参考实现**的形式存在于 `scripts/verify_baseline.py`，来源是旧仓库
`src/backend/detectors/cva.py` 与 `postprocessor.py` 的算法语义，逐行对齐（含 Otsu
直方图分箱方式与后处理顺序）。Phase 3 迁入 `backend` 时**必须**保持语义不变。

**纪律**：该区块不得随 backend 的重构而改动。若确需修改，必须走
「更新 `baseline.md` → 重跑三方对照 → 记录修订理由」流程。

```python
def frozen_otsu(data: np.ndarray, bins: int = 256) -> float:
    """Otsu 阈值：手动直方图 + 最大化类间方差。"""
    vmin = float(data.min())
    vmax = float(data.max())
    if vmax <= vmin:
        return vmin

    edges = np.linspace(vmin, vmax, bins + 1)
    width = edges[1] - edges[0]
    indices = np.clip(((data - vmin) / width).astype(np.int64), 0, bins - 1)
    counts = np.bincount(indices.ravel(), minlength=bins).astype(np.float64)
    centers = (edges[:-1] + edges[1:]) / 2.0

    total = counts.sum()
    if total == 0:
        return 0.0

    sum_all = float((centers * counts).sum())
    w_b = 0.0
    sum_b = 0.0
    best = 0.0
    max_variance = 0.0

    for i in range(bins):
        w_b += counts[i]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += centers[i] * counts[i]
        mean_b = sum_b / w_b
        mean_f = (sum_all - sum_b) / w_f
        variance = w_b * w_f * (mean_b - mean_f) ** 2
        if variance > max_variance:
            max_variance = variance
            best = float(centers[i])

    return best


def frozen_cva(before: np.ndarray, after: np.ndarray) -> tuple[float, np.ndarray]:
    """CVA：多维欧氏距离 + Otsu 二值化。"""
    delta = after.astype(np.float64) - before.astype(np.float64)
    magnitude = np.sqrt(np.sum(delta**2, axis=0))
    threshold = frozen_otsu(magnitude)
    return threshold, magnitude > threshold


def frozen_postprocess(mask: np.ndarray, min_size: int = 30) -> np.ndarray:
    """后处理：连通域过滤（>min_size）+ 3x3 闭运算。"""
    from scipy import ndimage

    label_mask, _ = ndimage.label(mask)
    counts = np.bincount(label_mask.ravel())
    keep = counts > min_size
    keep[0] = 0
    clean = keep[label_mask]
    return ndimage.binary_closing(clean, structure=np.ones((3, 3)), iterations=1)
```

注意 `frozen_postprocess` 的 `ndimage.label` 用的是 scipy **默认结构**（4 邻域），与
C++ 侧 `extract_regions` 的 4 邻域一致。两处必须同步修改，否则语义漂移。

**禁止用被测代码自证**：连通域个数必须由 scipy 独立计算作对照。

---

## 8. 缺陷对照表

### 8.1 旧仓库已确认的缺陷（D 系列）

| 编号 | 位置 | 缺陷 | 现行处理 |
|---|---|---|---|
| D-1 | `bindings/module.cpp` | 2D 掩膜取 `shape(2)` 读到 `strides[0]`，一律写成 `W×W` | 按 `ndim()` 显式分支 |
| D-2 | `contour.cpp` | 起点未入 `visited` + 扫描起点未携带 ⇒ 边界劈成多段弧 | 边图分解：有向单位边、每条边恰用一次；「一域一环」成为图的性质（§3.3） |
| D-3 | `geojson.cpp` | 每环一个 Feature 却带 Region 级属性 ⇒ 面积重复计 N 倍 | 一个 Region 一个 Feature |
| D-4 | `raster_io.cpp` | `GDALAllRegister()` 每次调用重复执行 | 一次性注册 |
| D-6 | `labeling.cpp` | `unordered_map` 迭代序未定义 ⇒ `label` 跨平台不确定 | raster-scan 首次出现顺序 |
| D-7 | `contour.cpp` / `geojson.cpp` | 退化轮廓处理含糊；未覆盖共线情形 | 成员 < 3 返回空 `Boundary`；`forms_polygon` 兜底。Phase 2.1 起共线判据转为防御性（§5.2） |
| D-8 | `simplify.cpp` | 开曲线 DP 套闭环 ⇒ 结果随起始像素变，且随容差非单调 | 规范化起点 + 三锚点切分 |
| D-9 | `region.hpp` | 面积字段写作 `are_m2`，与 GeoJSON 的 `area_m2` 不一致 | 统一为 `area_m2` |

### 8.2 Phase 2 新发现

| 位置 | 缺陷 | 现行处理 |
|---|---|---|
| `contour.cpp` | 1 像素的洞被 `hole.size() < 3` 丢弃 | 边图分解天然得到该环，`find_holes` / `pixels_around` 整体删除（§3.6） |
| `bindings/module.cpp` | nanobind 静默转换掩膜，浮点幅度图不报错 | 加 `nb::noconvert()` |
| `bindings/module.cpp` | 退化 3D `(1,H,W)` 被静默当作 2D | 判据改 `dims != 2` |

### 8.3 Phase 2.1 新发现

| 位置 | 问题 | 处理 |
|---|---|---|
| `contour.cpp` | 顶点取**像素中心** ⇒ 外环是内接多边形，几何面积恒小于 `area_m2`（基线 −2.93 %、多区域 −17.63 %、最小区域 −31.4 %） | 改沿像素边界追踪，面积恒等式由构造保证（§3.2） |
| `contour.cpp` / `geojson.cpp` | 一像素宽细长结构被当作「共线退化」**整条剔除**，其真实面积从输出中消失 | 角点基准下是合法矩形，不再剔除（§3.2）。`multi_region_mask` 的 Feature 数 5 → 6 |
| `geojson.hpp` / `simplify.cpp` | 默认容差 `2.0` 使几何面积与 `area_m2` 不一致；且容差 0 时面积守恒依赖浮点比较 | 默认改 `0.0`，容差非正即短路返回（§4.4） |
| `raster.hpp` / `gdal_init.cpp` | `gdal_registration_count()` 自标「仅供测试」，却经 `SPATIAL_API` 出现在公开头并进入 DLL 导出表 | 收归 `engine/src/internal/gdal_registry.hpp`（不安装、不进导出表）；测试改链静态库 `spatial_static` |
| `config/local.example.toml` | 模板 `build_dir` 写 `./engine/build`，实际是 `engine/build/dev-win` ⇒ 照模板配置会 `import _spatial` 失败 | 对齐 `default.toml` 与 CMake 预设；新增 `scripts/verify_config.py` 作门禁 |
| `pyproject.toml` | `ruff check` 在中文代码库上产生 246/253 项 RUF001–003 误报；lint 范围未含 `scripts/` | `ignore` RUF001/002/003，范围纳入 `scripts/`；`extend-exclude = ["docs"]` 使全仓库调用与声明范围调用一致 |

---

## 9. 不变量与复现

以下数值为**冻结锚点**，漂移即回归缺陷：

| 项 | 值 |
|---|---|
| Otsu 阈值 | `5.9168` |
| 变化像素 | `7209 / 65536` |
| 真实面积 | `720 900 m²` |
| 影像 | `(3, 256, 256) uint16` |
| GeoJSON Feature 数 | `1`（旧实现 `2`） |
| 属性面积合计 | `720 900 m²`（旧实现 `1 441 800 m²`） |

Phase 2.1 新增的锚点：

| 项 | 值 |
|---|---|
| 几何面积合计 == 属性面积合计 | 基线 + 多区域合计 `787 200 m²`，偏差 `0.00 %`（旧基准多区域 −17.63 %） |
| `multi_region_mask` 的 Feature 数 | `6`，等于连通域数（Phase 2 为 `5`） |
| `multi_region_mask` 的 label 序列 | `1,2,3,4,5,6` |
| 环的顶点基准 | 像素角点格点，`row ∈ [0, H]`、`col ∈ [0, W]` |

复现命令：

```bash
# 单元测试（40 项：边界、非方形、洞、一像素宽结构、几何面积恒等式）
ctest --test-dir engine/build/dev-win --output-on-failure    # 40/40

# 黄金基线（§7.1 / §7.2 / §7.3，含几何面积一致性）
uv run --no-sync python scripts/verify_baseline.py --phase 2

# 引擎 Python 契约（45 项）
uv run --no-sync python scripts/verify_bindings.py

# 配置与 CMake 预设的一致性（6 项）
uv run --no-sync python scripts/verify_config.py
```

夹具：`engine/tests/fixtures/`

| 文件 | 内容 |
|---|---|
| `change_mask.raw` / `.json` | 65536 字节，7209 像素，1 连通域，720900 m² |
| `multi_region_mask.raw` / `.json` | 120×64 非方形，6 连通域（4 实心 + 1 带洞 + 1 个 1 像素宽矩形）。Phase 2 曾把最后一者判为退化细条并整条剔除 |
| `before.tif` / `after.tif` | 基线影像对，`(3, 256, 256) uint16` |

**几何面积亦然**：`verify_baseline.py` 用 `shapely` 独立算出，不得调用引擎自身的
`signed_area_twice`；否则「几何面积 == 面积上报值」退化为自证。

---

## 10. 禁止事项

* **禁止**在绑定层写算法分支。绑定层只做类型转换与参数校验。
* **禁止**放宽掩膜参数的严格性（`nb::noconvert()` 不得移除）。放宽即重新引入
  「浮点幅度图静默通过」的错误路径。
* **禁止**让 C++ 侧接受非 `uint8`、非 C 连续的掩膜。
* **禁止**用 `unordered_map` 的迭代序决定输出顺序。
* **禁止**改 `_spatial` 的函数签名（backend 依赖该契约）。
* **禁止**在算法测试中使用方形影像作为唯一样本——`H == W` 会掩盖行列混淆类缺陷。
* **禁止**用被测代码自身验证自身（连通域个数须由 scipy 独立计算，几何面积须由
  `shapely` 独立计算）。
* **禁止**把轮廓顶点改回**像素中心**。该基准下几何面积恒小于 `area_m2`，只能靠「以
  `area_m2` 为准」的约定打补丁——那是把一个可判定的性质降级成人工纪律。判据见
  `verify_baseline.py` 的「几何面积 == 上报面积」。
* **禁止**移除 `simplify_boundary` 中「容差非正即短路」的分支，或把
  `GeoJsonOptions::simplify_tolerance` 的默认值改回正数。移除即把「容差 0 面积精确
  守恒」从构造保证降级为浮点巧合。
