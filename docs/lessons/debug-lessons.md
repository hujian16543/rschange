# 调试教训整理版（旧仓库 → 新仓库）

> **素材来源**（均只读）：旧仓库 `Debug_lesson.txt`（5 条表格行）、`project2-lessons-and-interview.txt`「一、学到的东西」（8 条编号条目）。
> **对照对象**：新仓库 `rschange`（`_build/Remote_sensing`），版本 `1.0.1`（Phase 7 收口 + v1.0.1 文档路径修正）。
> 文中的测试与门禁数字**实测于 Phase 6 收口 tip**（`dc8ee2b`／`v0.6.0`）；Phase 7 只增改文档，
> 产品代码与黄金基线冻结在 Phase 6，故数字未变——全量复跑记录见 `docs/verification/phase-7.md`。
> **整理纪律**：旧文中的路径、文件名、版本号一律替换为新仓库真实位置；数字取自 `docs/verification/phase-*.md`；无据可查者标 `待核实`。
> **条数核对**：两源文件合计 **13 条**，与提炼摘要的「13 条清单」一致，无差异。
> 其中 `Debug_lesson.txt` 的第 1/2/3/5 条与 project2 文档的第 1/2/3/6 条内容重叠（同一坑的多份记录），
> 按摘要建议**不做合并去重**，在 §1 总表中以「同源」列标注。

---

## 0. 缺陷编号的三套口径（引用前必读）

本仓库存在**三套互不同源**的 `D` 编号，混用会直接引错条目：

| 编号口径 | 出处 | 覆盖范围 | 示例 |
|---|---|---|---|
| `D-1 … D-9`（带连字符） | `docs/algorithm.md` §8.1（:1252-1263） | C++ **引擎**缺陷 | `D-3` = 每环一个 Feature 导致面积重复计 N 倍 |
| `D1 … D7`（无连字符） | `docs/verification/phase-3.md` §3（后端缺陷核对 A） | **后端**分层缺陷 | `D3` = 属性面积重复计；`D5` = DLL 路径硬编码；`D7` = 异常外泄 |
| `附录 D-5` | `backend/src/rschange/spatial/__init__.py`、`loader.py` 的 docstring | 重构方案的**架构附录**条目 | 指「`_spatial` 的唯一访问点」，与缺陷无关 |

> 注意陷阱：两套缺陷编号中「`D-3` / `D3`」恰好都指「面积重复计」，但**其余编号完全不同源**
> （`algorithm.md` 的 `D-1` 是掩膜尺寸解析，`phase-3.md` 的 `D1` 是 CORS 通配符）。
> 本文件引用时一律写作 `algorithm.md D-3` 或 `phase-3 D3` 形式。

---

## 1. 教训总表（13 条）

