# ============================================================================
# 引擎测试
#
# 约定
# ----
# * 夹具目录以编译期宏注入，测试不依赖当前工作目录。
# * Windows 下把 spatial 的运行时 DLL 拷到测试可执行文件旁：PE 只从 exe 所在
#   目录及其搜索路径解析 DLL，跨目录调用会直接报「找不到指定模块」。
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
        spatial
        Catch2::Catch2WithMain
        nlohmann_json::nlohmann_json
        spatial_warnings
)

target_include_directories(spatial_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

target_compile_definitions(
    spatial_tests
    PRIVATE SPATIAL_TEST_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/fixtures"
)

if(WIN32)
    add_custom_command(
        TARGET spatial_tests
        POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
                $<TARGET_FILE:spatial> $<TARGET_FILE_DIR:spatial_tests>
        COMMENT "把 spatial 运行时 DLL 拷到测试可执行文件旁"
    )
endif()

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
