/// @file module.cpp
/// @brief Python 扩展模块 `_spatial` 的绑定层。
///
/// 职责边界
/// --------
/// 本文件只做「Python 对象 ↔ C++ 类型」的转换与参数校验，不含任何算法。
/// 出现多分支业务逻辑即为越界——它应下沉到引擎的 `src/`。
///
/// D-1：2D 掩膜的尺寸解析
/// ---------------------
/// 旧实现写的是：
///
///     int b = mask.ndim() == 3 ? static_cast<int>(mask.shape(0)) : 1;
///     int h = mask.shape(1);
///     int w = mask.shape(2);          // 2D 输入时越界
///
/// nanobind 的 ndarray 把 shape 与 strides 存放在**同一块**连续内存里
/// （shape 在前、strides 紧随其后）。因此对 2D 数组取 `shape(2)` 并不会
/// 越界崩溃，而是静默读到 `strides[0]`——它的值等于列数。于是 `h` 与 `w`
/// 同时被写成该值，任何 2D 掩膜都被当作 `W × W` 落盘。
///
/// 这个错误长期不可见，因为基线样本是 256×256 的**方形**影像，`H == W`
/// 时错误恰好被掩盖。非方形输入（如 100×200）才会暴露。
///
/// 现在按 `ndim()` 显式分支，其余维度直接抛异常。
///
/// 掩膜参数的可写性
/// ---------------
/// `Uint8Mask` 带 `nb::ro`。引擎的 `write_raster` / `extract_regions` 只读取
/// 掩膜，但它们取的是 `const std::uint8_t*`；而 nanobind 对非 const 标量的
/// `ndarray` 默认走 `cfg.ro == false` 分支，会在转换期直接拒绝只读数组
/// （见 nanobind `src/nb_ndarray.cpp` 的 `flag_bitmask_read_only` 判定）。
///
/// 显式标注 `nb::ro` 后读写数组与只读数组都接受，且绑定的表述与引擎的真实
/// 契约一致。实际影响：`np.frombuffer(...)`、只读内存映射等常见来源不再被拒。
///
/// 掩膜参数的隐式转换
/// -----------------
/// nanobind 的 ndarray 转换器在直接匹配失败时**默认回退到转换**：dtype 不符
/// 就转型复制，布局不符就拷成 C 连续。这带来一个静默出错的路径——
///
///     mask_to_geojson(magnitude, geo)   # magnitude 是 CVA 的浮点幅度图
///
/// 调用方漏掉二值化时，引擎不会报错，而是把每个非零像素当作变化像素，返回
/// 一份貌似合理的错误结果。浮点值还会被截断（300.0 -> 44，仍非零）。
///
/// 因此两个掩膜参数都加 `nb::noconvert()`：类型与布局不符即抛 `TypeError`，
/// 由调用方显式转换。这使绑定的实际行为与上面声明的 `Uint8Mask` 一致——
/// 只读、C 连续、`uint8` 三种约束缺一不可。

#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

#include "spatial/geojson.hpp"
#include "spatial/labeling.hpp"
#include "spatial/raster.hpp"

namespace nb = nanobind;

namespace {

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

/// 把 Python 的 6 元列表拷进 C 数组。
///
/// @throws std::invalid_argument 长度不是 6
void parse_geo_transform(const std::vector<double>& geo, double (&out)[6]) {
    if (geo.size() != 6) {
        throw std::invalid_argument("geo_transform 必须是 6 个浮点数，实得 " +
                                    std::to_string(geo.size()) + " 个");
    }
    for (std::size_t i = 0; i < 6; ++i) {
        out[i] = geo[i];
    }
}

}  // namespace

NB_MODULE(_spatial, m) {
    m.doc() = "遥感变化检测空间引擎：GDAL 栅格读写与连通域矢量提取";

    m.def("print_gdal_version", &spatial::print_gdal_version, "打印底层 GDAL 版本号");

    // ------------------------------------------------------------------
    // read_raster(path) -> (array, width, height, bands, geo_transform, projection)
    // ------------------------------------------------------------------
    m.def(
        "read_raster",
        [](const std::string& path) {
            spatial::RasterData data = spatial::read_raster(path);

            // 像素缓冲的所有权转交堆，由 capsule 在 ndarray 回收时释放，
            // 使 Python 侧可零拷贝持有。
            auto* owned = new std::vector<std::uint16_t>(std::move(data.pixels));
            const nb::capsule owner(owned, [](void* pointer) noexcept {
                delete static_cast<std::vector<std::uint16_t>*>(pointer);
            });

            const std::size_t shape[3] = {static_cast<std::size_t>(data.band_count),
                                          static_cast<std::size_t>(data.height),
                                          static_cast<std::size_t>(data.width)};
            auto array =
                nb::ndarray<nb::numpy, std::uint16_t>(owned->data(), 3, shape, owner);

            const auto geo =
                std::vector<double>(data.geo_transform, data.geo_transform + 6);

            return nb::make_tuple(array, data.width, data.height, data.band_count, geo,
                                  data.projection);
        },
        nb::arg("path"), "读取 GeoTIFF 全部波段，返回 (array, width, height, bands, geo, projection)");

    // ------------------------------------------------------------------
    // write_raster(path, mask, geo, projection)
    // ------------------------------------------------------------------
    m.def(
        "write_raster",
        [](const std::string& path, const Uint8Mask& mask, const std::vector<double>& geo,
           const std::string& projection) {
            const MaskShape shape = parse_mask_shape(mask);
            double transform[6] = {};
            parse_geo_transform(geo, transform);
            spatial::write_raster(path, mask.data(), shape.width, shape.height, shape.bands,
                                  transform, projection);
        },
        nb::arg("path"), nb::arg("mask").noconvert(), nb::arg("geo"), nb::arg("projection"),
        "把 uint8 掩膜写成 GeoTIFF。mask 可为 2D (H, W) 或 3D (B, H, W)");

    // ------------------------------------------------------------------
    // mask_to_geojson(mask, geo) -> str
    // ------------------------------------------------------------------
    m.def(
        "mask_to_geojson",
        [](const Uint8Mask& mask, const std::vector<double>& geo) {
            // 形状解析只此一处（parse_mask_shape），此处仅追加「必须 2D」的
            // 约束。先前这里另写了一份 shape(0)/shape(1) 取值，属重复真相。
            //
            // 判据取 `dims != 2` 而非 `bands != 1`：退化 3D `(1, H, W)` 的
            // bands 也是 1，按后者会被静默当作 2D 接受，与本函数声明的
            // 「只接受 2D」矛盾。多波段影像里取单波段是常见操作，静默压维
            // 会掩盖调用方漏写 `arr[0]` 的错误。
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
}
