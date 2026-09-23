# ============================================================================
# spatial · 空间计算引擎
#
# 设计约定
# --------
# * 编译选项只作用于本工程自身的 target，不用 add_compile_options 全局下发。
#   这样第三方依赖（nlohmann/json、Catch2、nanobind）不会被告警策略牵连。
# * 版本号与 project VERSION 同步推进，不另设 VERSION 文件。
# * 机器相关的路径一律由调用方给出（GDAL 走 SPATIAL_GDAL_ROOT，解释器走
#   Python_EXECUTABLE），配置文件不得写死绝对路径。预设见 engine/CMakePresets.json。
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
# 构建开关
# ---------------------------------------------------------------------------
option(SPATIAL_BUILD_PYTHON "构建 Python 扩展 _spatial" ON)
option(SPATIAL_BUILD_TESTS "构建单元测试并接入 CTest" ON)
option(SPATIAL_WARNINGS_AS_ERRORS "把告警视为错误（只作用于本工程自身的 target）" ON)

# ---------------------------------------------------------------------------
# 告警策略
# ---------------------------------------------------------------------------
# 用 INTERFACE target 下发，而不是 add_compile_options：后者会连带作用于
# 第三方依赖（nlohmann/json、Catch2、nanobind），届时只能逐个再关掉。
add_library(spatial_warnings INTERFACE)
target_compile_options(
    spatial_warnings
    INTERFACE
        -Wall
        -Wextra
        -Wpedantic
        $<$<BOOL:${SPATIAL_WARNINGS_AS_ERRORS}>:-Werror>
)

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
# CPython，会让 find_package(Python) 解析出错误的导入库，详见
# cmake/PythonExtension.cmake 的「Python 运行时一致性」。故此处的搜索范围只
# 临时收敛到 SPATIAL_GDAL_ROOT，查找结束后立即还原，不给后续 find_package
# 留下污染。
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
# 引擎库：共享库 + 静态库
# ---------------------------------------------------------------------------
# 源码列表只写一份，两个 target 共用。写成两份必然漂移：新增一个 .cpp 时只改
# 一处，另一个 target 便在链接期以「未定义符号」的形式暴露——而那时错误信息
# 指向调用方，不指向漏改的列表。
set(
    SPATIAL_SOURCES
    src/contour.cpp
    src/gdal_init.cpp
    src/geojson.cpp
    src/labeling.cpp
    src/raster_io.cpp
    src/simplify.cpp
    src/version.cpp
)

# 共享库：Python 扩展 _spatial 的链接目标，也是唯一被安装的引擎产物。
add_library(spatial SHARED)
add_library(spatial::spatial ALIAS spatial)

target_sources(spatial PRIVATE ${SPATIAL_SOURCES})

target_include_directories(
    spatial
    PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
           $<INSTALL_INTERFACE:include>
    PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src
)

# 定义 SPATIAL_BUILDING 使 export.hpp 走 dllexport 分支。
target_compile_definitions(spatial PRIVATE SPATIAL_BUILDING)

target_link_libraries(
    spatial
    PRIVATE
        GDAL::GDAL
        nlohmann_json::nlohmann_json
        spatial_warnings
)

# 静态库：仅供 engine/tests/ 链接，不安装、不进任何发布产物。
#
# 存在的理由是「测试探针不得出现在共享库导出表里」：单元测试需要读取
# spatial::internal::gdal_registration_count()，而该符号被刻意排除在 DLL
# 导出面之外（见 src/internal/gdal_registry.hpp）。静态链接没有导出表这一层，
# 测试因而能用同一份源码、同一份内部状态做出断言，共享库的消费者却看不到它。
#
# SPATIAL_STATIC 以 PUBLIC 传播：测试自身也 include spatial/export.hpp，若不
# 定义该宏就会按消费方走 dllimport，去链接并不存在的导入库。
add_library(spatial_static STATIC)
add_library(spatial::static ALIAS spatial_static)

target_sources(spatial_static PRIVATE ${SPATIAL_SOURCES})

target_include_directories(
    spatial_static
    PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src
)

target_compile_definitions(spatial_static PUBLIC SPATIAL_STATIC)

target_link_libraries(
    spatial_static
    PRIVATE
        GDAL::GDAL
        nlohmann_json::nlohmann_json
        spatial_warnings
)

# ---------------------------------------------------------------------------
# Python 扩展模块 _spatial
# ---------------------------------------------------------------------------
if(SPATIAL_BUILD_PYTHON)
    include(cmake/PythonExtension.cmake)
endif()

# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------
if(SPATIAL_BUILD_TESTS)
    # Catch2 v3：MSYS2 未打包，故改为构建期获取，版本由 URL 中的 tag 钉死。
    # 声明名用小写，以便按 FetchContent 约定取到 catch2_SOURCE_DIR。
    FetchContent_Declare(
        catch2
        URL https://codeload.github.com/catchorg/Catch2/tar.gz/refs/tags/v3.7.1
    )
    set(CATCH_BUILD_TESTING OFF CACHE INTERNAL "不构建 Catch2 自带测试")
    set(CATCH_INSTALL_DOCS OFF CACHE INTERNAL "不安装 Catch2 文档")
    FetchContent_MakeAvailable(catch2)

    # catch_discover_tests 由 extras/Catch.cmake 提供，不在 Catch2 的 config 包里。
    list(APPEND CMAKE_MODULE_PATH "${catch2_SOURCE_DIR}/extras")

    enable_testing()
    add_subdirectory(tests)
endif()

# ---------------------------------------------------------------------------
# 安装
# ---------------------------------------------------------------------------
include(GNUInstallDirs)

install(
    TARGETS spatial
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
)
install(DIRECTORY include/spatial DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})

if(SPATIAL_BUILD_PYTHON)
    # Python 扩展的落点由调用方决定（例如装进虚拟环境的 site-packages）；
    # 这里只给出默认位置，不替调用方决定 Python 环境布局。
    install(
        TARGETS _spatial
        RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
        LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    )
endif()
