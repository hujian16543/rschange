# rschange · 旧仓库 → 新仓库迁移对照

> **旧仓库**（只读参考）：`Remote_Sensing_Change_Detection` —— 单体三级目录 + 脚本式实现的毕业设计原型，`README.md` 自述写于 2026-08-15 Docker 化完成后。
> **新仓库**：`rschange` —— C++ 空间引擎（GDAL + nanobind 扩展 `_spatial`）+ Python FastAPI 分层后端 + React 19 / TS / Vite 前端，uv workspace 管理依赖，7 阶段分层重构后冻结于 Phase 7。
>
> **本文纪律**：逐条给出「旧 → 新」落点。凡 `legacy-digest.md` 未覆盖的旧仓库信息，一律回到旧仓库源文件核实后才写入；仍不能确定的标 `待核实`，集中列于 §9。
> 左右两侧的规范性描述（ directory 名、字段名）以**各自仓库的源文件**为准，不采信旧 README / `CODE_MAP.md` 的转述（转述存在过时与遗漏，见 §7.1）。

---

## 1. 迁移总览

| 维度 | 旧仓库形态 | 新仓库形态 |
|---|---|---|
| 目录骨架 | `src/{core,backend,frontend}`，部署文件横跨仓库根与 `src/frontend/` 两级 | 顶层平铺 `engine/`、`backend/`、`frontend/`、`docker/`、`scripts/`、`tests/`、`docs/` |
| 引擎构建 | `cd src/core && cmake -B build && cmake --build build --config Release`（裸 CMake，无预设） | `cd engine && cmake --preset <dev-win\|dev-linux>` + `cmake --build --preset`（`CMakePresets.json` version 6） |
| 引擎代码组织 | 1 个绑定 `bindings.cpp` + 2 个实现 `tiff_io.cpp` / `stats.cpp` | 绑定 `bindings/module.cpp` + 6 个实现模块（`raster_io` / `labeling` / `contour` / `simplify` / `geojson` / `gdal_init`）+ `include/spatial/` 公开头 |
| 第三方 JSON 库 | `include/nlohmann/json.hpp` 随源码入库 | CMake `FetchContent` 拉取 `nlohmann/json` v3.11.3，不再入库 |
| 后端形态 | 模块级 `app = FastAPI(...)`（模块即应用） | `create_app()` 工厂 + `RuntimeContext` 依赖注入 |
| 后端分层 | 4 层：`main` / `routers` / `services` / `detectors` | 8 层：`api` / `pipeline` / `detectors` / `postprocess` / `io` / `spatial` + 叶层 `config` / `logging` / `errors` |
| 算法装配 | 编排函数里硬编码 `cva_detect(before, after)` | `Detector` 协议 + 注册表 + `api/deps.py:build_context()` 单一装配点 |
| 配置 | `config.py` 纯常量（端口、目录、体积上限） | `pydantic-settings` 分层配置，`RSCHANGE_*` 环境变量 > `config/local.toml` > `config/default.toml` |
| 依赖管理 | `requirements.txt` 7 个包无版本钉；`pip install` 裸命令 | uv workspace（`members = ["backend"]`），`uv.lock` 入库，`requires-python = ">=3.14,<3.15"` |
| Python 版本 | 本地 3.14、容器 3.12 混用（`DOCKER_PLAN.md` §5.5 曾问「用 3.12 可以吗？」并落地为 3.12） | 全链路锁定 `3.14.6`（`.python-version`、CI `check-latest: false`、容器 `python:3.14`） |
| 前端类型 | 手写 `src/types/detection.ts`（10 字段，与后端漂移） | 由 `docs/api/openapi.json` 生成 `api/generated/data-contracts.ts`，经 `api/types.ts` 转发；手写类型已删除 |
| 前端测试 | 无测试框架（`package.json` 无 `test` 脚本、无 vitest 依赖） | `vitest` + Testing Library，**109** 个用例（6 文件） |
| 契约产物 | 无 | `docs/api/openapi.json` 入库冻结；两段漂移门禁（详见 §4.4） |
| CI | 无 | `.github/workflows/ci.yml`，单 job × 双平台矩阵（Linux gcc / Windows MinGW） |
| 门禁脚本 | 无 | `scripts/verify_{baseline,bindings,config,version,containers}.py` |

---

## 2. 模块映射表

### 2.1 后端 Python

| 旧文件 | 旧职责 | 新落点 | 说明 |
|---|---|---|---|
| `src/backend/main.py` | 入口：装 DLL 路径、注册 CORS、挂路由、`root()`、启动 uvicorn | `backend/src/rschange/api/app.py`（`create_app()`、`main()`、`root()`）+ `api/routers/detection.py` + `api/errors.py` + `api/deps.py` | 一个模块拆为「应用工厂 / 路由 / 异常处理器 / 装配」四处；`:121-125` 明记为 CORS 缺陷修正 |
| `src/backend/config.py` | 纯常量：`ROOT_DIR` / `UPLOAD_DIR` / `OUTPUT_DIR` / `PORT=8000` / `MAX_UPLOAD_SIZE=500MB` | `backend/src/rschange/config.py` | 改为 `pydantic-settings` 分层模型，五段 `runtime` / `engine` / `logging` / `postprocess` / `baseline`；嵌套模型一律 `extra="forbid"` |
| `src/backend/routers/detection.py` | 校验后缀、存盘、调 `run_detection`、`serve_image` | `backend/src/rschange/api/routers/detection.py` | 路径与字段名不变（`POST /api/detect`、`GET /api/image/{filename}`）；错误模型、穿越防护、线程下放为新增 |
| `src/backend/services/detection.py` `run_detection()`（114 行单函数，7 步） | 编排整条流水线 + 重投影 + 四角 + PNG | `backend/src/rschange/pipeline/change_detection.py`（七步）+ `io/reproject.py` + `io/preview.py` | 旧实现的 7 步被拆为 7 个 `_` 前缀函数（`change_detection.py:128-295`）；`_reproject_geojson` / `_compute_image_corners` → `io/reproject.py`；`_save_rgb_png` → `io/preview.py` |
| `src/backend/detectors/cva.py` `cva_detect()` / `_otsu()` / `_histogram()` | CVA + Otsu | `backend/src/rschange/detectors/cva.py`（`CvaDetector` + 模块级 `histogram` / `otsu_threshold`）、`detectors/base.py`（协议）、`detectors/registry.py`（注册表） | 数值行为与旧实现逐位一致（256 箱直方图、Otsu 类间方差） |
| `src/backend/detectors/postprocessor.py` `postprocess(mask, min_size=30)` | 连通域过滤 + 3×3 闭运算 | `backend/src/rschange/postprocess/morphology.py`（`MorphologyPostprocessor`）、`postprocess/base.py` | `min_size` 与结构元边长提为构造参数，来源 `config.postprocess`；**本层无注册表** |
| `src/backend/schemas/detection.py` `DetectionResponse`（10 字段）/ `DetectionRequest`（两路径也未用于 HTTP） | 响应模型 | `backend/src/rschange/api/schemas/detection.py`（`DetectionResponse` 12 字段 + `ErrorResponse`） | 同名不同义：新仓库的 `DetectionRequest` 是 `pipeline` 内的 dataclass（`job_id` / 两个路径 / `output_dir`），不再是 pydantic 请求模型 |
| `src/backend/tests/test_cva.py` | 唯一后端测试 | `backend/src/rschange/tests/`（6 个测试模块） | 按层拆分：`test_api` / `test_architecture` / `test_config_logging` / `test_detectors_postprocess` / `test_io` / `test_pipeline` |

