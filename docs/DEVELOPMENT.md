# 开发者指南

> 适用对象：需要在本仓库上做开发、构建引擎、跑门禁或新增检测算法的工程师。
> 本文档为**声明式**规范：需要 / 必须 / 应当 / 禁止。所有命令均取自仓库内实际存在的文件
> （`scripts/`、`engine/CMakePresets.json`、`pyproject.toml`、`frontend/package.json`、
> `.github/workflows/ci.yml`），未列出的命令禁止在文档与协作口吻中出现。

---

## 0. 前提：运行环境必须提供 UTF-8 stdio

门禁脚本与 CLI 一律以**中文**输出（例如 `[PASS] 契约产物与当前代码一致`）。Python 的
stdio 编码取自进程 locale：中文 Windows（ACP 936）能表示中文，而 GitHub 托管 runner 为
`en-US` / ACP 1252，`print()` 一遇中文即抛 `UnicodeEncodeError: 'charmap' codec`。

因此：

* Windows 环境**必须**设 `PYTHONUTF8=1`（PEP 540 UTF-8 模式），否则门禁脚本在非中文
  代码页上崩溃；
* 该变量同时归一 `locale.getpreferredencoding(False)`——`tests/contract/test_openapi_frozen.py`
  以 `subprocess.run(text=True)` 读子进程输出，父进程若仍按 cp1252 解码 UTF-8 字节流会二次失败；
* Linux / macOS 的 locale 本就是 UTF-8，无需额外设置。

CI 已把 `PYTHONUTF8: "1"` 写进全局 `env`（`.github/workflows/ci.yml:98`）。本地需自行设置。

---

## 1. 环境搭建

### 1.1 版本矩阵（必须精确匹配）

| 项 | 值 | 出处 |
|---|---|---|
| Python | **3.14.6**（精确版本） | `.python-version:1`；`pyproject.toml:16` `requires-python=">=3.14,<3.15"` |
| uv | 最新版；`python-preference = "only-system"` | 根 `pyproject.toml:52` |
| Node | **24** | `frontend/package.json` `@types/node ^24.13.0`；`ci.yml:279` |
| CMake | ≥ 3.24 | `engine/CMakePresets.json:3` |
| C++ 标准 | C++20 | `engine/CMakeLists.txt` |
| Windows 工具链 | MSYS2 **MINGW64**（禁止 UCRT64） | `ci.yml:152-157`；扩展 ABI 标签 `mingw_x86_64_msvcrt_gnu` |
| GDAL | Windows 由 MSYS2 包提供；Linux 由系统包提供 | `ci.yml:4-5`、预设 `linux-base` 注释 |

`_spatial` 扩展的 **ABI 验证基线是 Python 3.14.6**。版本漂移会让基线断言失真，故
`.python-version` 必须写三段精确版本号——只写 `3.14` 会让 uv 解析到 conda 的 3.14.7 空环境。

### 1.2 一键引导

```bash
# Linux / macOS
bash scripts/bootstrap.sh

# Windows（PowerShell）
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1 -SkipSync   # .venv 已就绪时复检
```

两个脚本**幂等**，步骤编号一一对应：

| 步 | 动作 | 不满足时 |
|---|---|---|
| 1 | 断言 `uv` 可用 | `exit 1`（可用 `UV_BIN` 指定绝对路径） |
| 2 | 断言解释器可被**精确**解析（防 conda 陷阱） | 解析结果含 `conda` 或版本不精确即中止 |
| 3 | 创建项目级 `.venv` | 已存在则跳过 |
| 4 | 断言 `.venv` 解释器版本 == `3.14.6` | `exit 1`，提示删 `.venv` 重跑 |
| 5 | 按 `uv.lock` 安装依赖（`uv sync --all-packages`） | `SKIP_SYNC=1` / `-SkipSync` 时跳过 |
| 6 | 由 `config/local.example.toml` 生成 `config/local.toml` | 已存在**不覆盖** |
| 7 | 打印下一步命令 | — |

设计约束（改脚本时必须保持）：脚本内**禁止**出现机器相关绝对路径；**禁止**调用裸
`python` / 裸 `pip`；任一步不满足即 `exit 1`，不得继续。

第 6 步之后，Windows 上**必须**手工填写 `config/local.toml` 的 `engine.runtime_dll_dir`
（脚本只登记待办、不作推测）。Linux / macOS 留空即正确。

### 1.3 Windows 侧 MSYS2 与 GDAL

```bash
pacman -S mingw-w64-x86_64-gcc mingw-w64-x86_64-gdal mingw-w64-x86_64-ninja mingw-w64-x86_64-pkgconf
```

引擎构建需要三个环境变量（预设 `win-base` 从它们取值）：

| 变量 | 含义 |
|---|---|
| `SPATIAL_MINGW_ROOT` | MSYS2 的 `mingw64` 根目录（内含 `bin/gcc.exe`、`bin/g++.exe`） |
| `SPATIAL_GDAL_ROOT` | GDAL 安装根 |
| `SPATIAL_PYTHON` | 解释器绝对路径；**必须指向仓库 `.venv`**（不能是 MSYS2 自带 CPython） |

