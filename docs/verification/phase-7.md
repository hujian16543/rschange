# Phase 7 验收报告 · 文档固化与终验

> 独立验收官出具。所有判定取自本机当场重跑的真实命令输出、逐行源码核对与对旧仓库的只读核查，未作人工修饰。
> 本报告**只读**被测代码；唯一写入的仓库内文件即本文件（`docs/verification/phase-7.md`）。
> 探针日志与临时目录留在 `_work/p7/`，**未**进入仓库。
> 报告写入前后均核对 `git status --porcelain`：均为空（见 §7）。

> ### 本阶段形态说明
>
> Phase 7 为**文档固化与终验**阶段：产品代码与黄金基线冻结在 Phase 6，本阶段交付物是
> 四份工程文档（`ARCHITECTURE.md` / `DEVELOPMENT.md` / `MIGRATION.md` / `CONTRIBUTING.md`）、
> 三份调试教训（`docs/lessons/`）、四份归档文档（`docs/archive/`）与 README 定稿。
> 因此本报告的重心不是功能回归，而是：**文档所述是否与代码/命令实测一致、引用是否可逐条核查、
> 基准数字是否仍为真**。三条出口门 G7.1 / G7.2 / G7.3 分别覆盖盲测可用性、基线数字终检、旧仓库归档。

---

## 1. 验收对象与基准

| 项 | 内容 |
|---|---|
| 上一阶段 tag | **`v0.6.0`**（附注标签，标签对象 `9263058…`；`v0.6.0^{}` = 提交 `d5bfd1b`「Merge branch 'phase-6-cicd' into main」） |
| 本轮交付目标 | `T7.1` 盲测（无口口相传的隐含前提）；`T7.2` 基线数字终检；`T7.3` 旧仓库归档 tag；`T7.4` 四份工程文档 + 三份调试教训落库；`T7.5` README 定稿与版本 1.0.0 |
| 被检 tip | `3fa483b`（分支 `phase-7-docs` 与证据线 `verify-7-report` **同点**） |
| 版本真相源 | `backend/pyproject.toml:17` `version = "1.0.0"`，由 `scripts/verify_version.py` 守护 5 个判据 |
| 受管文件基线 | `git ls-tree -r v0.6.0` = **165**；`git ls-files`（HEAD）= **174**；净增 9（新增 11、删除 2、其余为修改，见 §2） |
| 本阶段分支形态 | 手册 §5 判定准则为「任务数 ≤ 3 且无并行需求 → 精简模式」；Phase 7 任务数为 **5**（7.1–7.5），**超过**阈值却仍走精简模式（L1 `phase-7-docs` + 证据线 `verify-7-report`，无 L2）。属对手册判定准则的**显式偏离**——已在 `CONTRIBUTING.md:35-37` 明文登记，判定见 §2 |
| L1 拉取基准 | `git merge-base v0.6.0 phase-7-docs` = `d5bfd1b`（= `v0.6.0^{}`），即 L1 确从上一阶段 tag 拉出，非从 `main` |
| 提交跨度 | `git rev-list --count v0.6.0..phase-7-docs` = **10** |

---

## 2. 交付范围与分支纪律

### 2.1 交付文件集合（`git diff --name-status v0.6.0 phase-7-docs`，共 29 项）

| 类别 | 条目 | 说明 |
|---|---|---|
| 新增 · 工程文档（4） | `CONTRIBUTING.md`、`docs/ARCHITECTURE.md`、`docs/DEVELOPMENT.md`、`docs/MIGRATION.md` | 本阶段核心交付 |
| 新增 · 调试教训（3） | `docs/lessons/README.md`、`debug-lessons.md`、`interview-notes.md` | 旧仓库两类素材整理版（合计 660 行） |
| 新增 · 过程归档（4） | `docs/archive/README.md`、`execution-handbook.md`、`migration-map.md`、`refactor-plan.md` | 历史记录，非规范 |
| 修改 · README（1） | `README.md`（270 行） | 按 G7.1 盲测结果定稿「5 分钟跑通」 |
| 修改 · 既有文档（3） | `docs/algorithm.md`、`docs/contracts.md`、`docs/api/openapi.json` | 口径更正 + 版本随迁（`info.version` 1.0.0） |
| 修改 · 版本（5） | `backend/pyproject.toml`、`pyproject.toml`、`frontend/package.json`、`uv.lock`、（`docs/api/openapi.json` 已计上） | 0.6.0 → 1.0.0 |
| 修改 · 预设（1） | `engine/CMakePresets.json` | **本阶段唯一的源码改动**：删除 `win-base` 中未被使用的 `CMAKE_C_COMPILER`（见 §4.4） |
| 修改 · 脚本（5） | `scripts/bootstrap.{sh,ps1}`、`gen-api-types.sh`、`verify_baseline.py`、`verify_version.py` | 注释 / 提示文本更正，**无行为变更**（diff 逐条核对见 §4.4） |
| 修改 · 注释（2） | `backend/src/rschange/detectors/__init__.py`、`engine/src/internal/gdal_registry.hpp` | 仅 docstring / 注释（45 → 42、注册路径措辞） |
| 删除（2） | `docs/archive/.gitkeep`、`docs/lessons/.gitkeep` | 占位符，目录已实际填充 |

分类计数：**新增 11 / 修改 16 / 删除 2 = 29**。

### 2.2 分支纪律判定

