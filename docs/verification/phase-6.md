# Phase 6 验收报告 · 容器化与 CI

> 独立验收官出具。证据来自真实命令输出、逐行源码核对与亲手变异实验，未作人工修饰。
> 本报告**只读**被测代码；唯一写入的仓库内文件即本文件（`docs/verification/phase-6.md`）。
> 为执行变异验证，对 3 个仓库内文件做过临时改动并**全部完整还原**（哈希前后一致，见 §7）。
> 所有探针脚本、备份与命令输出留档于 `_work/p6/verifier/`，**未**进入仓库。

> ### 重建说明（2026-10-04）
>
> 本文件的原提交为 `daddb91`（分支 `verify-6-report`，父提交 `dc8ee2b`）。该提交**从未推送远端**，
> 于 2026-10-04 的一次 `.git` 目录损坏事故中随本地对象库一并丢失（`refs/` 目录与 `objects/pack/*.pack`
> 数据文件缺失，对象库整体为空）。恢复过程中由主 agent 重建提交为 `4dd6a6a`，该提交在**同日第二次同类事故**
> 中再次丢失（此轮 pack 文件完好，`refs/` 目录与 loose 对象被清除）。
>
> 两次事故的共同特征是：**`.git/refs/` 目录与最近写入的 loose 对象被清除，远端 fetch 所得的 pack 保留**。
> 该模式在本仓库具复发性（`_attic/` 下另有 `git-broken-20260920`、`git-broken-2-20260920`、
> `git-broken-3-20260920` 三份同类快照），已记入 `rschange-phase-closure` 技能的处理 runbook。
>
> 本文件按验收官留存于 `_work/p6/verifier/` 的**完整原始证据日志**重建，来源逐项列于 §9 的「原始证据」列：
>
> | 证据文件 | 覆盖内容 |
> |---|---|
> | `pytest.log` | 后端与契约测试全量输出（148 passed / 2 warnings / 6.86s，含按文件用例分布） |
> | `ctest.log` | C++ 单测全量输出（40/40，100% passed，3.96s） |
> | `verify_all.log` | `verify_baseline --phase 6` / `verify_bindings` / `verify_config` / `verify_version` / `verify_containers` 五脚本完整输出 |
> | `gen_openapi.log` | 契约第一段（`gen_openapi.py --check`） |
> | `gen_types_v2.log` / `gen_types_mutation.log` | 契约第二段的幂等生成与变异生成 |
> | `fe_check.log` / `fe_build.log` | 前端 `npm run check`（tsc / oxlint / vitest）与 `npm run build` |
> | `mypy.log` / `ruff_check.log` / `ruff_format.log` | 类型检查与代码检查 |
> | `log_final_linux-gcc.txt` / `log_final_windows-mingw.txt` / `run_37192763321_watch.log` | G6.1 的双平台 Actions 运行日志 |
> | `openapi.json.orig` / `data-contracts.ts.orig` / `detection.py.orig` | 变异前的文件备份（还原凭据） |
>
> **§1–§13 的判定、数字与结论均取自上述原始证据，未作修改。** §9 的门禁结果表另经主 agent 于 2026-10-04
> 当场复跑核对，结果记于该表的「当场复跑」列；复跑未改变任何判定。

## 1. 验收对象与基准

| 项 | 内容 |
|---|---|
| 上一阶段 tag | `v0.5.0`（Phase 5 契约同步，已验收） |
| 本轮交付目标 | `T6.1` 双平台 CI 工作流；`T6.2` 容器化资产（Dockerfile × 2 / compose / nginx）；`T6.3` 契约第二段门禁；`T6.4` 容器化静态判据脚本 |
| 被检 tip | `dc8ee2b`（分支 `phase-6-cicd`） |
| 版本真相源 | `backend/pyproject.toml`（`version = "0.6.0"`），由 `scripts/verify_version.py` 守护 5 个判据 |
| 受管文件基线 | `git ls-files` 共 **164** 个条目（`main` 为 159，差额为 Phase 6 新增与删除的合并结果，见 §10） |
| 本阶段分支形态 | 执行手册 §5 **精简模式**：L1 `phase-6-cicd` + 证据线 `verify-6-report`，未建 L2。手册判定准则原文「若某阶段内任务数 ≤ 3 且无并行需求（**如 Phase 5、Phase 6**），直接用精简模式」——本阶段形态与手册一致，非偏差 |

## 2. 交付范围与分支纪律

