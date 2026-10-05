# 遥感变化检测平台 · 迁移映射与阶段拆解

> 本文是《Remote_Sensing_重构方案.md》的配套执行文档。
> 定位：把「阶段要做什么」细化到「哪个文件搬迁到哪个路径、哪个函数拆到哪个文件、哪个缺陷怎么修」。
> 性质：**执行前必须冻结的规格**。执行期只允许按此文档搬，不允许临场发挥。
> 版本 v1.0 · 制定于 Phase 0

---

## 附录 A · 旧 → 新 全量文件级迁移映射

**动作图例**：`移` 移动不改内容 · `改` 移动并修改 · `拆` 拆分为多文件 · `重写` 保留意图重写 · `删` 删除 · `归档` 移入 docs 保留 · `生成` 由工具生成，不入库

### A.1 根目录

| 旧路径 | 新路径 | 动作 | 变更说明 |
|---|---|---|---|
| `README.md` | `README.md` | 重写 | 快速开始改为 `scripts/bootstrap.ps1` 一键流程；补架构图与验收说明 |
| `.gitignore` | `.gitignore` | 重写 | **删除 `api_tests/` 与 `CAREER_PLAN.md` 两条**（§1 C7）；按 OS / IDE / 语言 / 项目产物四段组织 |
| `.dockerignore` | `.dockerignore` | 改 | 补 `.venv`、`engine/build`、`node_modules`、`config/local.toml` |
| `docker-compose.yml` | `docker-compose.yml` | 改 | 命名卷、健康检查、环境变量外置 |
| `Dockerfile.backend` | `docker/Dockerfile.backend` | 改 | 统一 Python 3.14；runtime 阶段只装 `libgdal`（非 `-dev`）；构建产物路径随 `engine/` 调整 |
| `requirements.txt` | 根 `pyproject.toml` + `uv.lock` | 拆 | 手写直接依赖 → uv 声明 + 哈希锁定；**不产生 `requirements.*` 文件**；采用 uv workspace（根管工具链，`backend/pyproject.toml` 管成员依赖） |
| `CODE_MAP.md` | `docs/ARCHITECTURE.md` | 改 | **保留函数级调用树**（该文档质量高，是核心资产）；补分层图与数据流图；函数路径全部更新 |
| `DOCKER_PLAN.md` | `docs/deploy.md` | 归档 | 已完成项移除；「需要确认」两项（Python 版本、数据目录）按 §9 决策改写 |
| `GEO_CAPABILITIES.md` | `docs/agent-capabilities.md` | 移 | 内容保留（项目 3 的输入采购单）；补完「第 2 层 HTTP 层」待盘点项 |
| `Debug_lesson.txt` | `docs/lessons/debugging.md` | 归档 | 表格形式保留；补 §1 A4/A6 两个新发现的成因分析 |
| `project2-lessons-and-interview.txt` | `docs/lessons/interview.md` | 归档 | 面试稿更新：新增契约生成、双平台 CI、可插拔算法；**「面积怎么算」需按 §附录 D 修正口径** |
| `project_graph`（80 KB） | `docs/archive/initial-architecture-plan.txt` | 归档 | 初版选型方案（含 vcpkg / Catch2 / uv 原始设想）。注：文件内引用的旧路径为 `C:/Users/Hujian/source/遥感变化检测/` |

### A.2 C++ 引擎