- 精简模式下 L1 `phase-7-docs` 从上一阶段 tag（`v0.6.0^{}` = `d5bfd1b`）拉出，未从 `main` 拉取，
  符合 `CONTRIBUTING.md` §1.1。
- 证据线 `verify-7-report` 从 L1 tip `3fa483b` 检出，**只**写 `docs/verification/phase-7.md`，
  与 L1 交付物集合互不重叠。
- **分支形态偏离（显式登记）**：手册 §5 判定准则为「任务数 ≤ 3 且无并行需求」，Phase 7 有 5 个任务，
  本应触发完整模式，实际仍用精简模式。偏离理由：五个任务全部只新增/修改文档、彼此无独立 revert 价值，
  且本仓库 `.git` 目录损坏事故已复发（`CONTRIBUTING.md:69-73`、`docs/verification/phase-6.md` 附录 A.3）。
  **后果判定**：失去单任务粒度回退能力；但阶段级隔离与验收证据链完整，且偏离已落库披露，
  不构成纪律违规。**判定：通过（含显式偏离）。**

---

## 3. G7.1 —— 盲测通过（无口口相传的隐含前提）

**判据（派单 §4 G7.1）**：README「5 分钟跑通」的 6 步在**命令形态与期望输出**上可照做；
盲测指出的隐含前提是否已写入 README；剩余卡点是否归因于环境限制而非文档缺陷。

### 3.1 对盲测报告的自洽性评估

独立阅读 `_work/p7/blind/report.md`（6 步全流程）与 `report-step3.md`（步骤 3 干净目录补做）：

- 首轮盲测的步骤 3 卡点（`cmake --preset dev-win` 退出码 1 + Ninja `Re-running CMake…` 无限循环）
  被正确归因为**预置构建目录内嵌开发仓库绝对路径**这一「预置副作用」，而非 README 缺陷；
- `report-step3.md` §C 以「把 `engine/build` 整体改名 → 全新 configure」消除了该副作用，
  一次跑通（configure rc=0 / 321.2 s，build rc=0 / 146 步），归因**成立且可复现**；
- 首轮步骤 4b 的 pytest 误报（`tests=145 failures=1`，`test_openapi_frozen` 报 `0.6.0` ≠ 重生成 `1.0.0`）
  归因为预置 `.venv` 启动器内嵌原仓库解释器，属**预置副作用**，重建 `.venv` 后 `148 passed`——归因正确；
- 其余卡点（`npm ci` 被 safe-delete 拦截、Node 24 需求 vs 默认 22、safe-delete 提示覆盖汇总行）
  归为**环境限制**，定性准确。
- 盲测声明「README 缺陷 0 条」与「步骤 3 的 configure 在干净树下亦因网络失败」的披露**自洽**：
  `github.com` 主机名 SNI 被本机封锁、而 CMake `FetchContent` 实际走 `codeload.github.com`（可达），
  已在 `report.md` §5 与 `report-step3.md` §E 显式披露。

**结论**：盲测报告证据自洽、归因正确，无「结论先于证据」的痕迹。

### 3.2 独立复跑（不引用盲测日志）

| 复跑项 | 命令 | 实测结果 | 退出码 |
|---|---|---|---|
| 引擎就地重配 | `cmake --preset dev-win`（`engine/` 下，注入三个 `SPATIAL_*` 环境变量） | `Configuring done (2.1s)` / `Generating done (0.2s)`，**无 `CMAKE_C_COMPILER` 告警** | **0** |
| 引擎构建 | `cmake --build --preset dev-win` | `ninja: no work to do.` | **0** |
| C++ 单测 | `ctest --test-dir engine/build/dev-win --output-on-failure` | `100% tests passed out of 40`（8.29 s） | **0** |
| 黄金基线 | `uv run python scripts/verify_baseline.py --phase 6` | §7.1 **11/11**、§7.2 **2/2**、§7.3 **7/7**，`结论：通过 —— Phase 6 预期状态已达成` | **0** |
| 后端+契约测试 | `uv run pytest -o addopts="" -rs --basetemp=<工作区外目录>` | `148 passed, 2 warnings`（17.69 s） | **0** |

> **safe-delete 现象（如实登记）**：原样 `uv run pytest -o addopts="" -rs` 在退出前清理临时目录时会被
> 本机 safe-delete 守卫拦截（`_work/p7/evidence/pytest.log` 末行 `EXIT=1`，附
> `[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED] {"count":139,...}`）。**该退出码 1 与用例无关**：
> 本次以 `--basetemp` 指向工作区外目录重跑，同一用例集 **rc=0 / 148 passed**。据此**不**判功能失败。

**判定：通过。** README 6 步命令形态与两个可独立核验的关键期望（`ctest` 的 `100% tests passed`、
`verify_baseline --phase 6` 的 `通过 —— Phase 6 预期状态已达成`）当场逐字命中；剩余卡点归因于环境限制。

### 3.3 README 是否写入盲测指出的 5 处隐含前提

逐条给出 README 行号与原文（**全部命中**）：