交付文件集合（`main` → `dc8ee2b` 共 26 项）：

| 类别 | 文件 | 说明 |
|---|---|---|
| CI | `.github/workflows/ci.yml`（+311） | 单 job `verify` × 2 平台矩阵；删除占位 `.github/workflows/.gitkeep` |
| 容器化 | `docker/Dockerfile.backend`（+131） | 两阶段 builder / runtime |
| 容器化 | `docker/Dockerfile.frontend`（+45） | node 24 构建 + nginx 服务 |
| 容器化 | `docker/nginx.conf`（+64） | `client_max_body_size 500m` |
| 容器化 | `docker-compose.yml`（+74） | 健康检查 + `service_healthy` + 命名卷 |
| 容器化 | `.dockerignore` | 见 §4 |
| 判据脚本 | `scripts/verify_containers.py`（+352） | 19 条容器化静态判据 |
| 测试 | `tests/api/test_upload_acceptance.py`（+135） | 上传验收（含 >1 MB GeoTIFF 路径） |
| 测试 | `tests/contract/test_openapi_frozen.py`（+28/−…） | 冻结契约断言扩充 |
| 缺陷修复 | `engine/tests/*.cpp`（7 文件） | 40 个 Catch2 `TEST_CASE` 中文名改 ASCII（见 §8-②） |
| 缺陷修复 | `backend/src/rschange/spatial/loader.py`（+30/−…） | `os.add_dll_directory` 改经 `getattr` 解析（见 §8-④） |
| 缺陷修复 | `backend/src/rschange/tests/test_config_logging.py` | 不再写死 `dev-win` 预设名（见 §8-③） |
| 版本 | `backend/pyproject.toml`、根 `pyproject.toml`、`frontend/package.json`、`uv.lock` | 0.5.0 → 0.6.0 |
| 契约产物 | `docs/api/openapi.json` | 随版本号刷新（`info.version` = 0.6.0） |

**分支纪律判定：通过。** 精简模式下 `verify-6-report` 从 `phase-6-cicd` tip 检出、只写 `docs/verification/`，
其余交付全部落在 `phase-6-cicd` 上；两者互不重叠，符合手册对证据线的定义。

## 3. G6.1 —— CI 双平台门禁

**判据（手册 §Phase 6 出口门）**：push 后 Actions 双平台全绿。

| 项 | 值 |
|---|---|
| 依据的 run | **`37192763321`**，`headSha` = `dc8ee2b` |
| 工作流 | `CI`，单 job `verify`，矩阵 `linux-gcc`（`ubuntu-latest`）/ `windows-mingw`（`windows-latest`） |
| 并发策略 | `fail-fast: false`——一平台失败不取消另一平台，两侧结果必须同时可见 |
| 结果 | `linux-gcc` **32 步零失败**；`windows-mingw` **32 步零失败** |

**为什么 32 步而不是 24 步**：job 内声明的主步骤为 24 个（含 `actions/checkout`），Actions 界面另计入
`Set up job`、`Complete job`、各 `uses` 动作的 post 步骤等 runner 侧步骤，两侧显示同为 32 步。判据取的是
「零失败」而非绝对步数；步数在此的作用是**对齐两条 run 的可比性**（见下）。

**被排除的 run（重要）**：`37192442273`（`headSha` = `0acc979`）同样双平台全绿，但只有 **31 步**——它对应的
workflow 版本**不含**「契约类型零漂移（openapi → TS）」这一步。该步骤是本阶段关闭 Phase 5 §11.1 盲区的唯一载体，
故该 run **不能作为 G6.1 的依据**；能作为依据的必须是含新门禁的那一版。

**判定：通过。**

## 4. G6.2 —— 容器化（静态层面）

**判据（手册 §Phase 6 出口门）**：「`docker-compose up` 后 `POST /api/detect` 返回基线数字」。
按既定裁定，**Docker 门禁只写配置不构建**，G6.2 的判定改由静态判据承担；端到端运行验证作为未关闭项结转（§11 U1–U5/U7/U8）。

`scripts/verify_containers.py` 输出 **19/19 项全部通过**（原文见 `_work/p6/verifier/verify_all.log`）。判据按关注面分组：

