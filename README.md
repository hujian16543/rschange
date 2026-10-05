# rschange · 遥感变化检测平台

基于 CVA（变化向量分析）、Otsu 阈值与沿像素边界追踪（crack following）的遥感影像变化检测平台；C++20 空间引擎通过 nanobind 暴露 `_spatial`，Python 3.14 / FastAPI 负责编排与服务，React 19 / TypeScript 6 / Vite 8 提供界面。

> 当前版本为 `1.0.0`。Phase 7 仅固化文档，产品代码与黄金基线冻结在 Phase 6；基线校验必须使用 `--phase 6`。

```text
React 前端 → HTTP /api → FastAPI → pipeline → detectors / postprocess / io / spatial
                                                        ↓
                                  _spatial（nanobind）→ libspatial → GDAL
```

## 前置要求

所有命令均从仓库根目录执行；标明其他工作目录的命令除外。

| 工具 | 要求 | 说明 |
|---|---|---|
| Python | **3.14.6** | `.python-version`、本地虚拟环境与 `_spatial` ABI 必须精确一致；不接受宽松的 `3.14` |
| uv | 必须可用，仓库未固定 uv 版本 | 依赖由 `uv.lock` 锁定；`python-preference = "only-system"`，需要预先安装 Python 3.14.6 |
| CMake | **3.24+** | `engine/CMakePresets.json` 的最低版本 |
| Ninja | 必须可用，仓库未固定版本 | Windows 使用 MSYS2 MINGW64 包，Linux 使用系统包 |
| Node.js | **24** | 与 CI、前端类型依赖及容器构建镜像保持同一主版本。`node --version` 必须返回 `v24.x`——本机若同时装有其他主版本，需先把 24 放进 `PATH` 首位；版本不足不会报错，只会静默使用 |
| Windows C++ 工具链 | **MSYS2 MINGW64（MSVCRT）** | 需要 `mingw-w64-x86_64-gcc`、`mingw-w64-x86_64-gdal`、`mingw-w64-x86_64-ninja`、`mingw-w64-x86_64-pkgconf`；禁止换用 UCRT64 |
| Linux C++ 工具链 | GCC、GDAL 开发包 | Debian/Ubuntu 包名为 `libgdal-dev`、`ninja-build` |

## 环境约定

| 约定 | 要求 |
|---|---|
| 字符编码 | 门禁脚本与 CLI 输出中文，运行环境必须提供 UTF-8 stdio；Windows 必须设置 `PYTHONUTF8=1` |
| Python 命令 | 必须使用 `uv run <cmd>`，禁止裸 `python` 与裸 `pip` |
| 工作区同步 | 必须使用 `uv sync --all-packages`；禁止使用裸 `uv sync`，否则 uv 会移除工作区成员 `backend` 的依赖 |
| 本机配置 | 机器相关路径只能写入已忽略的 `config/local.toml`，或通过 `RSCHANGE_*` / `SPATIAL_*` 环境变量传入 |
| Windows 工具链 | `SPATIAL_MINGW_ROOT` 与 `SPATIAL_GDAL_ROOT` 指向本机 `mingw64` 根目录，`runtime_dll_dir` 指向其 `bin` 目录 |
| CMake 预设 | 配置与构建命令必须在 `engine/` 下执行；产物分别进入 `engine/build/dev-win/` 与 `engine/build/dev-linux/` |

## 5 分钟跑通

依赖已就绪时全流程约 5 分钟。**首次执行需要联网**：第 3 步的 CMake 配置会经 `FetchContent`
从 `codeload.github.com` 获取 `nlohmann/json` v3.11.3 与 `Catch2` v3.7.1（合计约 9 MB），
第 4 步的 `npm ci` 同样需要网络。依赖已缓存后重配仅需数秒；慢速网络中首次配置耗时数分钟属
预期行为，不是卡死。

### Windows 11 + PowerShell

以下步骤要求 MSYS2 MINGW64 所需包已经安装。`<MINGW64_ROOT>` 必须替换为本机实际的 `mingw64` 目录；禁止假定其位于固定盘符。

