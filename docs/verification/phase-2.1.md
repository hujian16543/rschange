# Phase 2.1 验收报告 · 轮廓硬化修复

> 独立验收官出具。证据来自真实命令输出，未作人工修饰。除本文件外，本阶段**仅新增**
> `docs/verification/phase-2.1.md`，未修改引擎源码、脚本、夹具、配置或测试。
> 严格边界：全程**禁止任何 git 命令**（status/log/add/commit/diff/stash 等）；
> 唯一允许写入的文件即本文件；禁止 `pip install`、禁止裸 `python`/`pip`、禁止降低或跳过门禁。
> 故本报告**未**独立反查提交哈希与提交范围（git 被禁），被验范围以任务书给出的 5 项改动为准，
> 基准锚点 `v0.2.0 / main = 2664241` 取自任务书。

## 1. 验收对象与基准

| 项 | 内容 |
|---|---|
| 上一验收锚点 | Phase 2 报告（`docs/verification/phase-2.md`），对应 `v0.2.0` / `main = 2664241` |
| 本阶段被验对象 | 相对 v0.2.0 的 4 项代码改动 + 1 项文档入库 |
| 被验提交范围 | 任务书声明 5 个提交主题：①轮廓改沿像素边界（crack following）；②`gdal_registration_count()` 收归内部头；③配置模板与真相一致 + `verify_config.py`；④lint 策略（RUF001/002/003 + `scripts/`）；⑤`docs/algorithm.md` 入库。**提交哈希未独立反查（git 被禁）** |

### 1.1 五项改动要点（任务书口径）

1. **轮廓改沿像素边界追踪** —— 导出 GeoJSON 的几何面积精确等于 `area_m2`，与 GDAL 栅格转多边形语义对齐；`simplify_tolerance` 默认值改为 `0.0`，且容差 ≤0 时不简化。
2. **`gdal_registration_count()` 测试探针收归内部头** —— 不再经 `SPATIAL_API` 出现在 `engine/include/spatial/raster.hpp`，不进 `libspatial.dll` 导出表；内部测试仍可用。
3. **配置模板与真相一致** —— `config/local.example.toml` 示例值须与 `config/default.toml` 及 CMake 预设实际产物目录一致；新增 `scripts/verify_config.py` 作门禁。
4. **lint 策略落地** —— `pyproject.toml` 忽略 `RUF001/002/003`（中文全角标点误报），lint 范围显式纳入 `scripts/`。
5. **`docs/algorithm.md` 入库** —— 须与现行实现一致，不得残留描述已删除函数的内容作为「现行实现」。

## 2. 门禁逐条结果表

| # | 命令（来源：任务书门禁清单） | 关键原始输出 | 判定 |
|---|---|---|---|
| G1 | `cmake --build build/dev-win`（engine/ 下） | `ninja: no work to do.` | **通过** —— 先前已构建，产物最新 |
| G2 | `ctest --test-dir engine/build/dev-win --output-on-failure` | `100% tests passed, 0 tests failed out of 40`；`Total Test time = 8.25 sec` | **通过** —— 40/40 |
| G3 | `uv run python scripts/verify_baseline.py --phase 2` | `§7.1 11/11`、`§7.2 2/2`、`§7.3 7/7`，结论「通过 —— Phase 2 预期状态已达成」 | **通过** |
| G4 | `uv run python scripts/verify_bindings.py` | `失败项合计 = 0 -> 通过` | **通过** |
| G5 | `uv run python scripts/verify_config.py` | `判定项 6 项（跳过 0 项），不通过 0 项`，结论「通过」 | **通过** |
| G6 | `uv run ruff check .` | `All checks passed!` | **通过** |
| G7 | `uv run ruff format --check .` | `7 files already formatted` | **通过** |

**总判定依据（门禁）**：G1–G7 全部通过。CTest 用例数由 Phase 2 的 **38** 增至 **40**（+2，新增几何面积恒等式与追踪顺序无关性两项断言，见 §6）。

## 3. 独立核对 1：几何面积非循环论证

**方法**：直接阅读 `scripts/verify_baseline.py` 源码，定位几何面积的计算路径。

