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
/// 三种编译形态，由 CMake 各定义一个宏区分：
///
/// | 形态                  | 宏                 | Windows 下展开为  |
/// |-----------------------|--------------------|-------------------|
/// | 构建共享库 `spatial`  | `SPATIAL_BUILDING` | `__declspec(dllexport)` |
/// | 消费共享库（`_spatial`） | 不定义           | `__declspec(dllimport)` |
/// | 构建/链接静态库 `spatial_static` | `SPATIAL_STATIC` | 空字符串 |
///
/// `SPATIAL_STATIC` 必须优先于 `SPATIAL_BUILDING` 判断。静态库没有导入库，
/// 若按消费方走 `dllimport`，链接期会去找并不存在的 `libspatial.lib` 导入记录。
/// 该宏由 `spatial_static` 以 `PUBLIC` 传播，静态链接的测试因此自动取到空展开。

#if defined(_WIN32)
#  if defined(SPATIAL_STATIC)
#    define SPATIAL_API
#  elif defined(SPATIAL_BUILDING)
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
