# Phase 2 验收报告 · C++ 引擎解耦

> 证据来自真实命令输出，未作人工修饰。除本文件外，本阶段仅新增 `docs/verification/phase-2.md`，
> 未修改引擎源码、脚本、夹具、配置或测试。所有 git 命令均带
> `-c core.fscache=false -c core.autocrlf=false -c merge.autostash=false` 三项安全项。

## 1. 阶段出口门判定表

| # | 判据（来源：执行手册 §Phase 2 出口门） | 结论 | 证据 |
|---|---|---|---|
| G2.1 | `ctest --preset dev-win` 全绿 | **通过** | 38/38 通过，0 失败 |
| G2.2 | `_spatial` 在新路径下可 `import`，符号齐全 | **通过** | `import` 成功；`objdump -p` 导出表含 5 个 `spatial::*` 符号，四个公开函数均可 `hasattr` |
| G2.3 | §7.1 全部不变（阈值 `5.9168`、像素 `7209/65536`） | **通过** | `verify_baseline --phase 2`：§7.1 `11/11`，阈值 `5.9168`、变化像素 `7209` 逐字命中 |
| G2.4 | §7.2 全部由 FAIL 转 PASS（Feature `2→1`、面积 `1441800→720900`） | **通过** | §7.2 `2/2`：`Feature=1`、`area_sum=720900.0` |
| G2.5 | §7.3 语义断言全部成立 | **通过** | §7.3 `6/6`：含多区域 label 顺序、退化剔除、洞环、GEOS 合法性 |

**总判定**：**通过** —— 允许打 tag `v0.2.0`。
依据：G2.1–G2.5 全部通过；§7.1 不变量相对 Phase 1（同为 `11/11`）零漂移；§7.2 缺陷基线已从 FAIL 转正；§7.3 新语义断言全部成立，且无 `SKIP` 残留。

## 2. 环境与构建（真实输出）

### 2.1 `cmake --list-presets`

```text
（在 engine/ 目录下执行）
Available configure presets:
  "local-win"     - 本机 Windows / MSYS2 mingw-w64
  "dev-win"
  "dev-linux"
  "release-win"
  "release-linux"
```

`engine/CMakeUserPresets.json`（`local-win`）须为未入库的本机预设：

```text
$ git check-ignore -v engine/CMakeUserPresets.json
.gitignore:48:engine/CMakeUserPresets.json	engine/CMakeUserPresets.json
```

### 2.2 构建

```text
$ cmake --build engine/build/dev-win
ninja: no work to do.
```

（构建目录 `engine/build/dev-win` 已由 `local-win` 预设预配置；产物已是最新。）

### 2.3 CTest（先注入 MSYS2 runtime PATH）

```text
$ PATH="/c/Users/Hujian/DevCode/msys64/mingw64/bin:$PATH" ctest --test-dir engine/build/dev-win --output-on-failure
...
100% tests passed, 0 tests failed out of 38
Total Test time (real) =   2.70 sec
```

用例总数：**38**。用例名覆盖 `raster` / `labeling` / `contour` / `simplify` / `geojson` / `multi_region` / `pipeline` 七组（非仅方形影像——含 `非方形多波段往返`、`非方形单波段往返保留 H 与 W`、`多区域非方形影像行列不得互换` 等针对性用例）。

### 2.4 告警即错误是否生效

`SPATIAL_WARNINGS_AS_ERRORS` 在 `dev-win` 预设链下为 `ON`（`CMakeLists.txt:37` 默认 `ON`，
`engine/build/dev-win/CMakeCache.txt` 第 548 行 `SPATIAL_WARNINGS_AS_ERRORS:BOOL=ON`）。
强制重编一个源文件以验证零告警：

```text
$ touch engine/src/version.cpp
$ cmake --build engine/build/dev-win --target spatial 2>&1 | grep -i -E "warning|error"
（无任何匹配行，退出码 0）
$ cmake --build engine/build/dev-win --target spatial   # 复核
ninja: no work to do.
```