> **待核实**：`src/backend/tests/test_cva.py` 的**具体内容**未在 `legacy-digest.md` 中提炼，本文只记录其存在（旧 `src/` 文件树，共 52 个文件）。

### 2.2 C++ 引擎

| 旧文件 | 旧职责 | 新落点 |
|---|---|---|
| `src/core/src/bindings.cpp` | nanobind 绑定，四个函数 | `engine/bindings/module.cpp` |
| `src/core/src/tiff_io.cpp` | GDAL 读写栅格 + 重复注册驱动 | `engine/src/raster_io.cpp` + `engine/src/gdal_init.cpp`（一次性初始化） |
| `src/core/src/stats.cpp` | Two-Pass 连通域 + UnionFind + Moore 边界追踪 + DP 简化 + GeoJSON 组装（一个大文件，含 `regions_to_geojson` 的 4 步） | 拆为 `engine/src/labeling.cpp`、`contour.cpp`、`simplify.cpp`、`geojson.cpp` 四个模块 + `include/spatial/*.hpp` 公开头 |
| `src/core/include/spatial/stats.hpp` / `tiff_io.hpp` | 两个头 | `engine/include/spatial/{raster,labeling,contour,simplify,geojson,region,export}.hpp` |
| `src/core/include/nlohmann/json.hpp` | 第三方单头，**随源码入库** | 删除，改由 `FetchContent` 拉取 |
| `src/core/CMakeLists.txt` | 裸工程定义 | `engine/CMakeLists.txt` + `engine/CMakePresets.json` + `engine/cmake/PythonExtension.cmake` |
| `src/core/tests/main.cpp` | C++ 测试入口 | `engine/tests/test_{contour,geojson,labeling,multi_region,pipeline,raster_io,simplify}.cpp`（Catch2，40 个 `TEST_CASE`） |
| `src/core/tests/generate_synthetic.py` | 生成合成影像 | `scripts/make_multi_region_fixture.py`（多区域夹具）+ `fixtures` extra（`rasterio`）重生成影像对 |
| `src/core/tests/test_bindings.py` | 绑定层自测 | `scripts/verify_bindings.py`（42 项判据） |
| `src/core/tests/{before,after,change_mask}.tif`、`preview.png` | 手工产物 | `engine/tests/fixtures/{before.tif,after.tif,change_mask.{raw,json},multi_region_mask.{raw,json}}`（冻结，`.raw` 字节法定） |
| `src/core/src/remote-sensing/sensing.ipynb` | 孤立 notebook | **未迁移**，见 §7.1 |

### 2.3 前端

| 旧文件 | 新落点 | 说明 |
|---|---|---|
| `src/frontend/src/App.tsx` | `frontend/src/App.tsx` | 拆出 `ErrorBoundary`；业务状态全部下沉 `DetectionPage` |
| `src/frontend/src/api/client.ts` | `frontend/src/api/client.ts` | 新增相对 `/api` 基址约定、`ApiError` / `NetworkError` 分类、`code` 随错误抛出 |
| `src/frontend/src/hooks/useDetection.ts` | `frontend/src/features/detection/hooks/useDetection.ts` | 状态机语义保留；新增竞态保护（`runIdRef`） |
| `src/frontend/src/components/{UploadPanel,ResultPanel,DetectionButton}.tsx` | `frontend/src/features/detection/components/` 同名三个组件 + 新增 `ErrorAlert.tsx` / `ResultSkeleton.tsx` | 新增加载骨架与结构化错误提示 |
| `src/frontend/src/types/detection.ts`（手写 10 字段） | **删除**，由 `frontend/src/api/generated/data-contracts.ts` + `api/types.ts` 取代 | `docs/contracts.md:312` 明记「原手写类型已删除」 |
| — | `frontend/src/features/detection/errors.ts` / `format.ts` | 新增：错误按 `code` 分支映射、纯函数格式化 |
| — | `frontend/src/components/ui/`（6 个原语 + `index.ts`） | 新增：业务无关的 UI 原语层 |
| — | `frontend/src/test/{fixtures.ts,setup.ts}` | 新增：与契约逐字段对齐的测试夹具 |
| `src/frontend/src/assets/hero.png`、`vite.svg` | — | 未迁移，见 §7.1 |
| `src/frontend/{Dockerfile.frontend,nginx.conf}` | `docker/Dockerfile.frontend`、`docker/nginx.conf` | 部署文件收敛到顶层 `docker/` |
| `src/frontend/{package.json,tsconfig*.json,vite.config.ts,.oxlintrc.json}` | `frontend/` 下同名文件 | 新增 `vitest.config.ts`、`tsconfig.node.json` 保留 |

### 2.4 部署与仓库工具

