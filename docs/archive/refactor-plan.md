# 遥感变化检测平台 · 重构方案（Remote_Sensing_Change_Detection → Remote_sensing）

> 制定日期：2026-09-18
> 目标仓库：`C:\Users\Hujian\source\My_Project\Remote_sensing`（当前为空目录）
> 参考仓库：`C:\Users\Hujian\source\My_Project\Remote_Sensing_Change_Detection`（只读，不合并历史）
> **配套文档**：《Remote_Sensing_迁移映射与阶段拆解.md》—— 旧→新文件级映射、Phase 1 逐文件 WBS、C++ 函数级拆分归属、缺陷修复清单、子 agent 派单模板
> **配套文档**：《Remote_Sensing_执行手册_分支与派单.md》—— 逐阶段任务表、角色派单、分支命名与合并协议、冲突热点、回退策略
> 一句话：把「能跑的 Demo」重构成「可维护、可复现、可交接的工程项目」。数值结果必须严格不变；**结果正确性缺陷必须修正**（见 §7）。

---

## 0. 结论先行

| 问题 | 现状 | 重构后 |
|---|---|---|
| 环境 | 3 个 Python 解释器互相打架，PATH 上的还是空环境 | `uv` 管理的 1 个项目级 `.venv`，版本精确钉 `3.14.6` |
| 硬编码路径 | 3 处写死 `C:\Users\Hujian\...\msys64` | 0 处，全部收敛到 `config/local.toml` |
| 依赖 | 7 行裸包名，缺 `rasterio`，Docker 用 3.12 本地用 3.14 | uv workspace + `uv.lock`，双平台版本对齐 |
| 测试 | 脚本式 print，0 个自动化断言 | pytest + CTest + Vitest 三层 |
| 架构 | 后端 7 步塞进 1 个函数，算法硬编码不可插拔 | 分层 + 依赖注入 + 算法注册表 |
| CI | 无 | GitHub Actions 双平台矩阵 |
| 文档 | 散落 6 个 md/txt 在根目录 | `docs/` 归档 + 迁移对照表 |
| 交付过程 | 无版本里程碑，改动不可追溯 | 7 条集成分支 + 33 条任务分支 + 证据线，一阶段一 tag |

**验收锚点**分三档管理（详见 §7）：① **不变量**——Otsu 阈值 `5.9168`、变化像素 `7209 / 65536`、真实变化面积 `720900 m²`；② **必须修正的缺陷**——GeoJSON Feature 数 `2 → 1`、属性面积合计 `1441800 → 720900 m²`；③ **新增语义断言**——Feature 数 == 连通域数、面积合计 == 像素数 × 单像元面积。

**Phase 0 侦查结论**：共发现 **6 项 A 级（阻断性，含 2 项数据正确性缺陷）**、4 项 B 级（架构性）、7 项 C 级（工程性）、12 项 D 级（代码质量），合计 29 项。其中 A4、A6 为本次侦查新发现，均已在实测中复现。

---

## 1. 体检结果：旧项目问题清单

### A 级 · 阻断性（不修就谈不上"好配置环境"）

| # | 问题 | 证据 | 后果 |
|---|---|---|---|
| A1 | **Python 解释器分裂** | PATH 上 `python` → `C:\Users\Hujian\CIL\conda\python.exe`(3.14.7)，依赖全空；真实依赖在 `DevCode\python\python3.14`(3.14.6) | 照 README 敲 `pip install`，包装错地方，`import _spatial` 直接崩 |
| A2 | **硬编码绝对路径 3 处** | `main.py:5`、`services/detection.py:11`、`tests/test_cva.py:7` 都写死 `C:\\Users\\Hujian\\DevCode\\msys64\\mingw64\\bin` | 换机器/换用户即废 |
| A3 | **依赖清单不全** | `requirements.txt` 缺 `rasterio`（但 `generate_synthetic.py` 依赖它），全无版本号 | 复现失败不可控 |
| A4 | **边界追踪缺陷 → 面积虚报 2 倍**（数据正确性） | 实测：1 个连通域（7209 px，真实面积 720900 m²）被输出为 **2 个 Feature，各自称 720900 m²，合计 1441800 m²**。根因：`stats.cpp:161-166` 主循环在 `trace_ring` 返回后未把关**起点**写入 `visited`，导致同一连通域的边界被劈成左右两段弧、各自闭合；而 `regions_to_geojson` 第 ④ 步「每环一个 Feature」又把 **Region 级**的 `pixel_count`/`area_m2` 复制给每个环 → 属性重复 N 份 | 下游任何按 `properties.area_m2` 汇总统计的业务逻辑，结果直接翻倍；面试被追问"面积怎么算的"是硬伤 |
| A5 | **容器部署下大文件上传必失败** | `src/frontend/nginx.conf` 未设 `client_max_body_size`，nginx 默认上限 1 MB；而后端 `MAX_UPLOAD_SIZE = 500 MB` | Docker 部署时任何 >1 MB 的 GeoTIFF 上传返回 **413**，即实际可用性为零 |
| A6 | **`write_raster` 的 2D 输入路径静默写错尺寸** | 实测（4 组用例）：2D 输入一律被写成 `W × W` 正方形。`bindings.cpp:87` 的 `w = mask.shape(2)` 对 2D 数组越界，实际读到的是 `strides[0]`（行跨度）。`2D(100,200)` → 写出 `200×200`；`2D(200,100)` → 写出 `100×100`；`2D(64,512)` → 写出 `512×512`。仅 `H == W` 时侥幸正确 | 非方形影像（遥感常态）的输出栅格**尺寸错误且不报错**；`test_cva.py` 全程用 256×256 方形影像，恰好掩盖了该缺陷 |

### B 级 · 架构性（决定"易管理 / 解耦"）