| 旧路径 | 新路径 | 动作 | 变更说明 |
|---|---|---|---|
| `src/core/CMakeLists.txt` | `engine/CMakeLists.txt` + `engine/CMakePresets.json` | 重写 | 加 CTest、install 规则、`FetchContent` 拉 nlohmann/json、`-Werror` |
| `src/core/include/spatial/tiff_io.hpp` | `engine/include/spatial/export.hpp` + `raster.hpp` | 拆 | `SPATIAL_API` 宏 → `export.hpp`（**唯一定义点**）；`RasterData` → `raster.hpp` |
| `src/core/include/spatial/stats.hpp` | `engine/include/spatial/region.hpp` + `labeling.hpp` + `geojson.hpp` | 拆 | `PixelCoord`/`Region` → `region.hpp`；修 `are_m2` → `area_m2`；补 `std::hash<PixelCoord>`；删第 41 行被注释的死声明 |
| `src/core/src/tiff_io.cpp` | `engine/src/raster_io.cpp` + `engine/src/version.cpp` | 拆 | `print_gdal_version` 独立；`GDALAllRegister()` 一次化（见附录 D-4） |
| `src/core/src/stats.cpp` | `engine/src/labeling.cpp` + `contour.cpp` + `simplify.cpp` + `geojson.cpp` | 拆 | 12.9 KB 单文件承担 4 个职责，详见附录 C |
| `src/core/src/bindings.cpp` | `engine/bindings/module.cpp` | 改 | 修正 2D shape 解析（附录 D-1）；shape/geo 解析抽为具名函数 |
| `src/core/include/nlohmann/json.hpp`（1.0 MB） | 删除，改 `FetchContent` | 删 | 减少 1 MB 入库；版本在 CMakeLists 中钉死 |
| `src/core/src/remote-sensing/sensing.ipynb` | `notebooks/` 或删除 | 移 | 笔记本不得放在 C++ 源码目录 |
| `src/core/tests/main.cpp` | `engine/tests/test_raster_io.cpp` | 重写 | 裸可执行文件 → Catch2 + CTest 用例 |
| `src/core/tests/generate_synthetic.py` | `scripts/gen_fixtures.py` | 改 | 加 `--out` 参数；固定随机种子；**改用 GDAL 写盘**（去掉对 rasterio 的隐式依赖） |
| `src/core/tests/test_bindings.py` | `backend/tests/test_spatial_bindings.py` | 重写 | 去掉硬编码路径；改为 pytest |
| `src/core/tests/{before,after}.tif` | `engine/tests/fixtures/` | 移 | 作为基线 fixture 入库（各约 300 KB） |
| `src/core/tests/change_mask.tif` | — | 删 | 生成物，不应入库 |
| `src/core/tests/preview.png` | — | 删 | 生成物，不应入库 |
| `src/core/.gitignore`（6 B） | 合并入根 `.gitignore` | 删 | 内容为 `build/`，已被根规则覆盖 |

### A.3 Python 后端

| 旧路径 | 新路径 | 动作 | 变更说明 |
|---|---|---|---|
| `src/backend/main.py` | `backend/src/rschange/api/app.py` | 重写 | 改为 `create_app()` 工厂（便于测试注入）；DLL 路径逻辑移出（附录 D-5）；修 CORS 反模式（§1 D1） |
| `src/backend/config.py` | `backend/src/rschange/config.py` | 重写 | 纯常量模块 → `pydantic-settings`，支持 `RSCHANGE_*` 环境变量与 `config/local.toml` |
| `src/backend/routers/detection.py` | `backend/src/rschange/api/routers/detection.py` | 移 + 改 | 路由只做 IO 与校验；业务逻辑下沉；异常映射为领域异常 |
| `src/backend/schemas/detection.py` | `backend/src/rschange/api/schemas/detection.py` | 移 + 改 | 补 `Field` 描述与 example（OpenAPI 契约质量直接影响 Phase 5 类型生成） |
| `src/backend/services/detection.py` | `pipeline/change_detection.py` + `io/preview.py` + `io/reproject.py` + `spatial/loader.py` | 拆 | 7 步上帝函数解耦，详见附录 D-5 |
| `src/backend/detectors/cva.py` | `detectors/cva.py` + `detectors/base.py` + `detectors/registry.py` | 拆 | 抽出 `ChangeDetector` 协议与注册表，实现可插拔 |
| `src/backend/detectors/postprocessor.py` | `postprocess/morphology.py` + `postprocess/base.py` | 拆 | 删除第 21 行 `print`（§1 D2）；`min_size` 提为可配置参数 |
| `src/backend/tests/test_cva.py` | `backend/tests/test_pipeline.py` | 重写 | 脚本式 print → pytest + 基线锚点断言（§7.1/7.2/7.3） |
| `src/backend/.gitignore`（6 B） | 合并入根 `.gitignore` | 删 | 内容为 `__pycache__/` |
| `src/backend/detectors/__init__.py`（0 B） | `detectors/__init__.py` | 移 | 补导出 |

### A.4 前端