判定：在 `-Werror` 生效的前提下，强制重编后构建成功且无 `warning`/`error` 输出行 → **零告警成立**。
（判据方式说明：直接以 `-Werror` 为开关——若存在告警则构建必失败；配合 `grep` 无命中，可判定零告警。）

### 2.5 `cmake --install` 落点核对

```text
$ cmake --install engine/build/dev-win --prefix <临时目录>
-- Installing: .../lib/libspatial.dll.a
-- Installing: .../bin/libspatial.dll
-- Installing: .../include/spatial/{contour,export,geojson,labeling,raster,region,simplify}.hpp   (7 个头文件)
-- Installing: .../lib/_spatial.cp314-win_amd64.pyd
```

落点齐全合理：共享库（`bin/libspatial.dll` + 导入库 `lib/libspatial.dll.a`）、公开头（`include/spatial/`）、
Python 扩展（`lib/_spatial.cp314-win_amd64.pyd`）。ABI 标签 `cp314` 与 `docs/contracts.md` §2 一致。

### 2.6 工作区干净性

```text
$ git status --short
（空）
```

`engine/build/`、`engine/CMakeUserPresets.json`、`config/local.toml`、`.venv` 均被 `.gitignore` 忽略
（逐一 `check-ignore` 命中），未入库泄漏。

## 3. 仓库自带校验工具（真实输出）

### 3.1 `verify_baseline.py --phase 2`

```text
组   判定项                                  期望                          实际                          结果   备注
----------------------------------------------------------------------------------------------------------------
7.1  影像形状                                [3, 256, 256]                 [3, 256, 256]                 PASS
7.1  影像 dtype                              uint16                        uint16                        PASS
7.1  geo_transform                           [500000.0000, 10.0000, 0.0000,[500000.0000, 10.0000, 0.0000,PASS
7.1  投影含标记                              UTM zone 50N                  True                          PASS
7.1  宽/高/波段                              256/256/3                     256/256/3                     PASS
7.1  Otsu 阈值                               5.9168                        5.9168                        PASS
7.1  变化像素（原始）                        7209                          7209                          PASS
7.1  变化像素（后处理后）                    7209                          7209                          PASS
7.1  变化率                                  0.110001                      0.110001                      PASS
7.1  真实变化面积 m²                         720900.0                      720900.0                      PASS
7.1  每个环首尾闭合                          True                          True                          PASS
7.2  GeoJSON Feature 个数                    1                             1                             PASS   旧引擎实际输出 2（缺陷：单连通域被劈成多段弧）
7.2  属性面积合计 m²                         720900.0                      720900.0                      PASS   旧引擎实际输出 1441800.0（缺陷：面积重复计 2 倍）
7.3  Feature 数 == 连通域个数                1                             1                             PASS   连通域个数由 scipy 独立计算，不依赖被测代码
7.3  面积合计 == 像素数 × 单像元面积         720900.0                      720900.0                      PASS
7.3  夹具元数据顺序 == scipy 首次出现顺序    [100, 200, 35, 138, 185, 5]   [100, 200, 35, 138, 185, 5]   PASS   元数据由几何定义直接写出，与任何实现无关
7.3  多区域 label 序列（退化项剔除后）       [1, 2, 3, 4, 5]               [1, 2, 3, 4, 5]               PASS   连通域 6 个，其中 1 个退化轮廓不产出 Feature
7.3  多区域 Feature 顺序 == scipy 顺序       [100, 200, 35, 138, 185]      [100, 200, 35, 138, 185]      PASS   期望顺序为各连通域首次出现的 raster-scan 位置序
7.3  多边形可被 GEOS 解析且不自交            全部合法（6 个）              6/6 合法                      PASS   洞环合计 1 个；几何面积合计 754000.0 m²，上报面积合计 786700.0 m²，偏差 -4.16%
----------------------------------------------------------------------------------------------------------------
  §7.1 不变量           11/11 通过
  §7.2 缺陷基线          2/2 通过
  §7.3 语义断言          6/6 通过
期望：三项全部通过
结论：通过 —— Phase 2 预期状态已达成
```

