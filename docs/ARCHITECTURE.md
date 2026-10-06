# rschange · 架构说明

> **适用对象**：需要在本仓库上做二次开发、代码审查或阶段验收的读者。
> **本文定位**：描述**系统如何分层、请求如何流动、约束由谁守护**。算法细节与 HTTP 契约不在此展开。
>
> **权威分工（本文不越界，也不与它们重复）**
>
> | 主题 | 权威文档 | 本文处理 |
> |---|---|---|
> | 空间引擎算法：几何基准、边图分解、闭曲线 DP、缺陷成因 | `docs/algorithm.md`（1362 行） | 只引用结论，不复述推理 |
> | 引擎绑定（`_spatial`）与 HTTP 接口契约 | `docs/contracts.md`（333 行） | §5 给概览与指向 |
> | 如何新增算法 / 后处理器（完整代码级步骤） | `docs/DEVELOPMENT.md` | §6 给机制说明与文件清单 |
> | 旧仓库 → 本仓库的文件级对照 | `docs/MIGRATION.md` | 不重复 |
> | 各阶段验收证据 | `docs/verification/phase-{1,2,2.1,3,3.1,4,5,6}.md` | 引用其中数字；Phase 7 为 `phase-7.md` |
>
> **事实来源纪律**：本文每条论断标注 `文件:行号` 或上述权威文档的章节。凡未在仓库内取得证据的条目，在 §9 显式标 `待核实`，不得含糊带过。

---

## 1. 系统全景

系统由三层语言栈构成：TypeScript 前端、Python 后端包 `rschange`、C++ 空间引擎。三层之间只有**两道窄接口**：前端与后端之间是 HTTP `/api/*`；后端与引擎之间是 nanobind 扩展模块 `_spatial` 的四个函数。

```text
═══════════════════════════════════════════════════════════════════════════════
 前端   frontend/          React 19 · TypeScript ~6.0.2 · Vite 8 · Tailwind v4
───────────────────────────────────────────────────────────────────────────────
        App.tsx → ErrorBoundary → features/detection/DetectionPage
        features/detection/hooks/useDetection.ts   状态机 idle→loading→success|error
        api/client.ts        detectChange()  FormData{before, after} → POST /api/detect
        api/types.ts  ←  转发 api/generated/data-contracts.ts（OpenAPI 生成，禁手写）
═══════════════════════════════════════════════════════════════════════════════
                                      │
                                      │  HTTP /api/*
                                      │  dev: vite proxy → :8000；容器: nginx 反代
                                      ▼
═══════════════════════════════════════════════════════════════════════════════
 后端   backend/src/rschange/                      依赖方向：自外向内，单向无环
───────────────────────────────────────────────────────────────────────────────
  api/            HTTP 边界层
        app.py       create_app()        ★唯一装配入口；app.state.rschange = RuntimeContext
        deps.py      build_context()     ★协议与实现的唯一接合处              (:53-76)
        errors.py    install_exception_handlers()  ★异常不外泄的唯一实现处
        routers/detection.py             POST /api/detect · GET /api/image/{filename}
        schemas/detection.py             DetectionResponse（12 字段）· ErrorResponse
                      │  Depends(get_context)
  pipeline/        用例编排层
        change_detection.py   detect_change()   七步编排，运行期不认具体算法
        _read_pair → _validate_pair → _detect → _clean → _write_previews
                                    → _vectorize → _assemble
                      │
                      ├── 注入 ────►  detectors/ · postprocess/（运行期不 import 二者）
                      ├── 直调 ────►  io/
                      └── 直调 ────►  spatial/
  detectors/        变化检测算法层（可插拔）◄── 注入 ChangeDetector
        base.py       ChangeDetector（Protocol + runtime_checkable，非抽象基类）
        registry.py   register / available / resolve（存实例，不存类）
        cva.py        CvaDetector   name="cva"
  postprocess/     掩膜后处理层（可插拔）◄── 注入 MaskPostprocessor
        base.py       MaskPostprocessor（Protocol）
        morphology.py MorphologyPostprocessor   name="morphology"  本层无注册表
  io/              产物层：backend 内唯一 import PIL / pyproj 处
        preview.py    save_rgb_png()             （PNG 预览图）
        reproject.py  reproject_geojson() / image_corners()   （pyproj → EPSG:4326）
  spatial/         对 C++ 扩展的唯一访问点
        __init__.py   PEP 562 模块级 __getattr__，延迟提供符号
        raster.py     Raster / read_raster / mask_to_geojson / write_raster
        loader.py     load_extension()  ★backend 产品代码内唯一 import _spatial 处
  config.py · logging.py · errors.py        叶层：仅三者可互相依赖
═══════════════════════════════════════════════════════════════════════════════
                                      │  nanobind ABI（cp314）
                                      ▼
═══════════════════════════════════════════════════════════════════════════════
 绑定   engine/bindings/module.cpp    NB_MODULE(_spatial)
───────────────────────────────────────────────────────────────────────────────
        只做类型转换与参数校验，禁止多分支业务逻辑；nb::noconvert + nb::ro
        read_raster / write_raster / mask_to_geojson / print_gdal_version
                                      │  链接
                                      ▼
═══════════════════════════════════════════════════════════════════════════════
 引擎   libspatial                    engine/include/spatial/ + engine/src/
───────────────────────────────────────────────────────────────────────────────
        raster_io.cpp   GDAL 读写（一次性初始化由 gdal_init.cpp 承担，D-4 修复点）
        labeling.cpp    Two-Pass 连通域，4 邻域，raster-scan 首现顺序
        contour.cpp     沿像素边界追踪（crack following）
        simplify.cpp    闭曲线 Douglas-Peucker，容差非正即短路
        geojson.cpp     Region 列表 → GeoJSON FeatureCollection
        gdal_init.cpp · version.cpp
        target：spatial（SHARED）+ spatial_static（STATIC，仅供测试）
                                      │
                                      ▼
═══════════════════════════════════════════════════════════════════════════════
 GDAL 3.12.3           Windows: MSYS2 MinGW-w64    Linux: libgdal-dev
═══════════════════════════════════════════════════════════════════════════════
```