| # | 盲测指出 | README 落点 | 原文（节选） |
|---|---|---|---|
| 1 | 联网/耗时 | `README.md:40-43` | 「依赖已就绪时全流程约 5 分钟。**首次执行需要联网**：第 3 步的 CMake 配置会经 `FetchContent` 从 `codeload.github.com` 获取 …（合计约 9 MB）… 慢速网络中首次配置耗时数分钟属预期行为，不是卡死。」 |
| 2 | `local.toml` 的 `runtime_dll_dir` 空值与环境变量兜底 | `README.md:59` | 「引导脚本生成的 `config/local.toml` 中 `engine.runtime_dll_dir` 为**空**…Windows 上该项由第 2 步的 `RSCHANGE_ENGINE__RUNTIME_DLL_DIR` 环境变量兜底，本流程无需手工填写…」 |
| 3 | 步骤 2 环境变量的会话范围 | `README.md:74` | 「这些变量只对**当前终端会话**有效。第 3 至第 5 步必须在同一会话内依次执行；只有第 6 步需要另开终端。」 |
| 4 | 步骤 3 失败后需复位工作目录 | `README.md:87` | 「若这一步失败，**必须先 `Pop-Location` 回到仓库根**再继续，否则后续 `uv run` 会在 `engine/` 下执行而找不到工作区。」 |
| 5 | 本机代理接管 `127.0.0.1` | `README.md:111` | 「若本机设置了 `HTTP_PROXY` / `HTTPS_PROXY`，对 `127.0.0.1` 的请求可能被代理接管而返回 502——此时用 `curl --noproxy '*' http://127.0.0.1:8000/` 或浏览器直接访问。」 |

Linux 分支（`README.md:150`、`:163`、`:184`）对第 2/3/4/5 点给出等价表述。

**判定要点复核**：README 的 6 步**不存在「照做即失败」的表述**；剩余卡点（网络封锁、safe-delete
守卫、Node 版本解析）均可归入**环境限制**而非文档缺陷。

---

## 4. G7.2 —— 基线数字终检

**判据（派单 §4 G7.2）**：重跑全量门禁并与文档声明数字逐条对照；主动检索应已不存在的过时数字；
抽取 10 条以上 `文件:行号` 引用逐条到源码核对。

### 4.1 全量门禁重跑（当场）

| 门禁 | 命令 | 文档声明 | 当场实测 | 判定 |
|---|---|---|---|---|
| C++ 单测 | `ctest --test-dir engine/build/dev-win --output-on-failure` | 40 | **40/40**，`100% tests passed` | 通过 |
| 后端+契约 | `uv run pytest -o addopts="" -rs --basetemp=…` | 收集 148 / 静态 `def test_` 123 | **148 passed**；静态 `def test_` = backend **112** + 根 `tests/` **11** = **123** | 通过 |
| 类型检查 | `uv run mypy` | 36 文件 | `Success: no issues found in 36 source files` | 通过 |
| 代码检查 | `uv run ruff check .` | 通过 | `All checks passed!` | 通过 |
| 代码格式 | `uv run ruff format --check .` | **51 files** | `51 files already formatted` | 通过 |
| 契约第一段 | `uv run python scripts/gen_openapi.py --check` | PASS | `[PASS] 契约产物与当前代码一致：docs/api/openapi.json` | 通过 |
| 黄金基线 | `uv run python scripts/verify_baseline.py --phase 6` | §7.1 11/11 · §7.2 2/2 · §7.3 7/7 | 逐项命中 | 通过 |
| 绑定判据 | `uv run python scripts/verify_bindings.py` | **42 项** | 判据行计数 **42**，`失败项合计 = 0 -> 通过` | 通过 |
| 配置判据 | `uv run python scripts/verify_config.py` | 6 | `判定项 6 项…不通过 0 项` | 通过 |
| 版本判据 | `uv run python scripts/verify_version.py` | 5，版本 1.0.0 | `判定项 5 项…不通过 0 项`，五项均 **1.0.0** | 通过 |
| 容器判据 | `uv run python scripts/verify_containers.py` | 19 | `19/19 项全部通过` | 通过 |
| 前端检查 | `cd frontend && npm run check` | tsc 0 / oxlint 0 / vitest 109 | tsc 0 错；`Found 0 warnings and 0 errors.`（32 files / 116 rules）；`Tests 109 passed (109)`（6 文件） | 通过 |
| 前端构建 | `cd frontend && npm run build` | — | `✓ built in 1.46s`，gzip 合计 0.30 + 4.10 + 81.98 = **86.38 KB** | 通过 |
| 契约第二段（CI 本地等价） | `npm run gen:types` 后 `git status --porcelain -- frontend/src/api/generated` | 空 | **空**（生成前后 `git status --porcelain` 均空） | 通过 |

### 4.2 过时数字扫描（主动找残留）

对 `README.md`、`CONTRIBUTING.md`、`docs/{ARCHITECTURE,DEVELOPMENT,MIGRATION,algorithm,contracts}.md`、
`docs/lessons/*.md`、`docs/archive/*.md` 逐条检索派单指定的 7 类过时值：

