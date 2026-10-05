# 遥感变化检测平台 · 执行手册（阶段 / 角色 / 分支 / 合并）

> 配套文档：《Remote_Sensing_重构方案.md》（为什么做）、《Remote_Sensing_迁移映射与阶段拆解.md》（搬什么）。
> 本文档定位：**怎么做、谁做、在哪条分支做、怎么合**。执行期只允许按本文档的分支与合并协议走。
> 版本 v1.0 · 制定于 Phase 0
> 环境基线（2026-09-18 实测）：`uv 0.12.5`（`C:\Users\Hujian\CIL\uv\uv.exe`，已在 PATH）· `git 2.54.0.windows.1` · 目标目录 `Remote_sensing` 为空 · 旧仓库 `HEAD=a096efc`，2 个提交，5 项未提交变更

---

## 0. 总览矩阵：阶段 × 角色 × 分支

> ⚠️ **分支名一律使用连字符，禁止使用斜杠**。原因见 §8「本机环境约束」——本机 git 无法写入嵌套引用名，斜杠分支会静默失败。

| 阶段 | 名称 | 执行角色 | 集成分支 | 基于 | 任务分支数 | 产出 tag |
|---|---|---|---|---|---|---|
| 0 | 基线冻结 | 🔍 `archaeologist` | —（无代码） | — | 0 | — |
| 1 | 环境与仓库奠基 | 🏗 `scaffolder` | `phase-1-bootstrap` | `main`（首次提交） | 4 | `v0.1.0` |
| 2 | C++ 引擎解耦 | ⚙️ `cpp-core` | `phase-2-engine` | `v0.1.0` | 8 | `v0.2.0` |
| 3 | 后端分层解耦 | 🐍 `backend` | `phase-3-backend` | `v0.2.0` | 6 | `v0.3.0` |
| 4 | 前端工程化 | 🎨 `frontend` | `phase-4-frontend` | `v0.3.0` | 4 | `v0.4.0` |
| 5 | 契约同步 | 📋 `contract` | `phase-5-contract` | `v0.4.0` | 3 | `v0.5.0` |
| 6 | 容器化与 CI | 🚀 `devops` | `phase-6-cicd` | `v0.5.0` | 3 | `v0.6.0` |
| 7 | 文档固化与终验 | ✍️ `writer` + 🕵️ `verifier` | `phase-7-docs` | `v0.6.0` | 5 | `v1.0.0` |
| 每阶段 | 对抗式核查 | 🕵️ `verifier` | `verify-N-report` | 对应 `phase-N` tip | 1 | （不单独打 tag） |

**分支总计**：L1 集成分支 7 条 · L2 任务分支 33 条 · 证据分支 7 条。任务分支与证据分支在合入后即删除，tag 保留全部节点。

---

## 1. 分支模型（两级 + 一条证据线）

### 1.1 三条分支线

| 线 | 命名 | 从哪拉 | 合到哪 | 生命周期 | 目的 |
|---|---|---|---|---|---|
| **L1 集成线** | `phase-N-<slug>` | **上一阶段的 tag**（不是 `main`） | `main`（`--no-ff`） | 阶段结束即合、即删 | 一个阶段一个可验收单元 |
| **L2 任务线** | `task-N.K-<slug>` | 本阶段 L1 分支 | 本阶段 L1 分支（`--no-ff`） | 任务验收即合、即删 | 隔离单点改动，失败可单独 revert |
| **证据线** | `verify-N-report` | 本阶段 L1 分支 tip | `main`（紧随 L1 之后） | 合入后保留至终验 | 验收报告独立于执行者产出 |

**命名分隔符必须用连字符 `-`，禁止用斜杠 `/`。** 本机 git 无法写入嵌套引用名（见 §8），`git switch -c phase/1-bootstrap` 会返回 0、更新 HEAD，但**不创建引用文件**，后续提交全部落在未出生 HEAD 上并被丢弃。这是静默数据丢失，必须在命名层面规避。

### 1.2 为什么 L1 必须从 tag 拉，而不是从 main

若从 `main` 拉，`main` 上任何别的合入都会混进本阶段基线，`git diff` 失去意义。从 tag 拉则保证：

