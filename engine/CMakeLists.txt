# ============================================================================
# spatial · 空间计算引擎
#
# 设计约定
# --------
# * 编译选项只作用于本工程自身的 target，不用 add_compile_options 全局下发。
#   这样第三方依赖（nlohmann/json、Catch2）不会被我们的告警策略牵连，
#   也便于 Phase 2 末段单独开启 -Werror。
# * 版本号与 project VERSION 同步推进，不另设 VERSION 文件。
# ============================================================================
cmake_minimum_required(VERSION 3.24)

project(
    spatial
    VERSION 0.2.0
    DESCRIPTION "Spatial engine for remote sensing change detection"
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Debug CACHE STRING "构建类型" FORCE)
endif()

# 引擎以共享库形式供 Python 扩展链接。
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# ---------------------------------------------------------------------------
# 外部依赖
# ---------------------------------------------------------------------------
# nlohmann/json：旧仓库把 1 MB 的单头文件提交进版本控制，属应当避免的做法。
# 改为构建期获取，版本由 URL 中的 tag 钉死，升级须显式修改此处。
include(FetchContent)

FetchContent_Declare(
    json
    URL https://codeload.github.com/nlohmann/json/tar.gz/refs/tags/v3.11.3
)
set(JSON_BuildTests OFF CACHE INTERNAL "不构建 nlohmann/json 自带测试")
set(JSON_Install OFF CACHE INTERNAL "不安装 nlohmann/json")
FetchContent_MakeAvailable(json)

# GDAL：由 SPATIAL_GDAL_ROOT 精确指路。
#
# 禁止为找 GDAL 而把 MSYS2 前缀塞进 CMAKE_PREFIX_PATH。该前缀内含第二套
# CPython，会让 find_package(Python) 解析出错误的导入库，详见本文件末段
# 「Python 运行时一致性」。故此处的搜索范围只临时收敛到 SPATIAL_GDAL_ROOT，
# 查找结束后立即还原，不给后续 find_package 留下污染。
if(SPATIAL_GDAL_ROOT)
    set(_spatial_saved_cmake_prefix_path "${CMAKE_PREFIX_PATH}")
    set(CMAKE_PREFIX_PATH "${SPATIAL_GDAL_ROOT}")
endif()

find_package(GDAL REQUIRED)

if(DEFINED _spatial_saved_cmake_prefix_path)
    set(CMAKE_PREFIX_PATH "${_spatial_saved_cmake_prefix_path}")
    unset(_spatial_saved_cmake_prefix_path)
endif()

# ---------------------------------------------------------------------------
# 引擎共享库
# ---------------------------------------------------------------------------
add_library(spatial SHARED)
add_library(spatial::spatial ALIAS spatial)

target_sources(
    spatial
    PRIVATE
        src/contour.cpp
        src/gdal_init.cpp
        src/geojson.cpp
        src/labeling.cpp
        src/raster_io.cpp
        src/simplify.cpp
        src/version.cpp
)

target_include_directories(
    spatial
    PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src
)

# 定义 SPATIAL_BUILDING 使 export.hpp 走 dllexport 分支。
target_compile_definitions(spatial PRIVATE SPATIAL_BUILDING)

target_compile_options(
    spatial
    PRIVATE
        -Wall
        -Wextra
        -Wpedantic
)

target_link_libraries(
    spatial
    PRIVATE
        GDAL::GDAL
        nlohmann_json::nlohmann_json
)

# ---------------------------------------------------------------------------
# Python 扩展模块 _spatial
# ---------------------------------------------------------------------------
find_package(Python 3.10 COMPONENTS Interpreter Development.Module REQUIRED)