| # | 问题 | 证据 | 后果 |
|---|---|---|---|
| B1 | **编排函数上帝化** | `services/detection.py` 的 `run_detection()` 一个函数干 7 件事（读栅格→检测→去噪→出图→算角点→转矢→统计） | 无法单测、无法替换单步、改一处怕崩全线 |
| B2 | **算法不可插拔** | `cva_detect` / `postprocess` 被硬编码串联，无抽象接口 | 想换 Otsu 为 KMeans、想加 IR-MAD，只能改主流程 |
| B3 | **无依赖注入** | `config.py` 是纯常量模块，被 `import` 到处用 | 测试无法替换数据目录/参数，只能改源码 |
| B4 | **同步阻塞** | `run_detection` 在请求线程里全跑完 | 大影像直接拖死单个 worker |

### C 级 · 工程性（决定"工程化"）

| # | 问题 | 证据 |
|---|---|---|
| C1 | 无 CI | 无 `.github/workflows/` |
| C2 | 无 Python 格式化/lint/类型检查 | 无 `pyproject.toml`、无 ruff/mypy 配置 |
| C3 | 无测试框架 | `pytest` 未安装；`test_cva.py` 靠 `print` 人工肉眼判断 |
| C4 | C++ 无测试集成 | `test_main.exe` 是裸可执行文件，未接 CTest |
| C5 | 前端无测试、无 lint 脚本 | `package.json` 有 `oxlint` 但无 `test` |
| C6 | 第三方头文件 vendored | `include/nlohmann/json.hpp` 1.0 MB 直接入库 |
| C7 | **测试资产被版本控制排除** | `.gitignore:27` 忽略 `api_tests/` → API 测试用例（`传入矢量图.yml` 等）根本没入库；`.gitignore:30` 忽略 `CAREER_PLAN.md` → 说明该 `.gitignore` 是从个人规划目录复制来的模板，未按项目裁剪 | 测试用例随仓库丢失；新仓库不得保留这两条 |

### D 级 · 代码质量（S 级小修）

| # | 位置 | 问题 |
|---|---|---|
| D1 | `main.py:26-27` | `allow_origins=["*"]` + `allow_credentials=True` —— **无效配置**，浏览器规范禁止此组合，等于 CORS 白名单形同虚设 |
| D2 | `postprocessor.py:21` | `print(f"[DEBUG] ...")` 残留在生产代码路径 |
| D3 | `services/detection.py:57` | `if hi - lo < 1e-6: hi = lo + 1` 单行 if，风格不统一 |
| D4 | `stats.hpp:32` | 字段名拼写错误 `are_m2`（应为 `area_m2`），且无 `std::hash<PixelCoord>` 特化（CODE_MAP 却说用了 hash set） |
| D5 | `stats.hpp:41` | 注释掉的死声明 `simplify_boundary` |
| D6 | `CMakeLists.txt` | 无 `CMakePresets.json`、无 install 规则、无 CTest、版本号 `0.1.0` 在 3 处硬编码 |
| D7 | `services/detection.py:42` | `HTTPException(500, str(e))` 把内部异常原文吐给客户端 |
| D8 | 目录卫生 | `src/core/src/remote-sensing/sensing.ipynb`（笔记本塞进 C++ 源码目录）、根目录 `project_graph`(80 KB 无扩展名) |
| D9 | `src/core/src/tiff_io.cpp:27,99` | `GDALAllRegister()` 在**每次** `read_raster` / `write_raster` 调用内重复执行（一次检测共 3 次）；应在模块初始化时执行一次 |
| D10 | `src/core/src/stats.cpp:79` | `std::unordered_map<int, Region>` 迭代顺序未定义 → `label` 分配顺序跨编译器/平台不确定。当前样本只有 1 个连通域未暴露，多区域场景下 Windows/Linux 的 `label` 可能不一致，**直接威胁 §7.3 的跨平台可复现性断言** |
| D11 | `src/core/src/stats.cpp:116` | `extract_boundary` 在 `pixels.size() < 3` 时返回 `{{}}`（含一个空环，而非空集合），语义含糊；当前仅靠下游 `simple.size() >= 6` 侥幸未崩 |
| D12 | `src/core/src/stats.cpp:271` | Douglas-Peucker 属**开曲线**简化算法，却被直接套用在**闭环**上（`dp_recurse(ring, 0, size-1)`）；闭合环需特殊处理才能保证首尾约束 |

---

## 2. 环境治理「三件套」

> 你说"我弄得太杂了，很难管理"——根因不是库装得多，是**没有隔离、没有配置、没有锁**。三件事解决。

### ① 隔离：`uv` 管理项目级 `.venv`（唯一解释器）

```
Remote_sensing\.venv\         ← uv 基于 DevCode\python\python3.14 (3.14.6) 创建
                                ABI tag 与现有 .pyd (cp314) 完全兼容
```

- 所有依赖只进这个 `.venv`，**不再碰 conda 那个 3.14.7**。
- 铁律：一切命令走 `uv run <cmd>` 或 `.venv\Scripts\python.exe -m pip`，**永不用裸 `pip` / 裸 `python`**（二者都会指回 conda）。
- `.python-version` 内容必须为精确的 `3.14.6`，配合 `pyproject.toml` 的 `requires-python = ">=3.14,<3.15"`。

**为什么是 3.14.6 而不是新建一个 3.13**：现有 C++ 产物 `_spatial.cp314-win_amd64.pyd` 是 cp314 ABI，换 3.13 必须重编；`.venv` 与 base 解释器 ABI 一致，直接复用，零风险。