`grep -c SKIP` 结果：**0**（确认输出中不存在 `SKIP` 字样）。

§7.1 为 `11/11`，与 Phase 1 报告（`docs/verification/phase-1.md`）的 `11/11` **完全相同** —— 不变量零漂移。
§7.2 由 Phase 1 的 `0/2 FAIL` 转为 `2/2 PASS`；§7.3 由 `0/2`（含 2 项 SKIP）转为 `6/6 PASS`。

### 3.2 `verify_bindings.py`

```text
== 1. 模块与公开函数 ==
  OK   _spatial 导入成功
  OK   四个公开函数齐备  read_raster, write_raster, mask_to_geojson, print_gdal_version
== 2. 2D 非方形掩膜写读一致（D-1）==
  OK   2D (100,200) 写读一致 / 像素值保持
  OK   2D (200,100) 写读一致 / 像素值保持
  OK   2D (64,512)  写读一致 / 像素值保持
  OK   2D (37,131)  写读一致 / 像素值保持
== 3. 3D 掩膜 ==  OK  (3,120,80) 写读一致
== 4. 方形掩膜 ==  OK  256x256 仍正确
== 5. 参数类错误必须抛 ValueError ==  OK  (1D/4D 掩膜、geo 5 项、3D mask_to_geojson)
== 6. IO 类错误必须抛 RuntimeError ==  OK  (文件不存在、目标目录不存在)
== 7. 掩膜参数的类型与布局严格性 ==
  OK   uint8 C 连续只读数组 被接受
  OK   float32/int32/bool/非C连续/F连续 均被拒绝 TypeError
  OK   write_raster 收到 float32 被拒绝 TypeError
  OK   mask_to_geojson 退化 3D (1,H,W) 被拒绝 ValueError
== 8. read_raster 元数据 ==  OK  (256/256/3, uint16, geo 一致, UTM zone 50N)
== 9. mask_to_geojson 端到端 ==  OK  (Feature=1, 面积=720900, Polygon, properties 恰为 label/pixel_count/area_m2)
== 10. 非方形掩膜的地理坐标范围 ==  OK  (经度/纬度均落在行列范围内，H≠W 不越界)
失败项合计 = 0  ->  通过
```

（顶部 `ERROR 4:` 两行为 GDAL 自身对 `RuntimeError` 负向用例的 stderr 噪声，非校验失败；末行明确 `失败项合计 = 0`。）

## 4. 独立复算结果（严禁调用仓库实现验证仓库实现）

独立脚本置于系统临时目录（`C:/Users/Hujian/AppData/Local/Temp/verify_p2_indep.py`），
**未** `import scripts/verify_baseline.py`，**未**复用其 `frozen_*`；仅以 `_spatial.read_raster` 读盘
（GDAL 读操作，非算法），CVA / Otsu / 后处理 / 连通域全部自实现。

### 4.1 基线锚点（before.tif / after.tif）

| 项目 | 自实现结果 | 期望 | 判定 |
|---|---|---|---|
| Otsu 阈值（自实现 256-bin 最大化类间方差） | `5.916767` | `5.9168`（±1e-4） | 通过（差 3.26e-5） |
| 变化像素（原始，magnitude > 阈值） | `7209` | `7209` | 通过 |
| scipy 连通域数 | `1` | `1` | 通过 |
| 变化像素（后处理后：连通域过滤 >30 + 3×3 闭运算） | `7209` | `7209` | 通过 |
| 真实变化面积 m²（`7209 × 100`） | `720900.0` | `720900.0` | 通过 |

### 4.2 多区域夹具三方对照（multi_region_mask.raw 原始字节）