| # | 一句话 | 来源 | 新仓库落点 | 守护状态 |
|---|---|---|---|---|
| L1 | `os.add_dll_directory` 在 Linux 上不存在 | Debug-1 / p2-① | `backend/src/rschange/spatial/loader.py:76` | 有守护（CI linux-gcc 的 mypy） |
| L2 | 声明与定义的 const 不一致 → `undefined symbol` | Debug-2 / p2-② | `engine/src/raster_io.cpp:13` + 双平台构建 | 有守护（编译期 + `verify_bindings.py`） |
| L3 | Git Bash MSYS 路径转换污染诊断结论 | Debug-3 / p2-⑥ | `.github/workflows/ci.yml:12-23` | **部分**——无针对路径转换的判据（见 L3） |
| L4 | `apt` 走海外源导致下载慢 | Debug-4 | 未采纳（`docker/Dockerfile.backend`） | `无守护` |
| L5 | `CXX_VISIBILITY_PRESET` 在全局 `-fvisibility=hidden` 下不可靠 | Debug-5 / p2-③ | `engine/include/spatial/export.hpp` | 有守护（ctest + objdump 导出表核对） |
| L6 | 跨平台不是「能编译」，是「每个平台都能编译并运行」 | p2-① | `engine/CMakePresets.json` + CI 双矩阵 | 有守护（双平台必过，`fail-fast: false`） |
| L7 | 不要为省事去掉 `const`；老 C API 用拷贝解除 const | p2-④ | `engine/src/raster_io.cpp:111-116` | 有守护（编译期，签名即契约） |
| L8 | Docker 多阶段构建与两个「源」的区分 | p2-⑤ | `docker/`（`Dockerfile.backend` 两阶段） | 有守护（`verify_containers.py` 19 条静态判据） |
| L9 | 前端分层与「果断删死代码」 | p2-⑦ | `frontend/src/` 分层 + 依赖清单无地图库 | 有守护（`npm run check`，vitest 109） |
| L10 | 调试方法论：环境 → 链接 → 签名 → 符号，且先验证方法本身 | p2-⑧ | `scripts/verify_*.py` 五个分层门禁 | 有守护（CI step 19 串联，各自报 PASS/FAIL 计数） |
| L11 | `.dll` / `.so` / `.dylib` 同一物的三种叫法；产物绑定工具链 | p2-①（附） | `engine/CMakePresets.json` 三形态宏 + `docker/Dockerfile.backend:101-102` | 有守护（CI 双平台 + ABI 标签断言） |
| L12 | 层缓存：首次慢、之后秒级；第一次构建慢属正常 | p2-⑤（附） | `docker/Dockerfile.backend:53-59` cache mount + CI `_deps` 缓存 | 部分（见 L12） |
| L13 | 读报错要抠字：`undefined symbol` 的符号名里 `K` 是关键 | p2-②（附）/ p2-⑧（附） | 无独立载体 | `无守护`（属方法论，见 L13 说明） |

> L11–L13 在原文中依附于 L6 / L8 / L2 段落，为保持「逐条可核查」单列成条，正文注明依附关系。

---

## 2. 逐条展开

### L1｜`os.add_dll_directory` 在 Linux 上崩溃

- **现象**：Linux 容器/进程里执行 `os.add_dll_directory(...)` 直接 `AttributeError`；Windows 上正常。
- **根因**：该 API 是 Windows 专属。Linux 找动态库靠 `LD_LIBRARY_PATH`，macOS 靠 `DYLD_LIBRARY_PATH`，均**不是** Python 代码能登记的东西。
- **修复**：不得直接取属性；平台差异靠「能力探测 + 显式失败」表达，而非 `if os.name == 'nt'` 静默跳过。
- **新仓库落点**：
  - `backend/src/rschange/spatial/loader.py:76` —— 经 `getattr(os, "add_dll_directory", None)` 取值；取不到时**显式报错**，禁止用 `type: ignore` 或布尔平台分支掩盖。
  - `backend/src/rschange/spatial/loader.py:34` —— 句柄统一收集在模块级 `_DLL_HANDLES`，生命周期与进程一致（丢弃返回值会在 GC 时静默摘除搜索路径）。
  - `config/default.toml:21` —— `engine.runtime_dll_dir`：Windows 必填；Linux/macOS 留空，改由 `LD_LIBRARY_PATH` / `DYLD_LIBRARY_PATH` 提供。
- **如何避免复发**：CI 的 `linux-gcc` 任务执行 `uv run mypy`（strict，`files = ["backend/src"]`，36 文件 0 错）。`add_dll_directory` 只存在于 Windows typeshed，改回直接属性访问在 Linux 上必红。该缺陷正是由双平台实跑暴露并记录于 `docs/verification/phase-6.md:213`（§8-④）。

### L2｜声明与定义的 `const` 不一致 → `undefined symbol`

- **现象**：链接期报 `undefined symbol`；新旧写法只差一个 `const`，修饰名差一个 `K`（`PKd` vs `Pd`），排查成本极高。
- **根因**：声明与定义分处两个编译单元，两侧看到的签名不同，编译器不报错，链接器按不同修饰名找符号。
- **修复**：声明与定义必须一字不差；**实现文件必须 include 自己的公开头**，使不一致在编译期即暴露。
- **新仓库落点**：
  - `engine/src/raster_io.cpp:13` —— `#include "spatial/raster.hpp"`；`engine/src/geojson.cpp`、`engine/src/simplify.cpp`、`engine/src/contour.cpp` 同构。签名不一致 → 编译期「重声明冲突」，比旧仓库的链接期报错早一个阶段。
  - `engine/include/spatial/*.hpp` 为唯一声明点，`engine/src/*.cpp` 为唯一实现点，一一对应。
  - `scripts/verify_bindings.py`（42 项检查，含四个公开函数的签名、返回结构、参数约束、异常类型、掩膜类型与布局）。