> ⚠️ **uv 的版本解析陷阱（2026-09-18 实测，必须记住）**
>
> ```
> uv python find 3.14     →  C:\Users\Hujian\CIL\conda\python.exe          ← 空环境，正是 A1 病根
> uv python find 3.14.6   →  C:\Users\Hujian\DevCode\python\python3.14\python.exe  ← 正确
> ```
>
> `.python-version` 若写宽松的 `3.14`，uv 会把 **conda 那个空环境**选出来，等于把 A1 直接焊进工具链，且比手工出错更隐蔽。两条约束必须同时满足：
> 1. `.python-version` 写 `3.14.6`（精确三段版本号）
> 2. `pyproject.toml` 中 `[tool.uv] python-preference = "only-system"`（禁止 uv 下载自管解释器，避免被 3.14.7 抢先）
>
> `bootstrap` 脚本在第 1 步必须断言 `.venv\Scripts\python.exe` 的版本与路径，不匹配即中止（fail fast），不得继续装依赖。

### ② 配置：路径全部外置

```
config/
├── default.toml          # 入库：跨平台默认值
├── local.example.toml    # 入库：模板（含所有可配置项说明）
└── local.toml            # .gitignore：本机真实路径
```

`local.toml` 内容形如：

```toml
[runtime]
host = "127.0.0.1"
port = 8000
data_dir = "./data"
max_upload_mb = 500

[engine]
# Windows 下 GDAL/MinGW 运行时 DLL 目录；Linux 留空走 LD_LIBRARY_PATH
runtime_dll_dir = "C:/Users/Hujian/DevCode/msys64/mingw64/bin"
# C++ 编译产物目录
build_dir = "./engine/build"

[logging]
level = "INFO"          # DEBUG/INFO/WARNING/ERROR
format = "json"         # json | console
```

**关键设计**：全项目只有**一个文件**（`backend/src/rschange/spatial/loader.py`）负责解析这些路径并调用 `os.add_dll_directory`。其余所有模块只 `from rschange.spatial import read_raster`，永不接触路径。

> 优先级链：环境变量 `RSCHANGE_*` > `config/local.toml` > `config/default.toml`

### ③ 锁定：可复现（uv 单一真相源）

```
Remote_sensing/
├── pyproject.toml         # ★ uv workspace 根：members=["backend"] + requires-python + [tool.uv] + ruff/mypy/pytest
├── uv.lock                # ★ 唯一锁文件（覆盖全部成员 + 哈希），入库
├── .python-version        # 精确 3.14.6
└── backend/pyproject.toml # 成员包 rschange：运行/开发依赖分组
```

**采用 uv workspace 而非单包**：把「环境根」与「业务包」分开——根管工具链与锁定，`backend/` 只管自己的依赖声明。新增第二个 Python 包（如未来的 `services/`）时无需重建根配置。

**关键决策**：`requirements.in` / `requirements.lock` **不再使用**。uv 的 `pyproject.toml` + `uv.lock` 已完整覆盖「声明 → 锁定 → 安装」三件事，额外维护一份 pip 格式清单只会制造第二个失同步点。

**`scripts/bootstrap.ps1` 一键流程**（`uv` 版）：

```
1. 断言 uv 存在（uv --version ≥ 0.12），否则提示安装并退出
2. 断言 uv python find 3.14.6 的返回值 == DevCode\python\python3.14\python.exe
   （不匹配即中止 —— 防 §2① 那个陷阱）
3. uv venv --python 3.14.6          # 创建 .venv，不下载自管解释器
4. uv sync --all-packages --all-groups   # 按 uv.lock 精确安装（含 dev 依赖）
5. 从 config/local.example.toml 生成 config/local.toml（若不存在）
6. 打印下一步提示（编译引擎 / 起服务）
```

日常命令一律走 uv，不激活 venv 也能跑：

```
uv run pytest            uv run ruff check backend/       uv run mypy backend/
uv add <pkg>             uv lock --upgrade                uv sync
```

**引擎（C++）不在 uv 管辖范围**：`.venv` 只解决 Python 侧；`_spatial.pyd` 由 CMake 编译后落到 `engine/build/`，由 `spatial/loader.py` 通过 `os.add_dll_directory` + `sys.path` 注入。两条链路在 `loader.py` 汇合，互不耦合。

### 需要准备的依赖（由 `uv sync` 自动完成，此处仅为清点）

| 分组 | 包 | 目标环境里现状 |
|---|---|---|
| C++ 编译期 | `nanobind` | 已装（`.venv` 内需重装） |
| 后端运行时 | `fastapi` `uvicorn[standard]` `pydantic` `pydantic-settings` `python-multipart` `numpy` `scipy` `pyproj` `pillow` | 已装（`.venv` 内需重装） |
| 开发工具 | `pytest` `pytest-cov` `httpx` `ruff` `mypy` | **❌ 全新需要** |
| 数据生成（可选） | `rasterio` | 已装（`.venv` 内需重装） |

> 注：`tomli` 不用装（Python ≥3.11 自带 `tomllib`）；`osgeo` 不用装（`rasterio` 已覆盖）；`scikit-build-core` 可选，本方案用 CMake + 手工路径，不强制。
> **不需要你手工下载任何包**——`uv sync` 会按 `uv.lock` 一次装完，且有哈希校验。你只需确认网络可达 PyPI 镜像。

### 验收门（Phase 1 出口）

- [ ] `uv python find 3.14.6` 返回值等于 `C:\Users\Hujian\DevCode\python\python3.14\python.exe`
- [ ] `.venv` 存在，`.venv\Scripts\python.exe --version` = `3.14.6`
- [ ] `uv run python -c "import fastapi, numpy, scipy, pyproj, PIL, nanobind"` 无报错
- [ ] `uv run pytest --version` / `uv run ruff --version` / `uv run mypy --version` 均可执行
- [ ] `config/local.toml` 已生成且被 git 忽略
- [ ] `git status` 干净（无 `.venv` / `local.toml` / `build/` 混入）
- [ ] 删除 `.venv` 后重跑 `scripts/bootstrap.ps1` 仍一次通过（可复现性证明）

