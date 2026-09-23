#pragma once

/// @file internal/gdal_registry.hpp
/// @brief 仅供测试的 GDAL 注册自省探针。**不属于公开 API，不导出，不安装。**
///
/// 背景
/// ----
/// `gdal_registration_count()` 原先声明在公开头 `spatial/raster.hpp` 并带
/// `SPATIAL_API`，因而出现在 `libspatial.dll` 的导出表里（Phase 2 观察项 O1）。
/// 问题不在于「多一个函数」，而在于它被冻结进了契约表面：一旦有消费者在
/// Python 侧或 C++ 侧调用，移除它就变成破坏性变更；而它唯一的用途是让
/// `test_raster_io.cpp` 对「GDAL 全驱动只注册一次」写出可断言判据——计时对比
/// 无法稳定成测。
///
/// 处置
/// ----
/// 头文件移入 `src/internal/`（不随 `install(DIRECTORY include/spatial ...)` 安装），
/// 声明不带 `SPATIAL_API`，Windows 下因而不进 DLL 导出表；非 Windows 下显式加
/// `visibility("hidden")`——共享库默认导出全部外部符号，仅靠「不加导出宏」不足以
/// 隐藏，必须显式声明。
///
/// 访问方式
/// --------
/// 仅 `engine/tests/` 可用：测试链接静态库 `spatial_static`（由同一份源码编译，
/// 定义 `SPATIAL_STATIC`），因此能直接解析该符号。共享库 `spatial` 的消费者
/// （`_spatial` 绑定模块）看不到它。
///
/// 共享库的导出面由 `scripts/verify_bindings.py` 的 45 项契约检查覆盖，不依赖
/// 本探针。

#if defined(_WIN32)
#  define SPATIAL_INTERNAL
#else
#  define SPATIAL_INTERNAL __attribute__((visibility("hidden")))
#endif

namespace spatial::internal {

/// 返回 `GDALAllRegister()` 的实际执行次数。
///
/// 判据来源：`std::call_once` 保护下的计数只应在首次 `ensure_gdal_initialized()`
/// 时自增一次；重复调用与经由 `read_raster` / `write_raster` 的隐式调用都不得
/// 使其增长（缺陷 D-4 的回归防线）。
SPATIAL_INTERNAL int gdal_registration_count() noexcept;

}  // namespace spatial::internal