| 检索目标（应已不存在） | 命中 | 判定 |
|---|---|---|
| `45`（旧绑定判据计数，现应 42） | 5 处，**全部为 `文件:行号` 中的行号**（`algorithm.md:44-45`、`change_detection.py:45-49`、`test_raster_io.cpp:45`、`base.py:45-62`）；**无**「45 项 / 45 判据」残句 | 通过（合法语境） |
| `50 files`（ruff 旧计数，现应 51） | **0** | 通过 |
| `123 个用例`（须双口径并列） | 所有 `123` 命中均为「静态 `def test_` 计数 123 / 收集 148」的**双口径并列**（`ARCHITECTURE.md:389`、`DEVELOPMENT.md:218/220/257`）；余者为行号 | 通过 |
| `§9-B` / `§9-C` / `§9-D`（不存在的章节号） | **0** | 通过 |
| `--phase 2`（除解释 `--phase 1` 语义外） | **0** | 通过 |
| `0.6.0`（除历史语境） | 10 处，逐条均为**合法历史语境**：`CONTRIBUTING.md:56/67/119`（Phase 6 示例，且 `:56` 注释显式写「Phase 7 收口产出的 tag 是 v1.0.0」）、`contracts.md:319/332`（记契约第二段于 `v0.6.0` 落地）、`docs/lessons/*:5/:11`（「实测于 Phase 6 收口 tip `dc8ee2b`／`v0.6.0`」）、`docs/archive/*`（历史归档） | 通过（合法历史语境） |
| `待核实` 中已关闭却仍挂着的事项 | D 系列编号口径已**就地标记关闭**（`ARCHITECTURE.md:466`「故**不再**标 `待核实`」；`MIGRATION.md:365`「**已关闭**」）；`docs/lessons/` 落点已由 `docs/lessons/README.md` 承接，无需再挂 `待核实` | 通过 |

### 4.3 `文件:行号` 引用抽查（> 10 条，逐条到源码核对）

抽取自 `docs/ARCHITECTURE.md` 与 `docs/DEVELOPMENT.md` 的引用，逐条打开源文件核对：

| # | 引用 | 源码实测 | 命中 |
|---|---|---|---|
| 1 | `backend/src/rschange/__init__.py:5-22`（分层声明） | 命中 | ✔ |
| 2 | `api/deps.py:53-76` `build_context()` | `:53 def build_context(` … `:76 )` | ✔ |
| 3 | `api/deps.py:39-51` `RuntimeContext` | `:39 @dataclass(frozen=True, slots=True)` / `:40 class RuntimeContext` | ✔ |
| 4 | `api/app.py:46` `API_PREFIX` | `:46 API_PREFIX = "/api"` | ✔ |
| 5 | `api/app.py:117` / `:119` / `:134` | `:117 setattr(app.state, STATE_ATTR, resolved)`、`:119 install_exception_handlers(app)`、`:134 include_router(..., prefix=API_PREFIX, ...)` | ✔ |
| 6 | `api/routers/detection.py:100-124` `_artifact_path()` 两道判定 | `:100 def _artifact_path` … `:124 return None` | ✔ |
| 7 | `api/routers/detection.py:189-208` `DetectionResponse` | `:195 return DetectionResponse(` … `:208 )` | ✔ |
| 8 | `pipeline/change_detection.py:298-304` `detect_change()` | `:298 def detect_change(` … `:304 )` | ✔ |
| 9 | `pipeline/change_detection.py:328-345` 七步编排 | `:328 before, after = _read_pair(...)` … `:345 )` | ✔ |
| 10 | `pipeline/change_detection.py:45-49` / `:51-58`（运行期 import / `TYPE_CHECKING`） | `:45-49` 恰 5 行运行期 import；`:51 if TYPE_CHECKING:` … `:58` | ✔ |
| 11 | `detectors/__init__.py:27` `registry.register(CvaDetector())` | `:27 registry.register(CvaDetector())` | ✔ |
| 12 | `detectors/cva.py:41` `HISTOGRAM_BINS` / `:105` `CvaDetector` | `:41 HISTOGRAM_BINS: Final[int] = 256`、`:105 class CvaDetector` | ✔ |
| 13 | `detectors/registry.py:5-6` / `:29` `override` 参数 | `:5-6` 两步说明；`:29 def register(..., *, override: bool = False)` | ✔ |
| 14 | `spatial/loader.py:34` / `:59` / `:85` / `:112` | `:34 _DLL_HANDLES`、`:59 _register_dll_directory`、`:85 lru_cache`、`:112 load_extension` | ✔ |
| 15 | `tests/test_architecture.py:51/67/120/137/144/182/196/227` | 八处用例与 `:144 forbidden` 逐一命中 | ✔ |
| 16 | `engine/src/internal/gdal_registry.hpp` / `region.hpp:28`(D-9) / `labeling.hpp:24`(D-6) / `contour.cpp:2`(crack following) | `region.hpp:28` 述 D-9、`labeling.hpp:24` 述 D-6、`contour.cpp:2` 述 crack following | ✔ |
| 17 | `DEVELOPMENT.md` → `.python-version:1` | `3.14.6` | ✔ |
| 18 | `DEVELOPMENT.md` → `pyproject.toml:16` / 根 `pyproject.toml:52` | `requires-python = ">=3.14,<3.15"` / `python-preference = "only-system"` | ✔ |
| 19 | `DEVELOPMENT.md` → `engine/CMakePresets.json:3` / `ci.yml:152-157` / `ci.yml:279` | `cmakeMinimumRequired 3.24` / `msystem: MINGW64` / `node-version: "24"` | ✔ |
| 20 | `DEVELOPMENT.md` → `config.py:229-245` `settings_customise_sources()` | `:229 @classmethod` … `:245 return (...)` | ✔ |
| 21 | `ARCHITECTURE.md:10`/`:11` 文档行数 | `docs/algorithm.md` = **1362** 行、`docs/contracts.md` = **333** 行，与文中一致 | ✔ |
| 22 | `ARCHITECTURE.md:163` `verify_bindings.py` **42** 项 | 独立运行计数 = 42 | ✔ |