---

## 3. 八阶段路线图

每个阶段遵循同一节拍：
```
① 子 agent 执行 → ② 独立验收 agent 反向核查 → ③ 基线锚点校验 → ④ 打 tag → ⑤ 出验收报告 → ⑥ 人工确认后方可进入下一阶段
```

**阶段与分支的对应**（完整协议见《Remote_Sensing_执行手册_分支与派单.md》）：

> 分支名一律扁平化（连字符），**禁止斜杠**。本机 git 无法写入嵌套引用名，斜杠分支会静默丢失提交（实测，详见执行手册 §8.1）。

| 阶段 | 执行角色 | 集成分支 | 基于 | 任务分支 | tag |
|---|---|---|---|---|---|
| 1 | 🏗 `scaffolder` | `phase-1-bootstrap` | `main` 首次提交 | 4 | `v0.1.0` |
| 2 | ⚙️ `cpp-core` | `phase-2-engine` | `v0.1.0` | 8 | `v0.2.0` |
| 3 | 🐍 `backend` | `phase-3-backend` | `v0.2.0` | 6 | `v0.3.0` |
| 4 | 🎨 `frontend` | `phase-4-frontend` | `v0.3.0` | 4 | `v0.4.0` |
| 5 | 📋 `contract` | `phase-5-contract` | `v0.4.0` | 3 | `v0.5.0` |
| 6 | 🚀 `devops` | `phase-6-cicd` | `v0.5.0` | 3 | `v0.6.0` |
| 7 | ✍️ `writer` + 🕵️ `verifier` | `phase-7-docs` | `v0.6.0` | 5 | `v1.0.0` |

**集成分支一律从上一阶段的 tag 拉出，不直接从 `main` 拉**——这是 `git diff v0.N.0 v0.M.0` 能精确表达「一个阶段做了什么」的前提。

**验收顺序**：验收官在集成分支 tip 上产出证据 → 判定通过后才合入 `main`。判定不通过时集成分支保留待修，`main` 不受影响。

---

### Phase 0 · 基线冻结
**状态：已完成 80%（我在规划阶段顺手做了）**

| 项 | 内容 |
|---|---|
| 子 agent | 🔍 **项目解读师** |
| 产出 | `docs/baseline.md`：黄金数字、血缘图谱、隐式契约、旧代码问题清单 |
| 已得结果 | 阈值 `5.9168`、变化像素 `7209/65536`、GeoJSON `679` 字符、影像 `(3,256,256) uint16`、GDAL `3.12.3`、`_spatial` 在 DevCode 3.14.6 下可加载 |
| 验收门 | 用 `scripts/verify_baseline.py` 一条命令复现上述全部数字 |

---

### Phase 1 · 环境与仓库奠基
| 项 | 内容 |
|---|---|
| 子 agent | 🏗 **框架构建师**（DevEx/Repo Architect） |
| 工作 | 新建 git 仓库；建目录骨架；建 `.venv` + `bootstrap.ps1/sh`；写 `config/` 三件套；写 `.gitignore` / `.gitattributes` / `.editorconfig` / `.python-version`；写 `pyproject.toml` + ruff/mypy/pytest 配置；写 `requirements.in` |
| 产出 | 见 §5 目录结构（除 engine/backend/frontend 源码） |
| 验收门 | ① `scripts/bootstrap.ps1` 在一台干净机器（或删除 `.venv` 后）一键跑通 ② 三件套生效：路径无硬编码（`grep -r "msys64" backend/` 为空）③ git 首次提交干净 |
| **说明** | 本阶段不动任何业务代码，只搭地基。**这是"进入 Phase 1"的标志** |

---

### Phase 2 · C++ 引擎解耦
| 项 | 内容 |
|---|---|
| 子 agent | ⚙️ **核心代码师**（C++ Core Engineer） |
| 工作 | ① 单头文件拆成 6 个职责头（`raster/region/labeling/contour/simplify/geojson`）+ `export.hpp` 收敛 `SPATIAL_API` ② `stats.cpp` 12923 字节拆成 `labeling.cpp` / `contour.cpp` / `simplify.cpp` / `geojson.cpp` ③ 修 `are_m2` → `area_m2`、补 `std::hash<PixelCoord>`、删死声明 ④ `nlohmann/json.hpp` 换成 `FetchContent`（去掉 1 MB 入库文件）⑤ `CMakePresets.json`（`dev-win` / `dev-linux` / `release`）⑥ 接 CTest，补 4 个 C++ 单测 ⑦ `nanobind_add_module` 补 `STABLE_ABI` 评估与 install 规则 ⑧ 编译加 `-Werror` |
| 产出 | `engine/` 完整可编译 + CTest 全绿 |
| 验收门 | ① `ctest --preset dev-win` 全绿 ② `_spatial` 在新路径下可 `import` ③ **基线数字不变** ④ `nm -D` 确认导出符号齐全 |
| 风险 | 拆文件时符号可见性回归（历史坑：`-fvisibility=hidden`）。→ `export.hpp` 单点收敛就是为防这个 |

---