| 旧文件 | 新落点 | 差异 |
|---|---|---|
| 仓库根 `Dockerfile.backend` | `docker/Dockerfile.backend` | builder 由 `python:3.12` 改为 `python:3.14-slim-bookworm`；runtime 由装 `libgdal-dev` 改为逐个尝试 `libgdal36…libgdal32` 运行时包；新增非 root 用户 `appuser` |
| `docker-compose.yml` | `docker-compose.yml` | 新增健康检查、`depends_on: condition: service_healthy`、命名卷 `rschange-data`、`.dockerignore`；删除废弃的 `version:` 字段 |
| `src/frontend/nginx.conf` | `docker/nginx.conf` | 新增 `client_max_body_size 500m`、`/assets/` 一年 immutable 缓存、`index.html` no-cache、反代超时与 `proxy_request_buffering off` |
| `requirements.txt`（7 包无钉） | `backend/pyproject.toml` 9 个运行依赖 + 根 `pyproject.toml` dev 组（9 项）+ `uv.lock` | `rasterio` 降为可选 extra `fixtures` |
| — | `scripts/{bootstrap,clean}.{sh,ps1}`、`scripts/gen-api-types.{sh,ps1}`、`scripts/verify_*.py`、`scripts/gen_openapi.py`、`scripts/engine_env.py` | 全部新增 |

### 2.5 文档

| 旧文件 | 新落点 | 说明 |
|---|---|---|
| `CODE_MAP.md`（「一次请求的生命周期」函数地图） | `docs/ARCHITECTURE.md` §3 数据流 + `docs/DEVELOPMENT.md` | 转为**以行进机器可复核的形态**承载：CODE_MAP 是人工转述且会过时，本文档与 ARCHITECTURE 的依据是可 grep 的 `文件:行号` |
| `GEO_CAPABILITIES.md`（未完成的第 0/1 层盘点） | `docs/ARCHITECTURE.md` §2 + 本文 §6 | 原文「待盘点」的第 2 层（HTTP）及其汇总在新仓库补齐 |
| `DOCKER_PLAN.md` | `docs/verification/phase-6.md` + `docker/` | 计划 vs 实际的差异对照见本文 §7.2 |
| `Debug_lesson.txt`（5 条）、`project2-lessons-and-interview.txt`（8 条） | `docs/lessons/`（`README.md` + `debug-lessons.md` + `interview-notes.md`） | 两源合计 **13 条**教训逐条整理为「现象 / 根因 / 修复 / 新仓库落点 / 复发判据」，对「新仓库无对应守护」的条目显式标注 `无守护`；面试讲述话术单列 `interview-notes.md`。按摘要建议**不做合并去重**，同源记录以「同源」列标注 |
| `README.md` | `README.md`（重写） | 旧 README 的三处过时描述均已在 `v1.0.0` 修正：`Moore 邻域` → 沿像素边界追踪（crack following）、`--phase 1` → `--phase 6`、4 个悬空文档链接 → 实存路径 |

---

## 3. 命令 / 接口变化

### 3.1 构建与运行

| 场景 | 旧命令 | 新命令 |
|---|---|---|
| 编译引擎 | `cd src/core && cmake -B build && cmake --build build --config Release` | `cd engine && cmake --preset dev-win` → `cmake --build --preset dev-win`（Linux 用 `dev-linux`） |
| 跑引擎测试 | `src/core/build/test_main.exe` | `ctest --test-dir engine/build/dev-win --output-on-failure` |
| 装依赖 | `pip install fastapi uvicorn numpy pyproj pillow`（README 命令，比 `requirements.txt` **少** `scipy` 与 `python-multipart`） | `uv sync --all-packages --frozen`（成员间的 promoted 依赖全部写入 `uv.lock`） |
| 启动后端 | `cd src/backend && python -m uvicorn main:app --reload --port 8000`（`"main:app"` 依赖工作目录恰为 `src/backend`） | `uv run uvicorn --factory rschange.api.app:create_app --reload` 或 `uv run python -m rschange.api.app`（与工作目录无关） |
| 启动前端 | `cd src/frontend && npm install && npm run dev` | `cd frontend && npm ci && npm run dev` |
| 前端检查 | `npm run lint`（仅 oxlint） | `npm run check`（= `tsc -b --noEmit && oxlint && vitest run`） |
| 重新生成前端类型 | — | `npm run gen:types`（或 `scripts/gen-api-types.{sh,ps1}`） |
| 校验基线 | — | `uv run python scripts/verify_baseline.py --phase 6`（**与 CI 取值一致**；`--phase 1` 只对旧引擎构建产物有意义） |

> **`--phase` 语义提醒**：`--phase 1` 表示「缺陷未修复，§7.2 / §7.3 **必须失败**」（`scripts/verify_baseline.py:18-21`、`:589`）。在已完成重构的仓库上跑 `--phase 1` 会判**不通过**，属正确使用下的正确结果，不是命令失灵。

### 3.2 Python 版本约束

旧仓库在本地跑 3.14、容器里跑 3.12，同一份 C++ 扩展需按 OS/Python 版本分别编译，但 `requires-python` 从未声明。新仓库锁定一条线：

| 项 | 值 | 出处 |
|---|---|---|
| `requires-python` | `>=3.14,<3.15` | 根 `pyproject.toml:16-17`、`backend/pyproject.toml:19` |
| `.python-version` | `3.14.6` | `.python-version` |
| CI Python | `3.14.6`，`check-latest: false` | `.github/workflows/ci.yml:127-128` |
| `_spatial` ABI | `cp314` | `docs/contracts.md:23` |

> **下探风险**：`api/routers/detection.py:120` 的 `except OSError, ValueError:` 是 Python 3.14（PEP 758）才允许的无括号异常组写法，在 3.13 及更早版本是 `SyntaxError`。新代码合法，但写例子时应**显式加括号**（`_work/p7/new-arch-digest.md` C1）。

### 3.3 HTTP 端点：路径不变，语义变化

三条端点的**路径与方法均未变**（`POST /api/detect`、`GET /api/image/{filename}`、`GET /`），前端基址仍为 `/api`。变化集中在语义与防御：