**抽查 22 条，全部命中。** 另核对 `.github/workflows/ci.yml` 步骤编号：以 `:118` 的无名 `actions/checkout@v4`
为 step 1 计，共 **24** 步；step 14 = C++ 单测（`:246`）、15 = Python 测试（`:251`）、16 = 类型检查（`:254`）、
17 = 代码检查与格式（`:257`）、18 = 契约漂移检测（`:262`）、19 = 仓库自检脚本（`:265`）、22 = 前端检查（`:287`）、
23 = 契约类型零漂移（`:295`）、24 = 前端构建（`:309`）——与文档声明**逐条一致**。

### 4.4 本阶段「唯一源码改动」独立验证

派单称本阶段唯一源码改动为 `fix(engine)` 移除 `win-base` 预设中未被使用的 `CMAKE_C_COMPILER`。独立核验：

| 核验点 | 实测 | 判定 |
|---|---|---|
| `engine/CMakeLists.txt` 的 `project()` 语言声明 | `engine/CMakeLists.txt:14-19` = `project(spatial VERSION 0.2.0 … **LANGUAGES CXX**)`——只声明 C++ | ✔ |
| `CMAKE_C_COMPILER` 在 `engine/` 下是否仍有读取方 | `grep -rn CMAKE_C_COMPILER engine/` 仅命中**构建缓存**（`build/dev-win/CMakeCache.txt`）与第三方 `_deps/json-src/cmake/ci.cmake`（json 自带，未参与本项目配置）；**无**项目侧读取方 | ✔ |
| `engine/CMakePresets.json` 是否仍含该键 | **无**（`win-base` 仅余 `CMAKE_BUILD_TYPE` / `CMAKE_CXX_COMPILER` / `SPATIAL_GDAL_ROOT` / `Python_EXECUTABLE`） | ✔ |
| 就地重配是否仍 rc=0 且无该告警 | `cmake --preset dev-win` → rc=**0**，输出无 `Manually-specified variables were not used … CMAKE_C_COMPILER` | ✔ |
| 该改动是否为唯一功能性源码改动 | `git diff v0.6.0 phase-7-docs` 中 `detectors/__init__.py`、`gdal_registry.hpp` 为**注释/docstring**；`bootstrap.*`、`gen-api-types.sh`、`verify_baseline.py`、`verify_version.py` 为**提示文本/注释**；`frontend/package.json` 为版本号。**唯一预设定制变量的删除**即 `engine/CMakePresets.json` 的 `CMAKE_C_COMPILER` | ✔ |

> **顺带发现（不阻断，但与之相关）**：`docs/DEVELOPMENT.md:135` 的 `win-base` 预设表格行**仍列出**
> `CMAKE_C_COMPILER=$env{SPATIAL_MINGW_ROOT}/bin/gcc.exe`，而该键已在 `3fa483b` 从预设删除。
> `DEVELOPMENT.md` 最后一次修改（`3218e8f`）早于该预设修复（`3fa483b`），故文档未随源码同步。
> 这属**文档与代码冲突**（按 `CONTRIBUTING.md` §4 以代码为准），登记为未关闭项 **N1**。
> 该项不计入 G7.2 的三条既定判据（基线数字 / 过时数字 / 引用核查），故**不影响 G7.2 判定**。

**判定：通过。** 全量门禁当场重跑与文档声明数字逐条一致；7 类过时数字无一残留（命中项均属合法历史语境或行号）；
22 条 `文件:行号` 引用全部命中；本阶段唯一源码改动经独立确认。**附 N1/N2 两条不阻断的文档缺陷（见 §8）。**

---

## 5. G7.3 —— 旧仓库归档 tag

**判据（派单 §4 G7.3）**：旧仓库存在附注 tag `archived-2026-09-18`；该提交树含五个目标文件；
旧仓库工作树未被破坏。

| 核验点 | 实测 | 判定 |
|---|---|---|
| 附注 tag 存在 | `git tag --list` = `archived-2026-09-18`；`git cat-file -t` = **`tag`**（附注标签） | ✔ |
| 标签对象 SHA / 指向提交 | 标签对象 `8fb8ec16ae1b12e57d239d96e10b167b0fb84618`；`archived-2026-09-18^{}` = `177e8e04b030984b61b70053e0624b1f5e79e9f6`（取提交必须用 `^{}`，不可用 `rev-parse` 的标签对象 SHA） | ✔ |
| tag 消息 | 「rschange 重构参考线 · 归档冻结」，明确「禁止作为变更来源 / 禁止 merge 进新仓库 / 不回写不删除」 | ✔ |
| 五个目标文件在 tag 树中 | `CODE_MAP.md`、`DOCKER_PLAN.md`、`GEO_CAPABILITIES.md`、`project2-lessons-and-interview.txt`、`Debug_lesson.txt` **各命中 1 处** | ✔ |
| 工作树未被破坏 | `git status --porcelain` = **仅** ` M .vscode/settings.json`（与预期一致，无其它改动/删除） | ✔ |

**判定：通过。** 旧仓库已归档冻结：附注 tag 就位、五份素材随 tag 完整保留、工作树除预期的
`.vscode/settings.json` 外未被触碰。

---

## 6. 门禁逐条结果表

