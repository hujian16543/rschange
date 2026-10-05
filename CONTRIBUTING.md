# 贡献指南

> 本文档为**声明式**规范：需要 / 必须 / 应当 / 禁止。判定一律给出**通过 / 不通过**。
> 命令与门禁的完整说明见 `docs/DEVELOPMENT.md`；CI 实际执行内容见 `.github/workflows/ci.yml`。

---

## 1. 分支模型

### 1.1 三条分支线

| 线 | 命名 | 从哪拉 | 合到哪 | 目的 |
|---|---|---|---|---|
| **L1 集成线** | `phase-N-<slug>` | **上一阶段的 tag**（不是 `main`） | `main`（`--no-ff`） | 一个阶段一个可验收单元 |
| **L2 任务线** | `task-N.K-<slug>` | 本阶段 L1 分支 | 本阶段 L1 分支（`--no-ff`） | 隔离单点改动，失败可单独 revert |
| **证据线** | `verify-N-report` | 本阶段 L1 tip | `main`（紧随 L1 之后） | 验收报告独立于执行者产出 |

命名分隔符**必须**用连字符 `-`，**禁止**用斜杠 `/`。现实用例：`phase-6-cicd`、
`task-4.1-ts-strict`、`verify-6-report`。

L1 必须从**上一阶段的 tag** 拉取，而非 `main`：从 `main` 拉会把别的合入混进本阶段基线，
`git diff v0.N.0 v0.N+1.0` 失去意义。

### 1.2 手册 §5 三档模式

| 模式 | 分支数 | 保留什么 | 失去什么 |
|---|---|---|---|
| 完整模式 | L1 + L2×K + verify | 每个任务可单独 revert | 分支操作次数多 |
| **精简模式** | L1 + 一条证据线（无 L2） | 阶段级隔离与回退；验收证据链完整 | 单任务粒度回退能力 |
| 最简模式 | 仅 L1 | 阶段隔离 | 证据分支独立性与单任务回退 |

**判定准则**：某阶段内任务数 ≤ 3 且无并行需求时**直接用精简模式**。完整模式只对高复杂度
阶段强制。Phase 5、Phase 6 均为精简模式（L1 + `verify-N-report`，未建 L2）。

### 1.3 合并与打 tag 的顺序

顺序**必须**如下（验收在合入 `main` **之前**完成，禁止未验收先污染稳定线）：

```bash
# ① 验收官从 L1 tip 检出证据线，只写 docs/verification/
git switch -c verify-6-report phase-6-cicd
git add docs/verification/phase-6.md
git commit -m "docs(verify): Phase 6 验收报告"
git switch phase-6-cicd
git merge --no-ff verify-6-report -m "merge(verify): Phase 6 证据并入集成分支"

# ② 判定通过后，L1 合入 main
git switch main
git merge --no-ff phase-6-cicd -m "merge: Phase 6 · 容器化与 CI"

# ③ 打 tag（打在含代码与证据的 main 上）
git tag -a v0.6.0 -m "Phase 6: 容器化与 CI（验收通过）"
#    上面的示例取自 Phase 6；Phase 7 收口产出的 tag 是 v1.0.0

# ④ 推送
git push origin main --follow-tags
```

纪律：

* **禁止 squash 合入**：squash 会压平任务级历史，丢掉「单个任务改动可单独 revert」的
  能力。`--no-ff` 合入后 `main` 上每个阶段仍只占一个合并节点，历史同样清爽。
* **tag 必须打在证据合入之后**：这样 `git checkout v0.6.0` 能同时读到代码与该阶段的
  验收结论，而不是只有代码、结论散落在对话里。
* **分支一律保留不删**。执行手册 §1.1 / §2.2 的「合入即删」自 `v1.0.0` 起**作废**：
  保留的 L1 / L2 / 证据线三线给出最细的回退粒度，且完整引用清单是 `.git` 目录损坏
  事故（2026-10-04，同一会话内两次）的恢复依据。**禁止**以「清理分支」为由删除
  `phase-*` / `task-*` / `verify-*`。代价是 `git branch` 列表持续增长，其可读性由
  命名规范维持，而非由删除维持。
* 判定为**不通过**时：**第 ② 步不执行**。集成分支保留待修，`main` 不受影响。
* 分支创建后**必须**立即验证引用已落盘：

  ```bash
  git rev-parse --verify refs/heads/task-6.1-xxx   # 必须返回 40 位 sha，非零退出即失败
  ```

