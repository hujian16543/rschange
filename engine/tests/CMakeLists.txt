# ============================================================================
# 引擎测试
#
# 约定
# ----
# * 夹具目录以编译期宏注入，测试不依赖当前工作目录。
# * 测试链接**静态库** `spatial_static`，不链接共享库 `spatial`。
#   理由是测试需要读取 spatial::internal::gdal_registration_count()，而该探针
#   被刻意排除在 DLL 导出面之外（Phase 2 观察项 O1）。静态链接没有导出表这一层，
#   测试可用同一份源码、同一份内部状态断言「GDAL 只注册一次」，共享库的消费者
#   却看不到该符号。共享库的导出面改由 scripts/verify_bindings.py 的 45 项
#   契约检查覆盖——那条路径经由 _spatial 绑定模块真实加载 libspatial.dll。
# * 因不再依赖 libspatial.dll，此处无需再把 spatial 的运行时 DLL 拷到测试
#   可执行文件旁。
# * 引擎依赖 MSYS2 的运行时（libgdal-38、libstdc++-6 等），故把
#   SPATIAL_GDAL_ROOT/bin 前置到测试的 PATH。
# ============================================================================

add_executable(
    spatial_tests
    test_contour.cpp
    test_geojson.cpp
    test_labeling.cpp
    test_multi_region.cpp
    test_pipeline.cpp
    test_raster_io.cpp
    test_simplify.cpp
)

target_link_libraries(
    spatial_tests
    PRIVATE
        spatial_static
        Catch2::Catch2WithMain
        nlohmann_json::nlohmann_json
        spatial_warnings
)

# ../src 供测试 include 内部头（internal/gdal_registry.hpp）。该目录不对
# 共享库的消费者开放，也不随 install 规则安装。
target_include_directories(
    spatial_tests
    PRIVATE ${CMAKE_CURRENT_SOURCE_DIR} ${CMAKE_CURRENT_SOURCE_DIR}/../src
)

target_compile_definitions(
    spatial_tests
    PRIVATE SPATIAL_TEST_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/fixtures"
)

include(Catch)

if(SPATIAL_GDAL_ROOT)
    catch_discover_tests(
        spatial_tests
        PROPERTIES
            ENVIRONMENT_MODIFICATION "PATH=path_list_prepend:${SPATIAL_GDAL_ROOT}/bin"
    )
else()
    catch_discover_tests(spatial_tests)
endif()
