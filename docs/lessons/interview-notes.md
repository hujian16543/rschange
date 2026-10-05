# 面试讲述稿 · rschange 遥感变化检测平台

> **文件定位**：可直接照着讲的项目讲述稿。含 30 秒版与 2 分钟版介绍、技术亮点（带可核查数字）、难点与取舍、8 组追问应答、诚实边界。
>
> **素材来源**（只读）：当期仓库事实采集（`docs/algorithm.md`、`docs/contracts.md`、各模块源码与测试）、
> 阶段验收报告 `docs/verification/phase-2.md`／`phase-2.1.md`／`phase-3.md`／`phase-5.md`／`phase-6.md`、
> 整理版 `debug-lessons.md`、旧仓库原始素材 `project2-lessons-and-interview.txt`。
>
> **数字纪律**：每个数字必须可在仓库（版本 `1.0.0`，Phase 7 收口）核对，落点以 `文件:行号` 或**测试名**给出；
> 无法核实者标 `待核实`，且**禁止**在讲述中当作既成事实。
> 数字**实测于 Phase 6 收口 tip**（`dc8ee2b`／`v0.6.0`）；Phase 7 只增改文档，未改产品代码与黄金基线。
>
> **缺陷编号三套口径**（引用前必读，详见 `debug-lessons.md` §0）：
> ① `docs/algorithm.md` §8.1 的 `D-1 … D-9` 记 **C++ 引擎**缺陷；
> ② `docs/verification/phase-3.md` §3 的 `D1 … D7` 记 **后端分层**缺陷；
> ③ `backend/src/rschange/spatial/__init__.py` docstring 的「附录 D-5」为**架构条目**，与缺陷无关。
> 本文引用一律写全来源文档名。
>
> **表述纪律**：§1／§2 的口语段落与 §5 的应答话术允许第一人称；其余章节（§3／§4／§6 及全部表格）为**声明式**，
> 使用「需要／必须／应当／禁止」句式，**禁止**「我们」。

---

## 1. 30 秒版

> 口语话术（可照念）：

「我独立完成了一个遥感变化检测平台：前端是 React 19 + TypeScript，后端是 FastAPI 分层的 Python 包，
核心是一个我用 C++20 手写的空间计算引擎，通过 nanobind 暴露成 Python 扩展 `_spatial`。
用户上传两期 GeoTIFF，我用 CVA 变化向量分析算逐像素差异、Otsu 自动定阈值，
再经我自己实现的 Two-Pass 连通域提取、沿像素边界追踪轮廓、Douglas-Peucker 简化，
把变化区域转成 GeoJSON 返回，并做前端可视化。
整套跑在 Windows / Linux 双平台 CI 上，最硬的一个数字是：黄金基线上 65 536 个像元里检出 7 209 个变化像元，
真实变化面积 720 900 平方米——这个数字在重构中被我发现旧实现虚报了一倍，最后定位到一个多环归属缺陷并修掉了。」

**要点锚点**（声明式）：

| 要素 | 内容 | 落点 |
|---|---|---|
| 是什么 | 遥感变化检测 Web 平台（上传两期影像 → 检测变化 → GeoJSON + 可视化） | 仓库根 `README` 级定位 |
| 技术栈 | C++20 空间引擎（GDAL + nanobind 扩展 `_spatial`）＋ FastAPI 分层后端（包 `rschange`）＋ React 19 / TypeScript ~6.0.2 / Vite 8；uv workspace 管依赖 | `backend/pyproject.toml`、`frontend/package.json`、`pyproject.toml` |
| 解决什么问题 | 两期影像的逐像素变化检测与矢量结果产出，且数字可复现、可门禁化 | `docs/algorithm.md`、`docs/contracts.md` |
| 最硬的一个数字 | 基线 `7209 / 65536` 变化像元、`720900 m²` 真实变化面积 | `scripts/verify_baseline.py:129-153` |

---

## 2. 2 分钟版

> 口语话术（可照念）：

「这个项目分三层，最有价值的是 C++ 空间引擎。

**算法层**：用 CVA——变化向量分析，对两期影像逐像素求欧氏距离模长，再用 Otsu 自动阈值分割，不需要人工调参；
后处理用连通域过滤去掉小噪声，再做形态学闭运算合并碎块。基线夹具上 Otsu 阈值是 5.9168，检出 7 209 个变化像元。

