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

find_package(GDAL REQUIRED)

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