- **如何避免复发**：CI step 12/13 在两个平台上配置并构建引擎；step 19 执行 `verify_bindings.py`。符号层面的独立核对另有 `docs/verification/phase-2.md:12`（G2.2，`objdump -p` 导出表）与 `docs/verification/phase-2.1.md:52-72`（导出表 9 个 `spatial::` 符号）。

### L3｜Git Bash 的 MSYS 路径转换污染诊断结论

- **现象**：在 MSYS shell 里跑带 `/path` 或 `-Dxxx=/path` 的命令，参数被自动改写为 Windows 路径；由此得出的诊断结论全是假象。
- **根因**：MSYS2 的路径转换发生在命令执行之前，被污染的不是被测对象而是**探测命令本身**。
- **修复**：两条路径二选一——设 `MSYS2_ARG_CONV_EXCL="*"` 禁用全部转换，或**根本不在 MSYS2 shell 里跑该命令**。
- **新仓库落点**：`.github/workflows/ci.yml:12-23` 采用后者并以「防复发，勿删」注释固化；CMake 用 runner 预装的 Windows 原生版本，PATH 里只加 `mingw64/bin` 以取得 Ninja、编译器与运行期 DLL。同文件 `:25-42` 记录同源陷阱二：禁止写死 `C:/msys64/mingw64`。
- **守护状态**：**无针对路径转换本身的自动化判据**——该类问题的判据是「规避」而非「检测」。
  间接防线为：① CI `windows-mingw` 任务 step 12/13 真实配置并构建（路径被转换则 CMake 报 “not a full path to an existing compiler tool”，`docs/verification/phase-6.md:210` §8-① 即该症状的实录）；② `scripts/verify_containers.py` 判据「容器化资产不含机器相关绝对路径」；③ `backend/src/rschange/tests/test_architecture.py:51`（`test_backend_has_no_machine_local_paths`，G3.5）。
- **如何避免复发**：改动 CI 的 shell 或把 CMake 搬进 MSYS2 shell 之前，必须同步恢复 `MSYS2_ARG_CONV_EXCL="*"`；该约束写在 `ci.yml:22-23`，删除注释即视为引入风险。

### L4｜`apt` 走海外源导致下载慢

- **现象**：`apt-get update` / `apt-get install` 在 `deb.debian.org` 上耗时不可接受。
- **根因**：默认软件源在境外。两个「源」需区分：Docker 源管**镜像**，Debian 源管**镜像里的软件包**。
- **修复（旧仓库做法）**：Dockerfile 内 `sed` 替换为清华 apt 源；Docker 侧配 `registry-mirrors`。
- **新仓库落点**：**未采纳**。`docker/Dockerfile.backend:41-48`（builder）与 `:81-92`（runtime）直接 `apt-get update`，未换源。
- **守护状态**：`无守护`。
- **原因说明**：该教训属**构建体验优化**，不构成正确性判据，故新仓库未为其设门禁；且把镜像源写死进 Dockerfile 会降低在境外 runner 上的可移植性。另需如实披露：容器**未在本机构建**（`docker/Dockerfile.backend:20-22`、`docs/verification/phase-6.md` §11 O1），apt 包解析路径仅经静态审查，换源与否均未经运行验证。若后续构建环境确需加速，应在 `scripts/verify_containers.py` 之外单独提供可切换的构建参数，并把「是否换源」记入构建文档。

### L5｜`CXX_VISIBILITY_PRESET` 在全局 `-fvisibility=hidden` 下不可靠