- 原始字节 `7680` → 重塑 `(64,120)`，非零 `663`。
- scipy 独立：`ndimage.label` → 连通域 `6`；首次出现顺序像素数 `[100, 200, 35, 138, 185, 5]`。
- 元数据 `regions` 像素数 `[100, 200, 35, 138, 185, 5]`，**两两不同**（顺序判据有效）。
- 引擎 `mask_to_geojson`：labels `[1,2,3,4,5]`、counts `[100,200,35,138,185]`。
- 三方一致性：**元数据顺序 == scipy 顺序**、**引擎 labels == 元数据 kept**、**引擎 counts == scipy（剔除退化）** 三者全部 `True`。
- 元数据自洽：`changed_pixels(663)==Σ(663)`、`components(6)==scipy(6)`、`degenerate_components(1)==len(dropped)(1)`、
  `expected_feature_count(5)==6-1`、`expected_pixels_in_features(658)==663-5`、`expected_area_m2(65800)==658×100` —— **全部自洽**。

### 4.3 GEOS 合法性（shapely，逐 Feature 断言 is_valid / 逐环 LineString.is_simple / area>0 / geom_type=="Polygon" / 内环数）

| 夹具 | Feature 数 | 洞环数 | 全部合法 | 几何面积 | 上报面积 | 偏差 |
|---|---|---|---|---|---|---|
| 基线 change_mask | 1 | 0 | 是 | `699800.0` | `720900.0` | `-2.93%` |
| 多区域 | 5 | 1 | 是 | `54200.0` | `65800.0` | `-17.63%` |
| 多区域 label3（35 像素） | — | — | 是 | `2400.0` | `3500.0` | `-31.43%` |

几何面积与 `area_m2` 偏差与 `docs/contracts.md` §5.1 表逐行一致（`-2.93%` / `-17.63%` 精确命中；
最小区域文档写 `-31.4%`，精确复算 `-31.43%`，为四舍五入，偏差 < 0.1 个百分点，见第 6 节观察 O3）。

### 4.4 `docs/contracts.md` 逐条核对

| 条款 | 实测 | 结论 |
|---|---|---|
| §3 四函数存在且可调用 | `read_raster/write_raster/mask_to_geojson/print_gdal_version` 均 `hasattr` 为真 | 通过 |
| §4 uint8 只读数组接受 | `np.frombuffer(...).reshape(8,8)` 被接受 | 通过 |
| §4 float32/int32/bool 拒绝 | 均 `TypeError` | 通过 |
| §4 非 C 连续（跨步）/ F 连续拒绝 | 均 `TypeError` | 通过 |
| §4 退化 3D `(1,H,W)` 拒绝 | `ValueError` | 通过 |
| §5 properties 字段恰为 `label`/`pixel_count`/`area_m2` | 两夹具所有 Feature 的字段集恰为该三元组 | 通过 |
| §5 一个连通域恰好一个 Feature | 基线 1 连通域 → 1 Feature；多区域 6 连通域 → 5 Feature（退化剔除） | 通过 |
| §5 退化细条（line_e, 5px）被剔除 | 引擎 labels 为 `[1..5]`，不含 `6` | 通过 |
| §5 洞环为内环 | 带洞 Feature（label5）坐标环数 `2`（首环外环 + 次环内环） | 通过 |
| §2 产物命名 / ABI | `_spatial.cp314-win_amd64.pyd` 存在且被加载 | 通过 |
| §6 异常消息原文 | 见下 | 通过（逐字一致） |

§6 异常消息原文（实测）与 `docs/contracts.md` §6 表逐字比对：

| 情形 | 实测原文 | 与文档一致 |
|---|---|---|
| 1 维掩膜 `write_raster` | `ValueError: 掩膜必须是 2D (H, W) 或 3D (B, H, W) 的 uint8 数组，实得 1 维` | 一致 |
| 3 维掩膜 `mask_to_geojson` | `ValueError: mask_to_geojson 只接受 2D (H, W) 的 uint8 掩膜，实得 3D (B, H, W)` | 一致 |
| `geo` 5 项 | `ValueError: geo_transform 必须是 6 个浮点数，实得 5 个` | 一致 |
| 文件不存在 `read_raster` | `RuntimeError: read_raster: 无法打开 <path>：... No such file or directory` | 一致（路径随输入） |
| 目标目录不存在 `write_raster` | `RuntimeError: write_raster: 创建失败 <path>：Attempt to create new tiff file ... failed: ... No such file or directory` | 一致 |