**禁止**写死 `C:/msys64/mingw64`：`setup-msys2` 在 release 模式下装到 `$RUNNER_TEMP/msys64`。
**禁止**在 MSYS2 shell 内跑 CMake（会触发 MSYS2 路径转换，破坏 `-D` 参数）；CMake 用原生
Windows 版本，只在 PATH 里追加 `mingw64/bin`。

---

## 2. 依赖管理铁律：必须 `uv sync --all-packages`

本仓库是 uv workspace：根 `pyproject.toml` 的 `[project].dependencies` 为**空**，
`[tool.uv.workspace].members = ["backend"]`。全部运行时依赖（fastapi、numpy、scipy、
pyproj、pillow、nanobind…）声明在**成员包** `backend/pyproject.toml` 里。

```bash
uv sync --all-packages            # 正确：安装工作区根 + 全部成员包
uv sync --all-packages --frozen   # CI 用法：严格按 uv.lock，不重新求解
uv sync --all-packages --extra fixtures   # 仅在需要重新生成合成测试影像时
```

**禁止裸 `uv sync`。**

| 项 | 内容 |
|---|---|
| 症状 | 裸 `uv sync` 后 `uv run pytest` / `uv run mypy` 报 `ModuleNotFoundError: fastapi`（或 numpy / scipy / pydantic）；`scripts/verify_version.py` 第 1 项 FAIL |
| 成因 | 裸 `uv sync` 只同步工作区根。根的依赖集为空，uv 据此把 `.venv` 收敛为「不含成员包运行时依赖」的状态——即**删除**已装好的 fastapi 等包 |
| 后果 | 后端不可导入、类型检查与全部 Python 门禁连锁失败；`verify_version.py` 因 `import rschange` 失败而报「元数据未随源码刷新」，与真实原因相隔甚远 |
| 恢复 | 重跑 `uv sync --all-packages` |

相关约束：

* `python-preference = "only-system"`：禁止 uv 下载自管解释器（会用 3.14.7 覆盖本机 3.14.6）。
* `scipy-stubs` 版本与 scipy 严格绑定，升级 scipy 必须同步升 stubs；**禁止**用
  `[[tool.mypy.overrides]] ignore_missing_imports` 掩盖 `import-untyped`。
* `pyyaml` 显式声明在 dev 组：`scripts/verify_containers.py` 解析 `docker-compose.yml` 需要它，
  不能依赖传递依赖。
* 新增依赖后**必须**提交 `uv.lock`。

---

## 3. 引擎构建

### 3.1 `engine/CMakePresets.json` 全部预设

**configurePresets（7 个）**

| 名称 | hidden | inherits | generator | binaryDir | 关键 cacheVariables |
|---|---|---|---|---|---|
| `base` | 是 | — | — | `${sourceDir}/build/${presetName}` | `CMAKE_EXPORT_COMPILE_COMMANDS=ON` |
| `win-base` | 是 | `base` | `Ninja` | 继承 | `CMAKE_BUILD_TYPE=Debug`；`CMAKE_CXX_COMPILER=$env{SPATIAL_MINGW_ROOT}/bin/g++.exe`；`SPATIAL_GDAL_ROOT=$env{SPATIAL_GDAL_ROOT}`；`Python_EXECUTABLE=$env{SPATIAL_PYTHON}` |
| `linux-base` | 是 | `base` | `Ninja` | 继承 | `CMAKE_BUILD_TYPE=Debug`；`Python_EXECUTABLE=$env{SPATIAL_PYTHON}` |
| `dev-win` | 否 | `win-base` | 继承 | `engine/build/dev-win` | 继承（Debug） |
| `dev-linux` | 否 | `linux-base` | 继承 | `engine/build/dev-linux` | 继承（Debug） |
| `release-win` | 否 | `win-base` | 继承 | `engine/build/release-win` | 覆盖 `CMAKE_BUILD_TYPE=Release` |
| `release-linux` | 否 | `linux-base` | 继承 | `engine/build/release-linux` | 覆盖 `CMAKE_BUILD_TYPE=Release` |

**buildPresets（4 个）**：`dev-win` / `dev-linux` / `release-win` / `release-linux`，各自
`configurePreset` 同名。

**testPresets（4 个）**：同上四名，`output = { "outputOnFailure": true }`。

开发期**必须**使用 `dev-*` 预设：`config/default.toml` 的 `engine.build_dir` 默认为
`./engine/build/dev-win`，与 `dev-win` 的 `binaryDir` 一致（`verify_config.py` 判据 1 守护）。

另有不入库的本机预设 `local-win`（`engine/CMakeUserPresets.json`），`binaryDir` 同为
`engine/build/dev-win`，仅用于给出本机三个绝对路径环境变量。

### 3.2 构建与测试命令

```bash
cd engine                                   # --preset 必须从 engine/ 目录调用
cmake --preset dev-win                      # 配置（Windows）
cmake --preset dev-linux                    # 配置（Linux）
cmake --build --preset dev-win              # 构建
cmake --build --preset dev-linux

ctest --test-dir engine/build/dev-win --output-on-failure     # C++ 单测（可在仓库根跑）
ctest --preset dev-win                                        # 等价写法
```