| # | 判据 | 声明值 / 期望 | 当场实测 | 判定 |
|---|---|---|---|---|
| **G7.1** | 盲测通过 | README 6 步可照做、5 处前提已写入 | 独立复跑 cmake / ctest / baseline / pytest 全 rc=0；5 处前提逐条命中的 README 行号见 §3.3 | **通过** |
| **G7.2** | 基线数字终检 | 全量门禁与文档数字一致、无过时数字 | 14 项门禁逐条吻合（§4.1）；7 类过时数字扫描通过（§4.2）；22 条引用全命中（§4.3） | **通过**（附 N1/N2） |
| **G7.3** | 旧仓库归档 tag | 附注 tag + 五文件 + 工作树完好 | 标签对象 `8fb8ec16…`、提交 `177e8e04…`、五文件各 1、status 仅 1 处修改 | **通过** |
| A | 交付范围与分支纪律 | `git diff --name-status v0.6.0 phase-7-docs` 与声明一致 | 29 项（11 A / 16 M / 2 D）；L1 自 `v0.6.0^{}` 拉出 | 通过 |
| B | 受管文件数 | 基线 165 → 174 | `git ls-tree -r v0.6.0` = 165；`git ls-files` = 174 | 通过 |
| C | 契约第一段零漂移 | PASS | `[PASS] 契约产物与当前代码一致` | 通过 |
| D | 契约第二段零漂移 | 工作树空 | `gen:types` 后 `git status --porcelain -- frontend/src/api/generated` 空 | 通过 |
| E | C++ 单测 | 40 | 40/40，100% passed | 通过 |
| F | 后端 + 契约测试 | 148 | 148 passed（隔离 basetemp，rc=0） | 通过 |
| G | 静态用例计数 | 123（112 + 11） | backend 112 + 根 11 = 123 | 通过 |
| H | 类型检查 | 36 文件 0 错 | `no issues found in 36 source files` | 通过 |
| I | 代码检查 / 格式 | 通过 / **51 files** | `All checks passed!` / `51 files already formatted` | 通过 |
| J | 环境与配置自洽 | 6 项 / 42 项 / 19 项 | verify_config 6、verify_bindings 42、verify_containers 19 | 通过 |
| K | 版本单一真相源 | 5 项，1.0.0 | 5 项全 PASS，均为 1.0.0 | 通过 |
| L | 基线数字不变 | §7.1 11/11 · §7.2 2/2 · §7.3 7/7 | 逐项命中 | 通过 |
| M | 前端检查 | tsc 0 / oxlint 0 / vitest 109 | tsc 0、`0 warnings and 0 errors`、`109 passed` | 通过 |
| N | 前端构建 | 可构建 | `✓ built in 1.46s`，gzip 合计 86.38 KB | 通过 |
| O | 旧仓库归档 | tag 就位、工作树完好 | 见 §5 | 通过 |
| P | 工作树无未跟踪残留 | — | 报告写入前后 `git status --porcelain` 均空 | 通过 |

> **关于变异测试**：`CONTRIBUTING.md` §6 体例含「变异测试」一项。Phase 7 为文档固化阶段，
> 唯一源码改动是删除一个未被使用的预设变量；且本次验收的操作边界**禁止**修改仓库内被测文件。
> 故**未执行**变异测试。其对门禁判别力的替代证据为：①全量门禁当场独立重跑（§4.1）；
> ②22 条 `文件:行号` 引用逐条到源码核对（§4.3）；③过时数字主动扫描（§4.2）——均以「不引用执行者结论、
> 自己重跑/自己找反例」的方式取得。该处置如实登记，不声称已做变异。

---

## 7. 写操作披露

### 7.1 对被测仓库的写操作

| 动作 | 对象 | 性质 | 还原凭据 / 影响 |
|---|---|---|---|
| 运行 `cmake --preset dev-win` | `engine/build/dev-win/`（**gitignored**） | 就地重配，写入构建缓存 | 非受控文件；报告写入前后 `git status --porcelain` 均空 |
| 运行 `cmake --build --preset dev-win` | 同上 | 无改动（`ninja: no work to do.`） | 同上 |
| 运行 `npm run gen:types` | `frontend/src/api/generated/` | 重新生成，与入库版本逐字节一致 | `git status --porcelain` 空（零漂移） |
| 运行 `npm run build` | `frontend/dist/`（**gitignored**） | 生成生产产物 | 非受控文件 |
| 运行 `uv run pytest … --basetemp=<工作区外>` | `_work/p7/verify7-tmp/pytest/` | 临时目录写入 | 在仓库**外** |
| 运行五个 `verify_*.py` / `gen_openapi.py --check` | 仅写系统临时目录 | 只读仓库 | 无 |

**本报告的唯一仓库内写入 = 新增 `docs/verification/phase-7.md`。** 对被测源码未作任何修改，
亦未执行任何写入类 git 命令（全程仅 `log` / `show` / `diff` / `status` / `rev-parse` / `merge-base` /
`ls-tree` / `cat-file` / `tag --list` / `check-ignore` / `rev-list`，以及对旧仓库的只读命令）。
`git status --porcelain` 在验收开始时为空、结束（提交前）时为空。

### 7.2 对旧仓库的写操作

对 `C:/Users/Hujian/source/My_Project/Remote_Sensing_Change_Detection` **只读**（`git tag --list` /
`cat-file` / `rev-parse` / `ls-tree` / `show` / `status`），未作任何修改。归档 tag 与提交 SHA 原样。

---

## 8. 未关闭项（即使不阻断也逐条列出）

### 8.1 本阶段新增（本次独立验收发现）