**空间引擎层**：这是核心。我用 C++20 手写了 Two-Pass 连通域提取、沿像素边界追踪（crack following）提取有序轮廓环、
闭合环的 Douglas-Peucker 简化，最后序列化成 GeoJSON。相比直接调 `scipy.ndimage.label`，这一层让我真正处理了
「一个连通域含洞、边界被劈成多条弧」这类几何语义问题——也正是它暴露了我最得意也最痛的一个缺陷：
旧实现给每条边界环各生成一个 Feature，却把整个区域的面积属性复制到每个 Feature 上，于是面积被重复计 N 倍，
把 720 900 平方米虚报成了 1 441 800，整整一倍。

**后端与前端**：后端是 FastAPI 分层包，依赖方向单向、装配点唯一、算法可插拔；前端是 React + TypeScript，
与后端契约严格对齐，靠一条由 OpenAPI 驱动的两段流水线保证前后端字段零漂移。

**工程化**：整套跑在单 job × 双平台的 CI 上，Linux 和 Windows 都必须绿。」

**技术亮点数字表**（声明式，全部可核查）：

| 维度 | 数字 | 落点 |
|---|---|---|
| C++ 单元测试 | `ctest` **40/40** 通过 | `docs/verification/phase-6.md` §9 表 D 行；`engine/tests/`（7 文件） |
| Python 测试 | `pytest` **148 passed** | `docs/verification/phase-6.md` §9-E |
| 前端测试 | `vitest` **109 passed**（6 文件） | `docs/verification/phase-6.md` §9-K |
| 类型检查 | `mypy` strict **36 源文件 0 错** | `pyproject.toml:104-105`；`phase-6.md` §9-F |
| 静态检查 | `ruff check` / `format` 通过（**50 files**） | `pyproject.toml:68-98`；`phase-6.md` §9-G |
| 响应契约字段 | `DetectionResponse` **12 字段**（7 必填 + 5 可选） | `backend/src/rschange/api/schemas/detection.py:56-74` |
| 领域异常 | **12** 个异常类 | `backend/src/rschange/errors.py` |
| `_spatial` 公开函数 | **4** 个（`read_raster`/`write_raster`/`mask_to_geojson`/`print_gdal_version`） | `docs/contracts.md` §3；`scripts/verify_bindings.py` |
| 黄金基线 | Otsu `5.916767423962816`（契约示例 `5.9168`）；变化像素 `7209 / 65536`；面积 `720900 m²` | `scripts/verify_baseline.py:129-153`；`schemas/detection.py:33-39` |
| 面积口径修正 | 属性面积合计 `1441800 → 720900 m²`；Feature 数 `2 → 1` | `engine/src/geojson.cpp`；`engine/tests/test_geojson.cpp:112` |
| 几何基准修正 | 多区域偏差 `-17.63% → 0.00%`，判据上限 `1e-6%` | `docs/verification/phase-2.1.md` §7；`engine/tests/test_geojson.cpp:255` |
| 双平台 CI | 单 job `verify` × 矩阵 `linux-gcc`/`windows-mingw`，各 **32 步零失败** | `.github/workflows/ci.yml`；run `37192763321` |
| 前端产物 | 构建总 gzip **86.38 KB** < 300 KB | `docs/verification/phase-6.md` §9-L |

---

## 3. 技术亮点

> 本节为声明式。每条给出「结论 → 可核查数字 → 落点」。

### 3.1 手写 C++20 空间引擎（GDAL + nanobind）

- 引擎暴露 4 个公开函数：`read_raster`、`write_raster`、`mask_to_geojson`、`print_gdal_version`；绑定层只做
  Python↔C++ 转换与参数校验，不含算法（`engine/bindings/module.cpp`）。
- 跨语言边界对数组类型与布局**必须**严格：`uint8` C 连续只读数组被接受，`float32`／`int32`／`bool`／非 C 连续／
  F 连续一律 `TypeError`；退化 3D `(1,H,W)` 掩膜抛 `ValueError`（`scripts/verify_bindings.py`，42 项检查，失败 0）。