CI 在配置时额外注入 ccache：

```bash
cmake --preset dev-win -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache
```

### 3.3 产物位置与 `runtime_dll_dir`

| 平台 | `_spatial` 产物 |
|---|---|
| Windows | `engine/build/<preset>/_spatial.cp314-win_amd64.pyd` + `libspatial.dll` |
| Linux | `engine/build/<preset>/_spatial.cpython-314-x86_64-linux-gnu.so` + `libspatial.so` |

* `engine.build_dir` 必须指向 `binaryDir`，相对路径按仓库根解析。
* `engine.runtime_dll_dir`：Windows **必填**，指向 MSYS2 的 `mingw64/bin`（提供
  `libgdal-*.dll`、`libstdc++-6.dll`）。PE 加载器不会去 MSYS2 目录里找，留空的症状是
  `import _spatial` 报「找不到指定模块」。Linux / macOS 留空，改由 `LD_LIBRARY_PATH` /
  `DYLD_LIBRARY_PATH` 提供。
* 加载实现有两份且**刻意互不导入**：产品代码走 `backend/src/rschange/spatial/loader.py`
  （backend 运行期唯一加载点），仓库脚本走 `scripts/engine_env.py:load_spatial()`。
  前者把 `os.add_dll_directory` 的返回句柄收集在 `_DLL_HANDLES`（丢弃句柄会让目录在 GC
  时被摘除，表现为「有时能导入、有时找不到 DLL」）；后者是短命脚本进程，未持有句柄。
  **新增脚本时禁止把后者的写法抄进长生命周期代码。**

### 3.4 平台差异速查

| 项 | Windows | Linux |
|---|---|---|
| 编译器 | MSYS2 mingw-w64 g++（MINGW64） | 系统 GCC |
| CPython | python.org MSVC 版（仓库 `.venv`） | 系统 CPython（仓库 `.venv`） |
| GDAL | MSYS2 包 | `apt install libgdal-dev` |
| 构建器 | Ninja（MSYS2 包） | `ninja-build` |
| `runtime_dll_dir` | 必填 | 留空 |
| 运行期库搜索 | `os.add_dll_directory` | `LD_LIBRARY_PATH` |

---

## 4. 运行测试

### 4.1 后端

```bash
uv run pytest                       # 默认：addopts = "-q --strict-markers"
uv run pytest -o addopts="" -rs     # CI 用法：还原汇总行与跳过原因
uv run pytest -m baseline           # 只跑基线锚点
uv run pytest -m "not slow"         # 排除需真实影像的用例
```

`pyproject.toml` 的 `[tool.pytest.ini_options]`：`testpaths = ["backend/src/rschange/tests",
"tests"]`、`pythonpath = ["backend/src"]`、`addopts = "-q --strict-markers"`。

`-q` 会压掉「多少通过、多少跳过」的汇总行，故 CI 用 `-o addopts=""` 覆盖它。
规模**两个口径必须区分**：源码静态 `def test_` 计数 **123**（`backend/` 112 + 根 `tests/` 11）；
`pytest` 实际收集 **148** 个用例，差额来自 `@pytest.mark.parametrize` 展开。验收报告（如
`docs/verification/phase-6.md` §9 表 E 行）报的是「**148 passed**」，静态计数才是 123。

`_spatial` 不可用时，依赖引擎的用例**跳过**而非失败（`engine_ready` 夹具）。

### 4.2 C++

```bash
ctest --test-dir engine/build/dev-win --output-on-failure
```

40 个 Catch2 `TEST_CASE`（contour 6 / geojson 8 / labeling 6 / multi_region 5 /
pipeline 2 / raster_io 5 / simplify 8）。测试链接**静态库** `spatial_static` 而非共享库，
以便读取内部探针 `gdal_registration_count()`。

### 4.3 前端

```bash
cd frontend
npm ci
npm run test      # vitest run
npm run check     # tsc -b --noEmit && oxlint && vitest run
npm run build     # tsc -b && vite build
```

`frontend/package.json` 的 8 个 scripts：`dev` / `build` / `lint` / `format:check` /
`test` / `check` / `preview` / `gen:types`。109 个用例。
`vitest.config.ts` 刻意**不设** `passWithNoTests`——无测试即失败。

---

## 5. 门禁全清单

提交前**必须**本地跑通；CI 双平台矩阵（linux-gcc / windows-mingw）会重跑同一组。