| 方面 | 旧行为 | 新行为 | 出处 |
|---|---|---|---|
| 字段名 | 恰为 `before` / `after`（已一致） | 一致，`multipart/form-data` | `docs/contracts.md:194` |
| 后缀白名单 | 校验 `.tif` / `.png` | `frozenset({".tif",".tiff",".png"})`，增加 `.tiff` | `routers/detection.py:55` |
| 体积上限 | `config.MAX_UPLOAD_SIZE` 声明 500 MB **但从不读取**；实际由反向代理（nginx 默认 1 MB）决定 | 应用层 `runtime.max_upload_mb`（默认 500），1 MiB 分块边收边计，超限即删半成品 → 413 / `upload_too_large` | `routers/detection.py:19-21`、`:72-97`；`contracts.md:196-198` |
| 静态文件目录穿越 | `os.path.join(UPLOAD_DIR, filename)` —— 绝对路径会让基目录被整个丢弃 | 「纯文件名 + resolve 复核」两道判定，任一不满足即 404 | `routers/detection.py:13-17`、`:100-124` |
| CPU 密集任务的调度 | `async def` 路由里直接调用同步流水线，**阻塞事件循环** | `await run_in_threadpool(detect_change, ...)` | `routers/detection.py:23-25`、`:181-187` |
| CORS | `allow_origins=["*"]` + `allow_credentials=True` 并存（白名单实际失效） | 白名单取 `runtime.allowed_origins`，`allow_credentials=False`，且配置期拒绝 `"*"` | `app.py:121-132`、`config.py` `_reject_wildcard` |
| 异常形状 | `except Exception as e: raise HTTPException(500, detail=str(e))` —— 内部信息全量外泄 | 全局处理器统一产出 `{"detail","code"}`；500 兜底为固定串「内部错误」，栈只进日志 | `api/errors.py`、`docs/contracts.md:249` |
| 两期影像可比性 | 静默沿用前一期的地理参考 | 形状 / `geo_transform`（容差 `1e-9`）/ 投影三项不一致即 400 `input_validation_error` | `change_detection.py:29-35`、`:145-172` |
| `job_id` | 由 before 文件名反推（`basename(...).replace("_before.tif","")`），命名一变 URL 全失效 | `uuid.uuid4().hex`，由调用方显式给出 | `change_detection.py:31-33`、`routers/detection.py:147` |
| 预览图目录 | 依赖上传目录恰好已存在 | 编排层 `_write_previews()` 显式 `mkdir(parents=True)` | `change_detection.py:36`、`:222` |

---

## 4. 契约变化

### 4.1 成功响应：10 字段 → 12 字段

| # | 字段 | 旧 | 新 | 变化 |
|---|---|---|---|---|
| 1 | `change_pixels` | `int` | `int`（`ge=0`） | 补约束 |
| 2 | `total_pixels` | `int` | `int`（`gt=0`） | 补约束 |
| 3 | `change_rate` | `float` | `float`（`ge=0, le=1`） | 补约束，明确取值区间 |
| 4 | `threshold` | `float` | `float` | 不变 |
| 5 | `detector` | — | `str` | **新增**：回带实际算法名，使结果可追溯（可插拔之后的必然要求） |
| 6 | `pixel_area_m2` | — | `float`（`gt=0`） | **新增**：单像元面积，让消费方自行换算，不必反推 |
| 7 | `changed_area_m2` | — | `float`（`ge=0`） | **新增**：`change_pixels × pixel_area_m2` |
| 8 | `geojson` | `str \| None` | `str \| None` | 不变；但内容语义变了（见 D-3） |
| 9-11 | `image_before_url` / `_after_url` / `_diff_url` | `str \| None` | `str \| None` | 不变 |
| 12 | `image_corners` | `list[list[float]] \| None` | 同 | 不变 |
| — | `status` | `str = "success"` | **移除** | 恒为 `"success"`，不携带信息；错误一律走 HTTP 状态码与 `ErrorResponse` |

**`status` 的移除 `v0.5.0` 落地**（`docs/contracts.md:219`；字段数 13 → 12 是相对 v0.3.0 的中间态，相对旧仓库则是 10 → 12）。三层同时守护该事实：`frontend/src/api/types.ts` 的 `@ts-expect-error`（字段被加回时转 `TS2578`）、`tests/contract/test_field_consistency.py:134` `test_status_is_absent_from_every_layer`、`:122` `test_detection_response_field_count`。

> **消费方迁移要点**：旧前端若读取 `resp.status` 判断成功与否，必须改为检查 HTTP 状态码——新版响应中该键**不存在**，读取得到 `undefined`，用 `=== "success"` 判成功会恒为假。

### 4.2 错误响应

旧仓促无统一错误模型：`HTTPException(500, detail=str(e))` 或框架默认的 `{"detail": [...]}`。新契约统一为 `{"detail": str, "code": str}`，12 个领域异常各自绑定状态码与 snake_case `code`（见 `docs/contracts.md` §9.5）。前端必须从「匹配 `detail` 文案」改为「按 `code` 分支」（`frontend/src/features/detection/errors.ts` 的层规约）。

### 4.3 GeoJSON 内容

同一字段名下的**内容语义发生变更**，这是本次迁移中最容易导致错误解读的一处：

| 项 | 旧语义 | 新语义 | 缺陷编号 |
|---|---|---|---|
| Feature 与 Region 的关系 | 每**环**一个 Feature | 每 **Region** 一个 Feature，多环合并进同一 Polygon（首环外环、其余内环） | D-3 |
| 属性归属 | Region 级 `pixel_count` / `area_m2` 复制给每个环 | Region 级属性每区只出现一次 | D-3 |
| 环顶点基准 | 像素中心（几何面积系统性偏小） | 像素角点格点（几何面积 ≡ `area_m2`） | Phase 2.1 发现项 |
| 坐标换算 | 由 anonymous 返回值顺序决定 | `lon = geo[0] + col·geo[1] + row·geo[2]`，`lat = geo[3] + col·geo[4] + row·geo[5]` | `docs/contracts.md:102` |
| 坐标系 | 引擎产出未转坐标；Python 侧 `_reproject_geojson` 兜底（CRS 解析失败则**静默返回原串**） | 仍为两步（引擎 → backend `io/reproject.py`），但 CRS 缺失改为显式 `CrsError`（400），不再静默兜底 | 旧 `services/detection.py:36-37` vs 新 `io/reproject.py` |

> 旧实现 `_reproject_geojson` 的 `except Exception: return geojson_str` 会把「坐标系无法解析」伪装成成功，返回一个坐标系错误的 GeoJSON；新实现显式抛 `CrsError`（400 / `crs_error`）。这是**刻意**剔除的静默兜底。

### 4.4 契约产物与门禁：从无到两段

| 段 | 旧 | 新 |
|---|---|---|
| ① pydantic → `docs/api/openapi.json` | 无 | `scripts/gen_openapi.py --check`（CI 步骤 18），字节级判据 |
| ② `openapi.json` → 前端 TS 类型 | 无（手写类型，与后端漂移） | CI 步骤 23「契约类型零漂移（openapi → TS）」（`ci.yml:295-307`），以重新生成 + 工作树比对实现，覆盖含类型变化的全部漂移形态 |
| 跨段三方一致 | 无 | `tests/contract/`（3 文件 9 用例） |