- 引擎单测 `ctest` **40/40**（`docs/verification/phase-6.md` §9 表 D 行）。符号可见性由 `SPATIAL_API` 宏**唯一定义**
  （`engine/include/spatial/export.hpp`），导出表经 `objdump -p` 核对（`docs/verification/phase-2.1.md` §4，共 9 个
  `spatial::` 符号，含 4 个公开函数）。

### 3.2 数值基线可复现且被门禁守护

- 冻结基线：影像 `(3, 256, 256)` `uint16`、UTM zone 50N；Otsu 阈值 `5.916767423962816`（契约示例写作 `5.9168`）；
  变化像素 `7209 / 65536`（变化率 `0.110001`）；真实面积 `changed_area_m2 = 720900 m²`（= 7209 × 100.0）。
- 落点：`scripts/verify_baseline.py:129-153`；示例值同源 `backend/src/rschange/api/schemas/detection.py:32-50`。
- 校验分组：`verify_baseline.py` 输出 §7.1 **11/11**（不变量）、§7.2 **2/2**（缺陷基线）、§7.3 **7/7**（语义断言）
  （`docs/verification/phase-2.1.md` §2-G3）。
- 独立复算：不 import 仓库实现，自实现 CVA / Otsu / 连通域后三方对照，Otsu 差 `3.26e-5`、变化像素 `7209` 命中
  （`docs/verification/phase-2.md` §4）。

### 3.3 核心缺陷修正：GeoJSON 属性归属（面积不再重复计）

- **缺陷**：旧实现**每环一个 Feature**，却把 Region 级 `pixel_count` / `area_m2` 复制到每条环的 Feature 上；
  基线样本是单连通域，其边界被劈成 2 条弧，于是 `720900 m²` 被计 2 次，合计虚报为 `1441800 m²`（虚报一倍）。
- **修正**：**一个 Region 一个 Feature**——首环为外环，其余为内环；合计回到 `720900 m²`，Feature 数 `2 → 1`。
- **编号**：`docs/algorithm.md` §8.1 的 **`D-3`**（引擎侧）；成因链见 `debug-lessons.md` §3。
- **落点**：`engine/src/geojson.cpp`（修复点）；守护测试 `engine/tests/test_geojson.cpp:112`
  （`geojson: exactly one Feature per Region (D-3)`）、`:128`（属性不跨 Region 重复计）、`:140`（含洞 Region 仍为一个 Feature）；
  实测表见 `docs/verification/phase-2.md` §3.1（`7.2 Feature 个数 1`、`属性面积合计 720900.0`）。

### 3.4 几何基准修正：几何面积恒等于成员像素数（Phase 2.1）

- **缺陷**：轮廓基准取**像素中心**时，上报 `area_m2` 与多边形自身几何面积不等——多区域偏差 `-17.63%`
  （几何 `54200.0` vs 上报 `65800.0`，`docs/verification/phase-2.md` §4.3）。
- **修正**：几何基准由像素中心改为**像素角点**（沿像素边界追踪，crack following），使「几何面积（像素单位）== 成员像素数」
  成为恒等式；判据容差上限 `1e-6%`。多区域偏差回到 **`0.00%`**（`66300.0 == 66300.0`）。
- **连带变更**：`multi_region_mask` 的 Feature 数 `5 → 6`（角点基准下一像素宽细长结构不再是退化几何）。
- **落点**：`engine/src/contour.cpp`；`engine/tests/test_geojson.cpp:255`
  （`geojson: geometric area equals area_m2 exactly (Phase 2.1 invariant)`）；`scripts/verify_baseline.py`
  以 **shapely 独立重算**面积后与引擎上报值比对（`docs/verification/phase-2.1.md` §7）。

### 3.5 分层后端与可插拔算法

- 依赖方向单向无环：**backend → `_spatial` → libspatial → GDAL**；装配点唯一 = `build_context()`
  （`backend/src/rschange/api/deps.py:53-76`）。
- `pipeline` **运行期不 import** `detectors/` 与 `postprocess/`：相关类型仅在 `if TYPE_CHECKING:` 块内
  （`backend/src/rschange/pipeline/change_detection.py:51-58`）；`detector` / `postprocessor` 是 `detect_change` 的
  **必填注入参数**。