**证据**：
- `scripts/verify_baseline.py:475` — `polygon = shapely_shape(feature["geometry"])`（导入自 `shapely.geometry.shape`，见 :454-456）。
- `scripts/verify_baseline.py:477` — `geometry_area += float(polygon.area)`。
- `scripts/verify_baseline.py:489-490` — `reported_area` 取自引擎 `properties.area_m2` 求和：`reported_area = area_sum + sum(float(f["properties"]["area_m2"]) for f in multi_features)`。
- `scripts/verify_baseline.py:516-524` — 「几何面积 == 上报面积」判据以 `deviation = (geometry_area - reported_area)/reported_area*100` 计算，容差 `GEOMETRY_TOL_PERCENT = 1e-6`（:147）。

**结论**：几何面积由 **shapely 独立算出**（第三方库），**不是**调用被测引擎的 `signed_area_twice` 或回读 `area_m2`。坐标本身来自引擎 `mask_to_geojson` 输出（属被测对象，允许调用），但面积值由 shapely 从坐标重算，与引擎上报的 `area_m2` 相互独立比对。**该项非自证，证据有效。**（透明说明：坐标溯源自引擎，故该判据验证的是「引擎的 `area_m2` 与其自身几何的 shapely 面积一致」，而非用与引擎完全无关的外部几何——这满足任务书「由独立第三方库算面积」的要求。）

## 4. 独立核对 2：DLL 导出表

**方法**：`objdump -p engine/build/dev-win/libspatial.dll`（objdump 位于 `C:/Users/Hujian/DevCode/msys64/mingw64/bin/objdump.exe`），过滤导出表中含 `spatial` 的符号。

**导出表中全部 `spatial::` 符号（9 个，C++ mangled 名 → 解调）**：

```
[0] _ZN7spatial11read_raster...                      → spatial::read_raster
[1] _ZN7spatial12write_raster...                     → spatial::write_raster
[2] _ZN7spatial15extract_regions...                  → spatial::extract_regions
[3] _ZN7spatial16extract_boundary...                 → spatial::extract_boundary
[4] _ZN7spatial17simplify_boundary...                → spatial::simplify_boundary
[5] _ZN7spatial18print_gdal_versionEv                → spatial::print_gdal_version
[6] _ZN7spatial18regions_to_geojson...               → spatial::regions_to_geojson
[7] _ZN7spatial19point_line_distance...              → spatial::point_line_distance
[8] _ZN7spatial23ensure_gdal_initializedEv           → spatial::ensure_gdal_initialized
```

**grep `gdal` 命中**：仅 `libgdal-38.dll` 的导入符号（`GDALAllRegister`/`GDALOpen`/…）及上述 `print_gdal_version`/`ensure_gdal_initialized` 两条命名含 `gdal` 的公开符号。**`gdal_registration_count` 在导出表中不存在。**

**结论**：导出表共 9 个 `spatial::` 符号，均不含 `gdal_registration_count`。验收对象 ② 达成。

## 5. 独立核对 3：公开头 grep

**方法**：在 `engine/include/` 下递归 grep `gdal_registration_count`。

**原始输出**：
```
=== grep gdal_registration_count in engine/include ===
(no matches in include)
```
对全仓库（排除 `build/`）源码再查：仅出现在 `engine/src/gdal_init.cpp`、`engine/src/internal/gdal_registry.hpp`、`engine/tests/test_raster_io.cpp`。头文件位置为 `engine/src/internal/gdal_registry.hpp:44`：`SPATIAL_INTERNAL int gdal_registration_count() noexcept;`，并由 `engine/src/internal/gdal_registry.hpp:34` 定义 `SPATIAL_INTERNAL __attribute__((visibility("hidden")))`（配合核对 2 的不可见性）。

**结论**：公开头 `engine/include/` 命中数 = **0**。验收对象 ② 达成。

## 6. 独立核对 4：夹具期望值自洽（自实现 4 邻域连通）

**方法**：自写 Python（**不依赖 scipy / 被测代码**），读取 `engine/tests/fixtures/multi_region_mask.raw`（7680 字节 = 120 列 × 64 行，每字节一像素，非 0 为变化像素），以纯 Python 栈式 BFS 实现 4 邻域连通域标记；独立统计连通域个数、各域像素数、首现顺序、以及洞（由边界洪泛背景后未达边界者）所在域。