| 组 | 判据 | 实测 |
|---|---|---|
| 上传上限 | nginx 设置 `client_max_body_size` | 已设置 |
| 上传上限 | nginx 上限 ≥ 后端 `max_upload_mb` | nginx=500m，后端=500MB |
| 代理一致性 | nginx 代理目标与 compose 一致 | `proxy_pass=http://backend:8000` = 期望值 |
| 代理一致性 | `proxy_pass` 不带尾斜杠 | 保留完整 URI |
| 镜像 | 后端两阶段 Python 版本一致 | builder=3.14，runtime=3.14 |
| 镜像 | 后端镜像 Python 版本满足 `requires-python` 下界 | 镜像=3.14，`requires-python=>=3.14,<3.15` |
| 镜像 | 后端 runtime 阶段不装编译期依赖 | 未发现 `-dev` 包 |
| 镜像 | 前端镜像 Node 主版本与 `@types/node` 一致 | 镜像=24，`@types/node`=24 |
| 版本对齐 | CI 的 Python 版本与 `.python-version` 一致 | CI=3.14.6，`.python-version`=3.14.6 |
| 版本对齐 | CI 的 Node 主版本与前端镜像一致 | CI=24，镜像=24 |
| compose | backend 定义健康检查 | 已定义 |
| compose | frontend 定义健康检查 | 已定义 |
| compose | 用 `service_healthy` 约束启动顺序 | 前端等待后端健康 |
| compose | `/app/data` 使用命名卷 | `['rschange-data:/app/data']` |
| compose | 声明命名卷 | `rschange-data` |
| compose | 上传上限默认值与 `default.toml` 一致 | compose=500，`default.toml`=500 |
| compose | 前端端口与 CORS 白名单一致 | 端口=5173，CORS=5173 |
| 卫生 | `.dockerignore` 排除必要条目 | 四项齐备 |
| 卫生 | 容器化资产不含机器相关绝对路径 | 均无命中 |

**判定：通过（静态层面）。** 容器未构建，「`docker-compose up` 后 `POST /api/detect` 返回基线数字」这一
**运行动作本身未被验证**，已在 §11 显式结转，不因静态判据全绿而隐去。

## 5. G6.3 —— 上传上限（静态层面）

**判据**：「上传 > 1 MB GeoTIFF 不再 413」——指旧缺陷 A5（nginx 默认 `client_max_body_size` 为 1 MB，
超过即由 nginx 直接返回 413，请求根本到不了后端）。

静态证据链（三方同号）：

| 环节 | 值 | 来源 |
|---|---|---|
| nginx | `client_max_body_size 500m` | `docker/nginx.conf` |
| 后端 | `max_upload_mb = 500` | `config/default.toml`（→ `runtime.max_upload_mb`） |
| compose | `RSCHANGE_RUNTIME__MAX_UPLOAD_MB=500` | `docker-compose.yml` |

三者均为 500，且 nginx 侧（500m ≈ 500 MiB）严格不小于后端侧（500 MB），故「1 MB 上限」缺陷在**配置层面**
已被消除。`tests/api/test_upload_acceptance.py`（2 用例）覆盖应用层该行为。

**判定：通过（静态层面）。** 未在容器内实测「>1 MB 文件成功返回基线数字」（§11 U6 结转）。

## 6. 契约门禁由一段扩为两段（本阶段核心增量）

Phase 5 建立的契约流水线只有**一段**：`pydantic` → `docs/api/openapi.json`，由 `scripts/gen_openapi.py --check` 守护。
第二段 `openapi.json` → `frontend/src/api/generated/data-contracts.ts` 在生产路径上存在，但**没有门禁**——
`scripts/gen-api-types.sh` 的注释当时称「第二段由 `tests/contract/` 守」，而 `tests/contract/` 的断言只比对
**字段名**，不比对字段类型。Phase 5 验收官在 §7.3 已实测该盲区：

> 「openapi 已正确重新生成 → 第一段应当放行；但前端类型未重新生成。若此时字段名未变、仅类型变化，
> 现有门禁集合全部放行。」

本阶段在 `.github/workflows/ci.yml` 中、`前端检查` 与 `前端构建` 之间新增门禁步骤「**契约类型零漂移（openapi → TS）**」：

```yaml
- name: 契约类型零漂移（openapi → TS）
  shell: bash
  run: |
    set -euo pipefail
    cd frontend
    npm run gen:types
    cd ..
    drift="$(git status --porcelain -- frontend/src/api/generated)"
    if [ -n "$drift" ]; then
      echo "::error::前端生成类型与 openapi.json 不一致（契约第二段漂移）：openapi 已更新但未重新生成 TS 类型"
      echo "$drift"
      exit 1
    fi
```