- 可插拔实证：新增一个检测器后，`pipeline/change_detection.py` 哈希前后一致（`2a83860…`）且新检测器跑通完整流水线，
  产物与基线一致（`7209` 像素 / `720900 m²`，`docs/verification/phase-3.md` §5）。
- 守护测试：`backend/src/rschange/tests/test_architecture.py:227`
  （`test_new_detector_is_pluggable_without_pipeline_change`，G3.4）。
- 领域异常 **12** 个，各带 `http_status` / `code` / `public_message`（`backend/src/rschange/errors.py`）；
  500 兜底响应体固定为 `{"detail": "内部错误", "code": "internal_error"}`，不含异常消息、类型名或栈
  （`backend/src/rschange/api/errors.py:102-127`）。

### 3.6 契约两段流水线（各有独立门禁，缺一不可）

- 第一段：`pydantic` →（`scripts/gen_openapi.py`，`--check` 字节级）→ `docs/api/openapi.json`。
- 第二段：`docs/api/openapi.json` →（`npm run gen:types`，`swagger-typescript-api`）→ `frontend/src/api/generated/data-contracts.ts`。
- 第二段由 CI 步骤「契约类型零漂移（openapi → TS）」守护（`.github/workflows/ci.yml`）。
- **第二段独占判别力由变异实验证明**：变体 B（改后端字段类型并重新生成 openapi）→ 第一段**正当放行**、第二段**变红**
  （`docs/verification/phase-6.md` §7）。
- 契约收缩守护：`status` 于 `v0.5.0` 移除（`13 → 12` 字段）；`frontend/src/api/types.ts:52-53` 以
  `@ts-expect-error` 做编译期断言，字段被加回即报 `TS2578`。

### 3.7 前端工程化与类型严格

- React 19 / TypeScript ~6.0.2 / Vite 8；`vitest` **109 passed**（6 文件）。
- 严格选项开启：`strict` 与 `noUncheckedIndexedAccess`（`frontend/tsconfig.app.json:23-24`）；`src/` 内
  `@ts-ignore` / `as any` / 非空断言 `!` **0 命中**（生成文件固定 `@ts-nocheck` 头部与契约断言行除外，
  `docs/verification/phase-5.md` §4.2）。
- 判别力由变异实验证明：竞态守卫改为恒假 → 红 3 例；`changed_area_m2` 渲染错接 → 红 6 例，且变异均完整还原
  （`docs/verification/phase-4.md` §5.4）。
- 错误处理按 `code` 分支，**禁止**匹配 `detail` 文案（`frontend/src/features/detection/errors.ts`）。

### 3.8 双平台 CI 与门禁脚本

- 单 job `verify` × 双平台矩阵：`linux-gcc`（`ubuntu-latest`, `dev-linux`）／`windows-mingw`（`windows-latest`, `dev-win`）；
  `fail-fast: false`（`.github/workflows/ci.yml`）。
- G6.1 判据 = Actions run `37192763321` 双平台各 **32 步零失败**；需显式排除只有 31 步、不含第二段门禁的 run
  `37192442273`（`docs/verification/phase-6.md` §3）。
- 门禁脚本（CI step 19 一次性串联）：`verify_baseline.py`（§7.1 11/11 + §7.2 2/2 + §7.3 7/7）、
  `verify_bindings.py`（42 项）、`verify_config.py`（6 项）、`verify_version.py`（5 项）、
  `verify_containers.py`（19 项，**不替代真实构建**）。
- 双平台实跑暴露并修复 5 处平台缺陷（`docs/verification/phase-6.md` §8），见 §4.5。

---

## 4. 难点与取舍

> 本节为声明式。每条按「方案 A vs 方案 B／选了哪个／代价是什么」组织。

### 4.1 GeoJSON 属性归属：环级 Feature vs 区域级 Feature