第二段是 Phase 6 新增，用于关闭 Phase 5 §11.1 登记的类型级漂移盲区；**该门禁已落地**（`docs/verification/phase-6.md` §6、§7）。`docs/contracts.md` §9.12 原文把同一件事写成「属遗留项」，该表述已于 `v1.0.0` 就地更正为「已落地」。

**Phase 5 遗留 → Phase 6 关闭**的迁移项（显式登记）：

| 遗留项 | 登记处 | 关闭方式与判据 | 状态 |
|---|---|---|---|
| 「openapi ↔ 生成类型」的类型比对缺失；openapi 已重生成而 TS 未重生成、仅类型变化时门禁可能放行 | `docs/verification/phase-5.md` §11.1（`docs/contracts.md:319` 引用为「§11.1」） | CI 步骤「契约类型零漂移（openapi → TS）」（`ci.yml:295-307`）：以入库 openapi 重新生成后比对工作树；判据为字节级而非字段名级，覆盖全部漂移形态 | **已关闭**（部署证据：Actions run `37192763321`；判别力证据：`phase-6.md` §7 变体 B——第一段正当放行时第二段仍变红） |

---

## 5. 缺陷修复对照（D 系列）

编号采用 `docs/algorithm.md` §8.1「旧仓库已确认的缺陷（D 系列）」的口径。**注意**：该表未收录 D-5，D-5 的定义取自 `docs/verification/phase-3.md` A.3 与 `backend/src/rschange/tests/test_architecture.py:54`；另有一套局部编号（见 §5.2）。

### 5.1 D-1 … D-9

| 编号 | 旧仓库落点 | 现象 | 根因 | 修复后行为 | 守护依据 |
|---|---|---|---|---|---|
| **D-1** | `src/core/src/bindings.cpp` | 2D 掩膜被当成 `W × W` 处理；非方形影像写出与读回的尺寸全错 | `mask.shape(2)` 在 2D 数组上不越界——nanobind 的 `shape` 与 `strides` 存放在**同一块**连续内存里，越界读到的是 `strides[0]`（其值恰等于列数）。长期不可见，因为基线样本是 256×256 **方形**，误差被 `H == W` 掩盖 | `parse_mask_shape()` 按 `ndim()` 显式分支：2D → `(H, W)`，3D → `(B, H, W)`，其余抛 `ValueError` | `engine/tests/test_raster_io.cpp:123`、`scripts/verify_bindings.py:100`、`docs/algorithm.md:1109-1125` |
| **D-2** | `src/core/src/stats.cpp` 的 Moore 邻域追踪 | 一个连通域的边界被劈成若干段互不相接的弧；基线圆盘样品产出 **2 条**弧 | 两处叠加：① 起点从未进入 `visited`（环回到起点时经 `n == start` 直接 return，`visited.insert(start)` 没机会执行），外层 raster-scan 遍历会再次起头；② 每步都从方向 0（正右）重新扫描，未把上一次的入射方向携带为扫描起点，等价于假定「上个像素永远在正左方」，遇到竖直段或凹角即折回 | 边图分解：成员像素朝向背景的每条边转为**有向**单位边，每条边恰用一次；「一域一环」是图的性质，不依赖扫描顺序 | `engine/tests/test_contour.cpp`、`test_pipeline.cpp:85`、`docs/algorithm.md:280-308` |
| **D-3** | `src/core/src/stats.cpp` 的 `regions_to_geojson` | **每环一个 Feature，却把 Region 级 `pixel_count` / `area_m2` 原样复制进每个 Feature**，属性面积被重复计 N 倍。基线样本：真实面积 `720900 m²`，输出合计 **`1441800 m²`**（虚报一倍） | 环与 Region 的层级关系没有被表达：多环本应属于同一 Polygon，旧实现却把它们并列为同级 Feature，导致 Region 属性随之复制 | 标准 GeoJSON 语义：**一个 Region 一个 Feature**；其 Polygon 以首条环为外环、其余为内环；Region 级属性每区只出现一次。基线两者的合计回到 `720900 m²` | `engine/tests/test_geojson.cpp:112`、`scripts/verify_baseline.py` §7.2（`720900.0` vs 旧引擎 `1441800.0`）、`docs/algorithm.md:905-915` |
| **D-4** | `src/core/src/tiff_io.cpp` | 每次调用读写都要重新注册一遍 GDAL 全驱动 | `GDALAllRegister()` 被放在访问路径上重复执行；`GDALDataset` 也未统一由 RAII 持有 | 一次性初始化（`ensure_gdal_initialized()`，`engine/src/gdal_init.cpp`）+ RAII 持有 `GDALDataset` | `engine/tests/test_raster_io.cpp:45`（经内部探针 `spatial::internal::gdal_registration_count()`）、`docs/contracts.md:156` |
| **D-5** | `src/backend/main.py:5-10`、`services/detection.py:11-16`（另有两个测试文件同类） | 同一段 DLL 路径解析 + `sys.path.insert` + `import _spatial` 被复制**四份**，且各自硬编码 `C:\Users\Hujian\DevCode\msys64\mingw64\bin` | 无分层概念，每个要用到引擎的模块自己引导一次；路径写死使仓库不可移植 | 收敛为 `backend/src/rschange/spatial/loader.py`（产品代码内唯一加载点），路径来自 `config.engine.build_dir` / `runtime_dll_dir`；`scripts/` 侧另有一份 `engine_env.py`，两侧**刻意互不导入**；`backend/` 内对 `msys64` / `C:/Users` 字面的扫描由测试守护 | `backend/src/rschange/tests/test_architecture.py:51`（G3.5）、`docs/verification/phase-3.md` A.3 |
| **D-6** | `src/core/src/stats.cpp` 的 `extract_regions` | 同一幅影像在不同标准库实现、不同编译选项下得到不同的 `label` 顺序；GeoJSON 无法逐字节比对 | 像素按根标签塞进 `std::unordered_map<int, Region>` 再遍历赋 1、2、3……`unordered_map` 的迭代顺序由哈希桶布局决定，标准不保证可重现 | 「扫描顺序即首次出现顺序」：Pass 2 沿 raster-scan 走一遍，用 `root → regions 下标` 槽位表在每个连通域的**第一个像素处**登记 | `engine/tests/test_labeling.cpp:85`、`test_multi_region.cpp`、`docs/algorithm.md:127-136` |
| **D-7** | `src/core/src/stats.cpp` 的 `extract_boundary` / `regions_to_geojson` | 退化轮廓的处理语义含糊：边界不满足条件的输入返回 `{{}}`（一个含空环的容器），调用约定不清楚；且只覆盖了「顶点少于 3」，未覆盖「顶点全部共线」——后者产出的零面积多边形交给 GEOS 会直接判 invalid | 缺少把「什么样的几何不能进 GeoJSON」写成一条可判定规则 | 只剩**一种**退化情形：**成员像素少于 3 个**（轮廓层返回空 `Boundary`，既不产 Feature 也不抛异常）；`forms_polygon()` 保留顶点数 ≥ 3 与 `signed_area_twice != 0` 两条判据。像素角点基准确立后，共线判据转为**防御性**（任何 ≥3 像素的 4 连通分量都能围出正面积环） | `engine/tests/test_contour.cpp:201`、`test_geojson.cpp:217`、`docs/algorithm.md:917-952` |
| **D-8** | `src/core/src/stats.cpp` 的 `simplify_boundary` / `dp_recurse` | 闭合环的简化结果**随起始像素变化**；顶点数随容差增大**非单调**（实测 1.5→4 点、4.0→8 点） | 把开曲线 Douglas-Peucker 直接套在闭合环上：递归的首锚点取的是一个任意起点且在递归过程中被删除 | 规范化起点 + 三锚点切分；并保留「容差非正即短路返回」分支，使容差 0 时面积精确守恒由**构造**保证而非浮点巧合 | `engine/tests/test_simplify.cpp:159`、`docs/algorithm.md:880-897` |
| **D-9** | `src/core/include/spatial/stats.hpp` 的 `Region` | C++ struct 里面积字段写作 `are_m2`（拼写残缺），而 GeoJSON `properties` 里又被写成正确的 `area_m2`，同一概念两个名字 | 命名未收敛；手写序列化处各写各的 | 统一为 `area_m2` | `engine/include/spatial/region.hpp:28`（注释明记 D-9）、`docs/contracts.md:100`（`properties` 恰三项，禁改名） |

