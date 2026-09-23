/// @file gdal_init.cpp
/// @brief GDAL 运行时的一次性初始化（缺陷 D-4 的修复点）。

#include "internal/gdal_registry.hpp"
#include "spatial/raster.hpp"

#include <gdal.h>

#include <atomic>
#include <mutex>

namespace spatial {
namespace {

/// `std::call_once` 保证 `GDALAllRegister()` 只执行一次，且在多线程下安全。
std::once_flag g_register_once;

/// 实际执行次数，仅供测试断言「一次性」是否成立。计数器留在本翻译单元的匿名
/// 命名空间内，外部只能经 spatial::internal::gdal_registration_count() 读取。
std::atomic<int> g_register_count{0};

}  // namespace

void ensure_gdal_initialized() {
    std::call_once(g_register_once, [] {
        GDALAllRegister();
        g_register_count.fetch_add(1, std::memory_order_relaxed);
    });
}

namespace internal {

int gdal_registration_count() noexcept {
    return g_register_count.load(std::memory_order_relaxed);
}

}  // namespace internal

}  // namespace spatial