**依赖方向单向、无环**（`backend/src/rschange/__init__.py:5-22` 声明，`docs/contracts.md:12`、`docs/algorithm.md:44-45` 复述）：

```text
backend → _spatial（nanobind 绑定层）→ libspatial（引擎核心）→ GDAL
```

**禁止**反向依赖；**禁止** backend 绕过 `_spatial` 直接加载 `libspatial.dll`（`docs/contracts.md:14`）；**禁止** backend 改 `_spatial` 的函数签名（`docs/algorithm.md:44`、`docs/contracts.md` §8 禁止事项）。

---

## 2. 目录职责对应表

### 2.1 前端 `frontend/src/`

| 层 | 路径 | 职责 | 关键文件 |
|---|---|---|---|
| 挂载 | `main.tsx` | 挂载 `#root`，缺失即抛错 | `main.tsx` |
| 应用根 | `App.tsx` | 页面语义、布局、错误边界；业务状态不在此层 | `App.tsx` |
| 功能页 | `features/detection/` | 承载该功能的**全部**状态与编排 | `DetectionPage.tsx` |
| 状态机 | `features/detection/hooks/` | `idle→loading→success/error`；不引入 TanStack Query | `useDetection.ts` |
| 契约类型 | `api/types.ts` | **契约类型的唯一入口**，纯转发别名，不含手写字段 | `types.ts`（`@ts-expect-error` 固化「`status` 已移除」，`docs/verification/phase-5.md` A.1 记为 52-53 行） |
| 生成产物 | `api/generated/data-contracts.ts` | 由 `openapi.json` 生成，带 `// @ts-nocheck`，**禁手改** | `swagger-typescript-api` |
| HTTP 客户端 | `api/client.ts` | 基址取相对路径 `/api`（**禁止**硬编码主机名）；错误体 `{detail, code}` | `client.ts` |
| UI 原语 | `components/ui/` | 与业务无关的可复用原语，统一由 `index.ts` 导出 | `Button / Card / Skeleton / Spinner / StatRow / ErrorBoundary` |
| 展示格式化 | `features/detection/format.ts` | 纯函数；不用 `toLocaleString` 做单位换算 | `format.ts` |
| 错误映射 | `features/detection/errors.ts` | **必须按 `code` 分支**，禁止匹配 `detail` 文案 | `errors.ts` |
| 设计令牌 | `styles/index.css` | Tailwind v4 `@theme`；组件**禁止**写 `bg-gray-100` 这类字面色值 | `index.css` |

### 2.2 后端 `backend/src/rschange/`

| 分层 | 路径 | 一句话职责 | 关键文件与位置 |
|---|---|---|---|
| HTTP 边界 | `api/` | 路由、装配、schema、异常映射；**禁止**业务编排、算法细节、直接接触 `_spatial` | `app.py:92-140` `create_app()`；`deps.py:53-76` `build_context()`；`errors.py:158-163` 注册顺序；`routers/detection.py:137/217`；`schemas/detection.py:56-74` |
| 用例编排 | `pipeline/` | 七步串联，**运行期不 import** 算法层 | `change_detection.py:298-304` `detect_change()`；七步函数 `:128/145/175/194/209/245/262` |
| 检测算法 | `detectors/` | 可插拔算法 + 注册表 | `base.py`（`Protocol` + `@runtime_checkable`）；`cva.py:105` `CvaDetector`；`registry.py`（`DEFAULT_DETECTOR="cva"`） |
| 掩膜后处理 | `postprocess/` | 可插拔后处理（**无**注册表） | `base.py`；`morphology.py:50` `MorphologyPostprocessor` |
| 产物 IO | `io/` | 预览图渲染、GeoJSON 重投影；backend 内**唯一** `import PIL` / `import pyproj` 处 | `preview.py`（`save_rgb_png`）；`reproject.py`（`reproject_geojson` / `image_corners`） |
| 空间访问 | `spatial/` | 对 `_spatial` 的唯一访问点 | `__init__.py`（PEP 562 `__getattr__`）；`loader.py:112-134`；`raster.py`（`Raster` / `read_raster` / `mask_to_geojson`） |
| 叶层 | `config.py` `logging.py` `errors.py` | 分层配置 / 结构化日志 / 领域异常 | `config.py:229-245` 来源优先级；`logging.py:20`（不 import `config`，免循环）；`errors.py` 12 个异常类 |

> **归属表更正**：`docs/algorithm.md:52-54` 的 §0 归属表曾把「CVA / Otsu / 后处理」的状态定格为「待迁入 `backend`（Phase 3）」。该表述已在 `v1.0.0` 就地更正为实际落点：`detectors/cva.py`（含模块级 `histogram` / `otsu_threshold`）与 `postprocess/morphology.py`，经 `registry` 的 `DEFAULT_DETECTOR` 与 `api/deps.py` 的 `build_context()` 默认装配。更正**只改表格单元内容、未增删行**，故该表行号仍是 52-54。本文 §2.2 与代码一致。

### 2.3 引擎 `engine/`

