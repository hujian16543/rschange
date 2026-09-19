/// @file version.cpp
/// @brief GDAL 版本上报，供诊断使用。

#include "spatial/raster.hpp"

#include <gdal.h>

#include <iostream>

namespace spatial {

void print_gdal_version() {
    std::cout << "GDAL Version: " << GDALVersionInfo("--version") << std::endl;
}

}  // namespace spatial