### 4.5 确定性

同一输入重复调用 `mask_to_geojson` 5 次，基线与多区域输出均**逐字节一致**（`True`）。

### 4.6 旧仓库只读性

```text
$ git -C <旧仓库> remote -v          # 新仓库：无输出（无 remote）
$ git -C <新仓库> log --oneline | wc -l   # 33
$ git -C <旧仓库> status --short
 M .vscode/settings.json
?? CODE_MAP.md
?? DOCKER_PLAN.md
?? GEO_CAPABILITIES.md
?? project2-lessons-and-interview.txt
$ git -C <旧仓库> rev-parse --short HEAD   # a096efc
```

新仓库**无 remote、33 个提交**，未合并旧仓库历史（满足"旧仓库当只读远端，绝不 merge"）。
旧仓库状态（1 修改 + 4 未跟踪）与《执行手册》§6 所述"HEAD=a096efc、2 提交、5 项未提交变更"基线一致；
本验收未对旧仓库执行任何写操作（仅 `git status`/`rev-parse` 读操作） → **只读性成立**。

## 5. 契约逐条核对汇总（与第 4.4 节同口径，结论）

- 四个函数存在、返回结构与文档一致：**通过**
- §4 数组契约（float32/int32/bool/非C连续/F连续/退化3D 拒绝；uint8 只读接受）：**通过**
- §5 语义（properties 字段名、`label` 顺序、一个 Region 一 Feature、退化剔除、洞环）：**通过**
- §6 异常消息原文与实测逐字一致：**通过**
- §2 产物命名与 ABI 标签 `cp314-win_amd64` 与实际文件一致：**通过**

`docs/contracts.md` 全部可判定条款实测与文档相符，**无一条不通过**。

## 6. 找茬结果：观察项与不通过项

**不通过项：无。**

**观察项（已检查范围，按严重度由低到高）：**

- **O1（设计整洁度，非缺陷）**：`gdal_registration_count()`（测试自省函数）经 `SPATIAL_API`
  暴露在 `engine/include/spatial/raster.hpp` 的公开 API 表面，并被 `libspatial.dll` 导出
  （`objdump -p` 可见）。该函数仅供 `test_raster_io.cpp` 断言 GDAL 一次性初始化，混入生产头与
  导出表削弱 API 纯洁性。建议后续收归 `tests/` 或 `#ifdef` 保护，但**不构成本阶段不通过**。
- **O2（可复现性前提，非缺陷）**：`engine/CMakeLists.txt` 在 configure 阶段经 `FetchContent`
  从 `codeload.github.com` 拉取 `nlohmann/json@v3.11.3` 与 `Catch2@v3.7.1`。离线或网络受限环境
  下 `cmake` 配置将失败。属有意设计（去掉入库 1 MB 单头文件），但构成"可复现"的隐含前提：
  构建机须可达 GitHub。建议文档显式标注此网络前提。
- **O3（文档数字，轻微）**：`docs/contracts.md` §5.1 最小区域偏差写为 `-31.4%`，精确复算为
  `-31.43%`（四舍五入，偏差 < 0.1 个百分点）。属文档约数，可接受；若要求严格一致可改为 `-31.43%`。
- **O4（对照基线，信息项）**：旧仓库 `.vscode/settings.json` 处于修改态、另有 4 个未跟踪文件，
  与《执行手册》§6 描述的"5 项未提交变更"完全一致；本验收未改动旧仓库 → 只读性成立（见 4.6）。