| 路径 | 职责 | 备注 |
|---|---|---|
| `CMakeLists.txt` | `project(spatial VERSION 0.2.0)`，C++20；target `spatial`(SHARED) / `spatial_static`(STATIC，仅供测试) / `_spatial` | 第三方经 FetchContent：`nlohmann/json` v3.11.3、`Catch2` v3.7.1 |
| `CMakePresets.json` | 预设 `base` / `win-base` / `linux-base`（hidden）+ `dev-win` / `dev-linux` / `release-win` / `release-linux`（configure/build/test 各 4 个） | `version: 6`，`cmakeMinimumRequired 3.24`；本机额外预设 `CMakeUserPresets.json` 不入库 |
| `include/spatial/export.hpp` | `SPATIAL_API` 宏的**唯一定义点**（导出 / 导入 / 空三态） | nanobind 全局 `-fvisibility=hidden`，故必须显式导出 |
| `include/spatial/region.hpp` | `PixelCoord{row,col}`、`Region{label,pixel_count,area_m2,pixels}`、`std::hash<PixelCoord>` | `region.hpp:28`：字段名统一为 `area_m2`（D-9） |
| `include/spatial/raster.hpp` | `RasterData`、`ensure_gdal_initialized()`、`read_raster()`、`write_raster()` | D-4 修复点 |
| `include/spatial/labeling.hpp` | `extract_regions(mask, w, h, geo) -> vector<Region>`，4 邻域，raster-scan 首现顺序 | D-6 修复点 |
| `include/spatial/contour.hpp` | `Boundary{outline, holes}`、`extract_boundary(pixels)` | D-2 修复点；几何基准为像素角点格点。**注意**：实现是「沿像素边界追踪（crack following）」，不是 Moore 邻域扫描（`contour.cpp:2`、`algorithm.md:276`、§3.3），README 首句的「Moore」措辞已过时 |
| `include/spatial/simplify.hpp` | `point_line_distance()`、`simplify_boundary(ring, tolerance)`，容差非正即短路 | D-8 修复点 |
| `include/spatial/geojson.hpp` | `GeoJsonOptions{simplify_tolerance = 0.0}`、`regions_to_geojson(...)` | D-3 / D-7 修复点 |
| `bindings/module.cpp` | `NB_MODULE(_spatial)`；只做类型转换与参数校验，**不得**含多分支业务逻辑 | 四个公开函数，`docs/contracts.md` §3 |
| `src/internal/gdal_registry.hpp` | 测试专用探针 `gdal_registration_count()`；不安装、不进 DLL 导出表 | 测试链接 `spatial_static` 才能读到 |
| `tests/` | 7 个 Catch2 文件，**40** 个 `TEST_CASE` | 夹具经编译期宏 `SPATIAL_TEST_FIXTURE_DIR` 注入 |

### 2.4 仓库工具与配置

| 路径 | 职责 | 关键事实 |
|---|---|---|
| `scripts/engine_env.py` | **脚本侧**的配置读取与 `_spatial` 装载（`load_config` / `resolve_path` / `load_spatial` / `fixtures_dir`） | 与 `backend` 侧**刻意互不导入**（`config.py:12-16` 声明），详见 §4.4 |
| `scripts/gen_openapi.py` | 冻结 / 校验 `docs/api/openapi.json`（`--check` 逐字节比对） | 契约第一段门禁载体，见 §5 |
| `scripts/verify_baseline.py` | 黄金基线 `§7.1 / §7.2 / §7.3`；内置与 `rschange` 完全独立的 FROZEN REFERENCE v0 | `--phase`：`1` = 期望 §7.2/7.3 失败；`>=2` = 全通过（`:191-196`、`:589`） |
| `scripts/verify_bindings.py` | 绑定层契约 **42** 项 | 与 `verify_baseline` 分工：接口 vs 语义 |
| `scripts/verify_config.py` | 配置一致性 **6** 项 | `default.toml` ↔ CMake 预设；模板示例值 ↔ `default.toml`；`legacy_*` 必须为空 |
| `scripts/verify_version.py` | 版本号 **5** 项 | 真相源 = `backend/pyproject.toml` |
| `scripts/verify_containers.py` | 容器化资产静态门禁 **19** 项（`docs/verification/phase-6.md` §4） | 明确**不**替代真实构建 |
| `scripts/bootstrap.{sh,ps1}` / `clean.{sh,ps1}` / `gen-api-types.{sh,ps1}` | 环境引导（7 步）、清理、前端类型生成 | bootstrap 幂等；clean **不**清 `.venv` |
| `config/default.toml` | 入库配置（`runtime` / `engine` / `logging` / `postprocess` / `baseline`） | 优先级 `RSCHANGE_<SECTION>__<KEY>` > `config/local.toml` > `config/default.toml` |
| `tests/`（仓库根） | HTTP 契约与端到端：`tests/contract/`（3 文件）· `tests/api/`（1 文件） | 根级与 backend 级 conftest 作用域不互通（`tests/conftest.py` docstring） |

> **计数口径提示**（`_work/p7/new-arch-digest.md` B4）：40 = Catch2 `TEST_CASE` 数；42 = `verify_bindings.py` 判据数；19 = `verify_containers.py` 判据数；6 / 5 = `verify_config` / `verify_version` 判据数。四者不同源，**禁止**并列混用。

---

## 3. 数据流：一次 `POST /api/detect`

下表按执行顺序逐步给出落点。步骤 1-3 在前端与网络层，4-10 在 HTTP 边界，11-32 在编排与下层，33-34 为异常与渲染路径。