### Phase 3 · 后端分层解耦
| 项 | 内容 |
|---|---|
| 子 agent | 🐍 **后端师**（Backend Engineer） |
| 工作 | ① 迁移到 src-layout 包 `backend/src/rschange/` ② `config.py` → `pydantic-settings`（三件套配置）③ `spatial/loader.py` 唯一负责 DLL 路径 + `_spatial` 加载 ④ 拆 `run_detection` 为 `pipeline/change_detection.py`（纯编排，依赖注入）⑤ 算法抽象：`detectors/base.py`（`ChangeDetector` 协议）+ `registry.py`（注册表，可插拔）⑥ 后处理同样抽象 ⑦ `io/preview.py` 出图、`io/reproject.py` 重投影，各自独立可测 ⑧ 结构化日志（`structlog` 风格自实现，去掉 `print`）⑨ 领域异常 + 全局异常处理器（不再泄漏内部异常原文）⑩ 修 CORS 反模式 ⑪ `create_app()` 工厂函数（便于测试注入）⑫ pytest 套件：单元 + 集成 + 基线锚点断言 |
| 产出 | `backend/` 可 `pip install -e .`，`pytest` 全绿 |
| 验收门 | ① `pytest` 全绿（≥15 个用例）② **基线锚点断言通过** ③ `ruff check` + `mypy` 零错误 ④ `POST /api/detect` 手测返回与旧版字段一致 |
| 关键 | 这一阶段是"解耦"的主战场。判断标准：能否在不改主流程的前提下新增一个检测算法（答案必须为"能"） |

---

### Phase 4 · 前端工程化
| 项 | 内容 |
|---|---|
| 子 agent | 🎨 **前端师**（Frontend Engineer） |
| 工作 | ① TS `strict: true` + `noUncheckedIndexedAccess` ② 引入 TanStack Query 替代手写 `useDetection` 状态机 ③ 按 feature 重组：`features/detection/{components,hooks,api}` ④ 抽取 `components/ui/` 基础组件 ⑤ Vitest + Testing Library 补组件测试 ⑥ 错误边界 + Loading 骨架 ⑦ Tailwind 规范化（`index.css` 只有 75 字节，需补主题变量）⑧ `npm run check`（tsc + oxlint + vitest 串起来） |
| 产出 | `frontend/` 可 `npm run build` |
| 验收门 | ① `npm run check` 全绿 ② `npm run build` 产物 < 300 KB gzip ③ 手工上传 before/after 出三图对比正确 |

---

### Phase 5 · 契约同步与端到端集成
| 项 | 内容 |
|---|---|
| 子 agent | 📋 **契约师**（API Contract Engineer） |
| 工作 | ① 冻结 OpenAPI schema → `docs/api/openapi.json`（入库，视为契约）② 前端类型从 OpenAPI **自动生成**（`openapi-typescript`），消灭"手工同步 TS 类型"这个隐患 ③ 写契约测试：后端响应必须匹配冻结 schema ④ 端到端集成测试（httpx 起 app → 上传真 tif → 断言基线）⑤ `scripts/gen-api-types.ps1/sh` |
| 产出 | 前后端类型同源 |
| 验收门 | ① 契约测试通过 ② 改了后端响应字段而没重生成类型时，CI 会**红**（证明这道闸有效）|
| 价值 | 这条是"工程化"最有说服力的产出之一，面试可讲：**契约先行 + 类型自动生成** |

---

### Phase 6 · 容器化与 CI
| 项 | 内容 |
|---|---|
| 子 agent | 🚀 **DevOps 师**（CI/CD Engineer） |
| 工作 | ① 修 Dockerfile：解决 3.12 vs 3.14 不一致（统一 3.14）、runtime 阶段只装 `libgdal`（不装 `-dev`）② `docker/Dockerfile.frontend` + `nginx.conf` ② GitHub Actions：**双平台矩阵**（`windows-latest` MinGW + `ubuntu-latest`），步骤：装 GDAL → 编 C++ → 装依赖 → CTest → pytest → 前端 check → 契约测试 ③ 依赖缓存（pip / npm / ccache）④ 修历史坑：`MSYS2_ARG_CONV_EXCL="*"` 写进脚本注释防复发 |
| 产出 | `.github/workflows/ci.yml` + 可用的 compose |
| 验收门 | ① push 后 Actions 双平台全绿 ② `docker-compose up` 后 `curl POST /api/detect` 返回基线数字 ③ 冷启动到出结果有耗时记录 |
| 风险 | Linux 侧 GDAL 版本与 Windows 的 3.12.3 可能不同 → 需在 CI 里钉版本或允许差异（用容差断言） |

---

### Phase 7 · 文档固化与终验
| 项 | 内容 |
|---|---|
| 子 agent | ✍️ **技术写作者** + 🕵️ **验收官**（对抗式） |
| 工作 | ① `README.md`（5 分钟跑通）② `docs/ARCHITECTURE.md`（架构图 + 数据流，从旧 CODE_MAP 升级）③ `docs/MIGRATION.md`（旧文件 → 新文件逐条对照）④ `docs/DEVELOPMENT.md`（如何加一个检测算法，给出完整示例）⑤ `docs/lessons/`（迁移 `Debug_lesson.txt` / `project2-lessons-and-interview.txt`，按主题归档）⑥ 更新面试讲稿（新技术点：契约生成、双平台 CI、可插拔算法）⑦ `CONTRIBUTING.md` |
| 验收门 | ① **盲测**：让一个没读过旧代码的人（或新会话的 agent）仅凭 README 从零跑通 ② 基线数字终检 ③ 旧仓库打 `archived` 标记 |

---

## 4. 子 agent 角色表

| 角色 | 代号 | 负责阶段 | 核心职责 | 交付判据 |
|---|---|---|---|---|
| 🔍 项目解读师 | `archaeologist` | 0 | 逆向旧代码，产出血缘图谱 / 隐式契约 / 基线 | 基线数字可复现 |
| 🏗 框架构建师 | `scaffolder` | 1 | 仓库骨架、环境三件套、脚本、规范 | `bootstrap` 一键跑通 |
| ⚙️ 核心代码师 | `cpp-core` | 2 | C++ 引擎解耦、CMake 现代化、算法零回归 | CTest 全绿 + 基线不变 |
| 🐍 后端师 | `backend` | 3 | Python 分层、DI、可插拔、日志、异常 | pytest 全绿 + 可插拔验证 |
| 🎨 前端师 | `frontend` | 4 | TS 严格化、状态库、组件化、测试 | `npm run check` 全绿 |
| 📋 契约师 | `contract` | 5 | OpenAPI 冻结、类型生成、契约测试 | 契约漂移能被 CI 抓住 |
| 🚀 DevOps 师 | `devops` | 6 | 双平台 CI、容器化、缓存 | Actions 双平台绿 |
| ✍️ 技术写作者 | `writer` | 7 | README / 架构 / 迁移 / 教程 | 盲测跑通 |
| 🕵️ 验收官 | `verifier` | 每阶段 | **对抗式核查**：默认假设上一个 agent 在说谎 | 驳回权；基线锚点比对 |