```
git diff v0.1.0 v0.2.0     # 精确等于「Phase 2 做了哪些改动」，零噪声
git switch -c hotfix v0.1.0  # 出问题可精确回退到某一阶段基线
```

### 1.3 为什么 tag 打在证据合入之后

tag 指向的提交因此**同时包含代码与验收证据**。任何人 `git checkout v0.2.0` 都能读到「这一阶段的验收结论是什么」，而不是只有代码、结论散落在对话里。

证据分支的合入路径为：`verify-N-report` → `phase-N-<slug>` → `main`。先并入集成分支再入 `main`，使集成分支自身成为「代码 + 证据」的完整单元。

### 1.4 为什么任务分支要合回 L1 而不是直接合 main

L2 是**阶段的内部实现细节**。阶段未通过验收前，`main` 必须保持上一个稳定状态。L2 直接进 `main` 会让 `main` 在阶段中途就退化。

---

## 2. 提交与合并协议

### 2.1 提交信息

```
<type>(<scope>): <subject>

type  : feat | fix | refactor | test | build | ci | docs | chore
scope : phase 号 + 模块，如 2/contour、3/plugin、1/uv
```

**约定**：每个 L2 任务分支内的提交，必须带本阶段号前缀（如 `refactor(2/contour): 拆分 extract_boundary`）。这样 `git log v0.1.0..v0.2.0 --oneline` 天然按任务分组可读。

### 2.2 合并命令（每个任务分支固定四步）

```bash
# ① 开任务分支（从本阶段集成分支）
git switch -c task-2.3-labeling phase-2-engine

# ② 做活 + 自检（自检命令见 §3 各阶段表）
# ③ 合回集成分支（--no-ff 保留任务节点，便于单独 revert）
git switch phase-2-engine
git merge --no-ff task-2.3-labeling -m "merge(2.3): labeling 拆分与 D-6 修复"

# ④ 删任务分支
git branch -d task-2.3-labeling
```

**分支创建后必须立即验证引用已落盘**（本机曾出现静默失败）：

```bash
git rev-parse --verify refs/heads/task-2.3-labeling   # 必须返回 40 位 sha，非零退出即失败
```

### 2.3 阶段合并（每个阶段固定五步）

> **顺序修正（2026-09-18）**：验收必须在合入 `main` **之前**完成。原方案把「合入 main」放在第 ① 步，等于未验收就先污染稳定线，与 §9.2「不通过不得推进」自相矛盾。

```bash
# ① 验收官在集成分支 tip 上产出证据（此时尚未合入 main）
git switch -c verify-2-report phase-2-engine
#    … 验收官独立复现，写 docs/verification/phase-2.md …
git add docs/verification/phase-2.md && git commit -m "docs(verify): Phase 2 验收报告"
git switch phase-2-engine
git merge --no-ff verify-2-report -m "merge(verify): Phase 2 证据并入集成分支"

# ② 判定通过后，才合入 main
git switch main
git merge --no-ff phase-2-engine -m "merge: Phase 2 · C++ 引擎解耦"

# ③ 打 tag（打在含代码与证据的 main 上）
git tag -a v0.2.0 -m "Phase 2: C++ 引擎解耦（验收通过）"

# ④ 清理
git branch -d phase-2-engine verify-2-report

# ⑤ 推送
git push origin main --follow-tags
```

> 判定 `不通过` 时：**第 ② 步不执行**。集成分支保留待修，`main` 不受影响、零损失。

### 2.4 回退策略（明码标价）

| 场景 | 命令 | 代价 |
|---|---|---|
| 阶段中途放弃 | `git switch main`（什么都不合） | 零损失，`main` 不受影响；任务分支保留可续做 |
| 阶段已合但发现回归 | `git revert -m 1 <merge-commit>` | 保留历史，可审计 |
| 阶段已合且 tag 错误 | `git reset --hard v0.1.0` + `git push --force-with-lease` | **仅在未推送或私有仓库可接受**；已推送时改用 `revert` |
| 单个任务改动有问题 | `git revert` 该任务 merge 节点 | L2 分支模型存在的意义 |