| # | 命令 | 检什么 | 失败意味着什么 |
|---|---|---|---|
| 1 | `ctest --test-dir engine/build/<preset> --output-on-failure` | 引擎 40 个 Catch2 用例：连通域顺序、轮廓环、GeoJSON 归属、简化、栅格 IO | 引擎行为回归或本机构建产物过期 |
| 2 | `uv run pytest -o addopts="" -rs` | 后端与契约测试（静态 `def test_` **123** 个；参数化展开后收集 **148** 个用例） | 功能或契约回归 |
| 3 | `uv run mypy` | `strict = true`，`files = ["backend/src"]` | 类型不严；`rschange.tests.*` 仅放宽 `disallow_untyped_defs` / `disallow_incomplete_defs` |
| 4 | `uv run ruff check .` | 规则集 `E,F,W,I,N,UP,B,C4,SIM,RUF`；`line-length=100`；`src=["backend/src","scripts"]` | 代码风格或未用导入等问题。**必须是 `ruff check .`**（与 CI 一致），而非 `ruff check backend/` |
| 5 | `uv run ruff format --check .` | 格式（双引号、100 列） | 未格式化。E501 由 formatter 承担，故 `ignore` 含 `E501` |
| 6 | `uv run python scripts/gen_openapi.py --check` | **契约第一段**：入库的 `docs/api/openapi.json` 是否与当前 pydantic 模型逐字节一致 | 改了响应模型却没重新生成契约产物。退出码 1 = 漂移或产物缺失 |
| 7 | `uv run python scripts/verify_baseline.py --phase 6` | 《重构方案》§7.1/§7.2/§7.3 黄金基线（Otsu 阈值 `5.9168`、变化像素 `7209/65536`、面积 `720900 m²`、多区域 label 顺序与几何面积一致性）。内置**独立于 backend** 的冻结参考实现 | 算法语义漂移，即回归缺陷。`--phase 1` 表示「缺陷未修复、失败才是正确」，**当前仓库必须用 `--phase 6`** |
| 8 | `uv run python scripts/verify_bindings.py` | `_spatial` 绑定层契约 42 项：函数齐备、签名、返回结构、异常类型、掩膜 `uint8` + C 连续、properties 字段名、非方形坐标范围 | 绑定层与 `docs/contracts.md` §3–§6 不一致 |
| 9 | `uv run python scripts/verify_config.py` | 6 项：`default.toml` ↔ 预设 `dev-win` 的 `binaryDir`；`local.toml` ↔ 预设 `local-win`；`local.example.toml` 示例值 ↔ `default.toml`（build_dir、fixtures_dir）；`legacy_*` 为空；Windows 上 `local.toml` 的 `runtime_dll_dir` 非空 | 配置三处漂移——历史上表现为「照抄模板得到错误配置，`import _spatial` 失败但报错指向模块不存在」 |
| 10 | `uv run python scripts/verify_version.py` | 5 项：真相源 = `backend/pyproject.toml`；`rschange.__version__`、`frontend/package.json`、根 `pyproject.toml`、`openapi.json` 的 `info.version` 必须同号 | 版本号漂移，且会把错版本号写进契约产物并带到前端。第 1 项同时是「元数据是否已随源码刷新」的判据——改完 `backend/pyproject.toml` 未跑 `uv sync --all-packages` 时它会 FAIL |
| 11 | `uv run python scripts/verify_containers.py` | 容器资产静态门禁 19 项（nginx 上限 ≥ `max_upload_mb`、`proxy_pass` 无尾斜杠且与 `API_PREFIX` 一致、Python/Node 三处同号、runtime 镜像无 `-dev` 依赖、健康检查与命名卷与启动顺序、`.dockerignore` 四项、无机器相关路径） | 容器化资产与代码声明脱节。**不替代真实构建** |
| 12 | `cd frontend && npm run check` | `tsc -b --noEmit` + `oxlint` + `vitest run` | 前端类型 / lint / 用例任一不通过 |
| 13 | `cd frontend && npm run build` | `tsc -b && vite build` | 产物不可构建 |
| 14 | **CI 独有**：契约类型零漂移（openapi → TS） | 以入库 `openapi.json` 重跑 `npm run gen:types`，再要求 `git status --porcelain -- frontend/src/api/generated` 为空 | **契约第二段**漂移：openapi 已更新但前端类型未重生成。字节级判据，覆盖「字段名未变、仅类型变化」这一 `tests/contract/` 字段级比对抓不到的路径 |

补充：

* `scripts/verify_version.py` 因 `import rschange` 依赖 `uv sync --all-packages`；且脚本内含
  `from engine_env import ...`，**必须**用 `python scripts/xxx.py` 形式跑（依赖
  `sys.path[0] = scripts/`）。
* `ruff` 范围：CI 用 `.`，靠 `extend-exclude = ["docs"]` 与 `backend/ scripts/` 等价。
  RUF001/002/003 在中文代码库上是固有误报，**禁止**逐处 `# noqa` 压制。
* 清理：`bash scripts/clean.sh` / `powershell -File scripts\clean.ps1`（**不清 `.venv`**）。

---

## 6. 配置系统

### 6.1 优先级（高 → 低）

```
构造参数 init_settings  >  RSCHANGE_<SECTION>__<KEY> 环境变量  >  config/local.toml  >  config/default.toml
```

由 `backend/src/rschange/config.py:229-245` 的 `settings_customise_sources()` 显式给出。
`dotenv_settings` 与 `file_secret_settings` 刻意不启用。
`local.toml` 已被 git 忽略，不存在时静默跳过。

### 6.2 `config/default.toml` 全部键与默认值