| 项 | 内容 |
|---|---|
| 方案 A | **每环一个 Feature**，Region 级属性复制到每条环的 Feature（旧实现） |
| 方案 B（选） | **一个 Region 一个 Feature**，首环外环、其余内环，Region 级属性只出现一次 |
| 代价 | 必须先把散落的边界弧**归并回 Region**（区分外环／内环），并补多区域夹具与洞环判据守护 |
| 收益 | 属性面积不再重复计 N 倍；基线 `1441800 → 720900 m²`、Feature `2 → 1` |
| 落点 | `docs/algorithm.md` §8.1 `D-3`；`engine/src/geojson.cpp`；`engine/tests/test_geojson.cpp:112,128,140` |

### 4.2 几何基准：像素中心 vs 像素角点

| 项 | 内容 |
|---|---|
| 方案 A | 轮廓取**像素中心**为格点，实现直观 |
| 方案 B（选） | 沿**像素边界**追踪（crack following），格点取像素角点 |
| 代价 | 边界追踪实现复杂度上升；简化容差默认值改为 `0.0`（容差 ≤ 0 时短路不简化，保证几何面积精确守恒，`engine/src/simplify.cpp`） |
| 收益 | 「几何面积 == 成员像素数」成为**恒等式**；多区域偏差 `-17.63% → 0.00%`，容差上限 `1e-6%` |
| 落点 | `docs/verification/phase-2.1.md` §7；`engine/tests/test_geojson.cpp:255` |

### 4.3 契约同步：手写前端类型 vs OpenAPI 生成

| 项 | 内容 |
|---|---|
| 方案 A | 前端手写类型，与后端 schema 靠人工对齐（旧实现 `types/detection.ts` 仅 10 字段，缺 3 字段） |
| 方案 B（选） | 删除手写类型，改由 OpenAPI **两段流水线**生成；转发层 `api/types.ts` 不含任何手写字段 |
| 代价 | 需维护两段门禁；生成器选型受限——**禁止**换回 `openapi-typescript`（其 peer 依赖要求 `typescript@^5.x`，与本仓库 `~6.0.2` 冲突）；生成文件带 `@ts-nocheck`，故编译期防线另置于转发层 |
| 收益 | 契约字段集逐层相等（三层均 12 字段），字段类型级漂移由第二段独占拦截 |
| 落点 | `docs/contracts.md`；`docs/verification/phase-5.md` §3／§7；`docs/verification/phase-6.md` §6／§7 |

### 4.4 算法装配：硬编码调用 vs 协议注入 + 注册表

| 项 | 内容 |
|---|---|
| 方案 A | `pipeline` 内直接调用 `cva_detect(...)`（旧实现） |
| 方案 B（选） | `detector` / `postprocessor` 定义为协议并作为 `detect_change` **必填注入参数**；装配收敛于 `build_context()` |
| 代价 | 多一层协议定义与装配点；`pipeline` 运行期零 import 具体算法这一性质需额外守护 |
| 收益 | 新增一种检测算法只改 `detectors/`，`pipeline` 文件哈希不变（G3.4 实证） |
| 落点 | `backend/src/rschange/pipeline/change_detection.py:51-58`；`backend/src/rschange/api/deps.py:53-76`；`test_architecture.py:227` |

### 4.5 跨平台：单平台「能编译」vs 双平台必过

| 项 | 内容 |
|---|---|
| 方案 A | 只保证本机（中文 Windows / MinGW）编译通过 |
| 方案 B（选） | 双平台矩阵**均为必过**，`fail-fast: false`；每平台各自编译、各自运行 |
| 代价 | CI 时长与维护成本上升；实跑暴露 5 处平台缺陷：① `setup-msys2` release 模式装在 `$RUNNER_TEMP/msys64` 而非 `C:\msys64`（唯一真相源是 `steps.msys2.outputs.msys2-location`）；② Catch2 中文用例名在 ACP=1252 下变 `?` → 40 个用例名改 ASCII；③ `test_config_logging.py` 写死 `dev-win` 预设名；④ `os.add_dll_directory` 仅存在于 Windows typeshed → 改 `getattr` 取值；⑤ `PYTHONIOENCODING` 优先级**高于** UTF-8 模式，须在子进程环境里剔除 |
| 收益 | 「能编译」升级为「每个平台都能编译并运行」；平台差异不再靠人工记忆 |
| 落点 | `.github/workflows/ci.yml`；`docs/verification/phase-6.md` §8 |