---

## 3. 逐阶段细化

### Phase 1 · 环境与仓库奠基 · 🏗 `scaffolder`

- **集成分支**：`phase/1-bootstrap`（`main` 首次提交之上）
- **前置**：无。`uv` 与 `git` 已就位。

**第 0 提交（直接在集成分支上做，不开任务分支）**
目录骨架 + `.gitkeep` —— 因为所有任务分支都需要这些目录存在，它必须先落地。

| 任务分支 | 交付内容 | 依赖 | 自检命令（必须附真实输出） |
|---|---|---|---|
| `task/1.1-repo-hygiene` | `.gitignore`（删 `api_tests/`、`CAREER_PLAN.md` 两条）· `.gitattributes` · `.editorconfig` · `.python-version`（内容精确 `3.14.6`）· `.dockerignore` | 第 0 提交 | `git status --porcelain` 结果为空；`git check-ignore -q .venv` 退出码 0 |
| `task/1.2-uv-env` | `backend/pyproject.toml`（`requires-python = ">=3.14,<3.15"` + `[tool.uv] python-preference = "only-system"`）· `uv.lock` · `scripts/bootstrap.ps1` · `scripts/bootstrap.sh` | 第 0 提交 | 删 `.venv` 后跑 `scripts/bootstrap.ps1`；`.venv\Scripts\python.exe -c "import fastapi,numpy,scipy,pyproj,PIL,nanobind"` 无报错 |
| `task/1.3-config` | `config/default.toml` · `config/local.example.toml`（含 Windows/Linux 两种 `runtime_dll_dir` 示例） | 第 0 提交 | `git check-ignore -q config/local.toml` 退出码 0 |
| `task/1.4-baseline-tool` | `scripts/verify_baseline.py`（规格见《迁移映射》附录 B10）· `scripts/clean.ps1` / `.sh` | 第 0 提交 | `uv run python scripts/verify_baseline.py --phase 1`；**期望 §7.1 全 PASS、§7.2 与 §7.3 全 FAIL** |

**并行窗口**：1.1 / 1.2 / 1.3 / 1.4 四者文件集不相交（1.2 与 1.4 同处 `scripts/` 但文件不重叠），**可四条并行**。

**执行记录（2026-09-18，实际交付与上表的偏差）**

| 偏差 | 内容 | 理由 |
|---|---|---|
| `task-1.2` 额外纳入 | 根 `pyproject.toml`（workspace 根，`package = false`）· `README.md` · `backend/src/rschange/__init__.py` | uv workspace 必须有根清单声明 `members`；hatchling 需要包目录存在才能构建成员包；README 承载环境约定 |
| `task-1.3` 实际交付 | `config/default.toml` · `config/local.example.toml`（`config/local.toml` 由 bootstrap 生成，不入库） | 与上表一致 |
| 分支命名 | 全部扁平化（`task-1.1-repo-hygiene` 等） | 见 §8.1 嵌套引用名缺陷 |
| 建库位置 | 在工作区内 `_build/Remote_sensing` 建库，校验通过后整体投放 | 见 §8.2 |

**阶段出口门**

| # | 判据 | 判定 |
|---|---|---|
| G1.1 | 删除 `.venv` 后 `scripts/bootstrap.ps1` 一次跑通 | 通过 / 不通过 |
| G1.2 | `grep -rn "msys64" backend/` 结果为空 | 通过 / 不通过 |
| G1.3 | `git status` 干净，`.venv` / `config/local.toml` / `build/` 均未入库 | 通过 / 不通过 |
| G1.4 | `verify_baseline.py --phase 1` 输出 §7.1 **全部 `PASS`**、§7.2 与 §7.3 **全部 `FAIL`** | 通过 / 不通过 |
| G1.5 | `.venv\Scripts\python.exe --version` = `3.14.6` | 通过 / 不通过 |

**产出 tag**：`v0.1.0`

---

### Phase 2 · C++ 引擎解耦 · ⚙️ `cpp-core`

- **集成分支**：`phase/2-engine`（基于 `v0.1.0`）
- **本阶段有严格依赖链**，不可乱序。