| 段 | 键 | 默认值 | 说明 |
|---|---|---|---|
| `runtime` | `host` | `"127.0.0.1"` | — |
| `runtime` | `port` | `8000` | 1–65535 |
| `runtime` | `data_dir` | `"./data"` | 上传与输出根目录，相对仓库根解析 |
| `runtime` | `max_upload_mb` | `500` | 派生 `max_upload_bytes = max_upload_mb × 1024²` |
| `runtime` | `allowed_origins` | `["http://localhost:5173", "http://127.0.0.1:5173"]` | **禁止**含 `"*"`（配置期拒绝） |
| `engine` | `runtime_dll_dir` | `""` | Windows 必填；Linux / macOS 留空 |
| `engine` | `build_dir` | `"./engine/build/dev-win"` | 必须与 CMake 预设 `binaryDir` 一致 |
| `logging` | `level` | `"INFO"` | — |
| `logging` | `format` | `"console"` | `console` \| `json` |
| `postprocess` | `min_size` | `30` | 连通块像素数**不超过**该值即被剔除 |
| `postprocess` | `structure_size` | `3` | 闭运算结构元边长（像素）；1 表示不做闭运算 |
| `baseline` | `fixtures_dir` | `"./engine/tests/fixtures"` | 黄金基线夹具目录 |
| `baseline` | `legacy_build_dir` | `""` | 仅 Phase 1 使用；Phase 2 起必须为空 |
| `baseline` | `legacy_fixtures_dir` | `""` | 同上 |

派生只读属性：`data_dir`、`uploads_dir`（`data_dir/uploads`）、`outputs_dir`
（`data_dir/outputs`）、`build_dir`、`runtime_dll_dir`、`fixtures_dir`。

### 6.3 `local.toml` 与 `local.example.toml`

* `config/local.example.toml` 入库，其键**全部处于注释状态**——照抄得到一份「全部回落
  `default.toml`」的空配置，其中 `engine.runtime_dll_dir` 为空。
* `config/local.toml` 由 bootstrap 第 6 步复制生成，已被 git 忽略，是本机覆盖的唯一落点。
* 两文件**禁止**写入机器相关绝对路径（由 `test_architecture.py` 的 G3.5 用例守护）。
* 注意模板中 `runtime.allowed_origins` 的注释示例只有 1 项，实际生效值以 `default.toml`
  的 2 项为准。

### 6.4 环境变量覆盖

| 规则 | 说明 |
|---|---|
| 前缀 | `RSCHANGE_`（`ENV_PREFIX`） |
| 嵌套分隔 | 双下划线 `__`：`RSCHANGE_RUNTIME__PORT` → `runtime.port`；`RSCHANGE_ENGINE__BUILD_DIR` → `engine.build_dir`；`RSCHANGE_POSTPROCESS__MIN_SIZE` → `postprocess.min_size` |
| 大小写 | `case_sensitive = False`，段名与键名不区分大小写 |
| 优先级 | **环境变量高于 `config/local.toml` 与 `config/default.toml`**。CI 正是靠这一点不生成 `local.toml` |
| 特殊项 | `RSCHANGE_REPO_ROOT`：唯一在 pydantic 求值**之前**读取的变量，用于 wheel 安装下显式给出仓库根 |
| 标量解析 | pydantic-settings 按字段类型解析；`scripts/engine_env.py` 独立实现为 `true`/`false` → bool，否则试 `int()`，失败保持字符串 |

配置模型一律 `extra="forbid"`，且每个嵌套模型**必须**单独继承 `_StrictModel`——
`Settings.model_config` 的 `extra` 不会向嵌套模型传播。TOML 出现未声明键即启动期报错。

---

## 7. 新增一个检测器（完整示例）

以下以 `NdviDiffDetector`（两期 NDVI 差值超过阈值即判变化）为例，从零到跑通。
协议、注册表与装配点的接口均取自源码：

| 依据 | 位置 |
|---|---|
| 协议与结果类型 | `backend/src/rschange/detectors/base.py:20-62` |
| 注册表 | `backend/src/rschange/detectors/registry.py:24-65` |
| 现有实现样板 | `backend/src/rschange/detectors/cva.py:105-129` |
| 包内注册时机 | `backend/src/rschange/detectors/__init__.py:27` |
| 装配点 | `backend/src/rschange/api/deps.py:53-76` |
| 配置模型基类 | `backend/src/rschange/config.py:104-112`、`168-180` |
| 编排层签名 | `backend/src/rschange/pipeline/change_detection.py`（`detect_change(request, *, detector, postprocessor, settings=None)`） |

**禁止**修改 `backend/src/rschange/pipeline/change_detection.py`。该约束由阶段出口门 G3.4
守护：`tests/test_architecture.py:227` 会比对注册前后该文件的 SHA-256 必须不变。

### 7.1 ① 实现 `Detector` 协议

新建 `backend/src/rschange/detectors/ndvi_diff.py`：