**原始数字**：
```
INDEP#4 components(4-conn) = 6
INDEP#4 pixel counts by raster-scan first appearance = [100, 200, 35, 138, 185, 5]
INDEP#4 sum pixels = 663
INDEP#4 hole pixels = 25
INDEP#4 hole-adjacent component ids (raster order 1-based) = [5]
INDEP#4 hole enclosed component pixel counts = {5: 185}
INDEP#4 largest component id (1-based) = 2  pixels = 200  has_hole = False
```

**与 `multi_region_mask.json` 期望值逐项对比**：

| 项 | 独立算出 | JSON 期望 | 一致 |
|---|---|---|---|
| 连通域个数 | 6 | `components: 6` | 是 |
| 退化项个数 | 0 | `degenerate_components: 0` | 是 |
| 期望 Feature 数 | 6 | `expected_feature_count: 6` | 是 |
| 各域像素数（首现序） | `[100,200,35,138,185,5]` | regions pixel_count `[100,200,35,138,185,5]` | 是（multiset 相等） |
| 像素合计 | 663 | `changed_pixels: 663` | 是 |
| 洞总数 | 1（25 洞像素） | `expected_holes_total: 1` | 是 |
| 洞所在域 | **label 5（ring_d，185 像素）** | `ring_d` 的 `holes: 1` | 是 |

**重要澄清（防误读）**：任务书问「最大的区域是否含洞」。按像素数，**最大区域是 blob_b（label 2，200 像素），它不含洞**；洞位于 **ring_d（label 5，185 像素）**。夹具 JSON 的声明（ring_d 含 1 洞、洞总数 1）与独立结果**完全吻合**，不存在不一致；仅须注意「最大区域」按像素数衡量时并非含洞者。

**结论**：夹具期望值自洽，连通域计数由独立实现得出（非被测代码自证）。验收对象 ①/⑤ 的夹具基础成立。

## 7. 独立核对 5：几何面积恒等式

**方法**：调用被测对象 `_spatial.mask_to_geojson` 产多区域 GeoJSON，再用 **shapely** 独立计算每条 Feature 几何面积，验证 `几何面积 == pixel_count × 单像元面积(100)` 且 `== area_m2`，合计 == 上报面积合计。

**原始数字**：
```
INDEP#5 label=1 pc=100 shapely_area=10000.0000 pc*100=10000.0000 area_m2=10000.0000 ok=True
INDEP#5 label=2 pc=200 shapely_area=20000.0000 pc*100=20000.0000 area_m2=20000.0000 ok=True
INDEP#5 label=3 pc=35  shapely_area=3500.0000  pc*100=3500.0000  area_m2=3500.0000  ok=True
INDEP#5 label=4 pc=138 shapely_area=13800.0000 pc*100=13800.0000 area_m2=13800.0000 ok=True
INDEP#5 label=5 pc=185 shapely_area=18500.0000 pc*100=18500.0000 area_m2=18500.0000 ok=True
INDEP#5 label=6 pc=5   shapely_area=500.0000    pc*100=500.0000    area_m2=500.0000    ok=True
INDEP#5 total shapely= 66300.0  total area_m2= 66300.0  expected 66300.0
INDEP#5 identity holds: True
```

**说明**：`label=5` 含洞（外环围 210 格点、内环 25 格点），shapely 算得 `210−25 = 185` 格点 ×100 = 18500，与 `pixel_count=185`、`area_m2=18500` 三者一致，证实「像素角点基准下几何面积 == 成员像素数」（含洞时即前景净像素）。

**结论**：每个 Feature 几何面积 == `pixel_count×100` == `area_m2`，合计 66300.0 = 上报面积合计。验收对象 ① 的「几何面积精确等于 area_m2」由独立 shapely 复算证实。基线单区域（7209 像素 → 720900 m²）的恒等式由 CTest 用例 #33「几何面积精确等于 area_m2（Phase 2.1 的几何基准）」与 `verify_baseline.py` §7.3「几何面积 == 上报面积（像素角点基准）」偏差 0.00%（787200.0 m² = 720900 基线 + 66300 多区域）共同覆盖。