### 4.6 容器门禁：真实构建 + 端到端 vs 静态判据

| 项 | 内容 |
|---|---|
| 方案 A | `docker-compose up` 后真实跑 `POST /api/detect`，核对返回基线数字 |
| 方案 B（选） | 受环境限制，容器**只写配置不构建**；G6.2／G6.3 改由 `verify_containers.py` 的 19 条静态判据承担 |
| 代价 | 容器未构建、端到端未实测——`docker-compose up` 的实际行为、镜像真实构建、健康检查是否生效、命名卷持久化均未验证 |
| 收益 | 仍可在静态层消除关键配置缺陷（上传上限三方同号：nginx `500m` ≥ 后端 `500MB`，≥ 1 MB 缺陷在配置层被消除） |
| 落点 | `docs/verification/phase-6.md` §4／§5／§11 O1 |

---

## 5. 8 组追问应答

> 本节每条的「应答」为口语话术（允许第一人称），「要点」为声明式落点。

### Q1｜为什么自己写 C++ 引擎和连通域，而不用 `scipy.ndimage.label`？

> 应答：「三个原因。第一是想真正掌握底层算法——Two-Pass + 并查集、沿像素边界追踪、闭曲线 Douglas-Peucker，
> 这些在图像分割与矢量化里是经典；第二是性能，C++ 引擎批量处理比 Python 侧调用更可控；第三，也是最主要的一点，
> 直接调库会掩盖几何语义问题——比如一个连通域含洞时边界被劈成多条弧、每条弧该不该各自成一个 Feature。
> 我写引擎时才踩到并修掉了这个坑：旧实现给每条环各发一个 Feature，属性面积被重复计，把 720 900 平方米虚报成了一倍。」

**要点**：缺陷为 `docs/algorithm.md` §8.1 `D-3`；修正 = 一个 Region 一个 Feature；守护测试
`engine/tests/test_geojson.cpp:112`、`:128`、`:140`。

### Q2｜CVA 与 Otsu 的原理？阈值怎么来的？精度多少？

> 应答：「CVA 是变化向量分析——对每个像素算两期影像各波段的差向量，取欧氏距离模长作为变化强度；
> 再用 Otsu 最大化类间方差自动定阈值，不需要人工调参。基线夹具上阈值是 5.916767423962816，取契约示例写法就是 5.9168。
> 精度指标方面，当前仓库没有单独的精度评估模块（IoU 之类尚未实现），这一点我不掩饰；现有保障是『数值可复现』——
> Otsu 阈值与变化像素 7 209 由仓库自带的黄金基线在每一步门禁里逐字核对，并有独立于被测实现的第三方复算。」

**要点**：阈值锚点 `scripts/verify_baseline.py:129-153`；独立复算见 `docs/verification/phase-2.md` §4；
`IoU / 精度评估模块` 状态 = **未实现（待核实：无对应文件）**，不得声称已有精度数字。

### Q3｜基线数字怎么保证不被改坏？

> 应答：「靠分层门禁加独立复算。仓库自带五个校验脚本，CI 里一次性串联：黄金基线判不变量与语义断言、
> 绑定层契约、配置一致性、版本同号、容器资产静态判据。基线分组是 §7.1 十一项不变量、§7.2 两项缺陷基线、
> §7.3 七项语义断言，全部通过才算绿。另外关键数字不靠被测实现自证——Otsu 与连通域由不 import 仓库实现的独立脚本复算，
> 几何面积则用第三方库 shapely 从坐标重算，容差上限 1e-6%。」

**要点**：`scripts/verify_baseline.py`（§7.1 11/11 + §7.2 2/2 + §7.3 7/7）；独立复算 `docs/verification/phase-2.md` §4；
几何面积独立重算 `docs/verification/phase-2.1.md` §3／§7。

### Q4｜你说的「面积虚报一倍」到底怎么发生的？

> 应答：「根因是归属语义错了。基线样本是单个连通域，但它的边界因为追踪起点的处理问题被劈成了两条弧。
> 旧实现的做法是『每条环生成一个 Feature』，同时把整个区域的 `area_m2` 复制到每个 Feature 的 properties 上。
> 两条弧就带了两份 720 900，输出合计变成 1 441 800，正好虚报一倍。修法是把语义改成『一个 Region 一个 Feature』，
> 首环作外环、其余作内环，属性只出现一次。修完之后 Feature 数从 2 变成 1，合计回到 720 900。」

