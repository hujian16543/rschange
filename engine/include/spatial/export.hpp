#pragma once

/// @file export.hpp
/// @brief 跨平台符号可见性宏 `SPATIAL_API` 的**唯一定义点**。
///
/// 背景
/// ----
/// nanobind 编译扩展模块时全局设置 `-fvisibility=hidden`。引擎的公开函数若不
/// 显式导出，Python 侧将链接不到符号。
///
/// 该宏此前在 `stats.hpp` 与 `tiff_io.hpp` 中各定义一份。重复定义在两边写法
/// 漂移时会产生难以定位的链接错误，故收敛到本文件；其余头文件一律
/// `#include "spatial/export.hpp"`。
///
/// 约定
/// ----
/// 构建引擎自身时由 CMake 定义 `SPATIAL_BUILDING`；消费方（如 `_spatial`
/// 绑定模块）不定义该宏，此时 Windows 下走 `dllimport`。

#if defined(_WIN32)
#  if defined(SPATIAL_BUILDING)
#    define SPATIAL_API __declspec(dllexport)
#  else
#    define SPATIAL_API __declspec(dllimport)
#  endif
#else
#  if defined(SPATIAL_BUILDING)
#    define SPATIAL_API __attribute__((visibility("default")))
#  else
#    define SPATIAL_API
#  endif
#endif
