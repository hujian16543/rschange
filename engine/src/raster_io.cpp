/// @file raster_io.cpp
/// @brief GeoTIFF 的读取与写出。
///
/// 与旧实现的差异
/// --------------
/// * `GDALAllRegister()` 收敛到 `ensure_gdal_initialized()`，不再每次调用重跑
///   全部驱动注册（D-4）。
/// * `GDALDataset` 由 RAII 持有，异常路径上不会泄漏句柄。旧实现在
///   `RasterIO` 失败时直接 `return`，`GDALClose` 被跳过。
/// * 失败一律抛 `std::runtime_error` 并带 GDAL 的错误消息，不再只往 stderr
///   写一行然后返回半初始化的结构体——那种做法让调用方无从判断失败原因。

#include "spatial/raster.hpp"

#include <gdal_priv.h>

#include <array>
#include <cstddef>
#include <memory>
#include <stdexcept>
#include <string>

namespace spatial {
namespace {

/// `GDALDataset` 的删除器。
struct DatasetCloser {
    void operator()(GDALDataset* dataset) const noexcept {
        if (dataset != nullptr) {
            GDALClose(dataset);
        }
    }
};

using DatasetPtr = std::unique_ptr<GDALDataset, DatasetCloser>;

[[noreturn]] void fail(const std::string& what) {
    throw std::runtime_error(what);
}

/// 取 GDAL 最近一条错误消息；为空时返回占位串，避免拼出空洞的诊断。
std::string last_gdal_error() {
    const char* message = CPLGetLastErrorMsg();
    return (message != nullptr && message[0] != '\0') ? std::string(message) : std::string("(GDAL 未提供错误消息)");
}

}  // namespace

RasterData read_raster(const std::string& filepath) {
    ensure_gdal_initialized();

    auto* opened = static_cast<GDALDataset*>(GDALOpen(filepath.c_str(), GA_ReadOnly));
    if (opened == nullptr) {
        fail("read_raster: 无法打开 " + filepath + "：" + last_gdal_error());
    }
    const DatasetPtr dataset{opened};

    RasterData result;
    result.width = dataset->GetRasterXSize();
    result.height = dataset->GetRasterYSize();
    result.band_count = dataset->GetRasterCount();

    if (result.empty()) {
        fail("read_raster: 影像尺寸或波段数非正：" + filepath);
    }

    const std::size_t per_band = result.pixels_per_band();
    result.pixels.resize(per_band * static_cast<std::size_t>(result.band_count));

    for (int index = 1; index <= result.band_count; ++index) {
        GDALRasterBand* band = dataset->GetRasterBand(index);
        if (band == nullptr) {
            fail("read_raster: 取不到第 " + std::to_string(index) + " 波段：" + filepath);
        }

        std::uint16_t* dest = result.pixels.data() + static_cast<std::size_t>(index - 1) * per_band;
        const CPLErr err = band->RasterIO(GF_Read, 0, 0, result.width, result.height, dest,
                                          result.width, result.height, GDT_UInt16, 0, 0);
        if (err != CE_None) {
            fail("read_raster: 第 " + std::to_string(index) + " 波段读取失败：" + filepath + "：" + last_gdal_error());
        }
    }

    dataset->GetGeoTransform(result.geo_transform);
    result.projection = dataset->GetProjectionRef();
    return result;
}

void write_raster(const std::string& path, const std::uint8_t* data, int width, int height,
                  int band_count, const double geo_transform[6], const std::string& projection) {
    if (data == nullptr) {
        fail("write_raster: 数据指针为空");
    }
    if (width <= 0 || height <= 0 || band_count <= 0) {
        fail("write_raster: 尺寸或波段数非正");
    }

    ensure_gdal_initialized();

    GDALDriver* driver = GetGDALDriverManager()->GetDriverByName("GTiff");
    if (driver == nullptr) {
        fail("write_raster: GTiff 驱动不可用");
    }

    auto* created = driver->Create(path.c_str(), width, height, band_count, GDT_Byte, nullptr);
    if (created == nullptr) {
        fail("write_raster: 创建失败 " + path + "：" + last_gdal_error());
    }
    const DatasetPtr dataset{created};

    // SetGeoTransform 要的是非 const 指针，因此从 const 入参拷一份。
    std::array<double, 6> transform{};
    for (std::size_t i = 0; i < transform.size(); ++i) {
        transform[i] = geo_transform[i];
    }
    dataset->SetGeoTransform(transform.data());
    dataset->SetProjection(projection.c_str());

    const std::size_t per_band = static_cast<std::size_t>(width) * static_cast<std::size_t>(height);
    for (int index = 1; index <= band_count; ++index) {
        GDALRasterBand* band = dataset->GetRasterBand(index);
        if (band == nullptr) {
            fail("write_raster: 取不到第 " + std::to_string(index) + " 波段：" + path);
        }

        auto* src = const_cast<std::uint8_t*>(data + static_cast<std::size_t>(index - 1) * per_band);
        const CPLErr err = band->RasterIO(GF_Write, 0, 0, width, height, src, width, height,
                                          GDT_Byte, 0, 0);
        if (err != CE_None) {
            fail("write_raster: 第 " + std::to_string(index) + " 波段写出失败：" + path + "：" + last_gdal_error());
        }
    }
}

}  // namespace spatial