### 5.2 编号口径冲突（须注意）

仓库内存在第二套局部编号，与 `algorithm.md` §8.1 **部分不兼容**：

| 编号 | `docs/algorithm.md` §8.1 口径 | `app.py:121` / `contracts.md:266` / `phase-3.md` 口径 |
|---|---|---|
| D-1 | 2D 掩膜尺寸解析 | CORS 通配符与凭据并存 |
| D-2 | 边界追踪 visited | 生产代码残留 `print` |
| D-3 | 每环一个 Feature（**一致**） | 每环一个 Feature（**一致**） |
| D-5 | （未收，见上表） | DLL 路径解析点（**一致**） |
| D-6 | `unordered_map` 迭代序（**一致**） | `unordered_map` 迭代序（**一致**） |
| D-7 | 退化轮廓处理 | 异常信息外泄 |

本文 §5.1 采用 `algorithm.md` §8.1 口径。**两套编号并存属「作用域不同」，不是同一事实的两种说法**：`algorithm.md` §8.1 的 `D-1…D-9` 记 **C++ 引擎**缺陷；`phase-3.md` §3 的 `D1…D7` 记**后端分层**缺陷；`spatial/__init__.py` docstring 的「附录 D-5」是**架构条目**，与缺陷无关。该作用域划分已写入 `docs/algorithm.md` §8.1 的「编号口径（本节即权威）」引用块（`v1.0.0`），引用时写全来源文档名即可，**无需**强行统一编号。

> 上表「第二套口径」中的三项也确实已修复并可独立核验：CORS（`app.py:126-132` + `config.py` `_reject_wildcard`）；无残留执行语句 `print`（`docs/verification/phase-3.md` A.2 实测 0 命中）；异常不外泄（`api/errors.py:102-127`，`phase-3.md` A.4 附真实响应体）。

---

## 6. 能力对照（旧 `GEO_CAPABILITIES.md` 的 5 项）

原文把这 5 项称为「可被 Agent 调用的 geo 能力清单」，并为每项给出「是否需改造才能进工具箱」的判断。下表给出旧原文判断与新仓库的实际落点。

| # | 能力 | 旧入口 | 原文「Agent 可调用性」判断 | 新仓库落点 | 判断在新仓库是否仍成立 |
|---|---|---|---|---|---|
| 1 | 读取栅格 | `_spatial.read_raster(path)` → `(array, w, h, bands, geo, proj)` | ❌ 需改造：输入是路径 ✓，输出是 numpy 二进制 → Agent 看不懂 | `engine/bindings/module.cpp` 的 `read_raster`；backend 侧封装为返回**具名** `Raster` 的 `spatial/raster.py:read_raster`；加载点收敛为 `spatial/loader.py` | **仍成立**：返回仍是 numpy。但「六元组」改为具名字段（`Read` 位置不再靠下标），可读性显著提高；真正让它进工具箱仍需上层包一层 JSON |
| 2 | 写入栅格 | `_spatial.write_raster(path, mask, geo, proj)` | ❌ 需改造：掩码须来自上游计算，管道末段才有意义 | `bindings/module.cpp` 的 `write_raster`（新增 `MaskShape` 维度解析、`nb::ro`、`nb::noconvert`）；backend `spatial/raster.py:write_raster` | **仍成立，且使用面更窄**：生产流水线**不调用**它，唯一调用方是 `tests/test_pipeline.py`（`_work/p7/new-arch-digest.md` B3） |
| 3 | mask → GeoJSON | `_spatial.mask_to_geojson(mask, geo)` → GeoJSON 字符串（**源坐标系**） | ❌ 半成品：输出已是文字 ✓，但坐标系未统一 | 引擎侧 `labeling/contour/simplify/geojson` 四模块；重投影仍在 `io/reproject.py::reproject_geojson` | **仍成立（刻意保留两步）**：原文设想的「合并为一个完整能力」在新架构中**未**合并；但失败模式由「静默返回原串」改为显式 `CrsError`（400） |
| 4 | CVA 变化检测 | `cva_detect(before, after)` → `(threshold, mask)` | ❌ 需改造：输入输出都是 numpy | `detectors/cva.py::CvaDetector.detect` → `DetectionResult(mask, threshold)`；另有抽象在于 `detectors/base.py` 协议 + `registry.py` 注册表 | **仍成立**（数组进出），但已具备按名装配的能力；参数仍不可调（`HISTOGRAM_BINS = 256` 为模块常量） |
| 5 | 后处理去噪 | `postprocess(mask, min_size=30)` | ❌ 需改造：纯数组进出；但 `min_size` 是数字参数 → 适合做成「可调旋钮」 | `postprocess/morphology.py::MorphologyPostprocessor.apply`；`min_size` 与 `structure_size` 提为构造参数，来源 `config.postprocess` | **针对「可调旋钮」一条已闭环**：两个旋钮均可通过 TOML / `RSCHANGE_POSTPROCESS__MIN_SIZE` 调节 |