| 旧路径 | 新路径 | 动作 | 变更说明 |
|---|---|---|---|
| `src/frontend/` | `frontend/` | 移 | **脱离 `src/`**，与 `backend/` 平级；消灭「前端藏在 Python 项目的 src 下」这一结构问题 |
| `src/frontend/src/App.tsx` | `frontend/src/App.tsx` | 改 | 拆出 Query Provider；布局逻辑抽为 `AppLayout` |
| `src/frontend/src/api/client.ts` | `frontend/src/api/client.ts` | 改 | 强化错误处理；超时控制；`BASE` 改为可配置 |
| `src/frontend/src/hooks/useDetection.ts` | `frontend/src/features/detection/hooks/` | 改 | 引入 TanStack Query（**可降级**：保留为轻封装，见 §8 取舍） |
| `src/frontend/src/types/detection.ts` | `frontend/src/api/generated/` | 生成 | 手写类型删除，改由 OpenAPI 自动生成（Phase 5） |
| `src/frontend/src/components/UploadPanel.tsx` | `frontend/src/features/detection/components/` | 移 | 按 feature 重组 |
| `src/frontend/src/components/DetectionButton.tsx` | `frontend/src/components/ui/` | 移 | 通用化，去业务耦合 |
| `src/frontend/src/components/ResultPanel.tsx` | `frontend/src/features/detection/components/` | 移 | 按 feature 重组 |
| `src/frontend/src/index.css`（75 B） | `frontend/src/styles/index.css` | 改 | 补主题变量、`client_max_body_size` 提示不在此处——见 `docker/nginx.conf` |
| `src/frontend/index.html` | `frontend/index.html` | 移 | 补 `<meta description>`、`lang="zh-CN"` |
| `src/frontend/vite.config.ts` | `frontend/vite.config.ts` + `vitest.config.ts` | 改 | 抽 `vitest.config.ts`；代理目标改为读环境变量 |
| `src/frontend/package.json` | `frontend/package.json` | 改 | 补 `test` / `check` / `typecheck` 脚本；锁 `engines` |
| `src/frontend/Dockerfile.frontend` | `docker/Dockerfile.frontend` | 移 + 改 | node 版本对齐；`npm ci` 替代 `npm install` |
| `src/frontend/nginx.conf` | `docker/nginx.conf` | 移 + 改 | **补 `client_max_body_size 500m;`（§1 A5，否则上传必 413）**；补 gzip、静态缓存头 |
| `src/frontend/public/{favicon.svg,icons.svg,test.geojson}` | `frontend/public/` | 移 | `test.geojson` 改名为示例数据并注明来源 |
| `src/frontend/README.md` | 并入根 `README.md` | 删 | 避免双份 README 失同步 |

### A.5 测试与 IDE

| 旧路径 | 新路径 | 动作 | 变更说明 |
|---|---|---|---|
| `api_tests/`（被 gitignore） | `tests/api/` | 移 + 取消忽略 | 内容为 `传入矢量图.yml` 等 API 用例；**重新纳入版本控制**；`url` 字段的值 `POST http://localhost:8000/api/detect` 格式有误（`method` 已声明 POST，url 不应再带 `POST ` 前缀） |
| `.vscode/c_cpp_properties.json` | `.vscode/c_cpp_properties.json` | 重写 | `cppStandard` 由 `c++17` 改为 `c++20`（与 CMakeLists 一致）；路径改相对 |
| `.vscode/tasks.json` | `.vscode/tasks.json` | 重写 | 删掉两条「生成活动文件」的废弃 gcc/g++ 任务；改为调用 CMakePresets 与 bootstrap |
| `.vscode/launch.json` | `.vscode/launch.json` | 重写 | 路径改相对；补 Python/FastAPI 调试配置 |
| `.vscode/settings.json` | `.vscode/settings.json` | 重写 | **`cmake.sourceDirectory` 与 `cmake.configureArgs` 中的绝对路径全部改为相对/变量**；`python.analysis.extraPaths` 改指 `.venv` |

### A.6 数据

| 旧路径 | 新路径 | 动作 | 变更说明 |
|---|---|---|---|
| `data/uploads/*`（约 40 个文件） | `data/uploads/.gitkeep` | 删内容 | 已被 gitignore，但需保留目录结构 |
| `data/outputs/` | `data/outputs/.gitkeep` | 新增 | 旧项目未显式使用（PNG 写回 uploads），重构后明确分离 |

---

## 附录 B · Phase 1 文件级 WBS

**目标**：地基。不碰任何业务代码。完成后 `git tag v0.1.0`。