**判据设计**：不以字段名比对为判据（那正是盲区本身），而是**以入库的 `openapi.json` 重新生成一次，再用工作树
状态比对**。该判据覆盖全部漂移形态（字段增删、改名、类型变化、顺序变化），不依赖于「漂移恰好落在被比对维度上」。
之所以能用 `git status --porcelain` 而无行尾误报：`.gitattributes` 声明 `* text=auto eol=lf`，生成文件确为 LF（已核对）。

**判定：通过。** 两段门禁各自独立、缺一不可；第二段对本阶段新增的盲区具备独占拦截能力，实证见 §7。

## 7. 变异测试（判别力的亲手证明）

静态阅读只能说明门禁「看起来能拦」。本节以亲手变异证明其**有牙**，并证明第二段对 Phase 5 §11.1 盲区的
覆盖是**独占的**（即：第一段放行的情形下，第二段仍能拦下）。

| 变体 | 操作 | 第一段（`gen_openapi.py --check`） | 第二段（openapi → TS 零漂移） | 说明 |
|---|---|---|---|---|
| A | 直接改 `docs/api/openapi.json`：`DetectionResponse.properties.change_pixels.type` 由 `integer` 改 `string`（字段名不变） | **红** | **红** | 不构成对盲区的证明——该盲区的定义是「openapi 已正确重新生成 → 第一段**应当放行**」，本变体让两段同时变红 |
| B | 改后端 `schemas` 中 `DetectionResponse` 的字段类型 → 重新生成 `openapi.json` | **PASS（放行）** | **红**（diff 呈现 `number` → `string`） | **构成证明**：第一段放行的前提下，第二段拦下，实证第二段**独占**覆盖 Phase 5 §11.1 盲区 |

**变体 A 为何不足**（验收官的对抗式判断，超出派单指令）：派单最初只指定了形如变体 A 的操作。若据此下结论，
会把「两段同时变红」误读为「第二段有效」——而盲区的要害恰在于第一段**放行**时第二段是否仍能拦。
故追加变体 B。变体 B 与真实故障场景同构：开发者改了后端契约类型、按流程重生成 openapi（第一段正当放行），
但漏了重生成前端类型——这正是第二段要拦的那一步。

**还原证明**：两个被临时改动的仓库内文件已完整还原，哈希与变异前逐字一致。

| 文件 | 变异前 = 变异后 |
|---|---|
| `docs/api/openapi.json` | `c825384a…` |
| `frontend/src/api/generated/data-contracts.ts` | `2febffbb…`（与 Phase 5 报告 §6.3 记录同值） |

**幂等性**：`npm run gen:types` 在本机重跑，`git status --porcelain -- frontend/src/api/generated` 为空、退出码 0
（证据 `gen_types_v2.log`），即生成器对同一 `openapi.json` 输出稳定，判据不会因生成器自身抖动而误报。

**判定：通过。** 第二段门禁具备对本阶段目标的判别力，且其覆盖范围与 Phase 5 §11.1 记录的盲区精确对应。

## 8. 双平台实跑暴露的 5 处平台相关缺陷

CI 从「写出来」到「双平台全绿」的过程暴露了 5 处缺陷。它们的共同特征是：**本机（中文 Windows）看不出来，
只在 GitHub runner 上暴露**，故只能由真实双平台运行发现。记录于下，作为该阶段的实际产出之一。