| # | 位置 | 动作 |
|---|---|---|
| 1 | `frontend/src/features/detection/hooks/useDetection.ts` `detect()` | `runIdRef` 递增做竞态保护，`status='loading'` |
| 2 | `frontend/src/api/client.ts` `detectChange()` | 构造 `FormData`（字段名恰为 `before` / `after`）；非 2xx → 解析 `{detail, code}` 抛 `ApiError`；网络失败 → `NetworkError` |
| 3 | 网络层 | dev：`vite.config.ts` `server.proxy['/api'] → http://localhost:8000`；容器：`docker/nginx.conf` `location /api/` → `http://backend:8000`（`proxy_pass` 不带尾斜杠以保留 `/api`） |
| 4 | `api/app.py:109-134` | 应用已由 `create_app()` 装配：`app.state.rschange = RuntimeContext`（`:117`）、异常处理器（`:119`）、CORS（`:126-132`）、路由挂载前缀 `/api`（`:134`） |
| 5 | `api/deps.py:79-87` `get_context()` | 从 `app.state.rschange` 取 `RuntimeContext`；缺失抛 `RuntimeError`（属装配期缺陷） |
| 6 | `api/routers/detection.py:143-144` | 两期文件后缀校验 → 不合白名单抛 `UnsupportedFormatError`（400） |
| 7 | `api/routers/detection.py:157-158` → `_save_upload()`（`:72-97`） | 按 `_CHUNK_BYTES = 1 MiB`（`:58`）边收边计；超限抛 `UploadTooLargeError`（413）并 `unlink` 半成品；两文件同批清理（`:159-163`） |
| 8 | `api/routers/detection.py:147-154` | `job_id = uuid.uuid4().hex`；统一落盘为 `uploads/{job_id}_before.tif` / `_after.tif` |
| 9 | `api/routers/detection.py:172-177` | 构造 `DetectionRequest`（`job_id` 与产物目录**显式给出**，不从文件路径反推） |
| 10 | `api/routers/detection.py:181-187` | 同步流水线经 `run_in_threadpool` 下放，避免阻塞事件循环 |
| 11 | `pipeline/change_detection.py:328-345` | 依次调用七步：`_read_pair → _validate_pair → _detect → _clean → _write_previews → _vectorize → _assemble` |
| 12 | `_read_pair()`（`:128-142`） | 两次 `spatial.read_raster(path, settings)` |
| 13 | `spatial/__init__.py` `__getattr__` | PEP 562 延迟提供符号——**此处才首次加载引擎**；写成 `spatial.read_raster(...)` 而非 `from ... import`，以免导入期拉起引擎（`change_detection.py:24-27`） |
| 14 | `spatial/raster.py` `read_raster()` | `load_extension(settings)` → `extension.read_raster(str(path))` → 六元组解包为具名 `Raster`；`RuntimeError` → `RasterReadError`（400） |
| 15 | `spatial/loader.py:112-134` `load_extension()` | **backend 产品代码内的 DLL 加载点**：校验 `build_dir` 存在；Windows 下 `runtime_dll_dir` 必填且存在 |
| 16 | `spatial/loader.py:85-109` `_load_cached()` | `lru_cache(maxsize=1)`（键取字符串，异常不缓存）；`_register_dll_directory`（`:59-82`，句柄存 `_DLL_HANDLES`，`:34`）→ `sys.path.insert` → `import _spatial`；失败抛 `EngineLoadError` |
| 17 | `engine/bindings/module.cpp` `read_raster` | `spatial::read_raster(path)` → 缓冲所有权转 `nb::capsule` → 返回六元组；零拷贝 `uint16`，shape `(bands, height, width)` |
| 18 | `_validate_pair()`（`:145-172`） | 三查：`shape` 相等、`geo_transform` 逐元素差 ≤ `1e-9`（`:75`）、`projection` 相等 → `InputValidationError`（400） |
| 19 | `_detect()`（`:175-191`） | `detector.detect(before.array, after.array)`；本步**不判断**用哪个算法 |
| 20 | `detectors/cva.py` `CvaDetector.detect()` | `delta = after - before`（float64）→ `magnitude = sqrt(sum(delta², axis=0))` → `otsu_threshold()`（256 箱）→ `DetectionResult(mask, threshold)` |
| 21 | `_clean()`（`:194-206`） | `postprocessor.apply(result.mask)`；形状被改 → `ProcessingError`（500） |
| 22 | `postprocess/morphology.py` `apply()` | scipy `label`（4 邻域）→ 剔除 `counts <= min_size` 的块 → 3×3 `binary_closing` 一次 |
| 23 | `_write_previews()`（`:209-242`） | 先 `mkdir(parents=True)`；按 `("before",None) ("after",None) ("diff",mask)` 三元组写 `{job_id}_{kind}.png` |
| 24 | `io/preview.py` `save_rgb_png()` | 按波段数分支（1 / ≥3 / 2 拒绝）→ 2/98 分位拉伸 → PIL 写 PNG；有掩膜时用 `Image.alpha_composite` 叠加红色半透明层 |
| 25 | `_vectorize()`（`:245-259`） | `spatial.mask_to_geojson(mask, geo)` → `reproject_geojson(raw, projection)` → `image_corners(...)` |
| 26 | `spatial/raster.py` `mask_to_geojson()` | `as_mask()`（`bool→uint8` C 连续；其它 dtype 抛 `TypeError`）→ `extension.mask_to_geojson(prepared, list(geo))` |
| 27 | `engine/bindings/module.cpp` `mask_to_geojson` | 强制 `dims == 2` → `spatial::extract_regions()` → `spatial::regions_to_geojson()`（默认容差 0.0） |
| 28 | 引擎内部链路 | `extract_regions`（Two-Pass 并查集，4 邻域）→ 每 Region `extract_boundary`（边图分解）→ `simplify_boundary`（容差 0，短路返回）→ `regions_to_geojson`（**一个 Region 一个 Feature**，`properties` 恰 `label` / `pixel_count` / `area_m2`） |
| 29 | `io/reproject.py` `reproject_geojson()` | `Transformer.from_crs(src, "EPSG:4326", always_xy=True)`；递归到叶子层以支持 MultiPolygon；CRS 缺失 → `CrsError`（400） |
| 30 | `io/reproject.py` `image_corners()` | 按 `geo` 六参数算左上 / 右上 / 右下 / 左下四点后转经纬度 |
| 31 | `_assemble()`（`:262-295`） | `pixel_area = abs(geo[1] × geo[5])`；`changed_area_m2 = change_pixels × pixel_area`；`change_rate = change_pixels / total_pixels`。面积与比率**只在此处导出一次** |
| 32 | `api/routers/detection.py:189-208` | `image_url(kind) = f"/api/image/{name}"`；构造 `DetectionResponse`（12 字段） |
| 33 | 异常路径 | 领域异常**不在路由捕获**，由 `api/errors.py` 的四个处理器统一映射：领域 / 校验(422) / HTTP(`http_<状态码>`) / 兜底 500 固定串 |
| 34 | 前端渲染 | `features/detection/components/ResultPanel.tsx`；错误经 `features/detection/errors.ts` `describeError()` **按 `code` 分支** |