### 1.4 回退策略

| 场景 | 命令 | 代价 |
|---|---|---|
| 阶段中途放弃 | `git switch main`（什么都不合） | 零损失；任务分支保留可续做 |
| 阶段已合但发现回归 | `git revert -m 1 <merge-commit>` | 保留历史，可审计 |
| 阶段已合且 tag 错误 | `git reset --hard v0.N.0` + `git push --force-with-lease` | 仅在未推送或私有仓库可接受；已推送时改用 `revert` |
| 单个任务改动有问题 | `git revert` 该任务 merge 节点 | L2 分支模型存在的意义 |

---

## 2. 提交规范

```
<type>(<scope>): <subject>
```

| `type` | 用途 |
|---|---|
| `feat` | 新功能 |
| `fix` | 缺陷修复 |
| `refactor` | 重构（行为不变） |
| `test` | 测试 |
| `build` | 构建 / 依赖 |
| `ci` | CI 配置 |
| `docs` | 文档 |
| `chore` | 发布、杂项 |

`scope` 为「阶段号 + 模块」，如 `2/contour`、`3/plugin`、`1/uv`。
L2 任务分支内的提交**必须**带本阶段号前缀，使 `git log v0.N.0..v0.N+1.0 --oneline`
天然按任务分组可读。

仓库实际使用的写法：

| 形态 | 示例 |
|---|---|
| 任务提交 | `refactor(2/contour): 拆分 extract_boundary` |
| 证据提交 | `docs(verify): Phase 2 验收报告` |
| 发布提交 | `chore(release): 0.6.0` |
| 任务合并 | `merge(2.3): labeling 拆分与 D-6 修复` |
| 阶段合并 | `merge: Phase 2 · C++ 引擎解耦` |
| 证据合并 | `merge(verify): Phase 6 证据并入集成分支` |

规范：

* 一行 subject **禁止**超过 72 字符；正文与 subject 之间空一行。
* 正文写「为什么」而不是「改了什么」——后者由 diff 表达。
* 一次提交只做一件事；**禁止**把格式化、依赖升级与逻辑改动混在一个提交里。
* 阶段号前缀与分支号必须一致，禁止跨阶段串号。

---

## 3. 门禁要求

### 3.1 提交前必须本地跑通

按顺序执行（完整说明与失败含义见 `docs/DEVELOPMENT.md` §5）：

```bash
# Python
uv sync --all-packages                                   # 禁止裸 uv sync
uv run pytest -o addopts="" -rs
uv run mypy
uv run ruff check .                                      # 必须是 "."，与 CI 一致
uv run ruff format --check .

# 契约第一段
uv run python scripts/gen_openapi.py --check

# 仓库自检
uv run python scripts/verify_baseline.py --phase 6       # 禁止用 --phase 1
uv run python scripts/verify_bindings.py
uv run python scripts/verify_config.py
uv run python scripts/verify_version.py
uv run python scripts/verify_containers.py

# 引擎
cmake --build --preset dev-win                           # 或 dev-linux
ctest --test-dir engine/build/dev-win --output-on-failure

# 前端
cd frontend && npm run check && npm run build
```

Windows 环境**必须**先设 `PYTHONUTF8=1`（门禁脚本以中文输出，非 UTF-8 stdio 会
`UnicodeEncodeError`）。

### 3.2 CI 会跑什么

`.github/workflows/ci.yml` 单 job `verify`，矩阵 `linux-gcc`（`dev-linux`）与
`windows-mingw`（`dev-win`），`fail-fast: false`——一平台失败不取消另一平台。

触发：`push` 到 `main` / `phase-*` / `verify-*`；`pull_request` 到 `main`；
`workflow_dispatch`。同一分支新推送取消旧运行。

24 个步骤分三段门禁：

| 段 | 覆盖步骤 | 管什么 |
|---|---|---|
| ① 功能正确性 | C++ 单测（CTest step 14）、Python 测试（step 15） | 功能是否回归 |
| ② 契约未漂移 | `tests/contract` + `gen_openapi.py --check`（step 18）+ **step 23「契约类型零漂移（openapi → TS）」** | 契约是否漂移 |
| ③ 环境 / 配置 / 绑定 / 版本 / 容器自洽 | step 19 的五个 `scripts/verify_*.py` | 资产是否自洽 |