**要点**：编号必须写全为 `docs/algorithm.md` §8.1 `D-3`（引擎）；成因链 `debug-lessons.md` §3；
转正判据 `docs/verification/phase-2.md` §3.1（`Feature=1`、`area_sum=720900.0`）。

### Q5｜跨平台怎么做的？Windows 和 Linux 差别大吗？

> 应答：「差别比想象的大，而且不是『代码能不能编译』的问题，是『每个平台都能编译并运行』的问题。
> 本机 MinGW 编出的 `.dll` 在 Linux 上完全不可用，必须各自编译。为此我做了双平台 CI 矩阵，两平台都是必过项。
> 真实跑下来暴露了五处只有 runner 上才看得见的缺陷，比如 `setup-msys2` 在 release 模式其实装到临时目录而不是 `C:\msys64`，
> 比如 Catch2 中文用例名在 runner 的 1252 代码页下会被替换成问号导致零匹配，还有 `os.add_dll_directory` 在 Linux 上根本不存在。
> 这些问题的共同点是本地中文 Windows 完全看不出来。」

**要点**：`docs/verification/phase-6.md` §8 五处缺陷；`_spatial` 唯一加载点 `backend/src/rschange/spatial/loader.py`
（经 `getattr(os, "add_dll_directory", None)` 取值）；`.github/workflows/ci.yml`。

### Q6｜前后端字段怎么保证不漂移？

> 应答：「用一条两段契约流水线，每段各有独立门禁、缺一不可。第一段是 pydantic 生成 OpenAPI，用字节级 `--check` 守住；
> 第二段是从入库的 OpenAPI 生成前端 TypeScript 类型，CI 里重新生成一次再用工作树状态比对，任何漂移都会红。
> 第二段不是装饰——我做过变异实验：故意改后端字段类型并重新生成 OpenAPI，第一段是正当放行的，只有第二段能拦下来。
> 另外契约字段从 13 收缩到 12、删掉恒为 success 的 `status` 时，我在前端用 `@ts-expect-error` 做了编译期断言，
> 字段一旦被加回来编译就会失败。」

**要点**：第二段独占判别力变异实验 `docs/verification/phase-6.md` §7；契约断言 `frontend/src/api/types.ts:52-53`；
`DetectionResponse` 12 字段 `schemas/detection.py:56-74`。

### Q7｜分层和可插拔怎么落地的？怎么证明新增算法不改核心？

> 应答：「依赖方向是单向的：后端到 `_spatial` 再到 libspatial 再到 GDAL，没有回指。
> 装配点我收敛到唯一一处，就是构建运行上下文那个函数；流水线在运行期完全不 import 具体算法，
> 检测器和后处理器是必填的注入参数——类型只在 `TYPE_CHECKING` 块里出现。证明方式不是靠嘴说：
> 我新增了一个检测器，跑完完整流水线，`pipeline` 那个文件的哈希前后完全一致，产物也和基线一致，7209 像素、720900 平方米。」

**要点**：装配点 `backend/src/rschange/api/deps.py:53-76`；运行期零 import
`backend/src/rschange/pipeline/change_detection.py:51-58`；哈希不变实证 `docs/verification/phase-3.md` §5。

### Q8｜容器测了吗？端到端跑了吗？

> 应答：「这个我必须如实说：**容器没有构建，端到端也没有实测**。当时受环境限制，容器化只写了配置，
> G6.2 和 G6.3 是用 19 条静态判据顶上的，CI 里也没有容器构建步骤。所以我能保证的是配置层面自洽——
> 比如上传上限三方同号、nginx 上限不小于后端上限，但『`docker-compose up` 之后真能返回基线数字』这件事本身没验证。
> 前端也一样：三图的像素叠加只做了代码级审查，没在真实浏览器里跑过。这些都在验收报告的未关闭项里写着。」

**要点**：诚实边界见 §6；来源 `docs/verification/phase-6.md` §11 O1；`docs/verification/phase-4.md` §11。

---

## 6. 诚实边界

