#pragma once

/// @file fixture.hpp
/// @brief 测试夹具的读取入口。
///
/// 夹具目录由编译期宏 `SPATIAL_TEST_FIXTURE_DIR` 注入，测试因此不依赖当前
/// 工作目录 —— 从 CTest、IDE 或命令行直接执行的结果一致。

#include <cstdint>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace fixture {

inline std::filesystem::path dir() {
    return std::filesystem::path(SPATIAL_TEST_FIXTURE_DIR);
}

inline std::filesystem::path path(const std::string& name) {
    return dir() / name;
}

inline std::vector<std::uint8_t> read_bytes(const std::string& name) {
    const std::filesystem::path target = path(name);
    std::ifstream in(target, std::ios::binary);
    if (!in) {
        throw std::runtime_error("无法打开夹具：" + target.string());
    }
    const std::string blob((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    return std::vector<std::uint8_t>(blob.begin(), blob.end());
}

inline nlohmann::json read_json(const std::string& name) {
    const std::filesystem::path target = path(name);
    std::ifstream in(target);
    if (!in) {
        throw std::runtime_error("无法打开夹具：" + target.string());
    }
    nlohmann::json document;
    in >> document;
    return document;
}

}  // namespace fixture