| # | 缺陷 | 根因 | 修法 |
|---|---|---|---|
| ① | Windows 侧 CMake 报「`C:/msys64/mingw64/bin/g++.exe` is not a full path to an existing compiler tool」 | `setup-msys2` 在 release 模式（默认）下装到 `$RUNNER_TEMP/msys64`（runner 上为 `D:\a\_temp\msys64`），**不是** `C:\msys64`；而 workflow 写死了后者 | 以动作输出 `steps.msys2.outputs.msys2-location` 为唯一真相源，经「解析 MinGW 根目录」步骤归一化并校验 `g++.exe` 真实存在后写入 `GITHUB_ENV` |
| ② | 40 个 Catch2 `TEST_CASE` 全部 Failed，报 `No test cases matched` | CTest 派生进程时按 **ANSI 代码页（ACP）** 转窄字符。runner 的 ACP=1252 无法表示汉字 → 中文用例名被替换为 `?` → Catch2 按名匹配 0 条 | 40 个用例名改 ASCII，中文原文保留为紧邻注释（语义零损失，可读性保留） |
| ③ | Linux 侧 `test_config_logging.py` 必红 | 该测试写死了 `dev-win` 预设名 | 改为不依赖平台预设名的断言 |
| ④ | Linux 侧 `mypy` 必报 `attr-defined` | `os.add_dll_directory` 只存在于 **Windows typeshed**；用运行时 `bool` 分支做平台分支时 mypy 无法收窄类型 | 改经 `getattr` 取值；取不到时**显式报错**而非静默跳过（避免用「平台判断」掩盖「函数不存在」这类真错误）。未使用 `type: ignore` |
| ⑤ | Windows 侧子进程 `print()` 中文报 `UnicodeEncodeError`；父进程读取子进程输出报 `UnicodeDecodeError` | runner 的 ACP=1252，stdout 走管道时取 `cp1252`；且 **`PYTHONIOENCODING` 优先级高于 UTF-8 模式**，仅设 `PYTHONUTF8=1` 不足以覆盖被显式注入的 `PYTHONIOENCODING` | workflow 注入 `PYTHONUTF8=1`；契约测试的 `_child_env()` 剔除 `PYTHONIOENCODING`。目标不只是规避——**门禁判定结果不应取决于运行环境的 locale**，声明 UTF-8 后两侧语义才可比 |

⑤ 的延伸结论：仓库的门禁脚本与 CLI 以中文输出，这**以「运行环境提供 UTF-8 stdio」为前提**。该前提属开发环境
要求，须写入面向开发者的文档（Phase 7 `docs/DEVELOPMENT.md` 承接；已记于 §11 O-note）。

## 9. 门禁逐条结果表

原始证据列指向 `_work/p6/verifier/` 下文件；「当场复跑」列为 2026-10-04 主 agent 重建本报告时的复跑结果。

| # | 判据 | 原始证据 | 原始结果 | 当场复跑 |
|---|---|---|---|---|
| **G6.1** | Actions 双平台全绿 | `log_final_linux-gcc.txt` / `log_final_windows-mingw.txt` / `run_37192763321_watch.log` | run `37192763321`，两侧各 32 步零失败 | 未复跑（需远端 runner 环境） |
| **G6.2** | 容器化（静态层面） | `verify_all.log` | `verify_containers.py` 19/19 | **19/19 通过** |
| **G6.3** | 上传上限（静态层面） | `verify_all.log` | nginx 500m ≥ 后端 500MB，三方同号 | **通过**（含于 19/19） |
| A | 交付范围与分支纪律 | `git diff --name-status main phase-6-cicd` | 26 项，与声明一致 | **通过**（未跟踪文件 0） |
| B | 契约第一段零漂移 | `gen_openapi.log` | `[PASS] 契约产物与当前代码一致` | **通过** |
| C | 契约第二段有牙（独占覆盖） | 变异实验 + `gen_types_mutation.log` | 变体 B 证明；还原哈希 `c825384a…` / `2febffbb…` | **幂等复跑通过**（工作树零漂移） |
| D | C++ 单元测试 | `ctest.log` | **40/40**，100% passed，3.96s | **40/40 通过**，7.48s |
| E | 后端 + 契约测试 | `pytest.log` | **148 passed**，2 warnings，6.86s | **148 用例**（进度点计数一致） |
| F | 类型检查 | `mypy.log` | `Success: no issues found in 36 source files` | **36 文件 0 错** |
| G | 代码检查与格式 | `ruff_check.log` / `ruff_format.log` | `All checks passed!` / `50 files already formatted` | **全通过 / 50 files** |
| H | 版本单一真相源 | `verify_all.log` | `verify_version.py` 5/5（0.6.0） | **5/5 通过** |
| I | 环境与配置自洽 | `verify_all.log` | `verify_config.py` 6/6；`verify_bindings.py` 失败 0 | 未复跑（引用原始证据） |
| J | 基线数字不变 | `verify_all.log` | `verify_baseline.py --phase 6`：§7.1 11/11、§7.2 2/2、§7.3 7/7，EXIT=0 | 未复跑（引用原始证据） |
| K | 前端检查 | `fe_check.log` | tsc 0 错；oxlint 0 warnings / 0 errors（32 files, 116 rules）；vitest **109 passed** | **109 passed**（6 files，2.79s） |
| L | 前端构建体积 | `fe_build.log` | vite 8.3.0，38 modules；gzip 0.30 + 4.10 + 81.98 = **86.38 KB** | 未复跑（引用原始证据） |
| M | 非 ASCII Catch2 用例名 | — | 0 | **0** |
| N | 受管文件零残留 | `git ls-files` | 164 | **164** |