### 6.1 新仓库新增、旧清单未列出的能力

| 能力 | 落点 | 说明 |
|---|---|---|
| GDAL 初始化幂等化 | `ensure_gdal_initialized()`（`engine/src/gdal_init.cpp`） | D-4 的直接产物；旧仓库无对应 |
| 统一的 `_spatial` 加载点 | `backend/src/rschange/spatial/loader.py::load_extension` | D-5 的直接产物；旧仓库该逻辑复制四份 |
| 掩膜入参严格模式 | `nb::noconvert()`（`bindings/module.cpp`） | 禁止隐式转换，拦住「浮点幅度图误当掩膜」的静默错误路径 |
| 影像四角经纬度 | `io/reproject.py::image_corners` | CODE_MAP 有此函数，GEO_CAPABILITIES 未列为能力 |
| 预览图渲染 | `io/preview.py::save_rgb_png` | 同上；新仓库把它从编排层移出，成为独立可测模块 |
| 契约机器可读形态 | `docs/api/openapi.json` + 前端生成类型 | 完全新增，见 §4.4 |

### 6.2 原文「待盘点」项的处置

原文第 2 层（HTTP）与最终汇总均为未勾选的 checkbox。新仓库已补齐：端点、请求约束、响应 schema、错误码体系、上传上限、目录穿越防护、CORS、可插拔约定、契约产物与漂移检测，全部写入 `docs/contracts.md` §9。

---

## 7. 未迁移 / 有意舍弃项

### 7.1 未迁移（逐条理由）

| 旧条目 | 处置 | 理由 |
|---|---|---|
| `src/core/src/remote-sensing/sensing.ipynb` | **未迁移** | 位于 `core/src` 之下的孤立 notebook，`CODE_MAP.md` 从未提及它；它不是产品链路的一部分。**待核实**：新仓库存在空的顶层 `notebooks/` 目录，是否作为其承接位置未见任何文档声明 |
| `src/core/include/nlohmann/json.hpp` | **删除**（改 FetchContent） | 第三方单头文件随源码入库会使 license 与升级不可审计；改为构建期拉取并锁定 v3.11.3 |
| `src/core/tests/preview.png`、`change_mask.tif` | **删除** | 手工生成的中间产物，未被任何判据引用；新仓库的 `.raw` + `.json` 夹具对由 `scripts/make_multi_region_fixture.py` 可重生成，属「法定夹具」而非残留 |
| `src/frontend/public/test.geojson` | **删除** | 前端写死的测试矢量，有独立于契约漂移的风险；新仓库的前端夹具改由 `src/test/fixtures.ts` 与契约逐字段对齐 |
| `src/frontend/src/assets/hero.png`、`vite.svg` | **删除** | 属 Vite 脚手架与装饰资源，非产品资产 |
| `Debug_lesson.txt`、`project2-lessons-and-interview.txt` | **已迁入** `docs/lessons/` | `docs/lessons/{README.md,debug-lessons.md,interview-notes.md}`：13 条教训逐条整理为「现象 / 根因 / 修复 / 新仓库落点 / 复发判据」，面试话术单列 `interview-notes.md`（详见 §2.5）。旧仓库这两个源文件随归档 tag `archived-2026-09-18` 永久保留 |
| `requirements.txt` | **替换** | 由 uv workspace + `uv.lock` 取代；7 包无钉被 9 个带约束的运行依赖替代，`rasterio` 降为可选 extra |
| 根级 `Dockerfile.backend` / `docker-compose.yml` 与 `src/frontend/` 下的 `Dockerfile.frontend` / `nginx.conf` | **重新落位** | 部署文件横跨两级目录是结构债；统一收敛到顶层 `docker/` |

### 7.2 `DOCKER_PLAN.md` 计划 vs 实际的差异（已在 Phase 6 纠正）

| 计划条目 | 旧仓库实际落地 | 新仓库处置 |
|---|---|---|
| runtime 阶段 GDAL 用 `libgdal34`（只装运行时） | **偏离**：用了 `libgdal-dev`（编译期包） | 改为逐个尝试 `libgdal36…libgdal32`，**禁止**退回 `-dev`；由 `verify_containers.py` 静态判据守护 |
| Python 版本 | 定为 3.12（计划曾问「3.12 可以吗」） | 全链路 3.14.6 单一版本，含容器与 CI |
| 五个待改文件的 `os.add_dll_directory` nt 守卫 | 旧 `main.py` 与 `services/detection.py` **确实**加了守卫，但路径仍硬编码 | 守卫连同整个逻辑被删除——取而代之的是「不在产品代码里出现机器路径」（G3.5） |
| nginx `client_max_body_size` | **缺失**，依赖默认 1 MB（即后来的 A5/上传上限缺陷） | `docker/nginx.conf` 声明 `500m`，与 `runtime.max_upload_mb` 同号，由 `verify_containers.py` 三方对齐判据守护 |
| `compose` 的服务启动顺序 | `depends_on: backend`（只等启动，不等健康） | `depends_on: condition: service_healthy` + backend healthcheck |
| 数据卷 | `./data:/app/data`（bind mount） | 命名卷 `rschange-data:/app/data` |

### 7.3 有意舍弃的能力