- **现象**：`libspatial` 的符号被隐藏，`_spatial` 扩展链接不到；调 CMake 的 `CXX_VISIBILITY_PRESET` 无效。
- **根因**：nanobind 编译扩展时全局设置 `-fvisibility=hidden`；CMake 的预设只在**无显式选项**时才生效，压不住命令行/全局注入的选项。函数级 `__attribute__((visibility("default")))` 优先级最高。
- **修复**：头文件里定义跨平台导出宏，公开函数逐个显式标注；宏**只定义一处**。
- **新仓库落点**：`engine/include/spatial/export.hpp` —— `SPATIAL_API` 的**唯一定义点**（`:4`），背景说明见 `:6-13`（旧实现在 `stats.hpp` 与 `tiff_io.hpp` 各定义一份，写法漂移时产生难以定位的链接错误）。三编译形态宏表见 `:19-27`：`SPATIAL_BUILDING` / 消费方 / `SPATIAL_STATIC`，且 `SPATIAL_STATIC` 必须优先判断。
- **如何避免复发**：
  1. 新增公开函数必须经 `SPATIAL_API`；测试专用探针改走 `engine/src/internal/gdal_registry.hpp` 的 `SPATIAL_INTERNAL`（展开为 `visibility("hidden")`，不导出、不安装）。
  2. 判据一：`engine/tests/CMakeLists.txt` 链接**静态库** `spatial_static` 以读取内部探针；判据二：`docs/verification/phase-2.1.md:52-72`（`objdump -p` 导出表含 9 个 `spatial::` 符号且**不含** `gdal_registration_count`）与 `:74-85`（`engine/include/` 下 grep `gdal_registration_count` 命中 0）。
  3. 判据三：ctest 40/40 在 `dev-win` 与 `dev-linux` 两个预设上均通过（CI step 14）。
- **附**：该教训的旧结论「符号问题先查签名，别急着动 visibility」仍成立——L2 与 L5 常同时出现，排查顺序须为签名 → 符号。

### L6｜跨平台不是「代码能编译」，是「每个平台都能编译 + 运行」

- **现象**：本机（Windows / MinGW）编译好的 `.dll` / `.pyd` 在 Linux 容器里完全不可用，必须重新编译。
- **根因**：二进制格式绑定操作系统与工具链，不是源码可移植性可覆盖的层面。
- **修复**：每个平台各自编译各自运行，并把「两平台都绿」固化为门禁。
- **新仓库落点**：
  - `engine/CMakePresets.json` —— 7 个 configure 预设 / 4 个 build 预设 / 4 个 test 预设，覆盖 `dev-win` / `dev-linux` / `release-win` / `release-linux`。
  - `.github/workflows/ci.yml` —— 单 job `verify` × 矩阵 `linux-gcc`（`ubuntu-latest`）/ `windows-mingw`（`windows-latest`），`fail-fast: false`。
- **如何避免复发**：两条平台都是**必过项**，无主次；`docs/verification/phase-6.md` §3 记录 G6.1 判据为 run `37192763321`，两侧各 **32 步零失败**（其中 24 步为 job 内声明步骤，余下为 runner 侧步骤）。该 run 必须是**含新增契约第二段门禁**的 workflow 版本——同为双绿的 run `37192442273` 只有 31 步、不含该步骤，已显式排除。

### L7｜const 正确性：不要为省事去掉 `const`

- **现象**：老 C API（GDAL `SetGeoTransform`）要求非 const 指针，于是有人直接把入参的 `const` 去掉。
- **根因**：去掉 `const` 会丢失「函数不会修改它」这一接口语义契约，且污染调用方。
- **修复**：入参保持 `const`；遇到要求非 const 的老 API，用**拷贝**安全解除 const。
- **新仓库落点**：`engine/src/raster_io.cpp:111-116` —— 注释「SetGeoTransform 要的是非 const 指针，因此从 const 入参拷一份」，以 `std::array<double, 6>` 拷贝后传 `transform.data()`。入参签名见 `:89-90`（`const double geo_transform[6]`）；同类签名见 `engine/src/geojson.cpp:41`、`:50`、`:88`。
- **如何避免复发**：签名即契约，编译期即可拦截——调用方传 const、实现方去掉 const 都会触发编译失败（配合 `SPATIAL_WARNINGS_AS_ERRORS`）。跨语言边界处另有 `scripts/verify_bindings.py` 断言掩膜参数的类型与布局严格性（拒绝 `float32` / `int32` / `bool` / 非 C 连续 / F 连续）。