| # | 文件 | 职责 | 关键规格 |
|---|---|---|---|
| B1 | `.gitignore` | 版本控制边界 | 四段：OS / IDE / Python / Node。**不含** `api_tests/`、`CAREER_PLAN.md` |
| B2 | `.gitattributes` | 换行符与二进制处理 | `* text=auto eol=lf`；`*.tif binary`；`*.ps1 text eol=crlf` |
| B3 | `.editorconfig` | 编辑器统一 | Python 4 空格、C++ 4 空格、TS 2 空格、缩进 `space`、`insert_final_newline` |
| B4 | `.python-version` | 钉 Python 版本 | 内容 `3.14.6`（与 base 解释器一致，保证 cp314 ABI 复用） |
| B5 | `.dockerignore` | 构建上下文裁剪 | 排除 `.venv`、`engine/build`、`node_modules`、`config/local.toml` |
| B6 | `config/default.toml` | 跨平台默认配置 | 入库。含 `[runtime] [engine] [logging]` 三段，见方案 §2② |
| B7 | `config/local.example.toml` | 本机配置模板 | 入库。每一项带注释说明；`runtime_dll_dir` 给出 Windows/Linux 两种示例 |
| B8 | `scripts/bootstrap.ps1` | Windows 一键环境 | 7 步：断言 `uv` 存在 → 断言 `uv python find 3.14.6` == DevCode 路径（防 conda 陷阱）→ `uv venv --python 3.14.6` → `uv sync --all-packages --all-groups` → 生成 `local.toml` → 打印下一步。**全程不调用裸 `pip` / 裸 `python`** |
| B9 | `scripts/bootstrap.sh` | Linux/macOS 一键环境 | 同上，POSIX 兼容 |
| B10 | `scripts/verify_baseline.py` | 基线锚点校验 | 见下方 B10 详规 |
| B11 | `scripts/clean.ps1` / `.sh` | 清理构建产物 | 清理 `engine/build`、`__pycache__`、`.pytest_cache`、`frontend/dist`；**不动 `.venv`**（避免重复下载依赖） |
| B12 | 根 `pyproject.toml` | workspace 根 + 工具配置 | `[tool.uv.workspace].members = ["backend"]`、`[tool.uv] python-preference = "only-system"`、`requires-python = ">=3.14,<3.15"`、`[tool.ruff]`、`[tool.mypy] strict`、`[tool.pytest.ini_options]` |
| B13 | `backend/pyproject.toml` | 成员包元数据 | `name = "rschange"`；`[project.dependencies]`（编译期/运行时）+ `[dependency-groups].dev`（pytest/ruff/mypy/httpx）；src layout |
| B14 | `uv.lock` | 锁定全量 | 由 `uv lock` 生成并入库（含哈希） |
| B15 | `.vscode/{settings,extensions,tasks,launch}.json` | IDE 配置 | 全相对路径；`extensions.json` 推荐 C++/Python/CMake/Ruff 插件 |
| B16 | 目录骨架 + `.gitkeep` | 结构占位 | `engine/{include/spatial,src,bindings,tests/fixtures}`、`backend/src/rschange/...`、`frontend/`、`docker/`、`docs/`、`tests/api/`、`data/{uploads,outputs}` |
| B17 | `README.md`（骨架版） | 入口文档 | 仅写快速开始 + 目录说明；完整版留 Phase 7 |
| B18 | git 初始化 | 版本控制 | `git init` → 首次提交 → `git tag v0.1.0` |

### B10 详规 · `scripts/verify_baseline.py`

**职责**：一条命令输出 §7.1 / §7.2 / §7.3 三组判定的通过情况。

**关键设计**：
- 通过 `config/local.toml` 的 `[engine].build_dir` 定位 `_spatial` 模块 → **Phase 1 阶段指向旧 `build/` 目录**（证明校验工具本身可用），Phase 2 起改指新 `engine/build/`
- 依赖 scipy 独立计算连通域个数，作为 `mask_to_geojson` 的对照基准（不依赖被测代码自证）
- 输出格式：逐项 `PASS` / `FAIL`，任一项 FAIL 时以非零码退出（供 CI 使用）
- 打印**实际值**而非仅结论，便于人工核查

**Phase 1 出口判据**：该脚本能跑起来并正确输出 §7.1 全部 `PASS`、§7.2 全部 `FAIL`（因为缺陷尚未修复——**FAIL 才是当前正确的预期结果**）。

---

## 附录 C · C++ 引擎拆分归属表（函数级）

### C.1 `stats.cpp`（311 行）→ 4 文件