**协作规则**：
1. **验收官独立于执行者**——同一阶段不容许"自己写自己验"。
2. 验收官的默认立场是**怀疑**（符合你要"指出问题"的偏好）：不接受"应该没问题"，只接受命令输出。
3. 并行仅在**无写冲突**时开启。Phase 2/3/4 之间接口未冻结，**串行**执行；Phase 6 的 CI 与 Phase 7 的文档可并行。
4. 跨阶段接口（`_spatial` 的 Python 签名、HTTP 响应 schema）在 Phase 2 结束时**冻结并写入 `docs/contracts.md`**，之后任何改动需走"改契约 → 改两端"流程。

---

## 5. Git 搭桥策略（两级分支 + 证据线）

```
main  ──●════════════════●════════════════●════════════════●──→  稳定线，只接受 --no-ff 合入
         ║                ║                ║                ║
         ║  phase-1       ║  phase-2       ║  phase-3       ║
         ║  ├task-1.1     ║  ├task-2.1     ║  ├task-3.1     ║
         ║  ├task-1.2     ║  ├task-2.2     ║  ├task-3.2     ║
         ║  └task-1.3     ║  └task-2.3     ║  └task-3.3     ║
         ▼                ▼                ▼                ▼
      v0.1.0 ─────────→ v0.2.0 ─────────→ v0.3.0 ─────────→ v0.4.0
         ↑                ↑                ↑
   verify-1-report  verify-2-report  verify-3-report        （证据线，独立于执行者）
```

**规则**：

1. **全新初始化**：`Remote_sensing` 从零 `git init`，不继承旧历史。
2. **一阶段一集成分支**：`phase-N-<slug>`，完成后以 `--no-ff` 合入 `main` 并打 tag `v0.N.0`。
   - **不用 squash**：squash 会把任务级历史压平，丢掉「单个任务改动可单独 revert」的能力。`--no-ff` 合入后 `main` 上每个阶段仍只占一个合并节点，历史同样清爽。
3. **搭桥（关键）**：下一阶段**从上一阶段的 tag 拉分支**，而不是从 `main`：
   ```
   git switch -c phase-2-engine v0.1.0
   ```
   好处：任两阶段之间可随时 `git diff v0.1.0 v0.2.0` 看精确变化；出问题可精确回退到某一阶段。
4. **任务分支隔离单点改动**：`task-N.K-<slug>` 从本阶段集成分支拉出，`--no-ff` 合回集成分支后即删。**仅当文件集不相交时才并行**（冲突热点清单见执行手册 §4）。
5. **证据线独立**：`verify-N-report` 由验收官从集成分支 tip 检出，只写 `docs/verification/`，先并入集成分支、再随集成分支进 `main`。**tag 打在证据合入之后**，使 tag 点自带验收结论。
   - **顺序修正**：验收必须在合入 `main` 之前完成。判定不通过时不合入，`main` 零损失。
6. **旧仓库当只读远端**：
   ```
   git remote add legacy ../Remote_Sensing_Change_Detection
   git fetch legacy
   git show legacy/main:src/core/src/stats.cpp      # 仅对已入库文件有效
   ```
   **只读引用，绝不 merge**——保证新仓库历史干净。

   > ⚠️ **已实测的坑**：旧仓库仅 2 个提交，且 `CODE_MAP.md`、`DOCKER_PLAN.md`、`GEO_CAPABILITIES.md`、`project2-lessons-and-interview.txt` **未被 git 跟踪**（`git status --porcelain` 显示为 `??`）。对这四个文件执行 `git show legacy/main:<path>` 会报 `path does not exist`。其中 `CODE_MAP.md` 恰是要升级为 `docs/ARCHITECTURE.md` 的核心资产——**必须从工作区直接读取**，且迁移期间禁止对旧仓库做任何写操作（`git add` / `stash` / `checkout` 一律禁止）。
7. **迁移对照**：`docs/MIGRATION.md` 逐条记录「旧文件 → 新文件 → 变更说明」，替代 git history 的追溯功能。
8. **`.gitattributes`** 管住换行符（Windows/Linux 双平台必需）与二进制 tif 的 diff 行为。
9. **回退策略**：阶段中途放弃 → 什么都不合（零损失）；已合但发现回归 → `git revert -m 1 <merge>`（保留可审计历史）；`reset --hard` 仅在未推送时允许。

---

## 6. 目标目录结构

