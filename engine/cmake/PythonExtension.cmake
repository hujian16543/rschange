# ============================================================================
# Python 扩展模块 _spatial
#
# 由顶层 CMakeLists 的 SPATIAL_BUILD_PYTHON 开关控制。抽成独立文件的原因：
# 仅编译引擎与测试的场合（例如只需跑 CTest 的 Linux CI）不必安装 nanobind，
# 开关体也无需嵌进顶层文件形成大段缩进。
#
# 本文件依赖（均由顶层文件或本文件自行建立）：
#   spatial        引擎共享库 target
#   spatial_warnings  告警策略 INTERFACE target
# ============================================================================

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
#   _Python_INCLUDE_DIR      = …/DevCode/python/python3.14/Include            （宿主，正确）
#   _Python_LIBRARY_RELEASE  = …/DevCode/msys64/mingw64/lib/libpython3.14.dll.a （MSYS2，错误）
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

# ---------------------------------------------------------------------------
# nanobind 与扩展 target
# ---------------------------------------------------------------------------
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
target_link_libraries(_spatial PRIVATE spatial spatial_warnings)