### L8｜Docker 多阶段构建与两个「源」

- **现象**：单阶段镜像体积达数 GB，且把编译器带进运行期。
- **根因**：编译期工具链（`build-essential` / `cmake` / `libgdal-dev`）在运行期无用，却留在同一镜像层里。
- **修复**：builder 阶段编译，runtime 阶段只留最小运行依赖，`COPY --from=builder` 只搬产物。
- **新仓库落点**：
  - `docker/Dockerfile.backend:28-66`（builder，`python:3.14-slim-bookworm`）→ `:71-131`（runtime，只装 `libgdalNN`）。
  - `:81-92` 逐个尝试 `libgdal36 … libgdal32` 并**显式失败**：Debian 不提供无版本包名，写死其一会在基础镜像换代时静默失效；`:79-80` 明令禁止退回 `libgdal-dev`。
  - `:11-15` 固化同源教训：builder 与 runtime 的 Python 必须同源（旧实现 3.12 / 3.14 混用导致 `_spatial` ABI 错配，症状是 import 期未定义符号且报错指向 Python 而非构建配置）。
  - `docker/Dockerfile.frontend`、`docker-compose.yml`、`docker/nginx.conf`、`.dockerignore`（四项必排除：`.venv/` / `engine/build/` / `node_modules/` / `config/local.toml`）。
- **如何避免复发**：`scripts/verify_containers.py` 提供 **19 条静态判据**（CI step 19），覆盖上传上限、反代语义、镜像版本、CI 一致性、编排、配置一致性、构建上下文、机器相关路径八组；`docs/verification/phase-6.md` §4 记录 19/19 通过。
- **边界披露**：容器**未构建**，G6.2 的「`docker-compose up` 后 `POST /api/detect` 返回基线数字」与 G6.3 的「>1 MB 上传不再 413」均只经静态判据，运行动作未验证（`docs/verification/phase-6.md` §11 O1 / U6）。

### L9｜前端分层架构与「果断删死代码」

- **现象**：地图方案弃用后，`MapView` / `Legend` / `geojson` 模块全部成为死代码，仍拖累 `tsc` 构建。
- **根因**：功能下线时只删了入口，没删被入口拽住的依赖树。
- **修复**：删除不留；分层保持 `types → api → hooks → components → App` 的单向依赖。
- **新仓库落点**：
  - 分层：`frontend/src/api/`（`client.ts`、`types.ts`、`generated/`）→ `frontend/src/features/detection/`（`hooks/`、`components/`、`errors.ts`、`format.ts`、`index.ts`）→ `frontend/src/App.tsx`；通用原语集中在 `frontend/src/components/ui/`。
  - 唯一出口：`frontend/src/features/detection/index.ts`（应用层只从此处导入）；契约类型唯一入口：`frontend/src/api/types.ts`（转发生成类型，不含手写字段）。
  - 死代码已清除：`frontend/package.json` 的运行时依赖仅 4 项（`react` / `react-dom` / `react-dropzone` / `lucide-react`），**无地图库**。契约中的 `image_corners` 保留但无地图渲染，记为 `docs/verification/phase-6.md` §11 O3。
- **如何避免复发**：`npm run check` = `tsc -b --noEmit && oxlint && vitest run`，CI step 22 执行；前端测试 **109 项**（6 文件，CI 实测 109 passed）。新增产物须经 `frontend/src/features/detection/index.ts` 暴露，禁止应用层深入 `components/` 或 `hooks/`。

### L10｜调试方法论：环境 → 链接 → 签名 → 符号，且先验证方法本身