| 任务分支 | 交付内容 | 依赖 | 自检命令 |
|---|---|---|---|
| `task/2.1-headers` | `engine/include/spatial/` 六头（`raster/region/labeling/contour/simplify/geojson`）+ `export.hpp`（`SPATIAL_API` 唯一定义点） | — | `cmake --build` 通过；`nm -D` 导出符号与旧版逐个比对 |
| `task/2.2-raster-io` | `raster_io.cpp` + `version.cpp` + `gdal_init.cpp`（**D-4** `GDALAllRegister()` 一次性化） | 2.1 | 旧 fixture 读写往返一致 |
| `task/2.3-labeling` | `labeling.cpp`（`UnionFind` + `extract_regions` + **D-6** 改 `std::map` 定序） | 2.1 | 多区域用例 `label` 排序确定 |
| `task/2.4-contour` | `contour.cpp`（`extract_boundary` + **D-2 Moore 邻域追踪修复**） | 2.3 | 单连通域断言 `ring 数 == 1` |
| `task/2.5-simplify` | `simplify.cpp`（`point_line_dist` / `dp_recurse` / `simplify_boundary` + **D-8** 闭环 DP 变体） | 2.4 | 断言输出环仍闭合、不自交 |
| `task/2.6-geojson` | `geojson.cpp`（**D-3** 属性归属修正 + **D-7** 空环语义） | 2.4 · 2.5 | `sum(area_m2) == 像素数 × 100` |
| `task/2.7-bindings` | `bindings/module.cpp`（**D-1** 2D shape 解析修正） | 2.2 | 非方形用例 `(100,200)` / `(200,100)` / `(64,512)` 写读一致 |
| `task/2.8-build-system` | `CMakePresets.json` · CTest 接入 · `FetchContent(nlohmann/json)` · `-Werror` · install 规则 | 2.1–2.7 全部 | `ctest --preset dev-win` 全绿 |

**并行窗口**：2.2 与 2.3 不同文件 → 可并行。2.7 与 2.4/2.5/2.6 无交集 → 可并行。**2.8 必须最后独占执行**（它要登记全部源文件，任何并发都会冲突）。

**`D-2` 的说明**：你提到的「moore 追踪算法没写对」，与本次侦查的 §1 **A4 是同一处缺陷**——`stats.cpp` 的 `trace_ring` 用的是 Moore 邻域边界追踪，返回时未把关**起点**写入 `visited`，导致主循环从另一个未访问边界像素重启，同一连通域产出多个环。修复归属 `task/2.4-contour`。

**阶段出口门**

| # | 判据 | 判定 |
|---|---|---|
| G2.1 | `ctest --preset dev-win` 全绿 | 通过 / 不通过 |
| G2.2 | `_spatial` 在新路径下可 `import`，`nm -D` 符号齐全 | 通过 / 不通过 |
| G2.3 | §7.1 全部不变（阈值 `5.9168`、像素 `7209/65536`） | 通过 / 不通过 |
| G2.4 | **§7.2 全部由 FAIL 转 PASS**（Feature `2 → 1`、面积 `1441800 → 720900`） | 通过 / 不通过 |
| G2.5 | §7.3 语义断言全部成立 | 通过 / 不通过 |

> G2.4 未达成即判定**修复未完成**，不允许进入 Phase 3。

**产出 tag**：`v0.2.0` · **同时冻结跨阶段接口写入 `docs/contracts.md`**（`_spatial` 的 Python 签名）

---

### Phase 3 · 后端分层解耦 · 🐍 `backend`

- **集成分支**：`phase/3-backend`（基于 `v0.2.0`）