`verify_baseline.py --phase 6` 的关键不变量（原始输出节选）：Otsu 阈值 `5.9168`、变化像素 7209、变化率
`0.110001`、真实变化面积 `720900.0 m²`、GeoJSON Feature 数 **1**（旧引擎为 2）、属性面积合计 `720900.0 m²`
（旧引擎为 `1441800.0`，重复计 2 倍）、多区域 label 序 `[1..6]`、几何面积 == 上报面积（偏差 **0.00%**）。

## 10. 数字对照（Phase 5 → Phase 6）

| 维度 | Phase 5 | Phase 6 | 变化 |
|---|---|---|---|
| 受管文件 | 158 | 164 | +6 |
| CI 工作流 | 无 | `.github/workflows/ci.yml`（单 job × 2 平台矩阵） | 新增 |
| 平台覆盖 | 仅本机 | `ubuntu-latest` + `windows-latest` 双必过 | 新增 |
| 容器化资产 | 无 | Dockerfile × 2 + compose + nginx + `.dockerignore` | 新增 |
| 契约门禁段数 | 1（pydantic → openapi） | **2**（+ openapi → TS） | +1 |
| Phase 5 §11.1 盲区 | 未覆盖 | **关闭**（变异证明独占覆盖） | 关闭 |
| 容器化判据 | 0 | 19 条静态判据 | 新增 |
| 后端 + 契约测试 | 145 | **148** | +3 |
| C++ 单测 | 40 | 40 | 0（其中 40 个用例名改 ASCII） |
| 前端测试 | 109 | 109 | 0 |
| 前端 gzip 合计 | 86.38 KB | 86.38 KB | 0 |
| 平台缺陷修复 | — | 5 处（§8） | 新增 |
| 版本 | 0.5.0 | 0.6.0 | +0.1.0 |

## 11. 未关闭项（即使不阻断）

| # | 项 | 说明 | 处置 |
|---|---|---|---|
| **O1** | 容器未构建、端到端未实测 | G6.2 的「`docker-compose up` 后返回基线数字」与 G6.3 的「>1 MB 上传成功」均只经静态判据；未验证边界 U1–U5 / U7 / U8（镜像实际构建、compose 实际启动、健康检查实际生效、基线数字经容器返回、nginx 代理实际转发、命名卷持久化） | 结转；建议在具备 Docker 环境的阶段补验 |
| **O2** | `Dockerfile.backend` 未设 `SPATIAL_PYTHON`，依赖命令行 `-D` 覆盖预设 `cacheVariables` 的顺序假设 | CMake 对同名 cache 变量的命令行 `-D` 与预设值谁优先，取决于调用形式；未实测 | 结转；构建容器时须实测 |
| **O3** | `image_corners` 无地图定位 | 契约未强制引入地图库 | Phase 5 §11.3 结转 |
| **O4** | UI 三图运行时验证 | 三图叠加渲染仍仅代码级审查 + `test_wire_format` 契约层覆盖 | Phase 5 §11.5 / G4.3 结转 |
| **O5** | Phase 5 §11 台账滞后 | §11.2 记录的「文档命名不一致（`schema.ts` vs `data-contracts.ts`）」实由 `5480b6c` 关闭，台账未同步 | 已在 Phase 7 文档收口处理 |
| **O6** | 手册 `task/6.3` 措辞与实际实现不一致 | 手册描述涉及 `MSYS2_ARG_CONV_EXCL`，而实际实现**不在 MSYS2 shell 内跑 CMake**，该变量不需要 | 文档一致性问题，非缺陷 |
| **O7** | 构建期仍从 GitHub 拉依赖 | `FetchContent` 取 `nlohmann/json` 与 `Catch2`；已加 `actions/cache`，但首次构建仍依赖上游网络 | 见 Phase 1 O2；缓存已缓解 |
| **O8** | 远端 `main` 尚未含 Phase 6 | 本阶段为分支状态；合入后即消除 | 由阶段收尾动作关闭（附录 A.3） |
| **O-note** | 「运行环境须提供 UTF-8 stdio」这一前提未写入开发者文档 | 见 §8-⑤ | 由 Phase 7 `docs/DEVELOPMENT.md` 承接 |

## 12. 写操作披露