| 旧行号 | 符号 | 新位置 | 可见性 |
|---|---|---|---|
| 14–32 | `struct UnionFind` | `engine/src/labeling.cpp`（匿名 namespace） | 内部 |
| 43–100 | `extract_regions` | `engine/src/labeling.cpp` | `SPATIAL_API` |
| 112–113 | `DR[8]` / `DC[8]` 常量 | `engine/src/contour.cpp`（匿名 namespace） | 内部 |
| 115–168 | `extract_boundary` | `engine/src/contour.cpp` | `SPATIAL_API`（当前是 `static`，Phase 2 需暴露以便单测） |
| 175–187 | `point_line_dist` | `engine/src/simplify.cpp` | 内部 |
| 196–219 | `dp_recurse` | `engine/src/simplify.cpp` | 内部 |
| 227–239 | `simplify_boundary` | `engine/src/simplify.cpp` | `SPATIAL_API`（恢复在头文件中的声明，替换旧死声明） |
| 250–310 | `regions_to_geojson` | `engine/src/geojson.cpp` | `SPATIAL_API` |

**跨文件依赖**：`geojson.cpp` 需要 `contour.hpp` + `simplify.hpp`；`contour.cpp` 需要 `region.hpp`。依赖方向单向：`geojson → contour → region`，`geojson → simplify → region`。

### C.2 `tiff_io.cpp`（154 行）→ 3 文件

| 旧行号 | 符号 | 新位置 |
|---|---|---|
| 8–11 | `print_gdal_version` | `engine/src/version.cpp` |
| 25–78 | `read_raster` | `engine/src/raster_io.cpp` |
| 90–153 | `write_raster` | `engine/src/raster_io.cpp` |
| 27, 99 | `GDALAllRegister()` 调用 | 抽出为 `engine/src/gdal_init.cpp` 的一次性初始化（附录 D-4） |

### C.3 `bindings.cpp`（109 行）→ 精简保留

| 旧行号 | 内容 | 处理 |
|---|---|---|
| 29–72 | `read_raster` lambda（capsule 所有权转移） | **保留在 bindings**（属 Python 边界关注点）；但 shape 构造与 `geo_transform → vector` 转换抽为具名辅助函数 |
| 80–94 | `write_raster` lambda | 修正 2D shape 解析（附录 D-1） |
| 96–105 | `mask_to_geojson` lambda | 加输入校验（维度、dtype） |

**原则**：`bindings/` 只做「Python 对象 ↔ C++ 类型」转换；出现算法或多分支业务逻辑即为越界。

---

## 附录 D · Phase 2 缺陷修复清单

每条均须配套一个失败用例（先红后绿）。