```python
"""NDVI 差值变化检测。

算法：对每个像元取红波段（第 0 波段）与近红外（第 1 波段）算 NDVI，两期 NDVI 之差的
绝对值超过 `threshold` 即判为变化。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

from rschange.detectors.base import DetectionResult
from rschange.errors import InputValidationError
from rschange.logging import get_logger

if TYPE_CHECKING:
    from numpy.typing import NDArray

__all__ = ["NdviDiffDetector"]

_logger = get_logger(__name__)

#: NDVI 至少需要的波段数（红 + 近红外）。
_MIN_BANDS: Final[int] = 2


class NdviDiffDetector:
    """两期 NDVI 差值超过阈值即判变化。"""

    name = "ndvi-diff"

    def __init__(self, threshold: float = 0.2) -> None:
        if not 0.0 <= threshold <= 2.0:
            raise ValueError(f"threshold 必须落在 [0.0, 2.0]，实得 {threshold}")
        self._threshold = threshold

    def detect(self, before: NDArray[np.uint16], after: NDArray[np.uint16]) -> DetectionResult:
        """计算两期影像的变化掩膜。

        @throws InputValidationError 形状不一致、非 3D 或波段数不足
        """
        if before.shape != after.shape:
            raise InputValidationError(
                f"两期影像形状不一致：before {before.shape}，after {after.shape}",
                public_message="两期影像的尺寸或波段数不一致",
            )
        if before.ndim != 3:
            raise InputValidationError(
                f"影像必须是 (bands, height, width) 的 3D 数组，实得 {before.ndim} 维",
                public_message="影像维度不符合要求",
            )
        if before.shape[0] < _MIN_BANDS:
            raise InputValidationError(
                f"NDVI 至少需要 {_MIN_BANDS} 个波段（红、近红外），实得 {before.shape[0]}",
                public_message="影像波段数不足以计算 NDVI",
            )

        delta = np.abs(self._ndvi(after) - self._ndvi(before))
        _logger.info(
            "NDVI 差值计算完成",
            detector=self.name,
            threshold=self._threshold,
            changed_pixels=int((delta > self._threshold).sum()),
        )
        return DetectionResult(mask=delta > self._threshold, threshold=self._threshold)

    @staticmethod
    def _ndvi(array: NDArray[np.uint16]) -> NDArray[np.float64]:
        """(bands, height, width) → (height, width) 的 NDVI；分母为 0 处取 0。"""
        red = array[0].astype(np.float64)
        nir = array[1].astype(np.float64)
        with np.errstate(divide="ignore", invalid="ignore"):
            ndvi = (nir - red) / (nir + red)
        return np.where(np.isfinite(ndvi), ndvi, 0.0)
```

协议要求（`detectors/base.py:45-62`）：

* `name: str` 唯一，用于注册表索引与日志字段；
* `detect(before, after) -> DetectionResult`，入参 `(bands, height, width)` 的 `uint16`，
  与 `spatial.read_raster` 的返回一致；返回掩膜是 `(height, width)` 的 `bool`；
* `detect` 必须是**纯函数**（同输入必同输出）；后处理、写盘、出图、重投影都不属本层；
* 协议是 `Protocol` + `@runtime_checkable`，**不需要继承任何基类**；
* `DetectionResult(mask=..., threshold=...)`：`threshold` 无阈值语义时填 `None`；
  派生属性 `changed_pixels` / `total_pixels` / `change_rate` 由 dataclass 提供。

### 7.2 ② 注册

注册语句写在 `backend/src/rschange/detectors/__init__.py`（**不是** `registry.py`）——
Python 导入任何子模块必先执行父包 `__init__`，因此「内置算法已装好」这一前提对任何
调用路径都成立：

```python
from rschange.detectors import registry
from rschange.detectors.base import ChangeDetector, DetectionResult
from rschange.detectors.cva import CvaDetector
from rschange.detectors.ndvi_diff import NdviDiffDetector

__all__ = ["ChangeDetector", "CvaDetector", "DetectionResult", "NdviDiffDetector", "registry"]

registry.register(CvaDetector())
registry.register(NdviDiffDetector())
```

注册表存**实例**不存类。重名注册默认抛 `ValueError`；确需替换须显式 `override=True`。

### 7.3 ③ 声明配置项

`backend/src/rschange/config.py`——新增一个继承 `_StrictModel` 的模型（嵌套模型的
`extra="forbid"` 必须逐个声明），并在 `Settings` 上加字段：

```python
class DetectorSettings(_StrictModel):
    """检测算法选择与参数。"""

    #: 未显式指定时使用的算法名。
    name: str = "cva"
    #: NDVI 差值阈值。`(name == "ndvi-diff")` 时生效。
    ndvi_threshold: float = Field(default=0.2, ge=0.0, le=2.0)
```

```python
class Settings(BaseSettings):
    ...
    detector: DetectorSettings = Field(default_factory=DetectorSettings)
```

`config/default.toml` 同步新增：

```toml
[detector]
name = "cva"
ndvi_threshold = 0.2
```

`config/local.example.toml` 同步加入**注释态**示例（与 `default.toml` 保持文档一致）。
注意其边界：`verify_config.py` 的模板判据**只覆盖** `build_dir` 与 `fixtures_dir` 两个键
（`verify_config.py` 判据 3 / 4），新增 `[detector]` 段**不会**进入该判据——这一步靠人工
对齐，不要期待门禁替你守住：

```toml
# [detector]
# name = "cva"
# ndvi_threshold = 0.2
```

### 7.4 ④ 注入到 `detect_change`