**1. 引导环境并同步整个 uv workspace。**

```powershell
$env:PYTHONUTF8 = "1"
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1 -SkipSync
uv sync --all-packages
```

期望：引导脚本完成 7 个步骤，`.venv` 使用 Python 3.14.6，`config/local.toml` 首次运行时生成，依赖同步退出码为 0。

引导脚本生成的 `config/local.toml` 中 `engine.runtime_dll_dir` 为**空**（脚本只登记待办、不作推测）。Windows 上该项由第 2 步的 `RSCHANGE_ENGINE__RUNTIME_DLL_DIR` 环境变量兜底，本流程无需手工填写；若要让配置在本机持久生效（不依赖环境变量），则必须把该键填为 MSYS2 `mingw64/bin` 的绝对路径，见 `docs/DEVELOPMENT.md` §1.2。

**2. 注入本机工具链与引擎位置。**

```powershell
$env:SPATIAL_MINGW_ROOT = "<MINGW64_ROOT>"
$env:SPATIAL_GDAL_ROOT = $env:SPATIAL_MINGW_ROOT
$env:SPATIAL_PYTHON = (Resolve-Path ".venv/Scripts/python.exe").Path
$env:RSCHANGE_ENGINE__RUNTIME_DLL_DIR = "$env:SPATIAL_MINGW_ROOT/bin"
$env:RSCHANGE_ENGINE__BUILD_DIR = "./engine/build/dev-win"
$env:PATH = "$env:SPATIAL_MINGW_ROOT/bin;$env:PATH"
```

期望：`$env:SPATIAL_MINGW_ROOT/bin/g++.exe`、`ninja.exe` 与 GDAL 运行时 DLL 均存在，`SPATIAL_PYTHON` 指向仓库内 `.venv`。

这些变量只对**当前终端会话**有效。第 3 至第 5 步必须在同一会话内依次执行；只有第 6 步需要另开终端。

**3. 配置并构建 C++ 引擎。**

```powershell
Push-Location engine
cmake --preset dev-win
cmake --build --preset dev-win
Pop-Location
```

期望：CMake 配置与构建均退出码为 0，`engine/build/dev-win/` 中生成 `_spatial` 扩展与 `libspatial` 动态库。

若这一步失败，**必须先 `Pop-Location` 回到仓库根**再继续，否则后续 `uv run` 会在 `engine/` 下执行而找不到工作区。

**4. 运行三组测试与黄金基线。**

```powershell
ctest --test-dir engine/build/dev-win --output-on-failure
uv run pytest
Push-Location frontend
npm ci
npm run check
Pop-Location
uv run python scripts/verify_baseline.py --phase 6
```

期望：CTest 输出 `100% tests passed`，pytest 与前端检查退出码为 0，基线脚本输出 `通过 —— Phase 6 预期状态已达成`。

**5. 在当前终端启动后端。**

```powershell
uv run uvicorn --factory rschange.api.app:create_app --reload
```

期望：Uvicorn 监听 `http://127.0.0.1:8000`；访问根路径返回服务名称与版本。

若本机设置了 `HTTP_PROXY` / `HTTPS_PROXY`，对 `127.0.0.1` 的请求可能被代理接管而返回 502——此时用 `curl --noproxy '*' http://127.0.0.1:8000/` 或浏览器直接访问。

**6. 新开一个 PowerShell 终端启动前端。**

```powershell
$env:PYTHONUTF8 = "1"
Set-Location frontend
npm run dev
```

期望：Vite 输出本地地址 `http://localhost:5173/`；浏览器打开该地址即可进入变化检测界面，`/api` 请求代理到后端 8000 端口。

### Linux + Bash

以下命令以 Debian / Ubuntu 为例，Python 3.14.6、uv、Node 24、CMake 3.24+ 与 GCC 需要预先可用。