```
Remote_sensing/
├── pyproject.toml                  # ★ uv workspace 根：members=["backend"]；集中 ruff/mypy/pytest 配置
├── uv.lock                         # ★ 唯一锁定文件（覆盖全部成员，入库）
├── .python-version                 # 精确 3.14.6
├── .github/workflows/
│   └── ci.yml                      # 双平台矩阵
├── .vscode/                        # tasks/launch/settings/extensions
├── config/
│   ├── default.toml                # 入库
│   ├── local.example.toml          # 入库（模板）
│   └── local.toml                  # gitignore
├── docs/
│   ├── baseline.md                 # Phase 0 基线锚点
│   ├── ARCHITECTURE.md             # 由 CODE_MAP.md 升级
│   ├── MIGRATION.md                # 旧→新对照
│   ├── DEVELOPMENT.md              # 如何新增一个检测算法
│   ├── deploy.md                   # 由 DOCKER_PLAN.md 归档改写
│   ├── agent-capabilities.md       # 由 GEO_CAPABILITIES.md 迁入
│   ├── contracts.md                # 冻结的跨阶段接口
│   ├── api/openapi.json            # 契约
│   ├── verification/               # ★ 验收官证据（phase-N.md），由 verify/N-report 分支产出
│   ├── archive/                    # initial-architecture-plan.txt（原 project_graph）
│   └── lessons/                    # debugging.md / interview.md
├── engine/                         # ── C++ 空间引擎 ──
│   ├── CMakeLists.txt
│   ├── CMakePresets.json
│   ├── include/spatial/
│   │   ├── export.hpp              # SPATIAL_API 唯一定义
│   │   ├── raster.hpp
│   │   ├── region.hpp
│   │   ├── labeling.hpp
│   │   ├── contour.hpp
│   │   ├── simplify.hpp
│   │   └── geojson.hpp
│   ├── src/
│   │   ├── raster_io.cpp
│   │   ├── gdal_init.cpp           # GDALAllRegister() 一次性初始化
│   │   ├── labeling.cpp
│   │   ├── contour.cpp
│   │   ├── simplify.cpp
│   │   ├── geojson.cpp
│   │   └── version.cpp
│   ├── bindings/module.cpp         # nanobind → _spatial
│   └── tests/
│       ├── CMakeLists.txt
│       ├── test_raster_io.cpp
│       ├── test_labeling.cpp
│       ├── test_simplify.cpp
│       └── fixtures/{before,after}.tif
├── backend/                        # ── Python 后端（uv workspace 成员）──
│   ├── pyproject.toml              # name = "rschange"；运行/开发依赖分组
│   └── src/rschange/
│       ├── config.py               # pydantic-settings
│       ├── logging.py
│       ├── errors.py
│       ├── spatial/
│       │   ├── loader.py           # ★ 唯一解析 DLL 路径的地方
│       │   └── raster.py
│       ├── detectors/
│       │   ├── base.py             # ChangeDetector 协议
│       │   ├── cva.py
│       │   └── registry.py         # 可插拔注册表
│       ├── postprocess/
│       │   ├── base.py
│       │   └── morphology.py
│       ├── pipeline/change_detection.py   # 纯编排（原 run_detection）
│       ├── io/
│       │   ├── preview.py
│       │   └── reproject.py
│       ├── api/
│       │   ├── app.py              # create_app() 工厂
│       │   ├── deps.py
│       │   ├── routers/{detection,health}.py
│       │   └── schemas/detection.py
│       └── tests/
│           ├── conftest.py
│           ├── test_cva.py
│           ├── test_postprocess.py
│           ├── test_spatial_bindings.py
│           ├── test_pipeline.py    # ★ 基线锚点断言
│           └── test_api.py
├── tests/
│   ├── api/                        # 原 api_tests/（重新纳入版本控制）
│   └── contract/                   # Phase 5 契约测试 + e2e
├── frontend/                       # ── React 前端 ──
│   ├── package.json
│   ├── vite.config.ts
│   ├── vitest.config.ts
│   └── src/
│       ├── api/{generated,client.ts}   # ← OpenAPI 自动生成
│       ├── features/detection/{components,hooks,types.ts}
│       ├── components/ui/
│       ├── styles/index.css
│       └── App.tsx
├── notebooks/                      # 原 src/core/src/remote-sensing/sensing.ipynb
├── scripts/
│   ├── bootstrap.ps1 / .sh         # uv 版一键环境
│   ├── build-engine.ps1 / .sh
│   ├── dev.ps1 / .sh               # 同时起前后端
│   ├── gen-api-types.ps1 / .sh
│   ├── gen_fixtures.py
│   ├── verify_baseline.py          # ★ 基线锚点一键校验
│   └── clean.ps1 / .sh
├── docker/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── nginx.conf
├── docker-compose.yml
├── data/{uploads,outputs}/.gitkeep
├── .editorconfig  .gitattributes  .gitignore  .dockerignore
├── CHANGELOG.md  CONTRIBUTING.md  README.md
```

---

## 7. 验收锚点（黄金基线）

`scripts/verify_baseline.py` 必须能一条命令复现下列全部。

### 7.1 不变量（必须一字不变；漂移即回归缺陷）

| 指标 | 期望值 | 容差 |
|---|---|---|
| 影像形状 | `(3, 256, 256)` | 精确 |
| dtype | `uint16` | 精确 |
| geo_transform | `[500000.0, 10.0, 0.0, 4000000.0, 0.0, -10.0]` | 精确 |
| 投影 | `PROJCS["WGS 84 / UTM zone 50N"...]` | 前缀匹配 |
| Otsu 阈值 | `5.9168` | ±1e-4 |
| 变化像素（原始） | `7209` | 精确 |
| 变化像素（后处理后） | `7209` | 精确 |
| 变化率 | `7209 / 65536` | ±1e-6 |
| 真实变化面积 | `720900.0` m² | ±1e-6 |
| 每个 GeoJSON 环首尾闭合 | 成立（旧引擎输出两段**闭合**弧） | 精确 |

> 归口修订（2026-09-18）：`每个环首尾闭合` 在旧引擎上即已成立——它输出的是两段闭合弧，
> 而非开口折线。因此该项是**不变量**，必须归 §7.1。先前的草稿把它放进 §7.3，
> 会把「修复前的正确行为」误判为「缺陷基线」，导致 Phase 1 的期望状态无法成立。

### 7.2 已知缺陷基线（Phase 2 **必须改变**；未改变即修复未完成）