| 任务分支 | 交付内容 | 依赖 |
|---|---|---|
| `task/3.1-src-layout` | `backend/src/rschange/` 包骨架 · `pyproject.toml` 补 `[project]` 与工具配置 · `uv.lock` 重锁 | — |
| `task/3.2-config-loader` | `config.py`（`pydantic-settings` 三件套）· `spatial/loader.py`（**D-5：全项目唯一 DLL 路径解析点**） | 3.1 |
| `task/3.3-plugin-arch` | `detectors/{base,cva,registry}.py` · `postprocess/{base,morphology}.py`（可插拔） | 3.2 |
| `task/3.4-pipeline-split` | `pipeline/change_detection.py`（7 步解耦）· `io/preview.py` · `io/reproject.py` | 3.2 · 3.3 |
| `task/3.5-api-layer` | `api/app.py`（`create_app()` 工厂）· routers · schemas · **D1 CORS 修复** · **D7 异常不外泄** · **D2 去 `print`** · 结构化日志 | 3.2 |
| `task/3.6-test-suite` | `tests/conftest.py` · 单元 + 集成 + **基线锚点断言**（≥15 用例） | 3.4 · 3.5 |

**并行窗口**：3.3 与 3.5 无文件交集 → 可并行。3.4 依赖 3.3；3.6 收口。

**阶段出口门**

| # | 判据 | 判定 |
|---|---|---|
| G3.1 | `uv run pytest` 全绿（≥15 用例） | 通过 / 不通过 |
| G3.2 | `uv run ruff check` + `uv run mypy` 零错误 | 通过 / 不通过 |
| G3.3 | §7 三档全部通过 | 通过 / 不通过 |
| G3.4 | **可插拔验证**：新增一个检测算法无需改 `pipeline/change_detection.py` | 通过 / 不通过 |
| G3.5 | `grep -rn "msys64" backend/` 为空 | 通过 / 不通过 |

**产出 tag**：`v0.3.0` · **冻结 HTTP 响应 schema 写入 `docs/contracts.md`**

---

### Phase 4 · 前端工程化 · 🎨 `frontend`

- **集成分支**：`phase/4-frontend`（基于 `v0.3.0`）

| 任务分支 | 交付内容 | 依赖 | 备注 |
|---|---|---|---|
| `task/4.1-ts-strict` | `tsconfig` 开启 `strict` + `noUncheckedIndexedAccess`，修全部类型报错 | — | **必须同时一次性写全 `package.json` 的依赖项**，见 §4 冲突热点 |
| `task/4.2-restructure` | `features/detection/{components,hooks}` · `components/ui/` · `styles/index.css` 主题变量 | 4.1 | |
| `task/4.3-state-layer` | TanStack Query 接入 | 4.2 | **可降级**：保留轻封装即跳过本任务分支 |
| `task/4.4-test-a11y` | Vitest + Testing Library · 错误边界 · Loading 骨架 · `npm run check` | 4.2 | |

**阶段出口门**

| # | 判据 | 判定 |
|---|---|---|
| G4.1 | `npm run check`（tsc + oxlint + vitest）全绿 | 通过 / 不通过 |
| G4.2 | `npm run build` 产物 < 300 KB gzip | 通过 / 不通过 |
| G4.3 | 手工上传 before/after，三图对比正确 | 通过 / 不通过 |

**产出 tag**：`v0.4.0`

---

### Phase 5 · 契约同步 · 📋 `contract`

- **集成分支**：`phase/5-contract`（基于 `v0.4.0`）

| 任务分支 | 交付内容 | 依赖 |
|---|---|---|
| `task/5.1-freeze-openapi` | `docs/api/openapi.json` 冻结入库 | — |
| `task/5.2-gen-types` | `scripts/gen-api-types.ps1` / `.sh` · `frontend/src/api/generated/` · 删除手写类型 | 5.1 |
| `task/5.3-contract-test` | `tests/contract/` · e2e（起 app → 上传真 tif → 断言基线） | 5.1 · 5.2 |

**阶段出口门**

| # | 判据 | 判定 |
|---|---|---|
| G5.1 | 契约测试通过 | 通过 / 不通过 |
| G5.2 | **反向验证**：故意改一个后端响应字段但不重生成类型，CI 必须变红 | 通过 / 不通过 |

> G5.2 是这道闸门唯一的存在性证明。不红即说明契约未真正生效，判不通过。

**产出 tag**：`v0.5.0`

---

### Phase 6 · 容器化与 CI · 🚀 `devops`