- **现象**：按层次排查却始终定位不到，因为每一层的探测命令本身是错的（见 L3）。
- **根因**：验证方法未经验证，结论建立在被污染的观测之上。
- **修复**：每次只验证一个变量，并在排查前先确认「探测命令本身可信」。
- **新仓库落点**：该层次结构被固化为**五个独立门禁脚本**，各自只判一层、各自报 PASS/FAIL 计数：

  | 脚本 | 判的那一层 | 规模 |
  |---|---|---|
  | `scripts/verify_baseline.py` | 数值基线（§7.1 不变量 / §7.2 缺陷基线 / §7.3 语义断言） | 11/11 + 2/2 + 7/7 |
  | `scripts/verify_bindings.py` | 跨语言绑定契约（签名 / 返回 / 参数 / 异常 / 布局） | 42 项，失败 0 |
  | `scripts/verify_config.py` | 分层配置 / CMake 预设 / 本机模板三者互相对得上 | 6 组判据 |
  | `scripts/verify_version.py` | 版本号同号（真相源 `backend/pyproject.toml`） | 5 组判据 |
  | `scripts/verify_containers.py` | 容器化资产静态门禁 | 19 条 |

- **如何避免复发**：CI step 19 一次性串联五个脚本；任一失败即红。契约层另有 CI step 18（`gen_openapi.py --check`，守第一段）与 step 23（契约类型零漂移，守第二段）。`docs/verification/phase-6.md` §9 逐条记录结果。

### L11｜`.dll` / `.so` / `.dylib` 是同一物的三种叫法

- **现象**：换平台后产物名与加载方式全变，误以为是「另一种东西」。
- **根因**：只记住了 Windows 的文件后缀名，不理解「共享库」这一统一概念。
- **修复**：以「共享库 + 导入/导出语义」建模，平台差异收敛到一个宏与一个加载点。
- **新仓库落点**（依附 L6）：`engine/include/spatial/export.hpp:19-27` 的三形态宏表（`dllexport` / `dllimport` / 静态库空展开）；`docker/Dockerfile.backend:101-102` 只搬 `_spatial*.so` 与 `libspatial.so*`。Windows 侧扩展 ABI 标签 `mingw_x86_64_msvcrt_gnu` 与 `cp314` 被 `scripts/verify_bindings.py` 断言。
- **如何避免复发**：CI 双平台构建（step 12/13）+ `verify_bindings.py`；扩展文件名或 ABI 标签变化会被后者抓到。

### L12｜层缓存：首次构建慢属正常

- **现象**：第一次构建耗时数十分钟，误判为配置错误。
- **根因**：首次构建要下载依赖并完整编译；后续命中层缓存才是秒级。
- **修复**：把「变化频率低」的依赖层放在 Dockerfile 前部，源码层放在后部；依赖锁文件单独成层。
- **新仓库落点**：`docker/Dockerfile.backend:51-59` —— 先 `COPY pyproject.toml uv.lock` 装依赖，再 `COPY . .` 装工程自身，并配 `--mount=type=cache,target=/root/.cache/uv`；`:40-48` 把编译期系统依赖与源码分离。引擎侧由 CI step 10（缓存 `engine/build/*/_deps`）与 step 11（ccache）承担。
- **守护状态**：**部分**——缓存配置本身无判据，容器未构建故缓存命中率未实测；C++ 侧的构建缓存有 CI step 10/11 实际生效（属运行事实，非断言）。
- **如何避免复发**：调整 Dockerfile 层序时，须保证「依赖锁文件层」仍在「源码层」之前；该顺序被 `:50` 的注释固化。

### L13｜读报错要抠字：`undefined symbol` 的符号名里 `K` 是关键

- **现象**：同一个 `undefined symbol` 报错，排查方向完全不同（符号没导出 vs 签名不一致）。
- **根因**：修饰名里的 `K` 表示 const，是区分两类故障的唯一线索；不读符号名就只能靠猜。
- **修复**：遇到 `undefined symbol`，第一件事是比对报错符号与库里实际符号（`nm -D` / `objdump -p`）。
- **新仓库落点**：**无独立载体**。该条属方法论，不对应任何代码位置；其可核查的替代物是 L2 与 L5 的判据（编译期拦截 + 导出表核对），以及 `docs/algorithm.md` §8.1 的 `D` 系列缺陷表（把「曾经踩过的坑」变成「有编号、有落点的条目」）。
- **守护状态**：`无守护`。原因：软件工程上无法为「读报错的方式」设自动化判据；只能靠文档固化与 code review。