| 指标 | 现状（错误值） | Phase 2 目标 | 关联缺陷 |
|---|---|---|---|
| GeoJSON Feature 个数 | `2` | `1` | §1 A4 单连通域被拆成 2 段弧 |
| `sum(properties.area_m2)` | `1441800.0` m² | `720900.0` m² | §1 A4 面积重复计 2 倍 |
| GeoJSON 字节长度 | `679` | 由修复结果决定（**不再作为锚点**） | — |

### 7.3 新增语义断言（旧版未覆盖；重构后必须成立）

| 断言 | 现状 | 目标 |
|---|---|---|
| `len(features) == 连通域个数` | ❌ `2 ≠ 1` | 相等 |
| `sum(properties.area_m2) == 变化像素数 × 单像元面积` | ❌ 2 倍虚报 | 相等（±1e-6） |
| 多区域场景下 `label` 分配顺序确定 | ❌ `unordered_map` 迭代序未定义 | 按 raster-scan 首次出现顺序 |
| 每个 Polygon 不自交、可被 GEOS 解析 | 未验证 | 通过 |

**Phase 1 的期望状态**（`verify_baseline.py --phase 1` 必须复现）：

| 组 | 期望 | 理由 |
|---|---|---|
| §7.1 不变量 | 全部 `PASS` | 不变量在修复前后都必须成立 |
| §7.2 缺陷基线 | 全部 `FAIL` | 缺陷尚未修复，**失败才是正确结果** |
| §7.3 语义断言 | 全部 `FAIL` | 语义改进尚未落地 |

> ⚠️ **本节是整条流水线的唯一真理。**
> §7.1 任何漂移一律按回归缺陷处理，不接受"新算法更好"作为辩解。
> §7.2 若修复后数值**未改变**，说明该项修复未完成，该阶段判定为 `不通过`。
> §7.3 是把"跑得通"提升为"结果可信"的关键闸门；缺任一项，Phase 2 不得通过。

---

## 8. 风险与取舍（明码标价）

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| 拆 C++ 文件导致符号导出回归 | 中 | 高（`import _spatial` 崩） | `export.hpp` 单点收敛 + `nm -D` 断言进 CI |
| Linux CI 的 GDAL 版本 ≠ 3.12.3 | 高 | 中（阈值微差） | 基线断言加容差；CI 里钉 GDAL 版本 |
| 契约生成引入新工具链 | 中 | 低 | 只在 Phase 5 引入，此时后端已稳定 |
| 阶段过多导致半途而废 | 中 | 高 | 每阶段独立可交付；Phase 1 完成后工程质量即已优于现状，允许在任一阶段停止且不留半成品 |
| 前端重构收益低（当前只有 3 个组件） | 中 | 低 | Phase 4 可降级为"只做 TS 严格化 + 测试"，不引状态库 |
| venv 隔离后需重装全部依赖 | 高 | 低 | `bootstrap.ps1` 一次装完，可接受 |

**明确的取舍**：
- ✅ 保留 C++ 引擎（这是项目最有面试价值的部分，不推倒重来）
- ✅ 保留算法（CVA + Otsu + Two-Pass + Moore + DP），**一个字不改逻辑**
- ❌ 不引入 Celery/Redis 任务队列（Phase 3 只做接口预留，不落地，避免过度工程）
- ❌ 不迁移到 vcpkg（按你决定，保持 MSYS2 + 路径配置化）
- ❌ 不做微服务拆分（单体分层足够）

---

## 9. 执行前置条件与交付规范

### 9.1 进入 Phase 1 的前置条件（阻塞项）

| # | 条件 | 责任方 | 状态 |
|---|---|---|---|
| P1 | 本方案与《执行手册》经确认 | 胡建 | 待确认 |
| P2 | `uv` 可用（`uv --version` ≥ 0.12） | — | ✅ 已满足（`0.12.5`，`C:\Users\Hujian\CIL\uv\uv.exe`） |
| P3 | `git` 可用 | — | ✅ 已满足（`2.54.0.windows.1`） |
| P4 | 网络可达 PyPI 镜像（供 `uv sync` 拉包） | 胡建 | 待确认 |
| P5 | `Remote_sensing` 目录保持为空 | — | ✅ 已满足（实测 0 条目） |
| P6 | 旧仓库在迁移期间**不做任何写操作** | 胡建 | 待确认（当前有 5 项未提交变更） |

**依赖清单**（13 个包，全部由 `uv sync` 自动落地，无需手工下载）：

- 需要新增到声明中：`pytest`、`pytest-cov`、`ruff`、`mypy`
- 需要在新 `.venv` 内重装：`nanobind`、`fastapi`、`uvicorn[standard]`、`pydantic`、`pydantic-settings`、`python-multipart`、`numpy`、`scipy`、`pyproj`、`pillow`、`httpx`、`rasterio`

> **不需要 `pip install`**。唯一的外部前置是 `uv`（已就位）与网络可达。

### 9.2 阶段交付规范（每阶段结束必须提供，缺项即视为未完成）

1. 阶段编号与整体进度定位
2. 文件级改动清单
3. 验证命令及其**真实输出**（不接受描述性结论）
4. 验收门判定：`通过` / `不通过`。判为不通过时，该阶段不得推进至下一阶段
5. 下一阶段的输入清单

### 9.3 验收规范

- 验收官独立于执行者；同一阶段禁止自写自验
- 默认立场为怀疑：判定依据只能是命令输出，不接受"应该没问题"
- 基线锚点（§7）任何漂移一律按回归缺陷处理，优先级高于功能演进
- 跨阶段接口冻结后（见 §4 协作规则 4），修改须走「改契约 → 改两端」流程，禁止单侧变更

---

*文档版本 v1.0 · 制定于 Phase 0 完成后*