- **集成分支**：`phase/6-cicd`（基于 `v0.5.0`）

| 任务分支 | 交付内容 | 依赖 |
|---|---|---|
| `task/6.1-docker` | `docker/Dockerfile.backend` · `docker/Dockerfile.frontend` · `docker/nginx.conf`（**补 `client_max_body_size 500m;`，D-A5**）· `docker-compose.yml` | — |
| `task/6.2-ci-matrix` | `.github/workflows/ci.yml`（`windows-latest` MinGW + `ubuntu-latest` 双平台矩阵） | — |
| `task/6.3-cache` | uv / npm / ccache 缓存 · `MSYS2_ARG_CONV_EXCL="*"` 写进脚本注释防复发 | 6.2 |

**阶段出口门**

| # | 判据 | 判定 |
|---|---|---|
| G6.1 | push 后 Actions 双平台全绿 | 通过 / 不通过 |
| G6.2 | `docker-compose up` 后 `POST /api/detect` 返回基线数字 | 通过 / 不通过 |
| G6.3 | 上传 >1 MB GeoTIFF 不再返回 413 | 通过 / 不通过 |

**产出 tag**：`v0.6.0`

---

### Phase 7 · 文档固化与终验 · ✍️ `writer` + 🕵️ `verifier`

- **集成分支**：`phase/7-docs`（基于 `v0.6.0`）

| 任务分支 | 交付内容 | 责任角色 |
|---|---|---|
| `task/7.1-quickstart` | `README.md`（5 分钟跑通） | `writer` |
| `task/7.2-arch-migration` | `docs/ARCHITECTURE.md`（从 `CODE_MAP.md` 升级）· `docs/MIGRATION.md`（逐条对照） | `writer` |
| `task/7.3-dev-guide` | `docs/DEVELOPMENT.md`（新增算法完整示例）· `CONTRIBUTING.md` | `writer` |
| `task/7.4-lessons` | `docs/lessons/` 归档 · 面试稿更新（面积口径按附录 D 修正） | `writer` |
| `task/7.5-blind-run` | **盲测**：新会话 agent 仅凭 README 从零跑通，记录全部卡点 | 🕵️ `verifier` |

**阶段出口门**

| # | 判据 | 判定 |
|---|---|---|
| G7.1 | 盲测通过（无口口相传的隐含前提） | 通过 / 不通过 |
| G7.2 | 基线数字终检 | 通过 / 不通过 |
| G7.3 | 旧仓库打 `archived-2026-09-18` annotated tag | 通过 / 不通过 |

**产出 tag**：`v1.0.0`

---

## 4. 冲突热点与对策

任务分支的价值取决于「文件集是否真的不相交」。以下三处**必然冲突**，必须预先处理：

| 热点文件 | 冲突任务 | 对策 |
|---|---|---|
| `frontend/package.json` | `4.3`（加 TanStack Query）· `4.4`（加 Vitest） | **在 `task/4.1-ts-strict` 一次性写全所有新增依赖**，4.3/4.4 只改源码不改 `package.json` |
| `frontend/src/App.tsx` | `4.2`（重组）· `4.3`（接 Provider） | 4.3 依赖 4.2，**串行**，已在内置依赖中体现 |
| `engine/CMakeLists.txt` | `2.1`–`2.7` 每个任务都要登记新源文件 | **`task/2.1` 一次性写入全部目标文件条目**（此时文件尚不存在，但 CMake 允许先登记后补文件）；2.8 收口 |

**通用规则**：任何任务分支若预计触碰上表文件或 `*.lock`，**不得与其他任务并行**。

---

## 5. 精简模式（明码标价）

33 条 L2 任务分支对单人 + AI 协作属于偏重。若分支管理成本开始超过收益，可降级：

| 模式 | 分支数 | 保留什么 | 失去什么 |
|---|---|---|---|
| **完整模式**（本文档默认） | L1×7 + L2×33 + verify×7 | 每个任务可单独 revert；`git log --graph` 完整叙事 | 分支操作次数多 |
| **精简模式** | L1×7 + verify×7 | 阶段级隔离与回退；验收证据链完整 | 单任务粒度回退能力 |
| **最简模式** | L1×7 | 只有阶段隔离 | 证据分支独立性与单任务回退 |