## 8. 独立核对 6：容差默认值与 ≤0 分支

**方法**：grep `simplify_tolerance` 于 `engine/include` 与 `engine/src`，并阅读 `simplify.cpp` 相关分支。

**证据**：
- `engine/include/spatial/geojson.hpp:23` — `double simplify_tolerance = 0.0;`（注释：`/// 默认 0.0，即不简化`）。
- `engine/src/simplify.cpp:99-103`：
  ```cpp
  if (tolerance <= 0.0) {
      // 容差 0 的语义是「面积精确守恒」……顶点恰好落在弦上时距离为 0，会被判为可删，几何随之改变。
      return ring;
  }
  ```
- `engine/src/simplify.cpp:96-98` — `if (count < 4) { return ring; }`（少于 4 点不简化）。

**结论**：默认 `simplify_tolerance = 0.0`；当 `tolerance <= 0.0` 时直接短路返回原环（不简化），由构造保证「容差 0 → 几何面积精确守恒」。验收对象 ① 达成。`docs/algorithm.md` §4.4 / §10 亦将该分支列为「禁止移除」项，与代码一致。

## 9. 文档一致性（验收对象 ⑤）

- `docs/algorithm.md` §3.6（:549-558）明确 `find_holes` 与 `pixels_around` **整体删除**，并以「旧 `find_holes`…旧 `pixels_around`…」的过去式描述，将其作为被删除项，**未**以「现行实现」口吻呈现 → 满足「不得残留描述已删除函数作为现行实现」。
- 文档 §3（crack following）、§4（闭曲线 DP）、§4.4（容差≤0 短路）、§5.4（几何面积恒等式）、§8.3（Phase 2.1 改动表）均与源码（核对 1/2/3/6）及实测（核对 4/5）逐条一致。
- `docs/algorithm.md` §5.4 表载多区域「几何面积合计 66 300 m² == 属性面积合计 66 300 m²，偏差 0.00 %」，与核对 5 的 66300.0 精确吻合。
- `pyproject.toml:79` `ignore = ["E501","RUF001","RUF002","RUF003"]` → 验收对象 ④ 的 RUF 忽略落地；`src = ["backend/src","scripts"]`（:53）+ `extend-exclude = ["docs"]`（:64），且 `ruff check .` 通过、`ruff format --check .` 报告 7 文件已格式化 → `scripts/` 确在 lint 范围（验收对象 ④ 达成）。
- `scripts/verify_config.py` 存在并 G5 通过（6/6），覆盖 `local.example.toml` 与 `default.toml`/CMake 预设一致性 → 验收对象 ③ 达成。

## 10. 与前序锚点（Phase 2）对比

| 指标 | Phase 2 锚点 | Phase 2.1 实测 | 漂移判定 |
|---|---|---|---|
| CTest 用例数 | 38 | **40** | +2（新增几何面积恒等式、追踪顺序无关性），非回归 |
| §7.1 | 11/11 | 11/11 | 零漂移 |
| §7.2 | 2/2 | 2/2 | 稳定 |
| §7.3 | 6/6 | **7/7** | +1（新增「几何面积 == 上报面积（像素角点基准）」） |
| Feature 数（多区域） | 5（line_e 被剔） | **6** | 预期变更：角点基准下 1 像素宽结构合法（文档 §3.2/§8.3 已裁定） |
| 属性面积合计 | 720900 m²（基线） | 720900 m²（基线）+ 66300 m²（多区域） | 稳定 |
| 多区域几何 vs 上报偏差 | −17.63 % | **0.00 %**（66300 == 66300） | 修复达成（像素角点基准） |
| `gdal_registration_count` 在公开头/DLL | 存在（Phase 2 观察项 O1） | **0 命中 / 不导出** | 已清理 |
| 配置模板一致性门禁 | 无 | 6/6 通过 | 新增达成 |