装配点是 `backend/src/rschange/api/deps.py:build_context()`——协议与实现的唯一接合处。
带参数的算法在构造期注入（与 `MorphologyPostprocessor` 同一写法）：

```python
from rschange.detectors import NdviDiffDetector, registry


def build_context(
    settings: Settings | None = None,
    *,
    detector: ChangeDetector | None = None,
    postprocessor: MaskPostprocessor | None = None,
) -> RuntimeContext:
    resolved = settings if settings is not None else get_settings()

    if postprocessor is None:
        postprocessor = MorphologyPostprocessor(
            min_size=resolved.postprocess.min_size,
            structure_size=resolved.postprocess.structure_size,
        )

    return RuntimeContext(
        settings=resolved,
        detector=detector if detector is not None else _resolve_detector(resolved),
        postprocessor=postprocessor,
    )


def _resolve_detector(settings: Settings) -> ChangeDetector:
    """按配置装配检测算法：带参数的算法在此构造，其余走注册表。"""
    if settings.detector.name == NdviDiffDetector.name:
        return NdviDiffDetector(threshold=settings.detector.ndvi_threshold)
    return registry.resolve(settings.detector.name)
```

`detect_change` 本身**不改**。需要在测试或脚本里直接指定算法时，显式传入即可：

```python
outcome = detect_change(
    request,
    detector=NdviDiffDetector(threshold=0.3),
    postprocessor=context.postprocessor,
    settings=context.settings,
)
```

或整体替换应用装配：

```python
app = create_app(context=RuntimeContext(settings, NdviDiffDetector(0.3), StubPostprocessor()))
```

### 7.5 ⑤ 写测试

新建 `backend/src/rschange/tests/test_ndvi_diff.py`：

```python
"""NDVI 差值检测器。

样本一律取**非方形**（height != width）——方形样本会让 H == W，掩盖转置类缺陷。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from rschange.detectors import registry
from rschange.detectors.base import ChangeDetector
from rschange.detectors.ndvi_diff import NdviDiffDetector
from rschange.errors import InputValidationError

if TYPE_CHECKING:
    from collections.abc import Iterator

    from numpy.typing import NDArray


@pytest.fixture
def restores_registry() -> Iterator[None]:
    """注册表是模块级全局；用例改动它之后必须还原。"""
    snapshot = dict(registry._REGISTRY)
    try:
        yield
    finally:
        registry._REGISTRY.clear()
        registry._REGISTRY.update(snapshot)


def _pair(height: int = 24, width: int = 40) -> tuple[NDArray[np.uint16], NDArray[np.uint16]]:
    """构造非方形样本：前一期全 1000，后一期近红外抬到 6000。"""
    assert height != width, "样本必须是非方形"
    before = np.full((2, height, width), 1000, dtype=np.uint16)
    after = before.copy()
    after[1, :, :] = 6000
    return before, after


class TestNdviDiffDetector:
    def test_satisfies_protocol(self) -> None:
        """不继承任何基类也须被 isinstance 接受。"""
        assert isinstance(NdviDiffDetector(), ChangeDetector)

    def test_non_square_shape_is_preserved(self) -> None:
        before, after = _pair()
        result = NdviDiffDetector(threshold=0.2).detect(before, after)
        assert result.mask.shape == (24, 40)
        assert result.mask.dtype == np.bool_
        assert result.total_pixels == 24 * 40

    def test_identical_images_produce_empty_mask(self) -> None:
        before, _ = _pair()
        result = NdviDiffDetector().detect(before, before.copy())
        assert result.changed_pixels == 0
        assert result.change_rate == 0.0

    def test_threshold_is_reported(self) -> None:
        before, after = _pair()
        assert NdviDiffDetector(threshold=0.35).detect(before, after).threshold == 0.35

    def test_shape_mismatch_rejected(self) -> None:
        before = np.zeros((2, 24, 40), dtype=np.uint16)
        after = np.zeros((2, 24, 41), dtype=np.uint16)
        with pytest.raises(InputValidationError) as caught:
            NdviDiffDetector().detect(before, after)
        assert caught.value.http_status == 400

    def test_single_band_rejected(self) -> None:
        array = np.zeros((1, 24, 40), dtype=np.uint16)
        with pytest.raises(InputValidationError, match="NDVI"):
            NdviDiffDetector().detect(array, array.copy())

    @pytest.mark.parametrize("threshold", [-0.1, 2.1], ids=["负", "超上界"])
    def test_invalid_threshold_rejected(self, threshold: float) -> None:
        with pytest.raises(ValueError, match="threshold"):
            NdviDiffDetector(threshold=threshold)

    def test_registration_is_visible(self, restores_registry: None) -> None:
        registry.register(NdviDiffDetector(threshold=0.3))
        assert "ndvi-diff" in registry.available()
        assert registry.resolve("ndvi-diff").name == "ndvi-diff"


@pytest.mark.usefixtures("engine_ready", "restores_registry")
def test_pipeline_runs_new_detector(before_path, after_path, tmp_path, context) -> None:
    """G3.4：注册新算法后，编排层无需任何改动即可使用它。"""
    from rschange.pipeline import DetectionRequest, detect_change

    registry.register(NdviDiffDetector(threshold=0.05))
    request = DetectionRequest(
        job_id="ndvi",
        before_path=before_path,
        after_path=after_path,
        output_dir=tmp_path / "outputs",
    )
    outcome = detect_change(
        request,
        detector=registry.resolve("ndvi-diff"),
        postprocessor=context.postprocessor,
        settings=context.settings,
    )
    assert outcome.detector == "ndvi-diff"
```