**判定准则**：若某阶段内任务数 ≤ 3 且无并行需求（如 Phase 5、Phase 6），**直接用精简模式**。完整模式只对 Phase 2、Phase 3 这两个高复杂度阶段强制。

---

## 6. 旧仓库桥接的正确姿势（含一处已实测的坑）

```bash
git remote add legacy ../Remote_Sensing_Change_Detection
git fetch legacy
```

**坑（2026-09-18 实测）**：旧仓库 `HEAD=a096efc`，仅 2 个提交，且下列文件**未被 git 跟踪**（`git status --porcelain` 显示为 `??`）：

```
?? CODE_MAP.md
?? DOCKER_PLAN.md
?? GEO_CAPABILITIES.md
?? project2-lessons-and-interview.txt
```

因此 `git show legacy/main:CODE_MAP.md` 会报 `path does not exist`。**这 4 个文件必须从工作区直接读取**，不能走 legacy 历史。`CODE_MAP.md` 恰是《迁移映射》A.1 点名要升级为 `docs/ARCHITECTURE.md` 的核心资产——若误以为它在历史里而清了工作区，会直接丢失。

**规则**：桥接前先执行 `git status --porcelain` 并记录未跟踪清单；迁移期间**禁止对旧仓库做任何写操作**（包括 `git add` / `git stash` / `git checkout`）。

---

## 7. 每阶段必须交付的执行报告（缺项即视为未完成）

| # | 项 | 说明 |
|---|---|---|
| 1 | 阶段编号与进度定位 | 形如 `Phase 2 / 8` |
| 2 | 分支清单 | 本阶段开了哪些 L1/L2/verify 分支，各自合并节点 hash。**必须附 `git for-each-ref` 真实输出** |
| 3 | 文件级改动清单 | `git diff <上游 tag>..<本阶段 tag> --stat` 的真实输出 |
| 4 | 验证命令与**真实输出** | 不接受描述性结论 |
| 5 | 验收门判定 | 逐项 `通过` / `不通过`；出现「不通过」不得推进 |
| 6 | 下一阶段输入清单 | 上游冻结的接口/契约与必读文件 |

---

## 8. 本机环境约束（2026-09-18 实测，执行期必须遵守）

### 8.1 git 无法写入嵌套引用名（阻断级，已实测）

| 操作 | 结果 |
|---|---|
| `git update-ref refs/heads/flatbranch <sha>` | ✅ 引用文件写入成功 |
| `git update-ref refs/heads/nested/branch <sha>` | ❌ 退出码 0，但 `.git/refs/heads/nested/branch` 不存在 |
| PowerShell 在 `.git/refs/heads/` 下 `New-Item -ItemType Directory` | ✅ 成功（**排除权限问题**） |
| 预建 `.git/refs/heads/phase/` 后 `git update-ref refs/heads/phase/x` | ❌ 仍失败 |
| `git symbolic-ref` / `git rev-parse` / `git commit` / `git log` | ✅ 全部正常 |

**故障表现**：`git switch -c phase/1-bootstrap` 打印 `Switched to a new branch`、退出码 0，`.git/HEAD` 被改写为新分支名，但**引用文件从未创建**。此后该分支处于「未出生」状态，所有提交只生成对象、不推进引用——**提交被静默丢弃**。`git branch -vv` 只显示 `main`，`git branch <name>` 报 `fatal: not a valid object name`。

**规避规则（强制）**：
1. 分支名一律扁平化，用连字符：`phase-1-bootstrap`、`task-1.2-uv-env`、`verify-1-report`。
2. 每次创建分支后立即断言 `git rev-parse --verify refs/heads/<name>`（必须返回完整 sha，非零退出即失败）。
3. 任何阶段交付报告中的「分支清单」，必须附 `git for-each-ref refs/heads` 的真实输出。
4. tag 不受影响（`refs/tags/v0.1.0` 为扁平名）。

### 8.2 目标路径上建库不稳定 → 必须「离位构建、整体投放」（阻断级，已实测）