---

## 3. 专题：面积口径修正（`1441800` → `720900` m²）

> 本条**不在旧 13 条教训之内**，是重构过程中由基线工具暴露并由新仓库彻底修正的核心缺陷，
> 编号为 `algorithm.md D-3`（引擎侧）。因涉及对外讲述的关键数字，单独成节。

### 3.1 缺陷形态

| 项 | 旧实现 | 新实现 |
|---|---|---|
| Feature 归属 | **每环一个 Feature** | **一个 Region 一个 Feature** |
| 属性携带 | Region 级 `pixel_count` / `area_m2` 复制到每个 Feature | Region 级属性只出现一次 |
| 多环语义 | 每环独立成 Polygon | 首环为外环、其余为内环（标准 GeoJSON Polygon） |
| 基线样本结果 | Feature `2`、属性面积合计 `1441800.0` m² | Feature `1`、属性面积合计 `720900.0` m² |

**成因链**：基线样本是单连通域，其边界被 `algorithm.md D-2`（起点未入 `visited` + 扫描起点未携带）劈成 **2 条弧**；
旧实现对每条弧各生成一个 Feature 并各自携带整区的 `area_m2`，于是 `720900` 被计 2 次，合计 `1441800` m²——虚报整整一倍。
`N` 即环数：`N = 2`。

### 3.2 证据链（逐条可复核）

| 证据 | 位置 | 内容 |
|---|---|---|
| 缺陷定义 | `docs/algorithm.md:905-915`（§5.1） | 「一个 Region 若含 N 条环，它的面积就在输出里出现 N 次」；「720900 m² 的真实面积在输出里合计成 1441800 m²」 |
| 缺陷表行 | `docs/algorithm.md:1258`（§8.1，`algorithm.md D-3`） | 「每环一个 Feature 却带 Region 级属性 ⇒ 面积重复计 N 倍」→「一个 Region 一个 Feature」 |
| 转正判据 | `docs/verification/phase-2.md:14`（G2.4） | Feature `2→1`、面积 `1441800→720900` |
| 实测表行 | `docs/verification/phase-2.md:119-120` | `7.2 属性面积合计 m² 720900.0` PASS，备注「旧引擎实际输出 1441800.0（缺陷：面积重复计 2 倍）」 |
| 未回归确认 | `docs/verification/phase-3.md:73`（A.5） | `phase-3 D3`（属性面积重复计）由 §7.2 `2/2` 确认未回归 |
| 旧值留档 | `scripts/verify_baseline.py:148-153` | Phase 1 现状值：Feature `2`、面积合计 `1441800.0`（作为「缺陷未修复」期望值保留） |

> **编号口径警示**：`docs/verification/phase-3.md` 的 `D3` 与 `docs/algorithm.md` 的 `D-3` 在此处**恰好同义**，
> 但两套编号的其余条目不同源（见 §0）。引用时必须写全来源文档名。

### 3.3 新仓库的守护（每一条都可执行）

| 守护 | 位置 | 断言 |
|---|---|---|
| 归属语义 | `engine/tests/test_geojson.cpp:112` | `geojson: exactly one Feature per Region (D-3)` |
| 不重复计 | `engine/tests/test_geojson.cpp:128` | `geojson: properties are not double counted across Regions` |
| 面积 ↔ 像素数 | `engine/tests/test_multi_region.cpp:173` | `multi_region: one Feature per Region, area matches pixel count` |
| 洞环语义 | `engine/tests/test_geojson.cpp:140` | `geojson: a holed Region stays one Feature with the hole as an inner ring` |
| 退化剔除 | `engine/tests/test_geojson.cpp:217` | `geojson: degenerate contours produce no Feature (D-7)` |
| 端到端（引擎） | `engine/tests/test_pipeline.cpp:51`、`:115` | 冻结夹具全链路结果与可复现性 |
| 端到端（Python） | `scripts/verify_baseline.py` §7.2 | Feature 数 == 连通域个数；属性面积合计 == `720900.0` |
| 独立复算 | `docs/verification/phase-2.md:168-192`（§4） | 不 import 仓库实现，自实现 CVA/Otsu/连通域后三方对照 |