### 3.1 `GET /api/image/{filename}`

`routers/detection.py:100-124` 的 `_artifact_path()` 执行**两道**判定（任一不满足即 `None` → 404，`contracts.md` §9.6）：

1. **纯文件名**：`name` 非空、`Path(name).name == name`、不以 `.` 开头、不含 `..`、不含 `/` 与 `\`（`:110-113`）；
2. **resolve 复核**：对 `outputs_dir` / `uploads_dir` 逐个求 `candidate.relative_to(root)`，不成立即跳过（`:115-124`）。

两道**必须并存**：符号链接、Windows 短文件名、大小写差异都能绕过单靠第一道的检查。

---

## 4. 依赖规则与守护

### 4.1 分层方向（Python 侧）

由 `backend/src/rschange/__init__.py:5-22` 声明：**只允许上层导入下层**。自外向内为

```text
api/ → pipeline/ → detectors/ · postprocess/ → io/ → spatial/ → config.py · logging.py · errors.py
```

**反向依赖禁止清单**（`backend/src/rschange/tests/test_architecture.py:144`）：`config.py` / `logging.py` / `errors.py` / `spatial/` / `io/` / `postprocess/` / `detectors/` 一律禁止导入 `rschange.api` 与 `rschange.pipeline`。

### 4.2 装配点唯一

`api/deps.py:53-76` 的 `build_context(settings=None, *, detector=None, postprocessor=None)` 是**协议与实现的唯一接合处**：

| 槽位 | 缺省行为 | 位置 |
|---|---|---|
| `settings` | `get_settings()` 进程级单例 | `deps.py:64` |
| `postprocessor` | `MorphologyPostprocessor(min_size=..., structure_size=...)`，参数取 `config.postprocess` | `deps.py:66-70` |
| `detector` | `registry.resolve()`（即 `DEFAULT_DETECTOR = "cva"`） | `deps.py:74` |

`RuntimeContext` 为 `@dataclass(frozen=True, slots=True)`（`deps.py:39-51`），三字段 `settings` / `detector` / `postprocessor`。测试替换依赖**不需要打桩**，直接 `create_app(context=RuntimeContext(settings, StubDetector(), StubPostprocessor()))`（`app.py:101-103`、`deps.py:9-15`）。

### 4.3 `pipeline` 运行期不得认识算法层

`pipeline/change_detection.py` 的运行期顶层 import 仅 6 行（`:45-49`）：`rschange.spatial`、`rschange.errors`、`rschange.io.preview`、`rschange.io.reproject`、`rschange.logging` + 标准库。`detectors.base` 与 `postprocess.base` 的 import 写在 `if TYPE_CHECKING:` 块内（`:51-58`）。`detector` / `postprocessor` 是 `detect_change()` 的**必填关键字参数**（`:298-304`），本层不提供默认值。

### 4.4 唯一 DLL 解析点的准确表述

**不得**写作「全项目只有一处」。正确表述是**两侧各一份、刻意互不导入**：

| 侧 | 实现 | 句柄处理 |
|---|---|---|
| 产品代码（`backend/`） | `backend/src/rschange/spatial/loader.py`（`load_extension` / `_load_cached` / `_register_dll_directory`） | 句柄收集于模块级 `_DLL_HANDLES`（`loader.py:34`），生命周期与进程一致 |
| 仓库脚本（`scripts/`） | `scripts/engine_env.py:load_spatial()` | 裸调用 `os.add_dll_directory`，不保存返回值（`engine_env.py:95`、`:98`） |

两侧读同一组配置文件、遵循同一优先级链，但**互不导入**：`scripts/` 须在 backend 未安装时也能跑（`config.py:12-16`）。依据：`_work/p7/inconsistencies.md` 条目 7、条目 8。脚本侧的句柄差异按**已知差异**记录，**不得**简单抄为样板。

### 4.5 守护测试

| 约束 | 守护用例 | 位置 |
|---|---|---|
| backend 内无机器本地路径（G3.5） | `test_backend_has_no_machine_local_paths` | `backend/src/rschange/tests/test_architecture.py:51` |
| `import rschange.pipeline` 不拉入引擎与算法 | `test_pipeline_import_does_not_load_engine_or_algorithms` | `:67` |
| 算法层 import 仅存在于 `TYPE_CHECKING` | `test_pipeline_imports_algorithms_only_for_typing` | `:120` |
| 下层禁止导入上层 | `test_lower_layers_do_not_import_upper_layers` | `:137` |
| 叶层仅互相依赖 | `test_leaf_modules_depend_only_on_each_other` | `:182` |
| 契约类不得依赖具体实现（含 numpy 也在 `TYPE_CHECKING` 下） | `test_detector_contract_has_no_concrete_dependencies` | `:196` |
| 新增算法后 `change_detection.py` 哈希不变（G3.4） | `test_new_detector_is_pluggable_without_pipeline_change` | `:227` |
| HTTP 边界：路由 / 错误映射 / 目录穿越 / CORS / 体积上限 | `test_api.py`（19 个 `def test_`） | `backend/src/rschange/tests/` |
| 契约三层字段一致、`status` 三层皆无 | `tests/contract/`（3 文件 9 用例） | `tests/contract/` |

---

## 5. 契约两段流水线

权威描述见 `docs/contracts.md` §9.12；此处只给概览与门禁归属。

```text
backend/src/rschange/api/schemas/*.py
        │  ①  scripts/gen_openapi.py  （生成 / --check 逐字节比对）
        ▼
docs/api/openapi.json            ← 冻结入库，OpenAPI 3.1.0
        │  ②  npm run gen:types（swagger-typescript-api）
        ▼
frontend/src/api/generated/data-contracts.ts   ← 冻结入库
        │     前端只经 api/types.ts 转发消费
```

| 段 | 载体 | 门禁 | 判据粒度 |
|---|---|---|---|
| ① | `scripts/gen_openapi.py` | CI 步骤 18：`gen_openapi.py --check`；`tests/contract/test_openapi_frozen.py` | **字节级**（`sort_keys=True` + LF，跨平台逐字节可复现） |
| ② | `frontend/package.json` 的 `gen:types` | CI 步骤 23「契约类型零漂移（openapi → TS）」（`.github/workflows/ci.yml:295-307`）：重新生成后 `git status --porcelain -- frontend/src/api/generated` 必须为空 | **工作树级**，覆盖字段增删、改名、类型变化、顺序变化全部形态 |
| 跨段 | `tests/contract/test_field_consistency.py`、`test_wire_format.py` | 同一 pytest 运行 | 字段名集 / 必填性 / `status` 有无 / 真实响应的线格式 |

**两段各有独立门禁，缺一不可。** 第二段是 Phase 6 新增，用于关闭 Phase 5 §11.1 登记的类型级漂移盲区；`docs/verification/phase-6.md` §7 以变异实验证明了其**独占**拦截能力（变体 B：改后端字段类型并重新生成 openapi → 第一段正当放行，第二段变红）。

> **状态说明**：该判据的覆盖边界原登记于 `docs/contracts.md` §9.12（原文写作「属遗留项」）。该表述已于 `v1.0.0` 就地更正为「已落地」——门禁在 Actions run `37192763321` 上双平台全绿执行（依据：`docs/verification/phase-6.md` §3、§6、§7；`_work/p7/inconsistencies.md` 条目 9）。

工具选型约束：生成器为 `swagger-typescript-api`，**禁止**换回 `openapi-typescript`——后者 peer 依赖要求 `typescript@^5.x`，与本项目 `~6.0.2` 冲突（`docs/contracts.md:313`）。

---

## 6. 扩展点

完整代码级步骤归 `docs/DEVELOPMENT.md`；本节只说明机制与「该改哪些文件」。

### 6.1 新增一种检测算法

机制：`ChangeDetector` 是 `Protocol`（非抽象基类，`@runtime_checkable`），`detectors/registry.py` 的 `_REGISTRY` 存**实例**而非类；内置算法在包 `__init__` 里注册（`detectors/__init__.py:27` `registry.register(CvaDetector())`），因为 import 任何子模块必先执行父包 `__init__`。

| 步骤 | 文件 | 改动 |
|---|---|---|
| 1 | `detectors/<name>.py`（新建） | 实现类：`name: str` 唯一 + `detect(before, after) -> DetectionResult`。**不继承**任何基类 |
| 2 | `detectors/__init__.py` | 导入并 `registry.register(XxxDetector())`（以 `registry.py:5-6` 的表述为准） |
| 3 | `config.py`（仅当有可调参数） | 新增继承 `_StrictModel` 的 Settings 类（`extra="forbid"`，每个嵌套模型须单独声明） |
| 4 | `config/default.toml` + `config/local.example.toml` | 同步新增；否则 `verify_config.py` 的模板对齐判据会失配 |
| 5 | `api/deps.py:build_context()` | 把 `settings.<section>` 注入构造函数（参照 `MorphologyPostprocessor` 的写法） |
| 6 | `backend/src/rschange/tests/test_detectors_postprocess.py` | 补用例；重置用 `restores_registry` 夹具 |
| 7 | `docs/contracts.md` §9.11 / §10 | 触及契约时走 §8 变更流程 |

**禁止改** `backend/src/rschange/pipeline/change_detection.py`。判据：`test_architecture.py:227`。

### 6.2 新增一种后处理器

`postprocess/` **没有注册表**——本层不提供按名解析的能力。实现 `MaskPostprocessor` 协议后，由调用方在装配期显式注入：产品路径改 `api/deps.py:build_context()`；测试路径直接构造 `RuntimeContext`。参数**必须**由构造期注入，不得写进 `apply()` 签名，也不得在模块内写死（`postprocess/base.py` 与 `postprocess/__init__.py` 的层规约）。

### 6.3 现状缺口（写新算法前须知）

| 缺口 | 现状 | 影响 |
|---|---|---|
| 算法不可按名选择 | `UnknownDetectorError`（400 / `unknown_detector`）已定义，但 HTTP 与 CLI **均未**暴露算法参数 | 多算法只能在代码层 `registry.resolve("<name>")` 或显式构造 `RuntimeContext` |
| `CvaDetector` 无可调参数 | 直方图箱数为模块常量 `HISTOGRAM_BINS = 256`（`cva.py:41`），改动该值会让 Otsu 阈值锚点漂移 | 目前不存在 `[detector]` 配置段，`DEFAULT_DETECTOR` 是编译期常量而非配置项 |

---

## 7. 构建与测试概览

### 7.1 引擎（CMake）

```bash
# 配置（须在 engine/ 下执行，否则找不到 CMakePresets.json）
cd engine && cmake --preset dev-win          # 或 dev-linux
cmake --build --preset dev-win
ctest --test-dir engine/build/dev-win --output-on-failure
```

| 项 | 值 | 出处 |
|---|---|---|
| 开关 | `SPATIAL_BUILD_PYTHON=ON`、`SPATIAL_BUILD_TESTS=ON`、`SPATIAL_WARNINGS_AS_ERRORS=ON` | `engine/CMakeLists.txt` |
| 告警下发 | INTERFACE target `spatial_warnings`（`-Wall -Wextra -Wpedantic <-Werror>`），不污染第三方依赖 | 同上 |
| 产物目录 | `engine/build/${presetName}` | `CMakePresets.json` `base` 预设 |
| Windows 环境变量 | `SPATIAL_MINGW_ROOT` / `SPATIAL_GDAL_ROOT` / `SPATIAL_PYTHON` | `win-base` 预设（`:13-27`） |
| 产物名 | Windows `_spatial.cp314-win_amd64.pyd`；Linux `_spatial.cpython-314-x86_64-linux-gnu.so` | `docs/contracts.md:21-23` |

### 7.2 后端（Python）

| 动作 | 命令 | 说明 |
|---|---|---|
| 依赖 | `uv sync --all-packages [--frozen]` | uv workspace，成员仅 `backend`；`python-preference = "only-system"` |
| 测试 | `uv run pytest`（CI：`uv run pytest -o addopts="" -rs`） | `testpaths = ["backend/src/rschange/tests", "tests"]`；引擎不可用时**跳过**而非失败（`tests/conftest.py` 的 `engine_ready`） |
| 类型 | `uv run mypy` | `strict = true`，`files = ["backend/src"]`；`rschange.tests.*` 仅放宽 `disallow_untyped_defs` / `disallow_incomplete_defs` |
| 静态 | `uv run ruff check backend/ scripts/`（CI 用 `.`） | CI 的 `.` 与前式等价，依赖 `extend-exclude = ["docs"]` |
| 运行 | `uv run uvicorn --factory rschange.api.app:create_app --reload` 或 `uv run python -m rschange.api.app` | `app.py:8-19` |

### 7.3 前端（Node）

| 动作 | 命令 |
|---|---|
| 依赖 | `npm ci` |
| 检查 | `npm run check`（= `tsc -b --noEmit && oxlint && vitest run`） |
| 构建 | `npm run build`（= `tsc -b && vite build`） |
| 类型生成 | `npm run gen:types` |

`vitest.config.ts` 刻意**不设** `passWithNoTests`（`facts.md` §2.4）。

### 7.4 测试规模（取 `docs/verification/phase-6.md` §9 的实跑数字）

| 组 | 实测 | 出处 |
|---|---|---|
| C++ `ctest` | **40/40** 通过 | `ctest.log`；静态 `TEST_CASE` 计数同为 40 |
| Python `pytest` | **148 passed** | `pytest.log`；源码静态 `def test_` 计数 123（`backend` 112 + 根 `tests/` 11），差额来自 `@pytest.mark.parametrize` 展开 |
| 前端 `vitest` | **109 passed**（6 文件） | `fe_check.log` |
| `mypy` | 36 源文件 0 错 | `mypy.log` |
| `ruff check` / `format` | `All checks passed!` / **52** files already formatted（Phase 6 收口时为 50；Phase 7 新增根 `CONTRIBUTING.md` 后 +1，v1.0.1 新增 `scripts/verify_doc_paths.py` 再 +1——`ruff format` 会一并格式化**根目录** Markdown 内的 Python 代码块，`docs/` 则由 `extend-exclude` 排除。计数构成 = 50 个 `.py` + 根 `README.md` + `CONTRIBUTING.md`） | Phase 6 原始日志 `ruff_check.log` / `ruff_format.log`；Phase 7 复跑见 `docs/verification/phase-7.md` |
| `verify_*` 五脚本 | 全通过 | `verify_all.log` |

### 7.5 CI 双平台矩阵

单 job `verify`，`strategy.fail-fast = false`，矩阵 `linux-gcc`（`ubuntu-latest`, `dev-linux`）与 `windows-mingw`（`windows-latest`, `dev-win`）。三段门禁定位（`.github/workflows/ci.yml:44-51`）：

| 段 | 步骤 | 管什么 |
|---|---|---|
| ① 功能正确性 | 14 CTest、15 pytest | 代码行为未回归 |
| ② 契约未漂移 | 18 `gen_openapi --check`、23 契约类型零漂移 | 见 §5 |
| ③ 环境自洽 | 19 `verify_baseline --phase 6` / `verify_bindings` / `verify_config` / `verify_version` / `verify_containers` | 环境、配置、绑定、版本、容器资产 |

> **环境前提**：本仓库的门禁脚本与 CLI 以中文输出，这以「运行环境提供 UTF-8 stdio」为前提。CI 注入 `PYTHONUTF8=1`；Windows 下注意 `PYTHONIOENCODING` 优先级高于 UTF-8 模式（`docs/verification/phase-6.md` §8-⑤）。该前提须写入开发者文档（`DEVELOPMENT.md` 承接）。

---

## 8. 关键不变量表

违反任一条即判回归缺陷。

### 8.1 契约与技能

| 不变量 | 值 | 权威出处 |
|---|---|---|
| `API_PREFIX` | `"/api"` | `app.py:46`、`contracts.md:181` |
| `DetectionResponse` 字段数 | **12**（7 必填 + 5 可选）；`status` 已于 `v0.5.0` 移除（13 → 12） | `schemas/detection.py:56-74`、`contracts.md:202-219` |
| 错误响应形状 | `{"detail": str, "code": str}`；422 额外含 `errors` | `contracts.md:223-225` |
| 领域异常类个数 | 12 | `errors.py`、`contracts.md:229-244` |
| `_spatial` 公开函数 | 4：`read_raster` / `write_raster` / `mask_to_geojson` / `print_gdal_version` | `contracts.md` §3、`verify_bindings.py` |
| 版本真相源 | `backend/pyproject.toml` 的 `[project].version`（当前 `1.0.1`） | `pyproject.toml:17`、`verify_version.py` 判据 1 |
| 装配点 | 唯一：`api/deps.py:build_context()` | `deps.py:53-76`、`phase-3.md` B.2 |
| G3.4 判据 | 新增算法后 `pipeline/change_detection.py` SHA-256 不变 | `contracts.md:306`、`phase-3.md` §5 |

### 8.2 几何与算法

| 不变量 | 值 | 权威出处 |
|---|---|---|
| 环顶点基准 | 像素**角点格点** `(r, c)`，`r ∈ [0, H]`、`c ∈ [0, W]`（比像素下标多一行一列） | `algorithm.md:114-116`、`contracts.md:95` |
| 环的有向面积 | 外环为正、洞环为负，符号相反 | `algorithm.md:118-119` |
| 几何面积 ≡ `area_m2` | 默认容差 0 下**精确相等**（偏差仅为浮点表示级），判据上限 `1e-6 %` | `contracts.md:103`、§5.1 |
| `simplify_tolerance` 默认值 | **0.0**（非正即短路返回） | `contracts.md:99`、`geojson.hpp` |
| `area_m2` 定义 | `pixel_count × |geo[1] × geo[5]|` | `contracts.md:101` |
| `properties` 字段 | 恰为 `label` / `pixel_count` / `area_m2`，**禁止**增删或改名 | `contracts.md:100` |
| 退化剔除 | 只剩一种：**成员像素 < 3 个**（轮廓层返回空环）；一像素宽细长结构是**合法**矩形 | `contracts.md:98`、`algorithm.md:329-332` |
| 连通性与 label 序 | 4 邻域；label 从 1 起按 raster-scan **首次出现顺序**，与容器迭代序无关 | `contracts.md:91-92`、`labeling.hpp:24` |
| Feature 数 | 等于**非退化**连通域数；一个 Region **恰好**一个 Feature（多环在同一 Polygon 内，首环外环、其余内环） | `contracts.md:93-94`、`algorithm.md:914-915` |
| 掩膜入参 | 必须 `uint8` + C 连续；**禁止**隐式转换（`nb::noconvert()`） | `contracts.md:77-85` |
| 输出确定性 | 同一输入在任意平台 / 标准库实现下逐字节一致 | `contracts.md:104` |

### 8.3 基线锚点（`contracts.md` §9.10、`algorithm.md` §9）

| 锚点 | 值 |
|---|---|
| Otsu 阈值 `threshold` | `5.916767423962816`（契约示例写作 `5.9168`） |
| 变化像素 / 总像素 | `7209 / 65536`（变化率 `0.110001`） |
| `changed_area_m2` | `720900 m²`（= 7209 × 100.0） |
| 影像 | `(3, 256, 256)`，`uint16`，UTM zone 50N |
| GeoJSON Feature 数 | **1**（旧实现为 2，见 `docs/MIGRATION.md` D-3） |
| 属性面积合计 | `720900 m²`（旧实现 `1441800 m²`） |
| `multi_region_mask` | Feature 数 6，label 序列 `1..6`，几何面积 == 上报面积（偏差 `0.00 %`） |

---

## 9. 待核实项

> 本文其余章节已就地给出「须同时注意的既有结论」（依赖方向 §1、装配点 §4.2、`pipeline` 解耦 §4.3、契约两段 §5、DLL 解析点 §4.4、`algorithm.md` §0 归属更正 §2.2、crack following §2.3），此处不再重复。

| # | 事项 | 现状与出处 |
|---|---|---|
| 1 | `docs/verification/phase-6.md` 曾被 `docker/Dockerfile.backend:20-22` 引用为不存在文件 | 该文件现已在 `docs/verification/` 下存在（本次采集时可见），悬空引用应已消除；**待核实** Docker 注释是否需同步更新编号 |
| 2 | `notebooks/`（仓库根，当前为空目录）是否有既定用途 | 本次 `ls` 结果为空；旧仓库 `src/core/src/remote-sensing/sensing.ipynb` 的承接位置未在任何文档声明 |
| 3 | `ctest` 注册用例数 40 与 `docs/verification/phase-2.md` 历史记录「38/38」的差异来源 | Phase 2 时为历史快照；`docs/verification/phase-6.md` §9 表 D 行实测同为 40/40。**未**追查中间版本差异，不影响当前结论 |
| 4 | `engine/CMakeLists.txt` 的 `project VERSION 0.2.0` 与仓库版本 `1.0.1` 不同号 | 引擎版本**不在** `verify_version.py` 的 5 项判据内（`new-arch-digest.md` B5）；属已知不自洽，写文档时勿据该值判引擎世代 |
| 5 | D 系列缺陷编号存在两套口径 | `docs/algorithm.md` §8.1 的 D-1 = 2D 掩膜尺寸解析，而 `app.py:121` 与 `contracts.md:266` 的 D1 = CORS 通配符；D-2 / D-7 同理存在碰撞。**已定性为「作用域不同」而非冲突**：§8.1 的 `D-1…D-9` 记 C++ 引擎缺陷，`phase-3.md` §3 的 `D1…D7` 记后端分层缺陷，`spatial/__init__.py` docstring 的「附录 D-5」是架构条目。该划分已写入 `docs/algorithm.md` §8.1 的「编号口径」引用块，故**不再**标 `待核实` |

---

*本文在**只读**前提下撰写：未对任何仓库执行 git 命令，未在仓库内创建、修改或删除文件。*