> 本节为声明式，列出**当前仍未做到**的事项，供被追问时如实回答，**禁止**隐去。逐条给出可核查来源。

| # | 未做到 / 未验证 | 说明 | 来源 |
|---|---|---|---|
| 1 | **容器未构建、端到端未实测** | G6.2（`docker-compose up` 后返回基线数字）与 G6.3（>1 MB 上传不再 413）均**只经 19 条静态判据**，Actions 中**无容器构建步骤**；镜像实际构建、compose 实际启动、健康检查实际生效、命名卷持久化均未验证 | `docs/verification/phase-6.md` §4／§5／§11 O1 |
| 2 | **前端 `image_corners` 无地图定位** | 契约描述「用于地图定位」，但前端**未引入地图库**，仅以文本表格展示四角经纬度 | `docs/verification/phase-4.md` §11-2；`docs/verification/phase-5.md` §11-3 |
| 3 | **上传「拒收 → 提示」端到端链未覆盖** | `jsdom` 的 `user.upload()` 直接派发 `change` 事件、**绕过** dropzone 的 `accept` / `maxSize` 过滤，故该链路需真实浏览器（Playwright 一类）才能覆盖；现有测试改为断言 `accept` 属性而非「文件被拒收」 | `frontend/src/features/detection/components/UploadPanel.test.tsx:195-198`；`frontend/package.json`（`jsdom ^26.0.0`） |
| 4 | **`mypy` 不覆盖 `scripts/`** | `[tool.mypy] files = ["backend/src"]`，仅覆盖后端产品代码 36 个源文件；门禁脚本本身未纳入 strict 类型检查 | `pyproject.toml:104-105` |
| 5 | **引擎不可用时部分测试跳过而非失败** | `backend/src/rschange/tests/conftest.py` 的 `engine_ready` 夹具使 `test_api.py` 等用例在 `_spatial` 不可用时**跳过**（skip），非报错 | `backend/src/rschange/tests/conftest.py`；`docs/verification/phase-6.md` 报告口径为「148 passed」 |
| 6 | **UI 三图像素叠加未运行时验证** | Phase 4 的 G4.3 要求真实浏览器 + 运行中后端核对三图，环境不具备，仅作代码级审查；Phase 5 的 `test_wire_format` 只补上了**契约响应层**的运行时验证 | `docs/verification/phase-4.md` §3.3／§6.3；`docs/verification/phase-5.md` §11-5 |
| 7 | **无精度评估模块** | CVA / Otsu 的「正确性」当前以**数值可复现**（黄金基线）与独立复算保障，**未**实现 IoU 等精度指标 | 旧素材 `project2-lessons-and-interview.txt` §二（「精度指标（IoU）后续可以补」）；仓库内无对应实现文件 |
| 8 | **构建期依赖 GitHub 网络** | `engine/CMakeLists.txt` 经 `FetchContent` 取 `nlohmann/json` 与 `Catch2`；离线或网络受限环境下 configure 会失败，CI 已加 `_deps` 缓存缓解但首次构建仍依赖上游 | `docs/verification/phase-2.md` §6 O2；`docs/verification/phase-6.md` §11 O7 |
| 9 | **`verify_containers.py` 不替代真实构建** | 19 条判据均为静态判定，脚本自身与文档均声明其**不替代**真实构建 | `scripts/verify_containers.py`；`debug-lessons.md` L8 |
| 10 | **本机覆盖配置不入库** | `config/local.toml`（含本机 DLL 目录）与 `engine/CMakeUserPresets.json` 已被 git 忽略，属预期；CI 无该覆盖时须用环境变量提供运行期目录 | `docs/verification/phase-3.md` §10 S2；`config/default.toml:21` |

> **讲述纪律提醒**：以上 10 条中，凡涉及「未验证」的，在讲述时**禁止**表述为「已验证」；
> 凡涉及数字的，必须能由给出的 `文件:行号` 或验收报告章节复核。

---

*本文件为 Phase 7 文档产出。所有 `文件:行号` 均可在当期仓库 HEAD（`dc8ee2b`，版本 `1.0.0`）上复核；
标注 `待核实` 或「未实现」者，禁止在对外材料中当作既成事实引用。*