> **Phase 2 列数值来源（均取自既有验收报告，非本次独立反查；git 被禁，未重跑 v0.2.0 产物）**：
> CTest `38` 见 `docs/verification/phase-2.md` §2.3「用例总数：**38**」；§7.3 `6/6` 见 §3.1「§7.3 语义断言 6/6 通过」；
> 多区域 Feature `5` 与偏差 `−17.63 %` 见 §4.2/§4.3；`gdal_registration_count` 在 Phase 2 公开头/DLL 见 §6 观察项 O1。
> 本报告 §2（G2/G3）已给出对应项的本次实测（40/40、§7.3 7/7、0 命中 / 不导出）。

## 11. 未通过项 / 存疑项

**不通过项：无。**

**存疑 / 澄清项（非缺陷，须记录以免误判）**：
- **S1（澄清，非缺陷）**：任务书问「最大的区域是否含洞」。独立结果：按像素数最大者是 blob_b（label 2，200 像素）**不含洞**；洞位于 ring_d（label 5，185 像素）。夹具与 `docs/algorithm.md` 的声明均正确，**无任何不一致**，仅修正「最大区域含洞」这一措辞假设。
- **S2（信息项）**：`libspatial.dll` 导出符号由 Phase 2 的 5 个增至本次实测的 9 个（`extract_regions`/`extract_boundary`/`simplify_boundary`/`regions_to_geojson`/`point_line_distance`/`ensure_gdal_initialized` 等随引擎能力增长），属正常演进，非泄漏。Phase 2 时的「5 个」来源：`docs/verification/phase-2.md` §1 G2.2（及 §2.5/§4.4）——「`objdump -p` 导出表含 5 个 `spatial::*` 符号」，非本次独立反查（git 被禁，未重跑 v0.2.0 产物）。
- **S3（信息项）**：本验收**未重新配置 CMake**（G1 直接 `ninja: no work to do`，产物已最新），故未触发 `FetchContent` 联网（Phase 2 观察项 O2）。若后续需重配，必须带 `FETCHCONTENT_SOURCE_DIR_JSON` / `FETCHCONTENT_SOURCE_DIR_CATCH2` 指向 `engine/build/dev-win/_deps/*-src`，否则将联网拉 GitHub 超时。

## 12. 总判定

# 通过

依据：门禁 G1–G7 全部通过（CTest 40/40、`verify_baseline` §7.1 11/11 §7.2 2/2 §7.3 7/7、`verify_bindings` 0 失败、`verify_config` 6/6、`ruff check`/`ruff format --check` 通过）；六项独立核对（几何面积由 shapely 独立算出、DLL 导出表无 `gdal_registration_count`、公开头 0 命中、自实现连通域与夹具完全一致、几何面积恒等式 66300.0 三方相等、容差默认 0.0 且 ≤0 短路）全部确认；`docs/algorithm.md` 与实现一致且正确标注已删除函数。相对 Phase 2 锚点无回归，Phase 2.1 四项代码改动与一项文档均达成。

## 13. 已知遗留问题清单

| 项 | 状态 | 责任阶段 |
|---|---|---|
| S3：CMake 配置期 `FetchContent` 依赖 GitHub 网络（仅在重配时触发；本次未触发） | 已知前提 | 后续 CI 须保证网络或缓存 `_deps` |
| S2：DLL 导出符号随引擎增长至 9 个 | 正常演进，非缺陷 | 终验记录 |
| S1：多区域「最大区域含洞」措辞假设易误读（实测洞在 ring_d，非像素最大域） | 已澄清，非缺陷 | 文档可加注（非阻断） |
| §5.1 几何基准「是否改沿像素边界追踪」原属待裁定开放项 | **已闭环**：由被验改动①执行，并记入 `docs/contracts.md` §9 `v0.2.1`（:180）「几何基准由像素中心改为**像素角点**…几何面积与 `area_m2` 一致（§5.1）」；§5.1（:106-121）当前偏差为 **0.00 %**，`−31.4 %` 列于「Phase 2 的历史偏差（已修正）」（:123-131），非遗留缺陷 | 已裁定并执行，见本报告 §7 |
| 后端（Phase 3）须复用本阶段 `_spatial` 契约，禁止改签名 | 约束生效中 | Phase 3 |