- **O5（覆盖说明，信息项，非盲区）**：任务预设的"只测方形影像掩盖行列混淆"盲区**已被覆盖**——
  `test_raster_io.cpp` 有 `非方形多波段往返一致` 与 `非方形单波段往返保留 H 与 W (D-1)`，
  `test_multi_region.cpp` 有 `非方形影像的行列不得互换`，`verify_bindings.py` 用 `(100,200)/(200,100)/(64,512)/(37,131)` 验证。
  但需注意：`test_pipeline.cpp` 直接读取冻结的 `change_mask.raw/.json`，**不**从 before/after.tif 经
  CVA+Otsu 复算；§7.1 的 Otsu 阈值与原始变化像素由 `verify_baseline.py` 的冻结参考实现（Python）独立
  复算并交叉验证，而非由 C++ 引擎。引擎本身不含 CVA/Otsu（属 Phase 3 Python 层职责），故不构成缺陷，
  但意味着"基线数字"的守护在引擎侧依赖 Python 工具链而非 CTest 单测。
- **O6（工具链限制，信息项）**：`nm -D _spatial.cp314-win_amd64.pyd` 对 MinGW 产出的 PE 报
  `no symbols`（不读 PE 导出表），故 G2.2 的"符号齐全"改以 `objdump -p` 导出表（§2.5/§4.4 证据）
  + `import`/`hasattr` 功能性验证为准。属工具限制，非符号缺失。

**构建/测试是否依赖当前工作目录或写死绝对路径**：`engine/tests/CMakeLists.txt` 以编译期宏
`SPATIAL_TEST_FIXTURE_DIR` 注入夹具目录（不依赖 CWD）；`scripts/engine_env.py` 相对仓库根解析路径；
`engine/` 源码与 `CMakeLists.txt` 中**无**硬编码 `C:/Users/...` 或 `msys64`（`grep` 仅在 gitignored 的
`build/dev-win/` 生成物中命中，源码零命中）。**未入库产物泄漏检查**：`.venv`、`engine/build`、
`config/local.toml`、`engine/CMakeUserPresets.json` 均被忽略，`git status --short` 为空。

## 7. 提交链

```text
*   013f689 merge(2.9): 多区域夹具与 §7.3 判据启用、绑定层契约保真修复、契约冻结
|\
| * 7b1391b docs(contracts): 冻结 _spatial Python 契约
| * a87959d fix(engine): 掩膜参数拒绝隐式转换与退化 3D；绑定校验工具入库
| * 8ec82d9 test(engine): 多区域夹具覆盖 label 顺序、退化剔除与洞环；启用 §7.3 两项判据
|/
*   ad521f9 merge(2.8): CTest/Catch2 单测、构建预设、-Werror 与安装规则；洞环与简化锚点修正
...（2.1–2.7 共 8 个任务合并节点，详见 git log --graph）
*   75e973f merge: Phase 1 环境与仓库奠基
|\
| *   01b4048 merge: verify-1 验收证据
| |\  
| | * 290a6e2 docs(verification): Phase 1 验收报告
```

证据分支 `verify-2-report` 由 `phase-2-engine` tip（`013f689`）检出，只含本文件。

## 8. 遗留与后续约束表

| 项 | 状态 | 责任阶段 |
|---|---|---|
| `docs/contracts.md` §5.1 "几何面积与 area_m2 偏差" 待裁定（是否改沿像素边界追踪） | 已知开放项，明确禁止验收阶段自行改动 | 项目负责人裁定后另立任务 |
| O1：`gdal_registration_count()` 测试探针混入公开 API | 观察，非阻断 | 后续清理（建议 Phase 5/7） |
| O2：构建期 FetchContent 依赖 GitHub 网络 | 已知前提，建议文档标注 | Phase 6 CI 须保证网络或缓存 |
| O3：§5.1 最小区域偏差为四舍五入值 | 文档微调，非阻断 | Phase 7 文档固化 |
| 后端（Phase 3）须复用本阶段 `_spatial` 契约，禁止改签名 | 约束生效中 | Phase 3 |
| 旧仓库只读性维持（HEAD=a096efc，5 项未提交变更未动） | 成立 | 终验打 `archived` 标记（Phase 7） |