### 3.4 延伸：几何面积与上报面积的一致性（Phase 2.1）

面积口径修正之后又暴露一层：上报的 `area_m2` 与**多边形自身的几何面积**是否一致。

| 阶段 | 多区域偏差 | 来源 |
|---|---|---|
| Phase 2（像素中心基准） | `-17.63%`（几何 `54200.0` vs 上报 `65800.0`） | `docs/verification/phase-2.md:199` |
| Phase 2.1（像素角点基准） | **0.00%**（几何 `66300.0` == 上报 `66300.0`） | `docs/verification/phase-2.1.md:130-131`、`:173` |

修法：几何基准由**像素中心**改为**像素角点**（沿像素边界追踪 / crack following），使「几何面积（像素单位）== 成员像素个数」成为恒等式；
判据 `engine/tests/test_geojson.cpp:255`（`geojson: geometric area equals area_m2 exactly (Phase 2.1 invariant)`），
并由 `scripts/verify_baseline.py:475-490` 用 **shapely 独立重算**面积后与引擎上报值比对（容差 `GEOMETRY_TOL_PERCENT = 1e-6`，`:147`）。
含洞区域同样成立：外环 210 格点 − 内环 25 格点 = 185 = `pixel_count`（`docs/verification/phase-2.1.md:134`）。

---

## 4. 附录 A：新仓库新增的守护（旧 13 条未记载的同类坑）

旧教训未覆盖、但重构中实际踩到并已单独设防的条目，供后续排查时对照。

| 坑 | 编号 | 守护位置 |
|---|---|---|
| **方形影像掩盖行列混淆**（只测 `W == H` 时 `H`/`W` 互换不可见） | `algorithm.md D-1` | `engine/tests/test_raster_io.cpp:85`（非方形多波段往返）、`:123`（非方形单波段往返保留 H 与 W）；`engine/tests/test_multi_region.cpp:253`（非方形影像行列不得互换），夹具刻意取 `120×64`（`test_multi_region.cpp:20`）；`scripts/verify_bindings.py:100-101` 用 `(100,200)/(200,100)/(64,512)/(37,131)` 四组非方形；`:288-311` 校验非方形掩膜的地理坐标范围 |
| 连通域 label 顺序跨平台不确定（`unordered_map` 迭代序） | `algorithm.md D-6` | `engine/tests/test_labeling.cpp:85`（raster-scan 首现顺序）；`engine/tests/test_multi_region.cpp:123` |
| 退化轮廓（成员 < 3、全共线）产出零面积多边形 | `algorithm.md D-7` | `engine/tests/test_contour.cpp:201`；`engine/tests/test_geojson.cpp:217` |
| 开曲线 DP 直接套闭环 → 结果随起始像素变、随容差非单调 | `algorithm.md D-8` | `engine/tests/test_simplify.cpp:159`（结果与起始顶点无关）、`:148`（顶点数随容差不增） |
| `GDALAllRegister()` 每次调用重复执行 | `algorithm.md D-4` | `engine/tests/test_raster_io.cpp:45`（`gdal_registration_count` 恰为 1） |
| 面积字段名 `are_m2` 与 GeoJSON 的 `area_m2` 不一致 | `algorithm.md D-9` | 统一为 `area_m2`；`scripts/verify_bindings.py` 断言 properties 恰为 `label`/`pixel_count`/`area_m2` |
| 常量输入下直方图 `bin_width == 0` → 除零未定义 | 后端修正项 | `backend/src/rschange/detectors/cva.py:55-59`（`vmin == vmax` 时全部归入首箱）；`docs/verification/phase-3.md:188` |
| 两期影像形状不一致时抛原始 `ValueError`（泄露内部信息） | 后端修正项 | `backend/src/rschange/detectors/cva.py:115-124` → `InputValidationError`（400）；`docs/verification/phase-3.md:189` |

---

*本文件为 Phase 7 文档产出。所有 `文件:行号` 均可在当期仓库 HEAD（`dc8ee2b`）上复核；标注 `待核实` 者禁止在对外材料中当作既成事实引用。*