| # | 项 | 说明 | 严重度 | 处置建议 |
|---|---|---|---|---|
| **N1** | `docs/DEVELOPMENT.md:135` 与 `engine/CMakePresets.json` 不一致 | 该行 `win-base` 预设表格仍写 `CMAKE_C_COMPILER=$env{SPATIAL_MINGW_ROOT}/bin/gcc.exe`，而该键已于 `3fa483b` 从预设删除。文档最后一次修改（`3218e8f`）早于该源码修复，未同步 | 中（文档与代码冲突，误导读者以为预设仍声明 C 编译器） | 合 `main` 前把该行 `CMAKE_C_COMPILER` 描述删除；本次受操作边界约束未代为修改 |
| **N2** | `docs/archive/README.md:18` 披露的绝对路径计数不符 | 文中称三份归档文档「共 21 处」（`refactor-plan.md` 14 / `execution-handbook.md` 4 / `migration-map.md` 3）；独立实测 `C:\Users\Hujian\…` 绝对路径为 **13 处**（10 / 2 / 1）。差异不影响归档内容（路径确实存在且有保留意图），仅披露数字偏大 | 低（元信息计数错误） | 更正为实测值 13（10/2/1），或改述为不给出具体数字 |
| **N3** | 目标路径 `C:/Users/Hujian/source/My_Project/Remote_sensing` 仍留有 7 个 Phase 1 遗留分支 | 实测分支 = `main` + `phase-1-bootstrap` + `task-1.1`…`task-1.4` + `verify-1-report`（7 个）；与「目标路径只投放 `main` + tag」的约定不符（tags 为 v0.1.0–v0.6.0） | 低（不影响产物，仅是投放路径整洁度） | 由主 agent 在收尾时处置；本次未触碰目标路径的任何引用 |

> **N1 与执行者结论的不一致（点名）**：执行阶段自核报告 `_work/p7/drafts/_verify-drafts.md` 记录了 8 条
> 不符项，但**未涵盖** N1——因为该自核发生在 `3218e8f` 时点，而删键修复 `3fa483b` 在其后，自核不可能看见。
> 本条系独立验收官在核验「唯一源码改动」时按图索骥发现。

### 8.2 执行阶段自核报告 8 条不符项的在库修复核对

对 `_work/p7/drafts/_verify-drafts.md` 的 8 条（高 1 / 中 6 / 低 1）逐条核对**落库文档**是否已修复：

| 原编号 | 原问题 | 落库文档实测 | 是否已修复 |
|---|---|---|---|
| 1-1（中） | `DEVELOPMENT.md:498-499` 关于 `local.example.toml` 需加 `[detector]` 注释态、否则 `verify_config` 可能失配的因果说法不成立 | `DEVELOPMENT.md:500-502` 已改为「`verify_config.py` 的模板判据**只覆盖** `build_dir` 与 `fixtures_dir` 两个键…新增 `[detector]` 段**不会**进入该判据——这一步靠人工」，并给出注释态示例 | **已修复** |
| 2-4（高） | `verify_bindings.py` 被 4 处写作 **45** 项（应为 42） | `ARCHITECTURE.md:163` = 42；`MIGRATION.md:62` = 42；`MIGRATION.md:339` = 42；`engine/src/internal/gdal_registry.hpp:28` 注释 = 42（`da128e0`）；全库无「45 项」 | **已修复** |
| 2-2（中） | `algorithm.md` 行数 1353（已漂移） | `ARCHITECTURE.md:10` = **1362**；实测 1362 | **已修复** |
| 2-3（中） | `contracts.md` 行数 331（已漂移） | `ARCHITECTURE.md:11` = **333**；实测 333 | **已修复** |
| 2-5（中） | `docs/archive/`「仅有 `.gitkeep`」表述已过时 | `MIGRATION.md` 全文已无该表述；`docs/archive/` 实含 4 个 `.md` | **已修复** |
| 2-6（中） | `ARCHITECTURE.md:137` 对 algorithm.md §0 归属表「待迁入」的更正声明自身过时 | `ARCHITECTURE.md:137` 已改述为「已在 `v1.0.0` 就地更正」；`algorithm.md:52-54` 实为「已实现（Phase 3 迁入）」 | **已修复** |
| 2-7（中） | 版本真相源「当前 0.6.0」（工作树瞬态） | `ARCHITECTURE.md:422` = `1.0.0`；`MIGRATION.md` 以 `v1.0.0` 表述；`backend/pyproject.toml:17` = 1.0.0 | **已修复** |
| 3-1（低） | 引 `phase-6.md` §9-B/C/D、`phase-5.md §11.1` 等非正式章节号 | 全库无 `§9-B` / `§9-C` / `§9-D`；改述为「§9 表 X 行」 | **已修复** |

**结论：8 条不符项在落库文档中全部修复**，无结转。

### 8.3 继承自 Phase 6 的未关闭项核对

