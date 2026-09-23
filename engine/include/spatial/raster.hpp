#pragma once

/// @file raster.hpp
/// @brief 栅格影像的读取、写出，以及 GDAL 运行时的一次性初始化。

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "spatial/export.hpp"

namespace spatial {

/// 一幅栅格影像的全部波段与空间参考。
///
/// 内存布局为 band-sequential：`pixels` 依次存放波段 0 的全部像素、波段 1 的
/// 全部像素……与 nanobind 交出的 `(bands, height, width)` 数组布局一致，
/// 因此 Python 侧可零拷贝持有。
struct RasterData {
    int width = 0;                      ///< 列数
    int height = 0;                     ///< 行数
    int band_count = 0;                 ///< 波段数
    std::vector<std::uint16_t> pixels;  ///< band-sequential 像素
    double geo_transform[6] = {};       ///< GDAL 仿射变换 6 参数
    std::string projection;             ///< WKT / PROJ 字符串

    [[nodiscard]] bool empty() const noexcept {
        return width <= 0 || height <= 0 || band_count <= 0;
    }

    [[nodiscard]] std::size_t pixels_per_band() const noexcept {
        return static_cast<std::size_t>(width) * static_cast<std::size_t>(height);
    }
};

/// 注册 GDAL 全部驱动。
///
/// 幂等：无论调用多少次，`GDALAllRegister()` 只真正执行一次（`std::call_once`
/// 保护）。旧实现在 `read_raster` / `write_raster` 各调一次，每次调用都重新
/// 遍历并注册全部驱动，属缺陷 D-4。
SPATIAL_API void ensure_gdal_initialized();

/// 读取 GeoTIFF 的全部波段。
///
/// @throws std::runtime_error 打开失败、波段类型不符或 `RasterIO` 出错。
SPATIAL_API RasterData read_raster(const std::string& filepath);

/// 以 GTiff 格式写出 `uint8` 栅格。
///
/// @param data band-sequential 缓冲区，长度须为 `width * height * band_count`
/// @throws std::runtime_error 驱动不可用、创建失败或 `RasterIO` 出错。
SPATIAL_API void write_raster(const std::string& path, const std::uint8_t* data,
                              int width, int height, int band_count,
                              const double geo_transform[6],
                              const std::string& projection);

/// 将 GDAL 版本号打印到 stdout。诊断用。
SPATIAL_API void print_gdal_version();

}  // namespace spatial