**故障表现**（同一处连续复现两次，均在 Phase 1 的 `task-1.2` 合并处）：

```
$ git merge --no-ff -m "merge: task-1.2 uv 环境" task-1.2-uv-env
fatal: <sha> is not a valid object
fatal: stash failed
```

此后仓库被破坏：`.git` 消失，且 `git switch` 从任务分支移出的文件不会恢复。
检查磁盘发现 `backend/`、`scripts/`、`pyproject.toml`、`uv.lock`、`README.md` 一并缺失。

**触发条件（确定性）**：工作区存在**未暂存的删除**时执行 `git switch` + `git merge`。
实测中该删除由 `uv sync --all-packages` 引起——`backend/src/rschange/*` 下的
`.gitkeep` 会在同步过程中消失，形成 ` D` 状态。

**规避规则（强制）**：

1. **离位构建**：git 历史与门禁校验一律在工作区内的构建目录（`_build/Remote_sensing`）完成，
   校验通过后再整体复制到目标路径。目标路径上**只做纯文件复制，不执行任何 merge**。
   构建产物可随时重放，失败不再丢进度。
2. **归一到 HEAD**：任何 `git switch` / `git merge` 之前必须执行 `git reset --quiet` +
   `git checkout -- .`，并断言 `git status --porcelain` 中**不存在非 `??` 开头的行**。
   这一步是消除 stash 路径的关键。
3. **顺序**：先归一化，再 `switch`，再归一化，最后 `merge`。
4. **快照**：每次 merge 前复制 `.git` 到备份目录；若 merge 后 `.git` 消失，从快照恢复。
5. **投放后必须现场复检**：在目标路径上重跑 G1.1–G1.5，不以构建目录的结果代替。

### 8.3 git 配置必须逐仓库关闭三项（阻断级，已实测）

本机 `C:\Users\Hujian\CIL\git\etc\gitconfig` 与 `~/.gitconfig` 中的以下配置会导致对象写入异常：

| 配置 | 本机值 | 后果 | 处理 |
|---|---|---|---|
| `core.fscache` | `true` | 目录 mtime 缓存失效 → 新写入的对象不可见 → `fatal: <sha> is not a valid object` | 仓库级置 `false` |
| `core.autocrlf` | `true` | 行尾双向转换与 `.gitattributes` 冲突，产生无谓的工作区改动 | 仓库级置 `false`，行尾统一交 `.gitattributes` |
| `merge.autostash` | 未设置 | 一旦走 stash 路径，脏工作区会直接摧毁仓库 | 仓库级显式置 `false` |

**执行方式**：`git -c core.fscache=false -c core.autocrlf=false -c merge.autostash=false <cmd>`，
并在 `git init` 后写入仓库级配置。每次 `commit` / `merge` 之后必须跑 `git fsck --no-progress --no-dangling`，
非零退出或输出含 `error` / `missing` 即中止。

### 8.4 其他实测约束

| 约束 | 说明 |
|---|---|
| bash 缺 `grep` / `dirname` / `ls` / `tail` | 沙箱内 PortableGit 的 bash 只有内建命令，**外部命令一律不可用**；检索改用 Grep 工具，git 与其他操作走 PowerShell 或 Python `subprocess` |
| 旧仓库 4 个文件未跟踪 | `CODE_MAP.md` / `DOCKER_PLAN.md` / `GEO_CAPABILITIES.md` / `project2-lessons-and-interview.txt` 为 `??` 状态，`git show legacy/main:<path>` 会失败，必须直接读工作区 |
| `uv python find 3.14` 指向 conda 空环境 | 必须精确钉 `3.14.6` + `python-preference = "only-system"` |
| 目标路径存在残留锁 | 曾出现 `PermissionError: [Errno 13]` 指向 `.git/objects` 下的文件；投放前须清除目标残留 `.git`，复制时先清只读属性并重试 |

---

*本文档与《Remote_Sensing_重构方案.md》《Remote_Sensing_迁移映射与阶段拆解.md》共同构成 Phase 0 规划产出。执行期任何偏离须先回到本文档更新协议，再动代码。*