另有类型检查（step 16）、`ruff check .` + `ruff format --check .`（step 17）、
`npm run check`（step 22）、`npm run build`（step 24）。

三段**任一失败即红**。阶段分支在合入 `main` **之前**就必须是绿的。

---

## 4. 文档规范

* 一律**声明式**中文：需要 / 必须 / 应当 / 禁止。**禁止**协作式口吻
  （「我们来看」「让我来解释」「建议可以试试」）。
* 判定**必须**给出 `通过` 或 `不通过`，禁止「基本满足」「大致 OK」。
* 每条命令必须可在仓库中核对；**禁止**编造命令、参数与文件名。
* 引用文件一律给路径，必要时给行号（`file:line`）。
* 未核实的内容**必须**显式标注 `待核实`，禁止以推测充当事实。
* 表格 + 代码块优先于长段落。
* **禁止**在文档与配置文件中写入机器相关绝对路径（`test_architecture.py` 的 G3.5 守护）。
* 已知不一致不得静默沿用：发现文档与代码冲突时，以**代码**为准并在报告中指出。

---

## 5. 改契约的流程

契约链路：

```
backend/src/rschange/api/schemas/*.py
   → (scripts/gen_openapi.py)  → docs/api/openapi.json
   → (npm run gen:types)       → frontend/src/api/generated/data-contracts.ts
```

改动 pydantic 模型后**必须**依次执行下列命令，否则 CI 两段契约门禁都会红：

```bash
# 1. 重新生成冻结的 OpenAPI 产物（覆盖写入）
uv run python scripts/gen_openapi.py

# 2. 重新生成前端 TS 类型
cd frontend && npm run gen:types && cd ..
#   等价入口：bash scripts/gen-api-types.sh  或  pwsh scripts/gen-api-types.ps1

# 3. 自检：两段门禁都应为通过
uv run python scripts/gen_openapi.py --check
git status --porcelain -- frontend/src/api/generated    # 必须为空
```

补充规则：

* `frontend/src/api/generated/data-contracts.ts` 是生成产物（带 `// @ts-nocheck`），
  入库但**禁止手改**；`frontend/src/api/types.ts` 只作转发别名，不含手写字段。
* 工具**禁止**换回 `openapi-typescript`：其 peer 依赖要求 `typescript@^5.x`，与本项目
  `~6.0.2` 冲突。
* 新增 / 删除 / 改类型响应字段时，同步更新 `docs/contracts.md` §9 与 `docs/api/openapi.json`；
  `DetectionResponse` 当前为 **12** 个字段（`status` 已于 `v0.5.0` 移除）。
* 改版本号：真相源只有 `backend/pyproject.toml` 一处。改完**必须**
  `uv sync --all-packages` 刷新元数据，再重跑 `gen_openapi.py` 与 `gen:types`
  （`info.version` 是契约产物的一部分）。
* `scripts/gen-api-types.sh` 只负责生成，**不做**漂移校验。

---

## 6. 验收证据

每阶段**必须**产出一份 `docs/verification/phase-N.md`，由独立于执行者的验收官出具，
落在证据线 `verify-N-report` 上（该分支只写 `docs/verification/`）。

体例（参照 `docs/verification/phase-6.md`）：

| 节 | 内容 |
|---|---|
| 1. 验收对象与基准 | 上一阶段 tag、交付目标、被检 tip、版本真相源、受管文件数、本阶段分支形态 |
| 2. 交付范围与分支纪律 | 交付文件清单 + 分支形态判定 |
| 3–N. 各出口门 | 逐门给出判据、实测证据、判定（通过 / 不通过） |
| 变异测试 | 亲手改坏再还原，证明门禁具备判别力 |
| 门禁逐条结果表 | 每个门禁的实际输出与判定 |
| 数字对照 | 与上一阶段的规模 / 计数对照 |
| 未关闭项 | 编号列表，逐条说明与处置；即使不阻断也必须列出 |
| 写操作披露 | 对仓库做过的一切写操作与还原凭据 |
| 总判定 | 三条出口门判定表 + 结论 |

纪律：

* 证据必须来自真实命令输出，禁止人工修饰；未执行的验证**必须**如实标注
  「未验证」并列入未关闭项（例如容器未构建、运行时未实测）。
* 探针脚本与日志**禁止**进入仓库，留存于 `_work/` 下。
* 判定不通过时，禁止把 L1 合入 `main`。