# ---------------------------------------------------------------------------
# Python 运行时一致性
# ---------------------------------------------------------------------------
# 背景
# ----
# 本机的 C++ 编译器是 MSYS2 的 mingw-w64 g++，而 CPython 由 python.org 官方
# 安装包提供（MSVC 构建，运行时名为 python314.dll）。二者属**两套独立运行时**：
# MSYS2 的 mingw64 前缀内另有一份自建 CPython，运行时名为 libpython3.14.dll。
#
# 客观后果（本机实测）
# --------------------
# 先前为找到 GDAL 而把 MSYS2 前缀写进 CMAKE_PREFIX_PATH，导致
# find_package(Python) 出现「头对库错」的解析：
#
#   _Python_INCLUDE_DIR      = C:/Users/Hujian/DevCode/python/python3.14/Include   （宿主，正确）
#   _Python_LIBRARY_RELEASE  = C:/Users/Hujian/DevCode/msys64/mingw64/lib/libpython3.14.dll.a （MSYS2，错误）
#
# 该扩展 import 时，为加载 libgdal-38.dll 必须把 msys64/mingw64/bin 放进 DLL
# 搜索路径，进程内因此装入第二份 CPython；nanobind 以该运行时的 API 操作宿主
# 的 PyObject，首次调用即访问违例。实测退出码 0xC0000005，且 Python 块缓冲
# 随进程一并丢失，stdout 全空——崩溃点因此极难定位。
#
# 处理
# ----
# 解释器、头目录、运行时库必须落在同一套安装之下。以下校验把这类「错源」由
# 运行期的访问违例提前为配置期的明确失败。
# ---------------------------------------------------------------------------
execute_process(
    COMMAND "${Python_EXECUTABLE}" -c "import sys; print(sys.base_prefix)"
    OUTPUT_VARIABLE _spatial_py_base_prefix
    OUTPUT_STRIP_TRAILING_WHITESPACE
    RESULT_VARIABLE _spatial_py_base_status
)
if(NOT _spatial_py_base_status EQUAL 0)
    message(FATAL_ERROR "无法向解释器询问安装前缀：${Python_EXECUTABLE}")
endif()

file(TO_CMAKE_PATH "${_spatial_py_base_prefix}" _spatial_py_base_prefix)

# 比较前统一大小写（Windows 路径不区分大小写），并去掉尾部斜杠。
string(REGEX REPLACE "/+$" "" _spatial_py_base_prefix "${_spatial_py_base_prefix}")
if(WIN32)
    string(TOLOWER "${_spatial_py_base_prefix}" _spatial_py_base_cmp)
else()
    set(_spatial_py_base_cmp "${_spatial_py_base_prefix}")
endif()

# 断言：artifact 位于 Python 安装前缀之下。空值与 -NOTFOUND 直接放行——
# 部分平台（如 Linux 的 Development.Module）不提供运行时库。
function(spatial_require_under_python_prefix artifact label)
    if(NOT artifact OR artifact MATCHES "-NOTFOUND$")
        return()
    endif()
    file(TO_CMAKE_PATH "${artifact}" _artifact_cm)
    if(WIN32)
        string(TOLOWER "${_artifact_cm}" _artifact_cmp)
    else()
        set(_artifact_cmp "${_artifact_cm}")
    endif()
    string(FIND "${_artifact_cmp}" "${_spatial_py_base_cmp}/" _position)
    if(NOT _position EQUAL 0)
        message(
            FATAL_ERROR
            "${label} 不在 Python 安装前缀之下。\n"
            "  解释器        : ${Python_EXECUTABLE}\n"
            "  安装前缀      : ${_spatial_py_base_prefix}\n"
            "  实得          : ${artifact}\n"
            "Python 扩展的解释器、头目录与运行时库必须来自同一套安装；错源会在进程内\n"
            "装入两套 CPython，表现为 import 时 0xC0000005 访问违例。\n"
            "请检查 CMAKE_PREFIX_PATH 是否指向了另含一份 Python 的前缀（例如 MSYS2 的 mingw64）。"
        )
    endif()
endfunction()

spatial_require_under_python_prefix("${Python_INCLUDE_DIRS}" "Python 头目录")

if(WIN32)
    foreach(_spatial_py_artifact IN ITEMS IMPORTED_LOCATION IMPORTED_IMPLIB)
        get_target_property(_spatial_py_value Python::Module ${_spatial_py_artifact})
        spatial_require_under_python_prefix(
            "${_spatial_py_value}"
            "Python::Module 的 ${_spatial_py_artifact}"
        )
    endforeach()
    unset(_spatial_py_artifact)
    unset(_spatial_py_value)
endif()

# nanobind 的 CMake 配置随 pip 包分发。未显式指定时向解释器询问其位置，
# 免得每个调用方都要手工传 -Dnanobind_DIR。
if(NOT nanobind_DIR)
    execute_process(
        COMMAND "${Python_EXECUTABLE}" -c
                "import nanobind, pathlib; print(pathlib.Path(nanobind.__file__).parent / 'cmake')"
        OUTPUT_VARIABLE _nanobind_cmake_dir
        OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE _nanobind_probe_status
    )
    if(_nanobind_probe_status EQUAL 0 AND EXISTS "${_nanobind_cmake_dir}")
        set(nanobind_DIR "${_nanobind_cmake_dir}")
    else()
        message(FATAL_ERROR "找不到 nanobind 的 CMake 配置。请确认当前解释器已安装 nanobind：${Python_EXECUTABLE}")
    endif()
endif()

find_package(nanobind CONFIG REQUIRED)

nanobind_add_module(_spatial bindings/module.cpp)
target_link_libraries(_spatial PRIVATE spatial)