| 原编号 | 项 | 本阶段核验 | 现状 |
|---|---|---|---|
| O1 | 容器未构建、端到端未实测 | 本阶段无 Docker 构建；`docs/verification/phase-6.md` §4/§5 与 `DEVELOPMENT.md:266` 均声明「不替代真实构建」 | **仍成立**（结转） |
| O2 | `Dockerfile.backend` 未设 `SPATIAL_PYTHON`，依赖命令行 `-D` 覆盖预设的顺序假设 | `docker/Dockerfile.backend:65` 仍以 `cmake --preset dev-linux -DPython_EXECUTABLE=/app/.venv/bin/python` 形式传参；「命令行 `-D` 与预设 `cacheVariables` 谁优先」仍未实测 | **仍成立**（结转） |
| O6 | 手册 `task/6.3` 的 `MSYS2_ARG_CONV_EXCL` 描述与实现不一致 | 手册已归档为 `docs/archive/execution-handbook.md`（历史记录，非规范）；本阶段文档已声明「禁止在 MSYS2 shell 内跑 CMake」（`DEVELOPMENT.md:89-90`） | **已随归档降级为历史**，不再是规范冲突 |
| O-note | 「运行环境须提供 UTF-8 stdio」未入开发者文档 | `DEVELOPMENT.md:10-24` 新增 §0「前提：运行环境必须提供 UTF-8 stdio」，含 `PYTHONUTF8=1`、`PYTHONIOENCODING` 优先级与子进程解码说明 | **本阶段关闭** |
| — | 阈值两处口径（`5.916767423962816` vs `5.9168`） | `contracts.md:297` 与 `ARCHITECTURE.md:446` 均并列给出两者并注明关系 | 已变更为**显式口径说明**（非静默不一致），保留 |
| — | `_OVERLAY_ALPHA` 是模块常量而非配置项 | `io/preview.py:56` 仍为 `_OVERLAY_ALPHA: Final[int] = 100` | **仍成立**（设计选择，无配置需求） |
| — | `image_corners` 仅文本表格无地图库 | `contracts.md:217` 仍为纯契约字段描述 | **仍成立** |
| — | jsdom 的 `user.upload()` 绕过 dropzone 过滤 | 本阶段未改前端测试 | **仍成立**（结转） |
| — | `mypy` 不覆盖 `scripts/` | `pyproject.toml:105` `files = ["backend/src"]` | **仍成立**（设计范围） |

---

## 9. 数字对照（Phase 6 → Phase 7）

| 维度 | Phase 6（`v0.6.0`） | Phase 7（`3fa483b`） | 变化 |
|---|---|---|---|
| 受管文件 | 165（`v0.6.0` 树） | 174 | +9 |
| 阶段提交数 | — | 10（`v0.6.0..phase-7-docs`） | 新增 |
| 工程文档 | 0 份（散在 `docs/verification/` 内） | `ARCHITECTURE.md` / `DEVELOPMENT.md` / `MIGRATION.md` / `CONTRIBUTING.md` | 新增 |
| 调试教训 | 0 | `docs/lessons/`（3 文件 660 行） | 新增 |
| 过程归档 | 0 | `docs/archive/`（4 文件） | 新增 |
| 版本 | 0.6.0 | **1.0.0** | +0.4.0 |
| C++ 单测 | 40 | 40 | 0 |
| 后端 + 契约测试 | 148 | 148 | 0 |
| 静态 `def test_` | 123 | 123 | 0 |
| 前端 vitest | 109 | 109 | 0 |
| `mypy` 文件 | 36 | 36 | 0 |
| `ruff format` 覆盖 | 50 files | **51 files**（+ 根 `CONTRIBUTING.md`） | +1 |
| `verify_bindings` 判据 | 42 | 42 | 0 |
| 契约门禁段数 | 2 | 2 | 0 |
| 黄金基线 | §7.1 11/11 · §7.2 2/2 · §7.3 7/7 | 同 | 0（冻结） |
| 前端 gzip 合计 | 86.38 KB | 86.38 KB | 0 |
| 源码功能改动 | 5 处平台缺陷（Phase 6） | **0**（仅注释/预设清理） | — |

---

## 10. 总判定

**通过。**

Phase 7（文档固化与终验）在「README 盲测 6 步可照做且 5 处隐含前提已写入、全量门禁当场重跑与
文档声明数字逐条一致、7 类过时数字无一残留、22 条 `文件:行号` 引用全部命中、旧仓库归档 tag 就位且
工作树完好、本阶段唯一源码改动经独立确认、执行阶段 8 条自核不符项全部在库修复」上达成出口门要求。
**未关闭项 N1（`DEVELOPMENT.md:135` 预设键过时）/ N2（归档路径计数 21 vs 实测 13）为不阻断的文档缺陷，
建议在 L1 合入 `main` 前一并修正。**

三条出口门判定：

| 门 | 判据 | 判定 |
|---|---|---|
| **G7.1** | 盲测通过（无口口相传的隐含前提） | **通过**（独立复跑 cmake / ctest 40/40 / baseline 11-2-7 / pytest 148 全 rc=0；5 处前提逐条命中） |
| **G7.2** | 基线数字终检 | **通过**（14 项门禁逐条吻合；过时数字扫描通过；22 条引用全命中）；附 N1 / N2 两条不阻断的文档缺陷 |
| **G7.3** | 旧仓库归档 tag | **通过**（附注 tag `archived-2026-09-18`、提交 `177e8e04…`、五份素材齐全、工作树仅 1 处预期修改） |

仓库 174 个受管文件；本次验收未修改任何被测源码，唯一仓库内写入为本报告。
未关闭项 N1–N3 与继承项 O1 / O2 等逐条列出，均不阻断本阶段出口。

---

*本报告在**独立于执行者**的前提下出具：所有判据由验收官当场重跑或逐条打开源码核验，未照抄执行者结论；
对执行者结论有两处补充/相左，已在 §4.4 与 §8.1 点名（N1、N2）。*