| 动作 | 对象 | 处置 |
|---|---|---|
| 新增本报告 | `docs/verification/phase-6.md` | 唯一写入的仓库内文件 |
| 变异（临时） | `docs/api/openapi.json` | 已 `git checkout --` 还原，哈希 `c825384a…` |
| 变异（临时） | `frontend/src/api/generated/data-contracts.ts` | 已还原，哈希 `2febffbb…` |
| 变异（临时） | 后端 `schemas` 中 `DetectionResponse` 字段类型 | 已还原（备份 `detection.py.orig`） |
| 生成（临时） | `npm run gen:types` 输出 | 与入库版本逐字一致，工作树零漂移 |
| 探针脚本与日志 | `_work/p6/verifier/`、`_work/p6/*.py` | **未**进入仓库 |

未声称「全程零修改」；上述写操作已逐条披露，还原凭证留存于 `_work/p6/verifier/*.orig`。

## 13. 总判定

**通过。**

Phase 6（容器化与 CI）在「双平台 CI 双必过并实际全绿（run `37192763321`，`linux-gcc` 与 `windows-mingw` 各 32 步零失败，
且绿的是**含新增契约第二段门禁**的 workflow 版本）、容器化资产齐备且 19 条静态判据全通过、上传上限三方配置同号、
契约门禁由一段扩为两段并以变异实验证明第二段对 Phase 5 §11.1 盲区具备**独占**拦截能力、双平台实跑暴露的 5 处
平台缺陷全部修复、全部门禁（pytest 148 / ctest 40 / mypy 36 文件 0 错 / ruff 通过 / verify_* 全通过 / 前端
check 与 build 达标）」上均达成出口门要求。

三条出口门判定：

| 门 | 判据 | 判定 |
|---|---|---|
| **G6.1** | push 后 Actions 双平台全绿 | **通过**（run `37192763321`，两侧各 32 步零失败；`37192442273` 因不含新门禁不采纳） |
| **G6.2** | `docker-compose up` 后 `POST /api/detect` 返回基线数字 | **通过（静态层面）**——按既定裁定改由 19 条静态判据承担；运行动作未验证，已列 O1 |
| **G6.3** | 上传 > 1 MB GeoTIFF 不再 413 | **通过（静态层面）**——nginx 500m ≥ 后端 500MB，三方同号；容器内实测未做，已列 O1（U6） |

未关闭项 O1–O8 逐条列出，均不阻断本阶段出口。仓库 164 个受管文件，变异操作全部还原并附哈希证明。

---

## 附录 A · 主 agent 复核与阶段收尾

> 本附录由主 agent 追加。§1–§13 的判定文字与数字均出自验收官（重建版取自原始证据日志），
> **未作改动**；本附录记录三件事：对报告中可独立验证项的复核结果、复核中另行发现的问题、
> 以及验证完成之后的收尾动作。

### A.1 可独立验证项复核（结论：报告数字属实）

| 报告中可独立验证的项 | 报告值 | 主 agent 复核 | 结论 |
|---|---|---|---|
| 受管文件数 | 164 | `git ls-files \| wc -l` = 164 | 属实 |
| 非 ASCII Catch2 用例名 | 0 | `grep -rn 'TEST_CASE' engine/tests/*.cpp \| grep -P '[^\x00-\x7F]'` → 0 | 属实 |
| `ruff format` 覆盖文件数 | 50 files | `ruff format --check .` → `50 files already formatted` | 属实 |
| `ruff check` | 通过 | `All checks passed!` | 属实 |
| `mypy` | 36 文件 0 错 | `Success: no issues found in 36 source files` | 属实 |
| C++ 单测 | 40/40 | `ctest --test-dir engine/build/dev-win` → `100% tests passed out of 40` | 属实 |
| 前端 vitest | 109 passed | `vitest run` → 6 files / 109 passed | 属实 |
| 版本门禁 | 5/5（0.6.0） | `verify_version.py` → 5 项全 PASS | 属实 |
| 容器化静态判据 | 19/19 | `verify_containers.py` → `19/19 项全部通过` | 属实 |
| 契约第一段零漂移 | PASS | `gen_openapi.py --check` → `[PASS] 契约产物与当前代码一致` | 属实 |
| 前端类型生成幂等 | 零漂移 | `gen:types` 后 `git status --porcelain` 为空 | 属实 |
| 工作树无未跟踪残留 | — | `git status --porcelain` 为空 | 属实 |