| ID | 关联 | 位置 | 现状 | 修复方案 | 对基线的影响 | 验证方式 |
|---|---|---|---|---|---|---|
| D-1 | §1 A6 | `bindings.cpp:85-87` | 2D 输入时 `w = mask.shape(2)` 越界，读到 `strides[0]`；2D 一律写成 `W×W` | 按 `ndim()` 分支：2D → `h=shape(0), w=shape(1)`；3D → `b=shape(0), h=shape(1), w=shape(2)`；其他维度抛异常 | 尺寸类断言转为正确 | 非方形用例 `(100,200)` / `(200,100)` / `(64,512)` 写读一致 |
| D-2 | §1 A4 | `stats.cpp:161-166` | `trace_ring` 返回后未把关**起点**写入 `visited`，主循环从另一未访问边界像素重启 → 同一连通域产出多个环 | 追踪结束后将整个环的全部像素写入 `visited`；主循环改为「每个连通域只追踪一次外环」 | **Feature 数 2 → 1**（§7.2 预期改变） | 单连通域用例断言 `len(features) == 1` |
| D-3 | §1 A4 | `stats.cpp:282-302` | 「每环一个 Feature」把 Region 级 `pixel_count`/`area_m2` 复制给每个环 → 面积重复计 N 倍 | 采用标准 GeoJSON 语义：多环归属**同一个 Feature 的 Polygon**，首环为外环、其余为内环；`properties` 保持 Region 级且**每个 Region 只出现一次** | 面积合计由 1441800 → 720900（§7.2） | 断言 `sum(area_m2) == 像素数 × 单像元面积` |
| D-4 | §1 D9 | `tiff_io.cpp:27,99` | `GDALAllRegister()` 每次调用都执行（一次检测 3 次） | 改为 `std::once_flag` 保护的一次性初始化 | 无 | 计时对比；断言多次调用结果一致 |
| D-5 | §1 A2 | `main.py:5`、`services/detection.py:11-16`、`test_cva.py:7-14`、`test_bindings.py:4-11` | 同一段 DLL 路径逻辑**重复 4 份**，且硬编码绝对路径 | 收敛到唯一模块 `spatial/loader.py`；其余全部改为 `from rschange.spatial import read_raster` | 无 | `grep -rn "msys64" backend/` 结果为空 |
| D-6 | §1 D10 | `stats.cpp:79` | `std::unordered_map<int, Region>` 迭代顺序未定义 → `label` 分配跨平台不确定 | 改为 `std::map`，或按 raster-scan 首次出现顺序排序 | 单区域样本无变化；多区域样本 `label` 变为确定值 | 多区域用例在不同构建下 md5 一致 |
| D-7 | §1 D11 | `stats.cpp:116` | `pixels.size() < 3` 返回 `{{}}`（含空环）语义含糊 | 返回空 `vector`，并在 `regions_to_geojson` 显式跳过 | 无 | 1–2 像素区域用例不产生 Feature 且不崩 |
| D-8 | §1 D12 | `stats.cpp:271` | Douglas-Peucker（开曲线算法）直接套用于闭环 | 对闭合环采用「以距起点最远点为切分点拆成两段开曲线」的闭曲线 DP 变体 | 顶点数可能变化 | 断言输出环仍闭合、不自交 |
| D-9 | §1 D4 | `stats.hpp:32,41` | 拼写 `are_m2`；被注释的死声明 | 重命名为 `area_m2`；删死声明并于 `simplify.hpp` 补正声明 | GeoJSON 字段名不变（本就是 `area_m2`） | 编译通过 + 字段名断言 |

> **执行顺序约束**：D-4 与 D-6 无基线影响，可先做；**D-1 → D-2 → D-3 有严格顺序**（尺寸对了才有意义谈环，环对了才谈属性归属），且 D-3 完成后必须重跑 §7.2 全表。

---

## 附录 E · 子 agent 派单模板

每张派单固定包含五项，缺一项视为派单无效。

```
【角色】<代号，如 cpp-core>
【阶段】Phase N · <阶段名>
【输入】① 必读文件清单（含路径）② 上游冻结的接口/契约
【产出】① 文件清单（含路径）② 必须可执行的验证命令
【边界】明确禁止触碰的目录/文件；明确不得修改的接口
【自检】提交前必须自行运行并附真实输出的命令
```

**验收官派单额外要求**：
- 派单中**不得**包含「请确认是否正确」这类引导性问题
- 派单必须提供**独立的复现路径**（不得复用执行者提供的脚本或结论）
- 默认立场：执行者的报告**未被证实**；只承认自己跑出的输出
- 必须给出 `通过` / `不通过` 二元判定，不接受「基本没问题」

---

## 附录 F · 基线 fixture 说明

| 文件 | 规格 | 来源 | 用途 |
|---|---|---|---|
| `engine/tests/fixtures/before.tif` | 256×256×3，uint16，EPSG:32650，10 m 像元 | 由 `scripts/gen_fixtures.py` 生成（固定种子 42） | 全链路基线输入 |
| `engine/tests/fixtures/after.tif` | 同上；中心半径 ≈48 像元区域模拟洪水（NIR ×0.15 / Red ×0.4 / Green ×0.6） | 同上 | 全链路基线输入 |
| 变化像素真值 | `7209`，全部落在 1 个连通域内 | 实测（scipy 独立验证） | 判定 §7.1 / §7.3 |
| 合成影像真实变化面积 | `720900.0` m² | `7209 × \|10×(-10)\|` | 判定 §7.2 / §7.3 |

**注意**：该 fixture 是**圆盘形单连通区域**，这正好是暴露 D-2/D-3 的理想样本；但**不足以覆盖多连通域与带洞场景**。Phase 2 须额外补充：
- 多连通域样本（验证 `label` 确定性与逐区域属性）
- 带洞环样本（验证 D-3 的内外环语义）
- 非方形样本（验证 D-1）

---

*本文档与《Remote_Sensing_重构方案.md》共同构成 Phase 0 的规划产出。执行期间任何偏离须先回到本文档更新规格，再动代码。*