**1. 安装 GDAL 与 Ninja，引导环境并同步整个 uv workspace。**

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends libgdal-dev ninja-build
export PYTHONUTF8=1
SKIP_SYNC=1 bash scripts/bootstrap.sh
uv sync --all-packages
```

期望：系统依赖安装成功，引导脚本完成 7 个步骤，`.venv` 使用 Python 3.14.6，依赖同步退出码为 0。

引导脚本生成的 `config/local.toml` 中 `engine.runtime_dll_dir` 为空；Linux 留空即正确（运行时库由 `LD_LIBRARY_PATH` 提供），不构成待办。

**2. 注入解释器与引擎位置。**

```bash
export SPATIAL_PYTHON="$PWD/.venv/bin/python"
export RSCHANGE_ENGINE__BUILD_DIR="./engine/build/dev-linux"
```

期望：`$SPATIAL_PYTHON` 可执行；Linux 的 `engine.runtime_dll_dir` 保持为空。

这些变量只对**当前 shell 会话**有效。第 3 至第 5 步必须在同一会话内依次执行；只有第 6 步需要另开终端。

**3. 配置并构建 C++ 引擎。**

```bash
cd engine
cmake --preset dev-linux
cmake --build --preset dev-linux
cd ..
```

期望：CMake 配置与构建均退出码为 0，`engine/build/dev-linux/` 中生成 `_spatial` 扩展与 `libspatial` 动态库。

若这一步失败，**必须先 `cd ..` 回到仓库根**再继续，否则后续 `uv run` 会在 `engine/` 下执行而找不到工作区。

**4. 运行三组测试与黄金基线。**

```bash
ctest --test-dir engine/build/dev-linux --output-on-failure
uv run pytest
(cd frontend && npm ci && npm run check)
uv run python scripts/verify_baseline.py --phase 6
```

期望：CTest 输出 `100% tests passed`，pytest 与前端检查退出码为 0，基线脚本输出 `通过 —— Phase 6 预期状态已达成`。

**5. 在当前终端启动后端。**

```bash
uv run uvicorn --factory rschange.api.app:create_app --reload
```

期望：Uvicorn 监听 `http://127.0.0.1:8000`；访问根路径返回服务名称与版本。

若本机设置了 `HTTP_PROXY` / `HTTPS_PROXY`，对 `127.0.0.1` 的请求可能被代理接管而返回 502——此时用 `curl --noproxy '*' http://127.0.0.1:8000/` 或浏览器直接访问。

**6. 新开一个 Bash 终端启动前端。**

```bash
cd frontend
npm run dev
```

期望：Vite 输出本地地址 `http://localhost:5173/`；浏览器打开该地址即可进入变化检测界面。

## 目录结构

```text
engine/                         C++20 空间计算引擎
├── include/spatial/            公开类型与函数声明
├── src/                        GDAL IO、连通域、边界、简化与 GeoJSON 实现
├── bindings/                   nanobind 模块 `_spatial`
└── tests/                      Catch2 测试与冻结夹具
backend/                        uv workspace 中的 Python 后端成员
└── src/rschange/
    ├── api/                    FastAPI 边界、schema、路由与依赖装配
    ├── pipeline/               变化检测用例编排
    ├── detectors/              可插拔检测算法
    ├── postprocess/            可插拔掩膜后处理
    ├── io/                     预览图与 GeoJSON 重投影
    └── spatial/                `_spatial` 的产品代码访问边界
frontend/                       React 19 / TypeScript 6 / Vite 8 前端
├── src/api/                    HTTP 客户端与生成的契约类型
├── src/components/ui/          通用 UI 原语
└── src/features/detection/     变化检测功能与状态机
scripts/                        环境引导、契约生成、清理与仓库门禁
config/                         默认配置、本机配置模板与被忽略的本机配置
tests/                          API 验收与三方契约测试
docs/                           架构、迁移、开发、算法、契约与阶段验收文档
docker/                         后端与前端镜像定义及 nginx 配置
data/                           上传与输出目录；运行时创建，内容不入库
```

后端依赖只允许由上层指向下层：`api → pipeline → detectors / postprocess → io → spatial`；协议与实现只在 `api/deps.py` 装配，业务代码禁止绕过 `spatial/` 直接导入 `_spatial`。