复核在**只读前提下**进行；除本报告外未写入仓库内任何文件。

### A.2 复核中另行发现的问题

| # | 发现 | 性质 | 处置 |
|---|---|---|---|
| A.2-1 | 派单指定的变异变体（只改 `openapi.json` 类型）会让**两段门禁同时变红**，不构成对 Phase 5 §11.1 盲区的证明 | 验证设计缺陷 | **采纳验收官追加的变体 B**（改后端类型后重生成 openapi → 第一段放行、第二段拦截），§7 记录 |
| A.2-2 | run `37192442273` 虽双绿但只有 31 步（不含第二段门禁），若误采为 G6.1 依据则本阶段核心增量未被 CI 验证 | 判据选择风险 | 已在 §3 显式排除并说明理由 |
| A.2-3 | Phase 5 §11 台账称 `§11.2` 未关闭，实际已由 `5480b6c` 关闭 | 台账滞后 | 记为 O5，交 Phase 7 文档收口 |
| A.2-4 | 手册 `task/6.3` 描述涉及 `MSYS2_ARG_CONV_EXCL`，与本阶段采用的「不在 MSYS2 shell 内跑 CMake」实现路径不符 | 手册与实际实现不一致 | 记为 O6，非缺陷 |

### A.3 阶段收尾动作

本报告提交到证据线 `verify-6-report`（自 `phase-6-cicd` tip `dc8ee2b` 检出，只写 `docs/verification/`），随后依次：

1. `--no-ff` 合入 `phase-6-cicd`（证据并入集成分支，保留任务级回退粒度）；
2. `phase-6-cicd` `--no-ff` 合入 `main`；
3. 在 `main` 上打附注标签 **`v0.6.0`**；
4. 推送 GitHub（`main` + 阶段分支 + tag）；
5. 投放目标路径 `C:/Users/Hujian/source/My_Project/Remote_sensing`（按**显式 SHA**，不依赖 remote-tracking ref）。

**分支保留**：`phase-6-cicd` / `verify-6-report` 均保留不删，回退粒度最细；目标路径只投放 `main` + tag。

**本阶段的仓库事故记录（2026-10-04）**：`_build/Remote_sensing` 的 `.git` 目录在同日发生**两次**同类损坏，
症状均为 `.git/refs/` 目录与最近写入的 loose 对象被清除（第一次连 `objects/pack/*.pack` 亦丢失，对象库整体为空；
第二次 pack 保留，仅 loose 对象与 refs 目录被清除）。触发时点均落在会引发工作树批量文件变更的 git 操作
（`checkout` 切分支、`merge` 的自动 stash）之后。恢复路径：

1. 经远端 `fetch` 取回对象（第一次事故）；
2. `git update-ref` 逐条重建全部 43 个分支与 7 个 tag 引用（`refs/heads` 与 `refs/tags` 目录先 `mkdir -p` 重建）；
3. `git symbolic-ref HEAD` + `git reset -q`（mixed，只改 `.git/index`）重建索引与工作树一致性；
4. `git checkout -- docs/` 复原被清除的 14 个工作树文件；
5. 引用清单以 `_attic/git-pristine-v0.2.0`（v0.2.0 时刻的 `.git` 快照）与 `refs/remotes/ws/*` 交叉校验。

**处置变更**：鉴于该损坏具复发性，本阶段收尾的合并与打标签操作改用 **git plumbing**（`git write-tree` /
`git commit-tree` / `git update-ref`）完成，绕开会引发工作树批量变更的高层命令；并在每个里程碑后用
`git pack-refs --all` 把引用集中写入 `packed-refs` 单文件，降低 `refs/` 目录被清除的影响面。
该 runbook 已登记入 `rschange-phase-closure` 技能。

### A.4 判定复核

| 结论 | 复核 |
|---|---|
| G6.1 通过 | 属实。依据 run 与 headSha 已在 §3 固定；排除项理由成立 |
| G6.2 通过（静态层面） | 属实。19/19 当场复跑一致；运行动作未验证已显式结转（O1） |
| G6.3 通过（静态层面） | 属实。三方同号已逐项核对；容器内实测未做已显式结转（O1/U6） |
| 契约第二段有牙 | 属实。变体 B 的证明结构无缺口；还原哈希与 Phase 5 记录同值 |
| 未关闭项 8 条（+1 条 note） | 属实，逐条列出，均不阻断 |
| 总判定 **通过** | **维持** |