| 能力 | 舍弃决定 | 依据 |
|---|---|---|
| **地图渲染** | 旧仓库的 `README.md:7` 仍把「MapLibre GL JS」写进技术栈，但旧 `src/frontend/package.json` 已无该依赖、`src/frontend/src/` 下亦无 `MapView` 等组件 —— 即**旧仓库执行阶段就已删除**。新仓库同样不引入地图库（`dependencies` 仅 `lucide-react` / `react` / `react-dom` / `react-dropzone`） | 旧 `project2-lessons-and-interview.txt` 第（7）条明确记为此举：「地图方案弃用后…全是死代码，留着会拖累 `tsc` 构建，果断删除」。`image_corners` 仍作为契约字段保留，供将来接入地图时定位（该缺口已登记为 `docs/verification/phase-6.md` O3） |
| **写出中间 GeoTIFF 产物** | 引擎能力（`write_raster`）与后端封装均保留，**但生产流水线不调用** | 编排层只写三张 PNG；唯一调用方是测试。`docs/verification/phase-6.md` 未将其列为未关闭项 |
| **算法 /  detectors 的 HTTP 选择参数** | 未实现 | `UnknownDetectorError` 已定义并纳入契约，但请求层暂不暴露算法名；多算法切换走代码层注入 |
| **定量精度评估（IoU 等）** | 未实现 | 旧仓库 interview 文档已自承「精度指标后续可以补一个评估模块」；新仓库同样未做，不在本次迁移范围内 |

---

## 8. 迁移后如何验证

### 8.1 一条命令的回归入口

```bash
uv run python scripts/verify_baseline.py --phase 6
```

该命令输出《重构方案》§7.1 / §7.2 / §7.3 三组判定。其中直接锚住本次迁移成果的关键判据：

| 判据 | 期望值 | 对应缺陷 |
|---|---|---|
| Otsu 阈值 | `5.9168` | 行为未漂移 |
| 变化像素 | `7209 / 65536` | 行为未漂移 |
| `changed_area_m2` | `720900.0 m²` | **D-3**（旧值 `1441800.0`） |
| GeoJSON Feature 数 | `1`（旧实现 `2`） | **D-2** + **D-3** |
| 属性面积合计 | `720900.0 m²`（旧实现 `1441800.0`） | **D-3** |
| `multi_region_mask` label 序列 | `[100, 200, 35, 138, 185, 5]` 的 **raster-scan 首现序**（`label` 为 `1..6`） | **D-6** |
| `multi_region_mask` Feature 数 | `6`（含被旧实现整条剔除的一像素宽矩形） | **D-7** + Phase 2.1 几何基准 |
| 几何面积 == 上报面积 | 偏差 `0.00 %`（上限 `1e-6 %`，由 `shapely` 独立计算） | Phase 2.1 几何基准 |

### 8.2 分工明确的其余四个脚本

| 命令 | 管什么 | 判据数 |
|---|---|---|
| `uv run python scripts/verify_bindings.py` | 绑定层接口契约（函数齐备、写读一致、异常类型、掩膜类型与布局严格性） | 42 |
| `uv run python scripts/verify_config.py` | 配置 ↔ CMake 预设 ↔ 本机模板三者一致 | 6 |
| `uv run python scripts/verify_version.py` | 版本号单一真相源（含 `rschange.__version__`、前端 `package.json`、根 `pyproject.toml`、`openapi.json` 的 `info.version`） | 5 |
| `uv run python scripts/verify_containers.py` | 容器化资产静态门禁（明确**不**替代真实构建） | 19 |

### 8.3 分层证据指向

| 想确认的事 | 去看 |
|---|---|
| 引擎算法是否零回归 | `ctest --test-dir engine/build/<preset> --output-on-failure`（40/40）；证据 `docs/verification/phase-6.md` §9 表 D 行 |
| 分层依赖与可插拔是否守住 | `backend/src/rschange/tests/test_architecture.py`（7 用例）；证据 `docs/verification/phase-3.md` §4 / §5 |
| HTTP 契约是否一致 | `tests/contract/`（3 文件 9 用例）+ `tests/api/test_upload_acceptance.py`；证据 `docs/verification/phase-5.md` §10、phase-6.md §9 表 B/C 行 |
| 契约产物是否漂移 | `scripts/gen_openapi.py --check` 与 CI 第二段门禁；证据 `docs/verification/phase-6.md` §6 / §7（含变异实验） |
| Phase 1 的「缺陷未修复」原始状态 | `docs/verification/phase-1.md`（若要复现旧行为，须把 `engine.build_dir` 指回旧构建产物，并使用 `--phase 1`） |
| 每个阶段的具体出口门 | `docs/verification/phase-{1,2,2.1,3,3.1,4,5,6}.md` |

### 8.4 与 CI 对齐

CI 的「仓库自检脚本」步骤按顺序跑 `verify_baseline.py --phase 6` → `verify_bindings.py` → `verify_config.py` → `verify_version.py` → `verify_containers.py`（`.github/workflows/ci.yml` step 19）。本地验证应与该顺序取值完全一致，尤其是 `--phase 6`——**不要**沿用旧 README 的 `--phase 1`。

---

## 9. 待核实项

| # | 事项 | 现状 |
|---|---|---|
| 1 | D 系列编号存在两套口径（D-1 / D-2 / D-7 在 `algorithm.md` §8.1 与 `app.py:121`、`contracts.md:266`、`phase-3.md` 之间碰撞） | **已关闭**：定性为「作用域不同」而非冲突——§8.1 的 `D-1…D-9` 记 C++ 引擎缺陷、`phase-3.md` §3 的 `D1…D7` 记后端分层缺陷、`spatial/__init__.py` docstring 的「附录 D-5」是架构条目。划分已写入 `docs/algorithm.md` §8.1 的「编号口径（本节即权威）」引用块；本文 §5.1 采用 §8.1 口径 |
| 2 | `src/backend/tests/test_cva.py` 的具体内容 | 仅知其存在（旧 `src/` 文件树）；`legacy-digest.md` 未提炼其用例 |
| 3 | 旧仓库 `src/frontend/Dockerfile.frontend` 的内容 | `legacy-digest.md` 明确记录「本次任务未读取其内容」 |
| 4 | 旧 `src/core/src/bindings.cpp` 是否有除 D-1 之外的中间形态（例如 `nb::noconvert` 何时加入） | `algorithm.md` §8.2 记为「Phase 2 新发现」，即 `noconvert` 属重构期新增而非旧仓库修复；**未**回旧仓库逐版核对 |
| 5 | 新仓库顶层空目录 `notebooks/` 是否承接旧 `sensing.ipynb` | 目录存在且为空；无任何文档声明其用途 |
| 6 | 旧 `project_graph/`、`api_tests/`、`build/`、`data/` 四个根目录 | 属生成物与调试辅助，未纳入 `src/` 52 文件统计，本次未逐一核实其与新仓库的对应关系 |

---

*本文在**只读**前提下撰写：未对任一仓库执行 git 命令，未在仓库内创建、修改或删除文件。*