跑通：

```bash
uv run pytest backend/src/rschange/tests/test_ndvi_diff.py -o addopts="" -rs
uv run mypy
uv run ruff check . && uv run ruff format --check .
```

改动只落在 `detectors/`（新增模块 + `__init__` 注册）、`config.py`、两份 TOML、
`api/deps.py` 与测试。`pipeline/change_detection.py` 的哈希必须不变。

---

## 8. 常见问题

| 现象 | 成因 | 处置 |
|---|---|---|
| `ModuleNotFoundError: fastapi` / `numpy` | 跑了裸 `uv sync`，成员包 `rschange` 的运行时依赖被卸载 | 重跑 `uv sync --all-packages` |
| `verify_version.py` 第 1 项 FAIL | 改了 `backend/pyproject.toml` 未重新同步元数据 | `uv sync --all-packages` |
| `import _spatial` 报「找不到指定模块」 | Windows 上 `engine.runtime_dll_dir` 为空或路径错；或 `engine.build_dir` 与预设 `binaryDir` 不一致 | 填 `config/local.toml` 的 `runtime_dll_dir` 指向 MSYS2 `mingw64/bin`；跑 `uv run python scripts/verify_config.py` |
| DLL 有时能导入、有时找不到 | `os.add_dll_directory` 的返回句柄被 GC 回收 | 句柄必须收集在模块级列表（见 `spatial/loader.py:34`）；新增长生命周期代码禁止裸调用 |
| 影像处理结果看着对，换真实数据就错 | 测试样本是 256×256 方形，`H == W` 掩盖了转置 / 轴序错误 | 测试**必须**含非方形样本（如 24×40） |
| 门禁脚本抛 `UnicodeEncodeError: 'charmap' codec` | 运行环境非 UTF-8 stdio（GitHub runner ACP 1252） | 设 `PYTHONUTF8=1` |
| 中文用例名在 CI 上失配 / 解码失败 | 父进程按 cp1252 解码 UTF-8 子进程输出 | 设 `PYTHONUTF8=1`；Catch2 用例名已统一为 ASCII |
| `--phase 1` 判不通过 | `--phase 1` 的语义是「缺陷未修复、失败才是正确结果」，只对旧引擎产物有意义 | 当前仓库用 `--phase 6`（与 CI 一致） |
| `uv` 解析到 conda 的 3.14.7 空环境 | `.python-version` 未写精确三段版本号 | 写 `3.14.6`；保持 `python-preference = "only-system"` |
| 改了配置没生效 | 模型 `extra="forbid"`，拼写错的键会启动期报错；若未报错说明改在了 `local.toml` 之外 | 检查键名与优先级（环境变量 > `local.toml` > `default.toml`） |
| 前端类型与后端字段不符 | 改了 pydantic 模型未重生成产物 | 见 CONTRIBUTING.md「改契约的流程」 |

---

## 9. 调试与诊断

日志设施在 `backend/src/rschange/logging.py`，不引入 `structlog`。进程边界调用一次
`configure_logging`，其余模块只 `get_logger(__name__)`：

```python
from rschange.logging import get_logger

logger = get_logger(__name__)
logger.info("变化检测完成", pixels=7209, rate=0.11)   # 关键字参数即结构化字段
logger.exception("处理失败", job_id=job_id)           # 仅在 except 块内，自动带 traceback
```

| 项 | 说明 |
|---|---|
| 配置键 | `logging.level`（默认 `INFO`）、`logging.format`（`console` \| `json`） |
| `console` | `2026-09-23 21:40:02 INFO  rschange.pipeline  变化检测完成  pixels=7209 rate=0.11` |
| `json` | 每行一个 JSON 对象，含 `ts` / `level` / `logger` / `msg` + 全部 `extra` 字段；`ensure_ascii=False` 保留中文 |
| 输出目标 | **stderr**。`stdout` 保留给进程正式输出（引擎 `print_gdal_version` 也走它） |
| 幂等 | 重复 `configure_logging` 会先清空既有处理器，不会重复打印 |
| 保留键 | `extra` 中与 `LogRecord` 内置属性同名的键会被加下划线后缀（`name` → `name_`），不会抛 `KeyError` |
| 不可序列化 | `json` 格式用 `default=str` 兜底，日志本身永不成为崩溃点 |

`configure_logging` **不**导入 `rschange.config`（日志比配置更底层，避免循环依赖）。

引擎侧诊断：`scripts/verify_bindings.py` 校验当前构建产物的绑定契约；
`spatial/raster.py:gdal_version()` 在**子进程**中调用 `print_gdal_version()`，以绕开
MSYS2/MSVC 双 CRT 的 stdout 问题。