## 常用命令

| 工作目录 | 命令 | 用途 |
|---|---|---|
| 仓库根 | `uv sync --all-packages` | 同步根工具与 `backend` 成员依赖 |
| 仓库根 | `uv run pytest` | 运行后端、API 与契约测试 |
| 仓库根 | `uv run mypy` | 严格类型检查 `backend/src` |
| 仓库根 | `uv run ruff check .` | 检查 `backend/` 与 `scripts/`；`docs/` 已由配置排除 |
| 仓库根 | `uv run ruff format --check .` | 检查 Python 格式，范围与 CI 一致 |
| 仓库根 | `uv run python scripts/gen_openapi.py --check` | 检查冻结 OpenAPI 是否漂移 |
| 仓库根 | `uv run python scripts/verify_baseline.py --phase 6` | 校验 Phase 6 黄金基线 |
| 仓库根 | `uv run python scripts/verify_bindings.py` | 校验 `_spatial` 绑定契约 |
| 仓库根 | `uv run python scripts/verify_config.py` | 校验配置、预设与本机模板一致性 |
| 仓库根 | `uv run python scripts/verify_version.py` | 校验各版本声明同号 |
| 仓库根 | `uv run python scripts/verify_containers.py` | 静态校验容器资产 |
| `engine/` | `cmake --preset dev-win` / `cmake --preset dev-linux` | 配置 Windows / Linux 开发构建 |
| `engine/` | `cmake --build --preset dev-win` / `cmake --build --preset dev-linux` | 构建 Windows / Linux 引擎 |
| 仓库根 | `ctest --test-dir engine/build/<preset> --output-on-failure` | 运行指定预设的 C++ 测试 |
| `frontend/` | `npm ci` | 按 lockfile 安装前端依赖 |
| `frontend/` | `npm run check` | 运行 TypeScript、oxlint 与 Vitest 检查 |
| `frontend/` | `npm run build` | 构建生产前端 |
| `frontend/` | `npm run gen:types` | 从冻结 OpenAPI 重新生成 TypeScript 类型 |
| 仓库根 | `uv run uvicorn --factory rschange.api.app:create_app --reload` | 启动开发后端 |

## 文档索引

| 文档 | 内容 |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 分层架构、跨语言边界、数据流与扩展点 |
| [`docs/MIGRATION.md`](docs/MIGRATION.md) | 旧实现到当前分层仓库的迁移对照 |
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | 开发环境、调试流程与新增检测算法指南 |
| [`docs/algorithm.md`](docs/algorithm.md) | 空间算法、几何基准与数值基线 |
| [`docs/contracts.md`](docs/contracts.md) | `_spatial` 与 HTTP 接口冻结契约 |
| [`docs/lessons/`](docs/lessons/README.md) | 调试教训归档与面试讲述稿 |
| [`docs/verification/phase-1.md`](docs/verification/phase-1.md) | Phase 1 环境与仓库奠基验收 |
| [`docs/verification/phase-2.md`](docs/verification/phase-2.md)、[`phase-2.1.md`](docs/verification/phase-2.1.md) | C++ 引擎解耦与轮廓硬化验收 |
| [`docs/verification/phase-3.md`](docs/verification/phase-3.md)、[`phase-3.1.md`](docs/verification/phase-3.1.md) | 后端分层与预览叠加验收 |
| [`docs/verification/phase-4.md`](docs/verification/phase-4.md) | 前端工程化验收 |
| [`docs/verification/phase-5.md`](docs/verification/phase-5.md) | 契约同步验收 |
| [`docs/verification/phase-6.md`](docs/verification/phase-6.md) | 容器化与双平台 CI 验收 |
| [`docs/verification/phase-7.md`](docs/verification/phase-7.md) | 文档固化与终验 |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | 贡献流程、提交要求与必跑门禁 |

## 许可证

本仓库公开可见，但**未附加开源许可证**，即保留所有权利（All rights reserved）。复制、修改、分发需事先取得作者授权。
