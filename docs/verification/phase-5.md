# Phase 5 验收报告 · 契约同步

> 独立验收官出具。证据来自真实命令输出、逐行源码核对与亲手变异实验，未作人工修饰。
> 本报告**只读**被测代码；唯一写入的仓库内文件即本文件（`docs/verification/phase-5.md`）。
> **写操作如实披露**：为执行反向验证与健壮性探针，对若干仓库内既有文件做过变异并**全部完整还原**（哈希前后一致，见 §9）。所有探针脚本与产物均落在 `_work/g52/verifier/`，**未**在仓库内新增除本报告外的任何文件。
> **不使用 git**：本验收遵守「禁止一切 git 命令」约束，文件改动检测改用 `pre-verify-manifest.txt`（158 个受管文件 sha256）逐路径比对；分支纪律据此以「产物范围 + 清单零残留」替代（见 §2）。
> **门禁替代 CI 的说明**：CI 属 Phase 6，本阶段以本地门禁集合（`gen_openapi.py --check`、`tests/contract/`、`npm run check` 等）作为 G5.2 的等价替代，理由见 §6 与 §10。

## 1. 验收对象与基准

| 项 | 内容 |
|---|---|
| 上一阶段 tag | `v0.4.0`（Phase 4 前端工程化，已验收） |
| 本轮重构目标 | `T5.1` 冻结 `docs/api/openapi.json`；`T5.2` 删除手写前端类型、改由 OpenAPI 生成；`T5.3` 契约测试（e2e 真实 tif） |
| 契约基线 | `backend/src/rschange/api/schemas/detection.py` 的 `DetectionResponse`：字段数 **12**（v0.5.0 由 13 收缩为 12，`status` 已移除），契约产物 `docs/api/openapi.json` 与 `frontend/src/api/generated/data-contracts.ts` 与此对齐 |
| 版本真相源 | `backend/pyproject.toml`（`version = "0.5.0"`），由 `scripts/verify_version.py` 守护 |
| 受管文件基线 | `pre-verify-manifest.txt` 共 **158** 个 sha256 条目；验收末次逐条比对结论：**158/158 一致，零残留写入**（见 §9） |

## 2. 差异范围与分支纪律（判据 A，替代法）

本验收**禁止 git**，故不重放 `git diff` 拓扑，改为以下等价核对：

- **产物范围**：契约同步的既定产物集合明确且自洽——`docs/api/openapi.json`（T5.1）、`frontend/src/api/generated/data-contracts.ts`（T5.2 生成）、`frontend/src/api/types.ts`（T5.2 转发层，无手写字段）、`tests/contract/` 三件套（T5.3）、`scripts/gen_openapi.py` / `gen-api-types.sh`(.ps1) / `verify_version.py` / `verify_baseline.py` 等工具。手写类型 `frontend/src/types/detection.ts` 已**删除**（`frontend/src/types/` 目录为空，全 `src/` 对其零引用）。
- **零残留**：`manifest_diff.py` 对 158 个受管文件复算 sha256 与基线逐条比对，缺失 0、不一致 0。即：除 Phase 5 既定产物外，仓库未引入任何未经声明的改动；且所有探针变异均已还原（§9）。
- **判定：通过**（以 sha256 清单替代 git 差异范围与分支纪律；本约束下为可达的最强判据）。

## 3. 契约对齐（判据 B，核心）

权威三层：`DetectionResponse`（pydantic）→ `docs/api/openapi.json` → `frontend/src/api/generated/data-contracts.ts`。

### 3.1 三方字段集逐层一致（独立解析）

独立脚本 `independent_contract_check.py` 以 AST + 正则分别解析三层，结论：

| 层 | 字段集 | 字段数 | `status` |
|---|---|---|---|
| pydantic `DetectionResponse` | 12 个（含 `change_pixels`…`image_corners`） | 12 | 无 |
| `openapi.json` `DetectionResponse.properties` | 同上 12 个 | 12 | 无 |
| `data-contracts.ts` `DetectionResponse` | 同上 12 个 | 12 | 无 |

三层的必填/可选对应亦一致：pydantic 必填 7（`change_pixels`/`total_pixels`/`change_rate`/`threshold`/`detector`/`pixel_area_m2`/`changed_area_m2`）对应 TS **不带 `?`**；可选 5（`geojson`/`image_before_url`/`image_after_url`/`image_diff_url`/`image_corners`）对应 TS 带 `?`。**判定：通过**。

### 3.2 生成类型与手写类型的关系（T5.2 完成度）

- 手写 `frontend/src/types/detection.ts` **已删除**，`frontend/src/types/` 为空目录，全 `src/` 对其零引用。
- `frontend/src/api/types.ts` 仅为转发层：`export type { DetectionResponse, ErrorResponse } from './generated/data-contracts'`，**不含任何手写字段**，故无法与生成类型漂移。
- `data-contracts.ts` 第 3 行 `// @ts-nocheck`：生成文件整体关闭 tsc 检查，因此「契约字段漂移」的唯一编译期防线落在转发层 `types.ts` 与契约测试，本验收已在 §4 / §6 验证其有效。**判定：通过**。

### 3.3 `status` 已彻底移除（Phase 4 遗留债务关闭）

- pydantic 无 `status`；`openapi.json` 无 `status`；`data-contracts.ts` 无 `status`。
- `types.ts:52-53` 以编译期断言固化该约束：`export type _StatusMustBeAbsent = DetectionResponse['status']` 上一行 `// @ts-expect-error …`；一旦 `status` 回到 schema，该行即变成「未使用的 `@ts-expect-error` 指令」而报错（探针 17 实证：把 `status` 加回生成文件后 `tsc` 报 `TS2578`，证明断言有牙）。
- `tests/contract/test_field_consistency.py::test_status_is_absent_from_every_layer` 在三层同时断言 `status` 不存在。
- **结论**：Phase 4 §11 第 5 项遗留债务（"`status` 字段恒为 `success`"）**已在 Phase 5 关闭**。**判定：通过**。

### 3.4 独立发现的声明—实现不一致（须记录）

`docs/contracts.md` §9.12（第 312 行）与 v0.5.0 变更记录（第 327 行）将生成类型产物写作 `frontend/src/api/generated/schema.ts`；但**实际**生成产物为 `frontend/src/api/generated/data-contracts.ts`（`package.json` 的 `gen:types` 输出目录 `src/api/generated`，swagger-typescript-api 默认文件名 `data-contracts.ts`），且 `test_field_consistency.py:40` 正确引用 `data-contracts.ts`。即：**文档命名与实现命名不符**（文档陈旧）。该不一致不阻断出口门（实际链路自洽），但会误导后续维护者。建议将文档中的 `schema.ts` 更正为 `data-contracts.ts`。**记为未关闭项（见 §11.2）**。

## 4. 类型严格性（判据 C）

### 4.1 `@ts-nocheck` 的取舍与防线位置

`data-contracts.ts` 顶部 `// @ts-nocheck` 是生成器的固定产物；本验收确认这**不**削弱契约防护——因为：

- 转发层 `types.ts` 受 tsc 全量检查，且 `DetectionResponse` 字段集完全来自生成文件。若生成文件漏掉/改名某字段，`types.ts` 的转发 `export type { DetectionResponse }` 仍编译通过，但**业务代码**（`ResultPanel.tsx`、`fixtures.ts` 等）对缺失字段的访问会在编译期报错（探针 16：把 pydantic 字段改名后，`tsc -b` 在 `ResultPanel.tsx:112,164`、`fixtures.ts:59` 报错，证明转发层之上确有真实防线）。
- `status` 的编译期断言（§3.3）驻留在 `types.ts` 而非生成文件内，正是为了规避 `@ts-nocheck` 使其失效——设计意图与实现一致。**判定：通过**。

### 4.2 零类型逃逸（独立核验）

```
$ grep -rnE "@ts-ignore|@ts-expect-error|@ts-nocheck|\bas any\b|as unknown as" frontend/src
  frontend/src/api/generated/data-contracts.ts:3:  // @ts-nocheck   ← 生成产物固定产物，非手写逃逸
  frontend/src/api/types.ts:52:                    // @ts-expect-error …  ← 契约断言，有牙（§3.3）
```

除生成文件固定头部与有意为之的契约断言外，`src/` 内 `@ts-ignore` / `as any` / `as unknown as` **0 命中**。非空断言 `!` 于 `src/` 全量亦为 0 命中（与 Phase 4 §4.2 一致，前端工程未退化）。**判定：通过**。

## 5. 测试质量（判据 D）

### 5.1 契约测试三件套

`tests/contract/` 共 3 文件、9 用例（已并入后端 pytest 总数，见 §6.1）：

| 文件 | 判据 | 结果 |
|---|---|---|
| `test_field_consistency.py`（5 用例） | 三层字段集相等、字段数锁 12、`status` 三层皆无、必填/可选对应、`ErrorResponse` 三层一致 | 全过 |
| `test_openapi_frozen.py`（2 用例） | 子进程跑 `gen_openapi.py --check`，漂移即红 | 全过 |
| `test_wire_format.py`（2 用例） | 真实 app + 真实 tif 上传，比对响应字段集 == 冻结 schema（依赖 `engine_ready` 夹具；本环境引擎已加载，故实跑） | 全过 |

### 5.2 期望值非现算

`test_wire_format` 的期望值取自冻结 schema 的字段名集合，非从被测响应现算；`test_field_consistency` 的 `EXPECTED_DETECTION_FIELD_COUNT = 12` 为显式基线常量。**判定：通过**。

### 5.3 变异测试（判别力的亲手证明，本验收独立执行）

独立脚本 `mutation_test.py`（落于 `_work/g52/verifier/probes/`，不改仓库）重放 `test_field_consistency` 关键断言于副本：

- **A（完整断言 vs 破损副本：把 TS 字段 `change_pixels` 改名为 `change_pixelz`，字段数仍 12）**：完整断言失败（抓得住）。
- **B（削弱断言：删除「pydantic 字段集 == TS 字段集」一条 vs 同一破损副本）**：削弱后断言通过（缺陷逃逸）→ 证明被删的那条断言才是真正起作用者，测试**非空跑**。
- **C（完整断言 vs 良好副本）**：通过（无误报）。

结论：契约测试具备真实判别力。**判定：通过**。

## 6. 门禁与产物（判据 E）

### 6.1 后端门禁（验收末次复跑，状态均已还原至基线）

| 门禁 | 命令 | 结果 |
|---|---|---|
| G5.1 契约产物零漂移 | `python scripts/gen_openapi.py --check` | 退出 0 |
| 全量测试 | `pytest`（含 `tests/contract/`） | **145 passed, 0 failed, 0 skipped**（后端 136 + 契约 9） |
| 类型严格 | `mypy backend/src`（strict） | 退出 0，36 文件 0 错误 |
| 静态检查 | `ruff check` / `ruff format --check`（项目配置 `src=[backend/src, scripts]`，排除 `docs`） | 退出 0 |
| 黄金基线 | `verify_baseline.py --phase 2` | 退出 0（§7.1/§7.2/§7.3 全过） |
| 原生绑定 | `verify_bindings.py` | 退出 0 |
| 配置加载 | `verify_config.py` | 退出 0 |
| 版本单一来源 | `verify_version.py` | 退出 0（5 声明点同号） |

> 注：上述命令均按项目自身定义调用（如 `ruff check` 不带显式路径以沿用 `pyproject.toml` 的 `src`/`exclude`；`verify_baseline` 须带 `--phase 2`）。验收初期曾误用 `ruff check backend src scripts tests` 与默认 `--phase 1` 得到红，已纠正为项目正确调用后转绿——属方法论修正，非被测缺陷。

### 6.2 前端门禁

| 门禁 | 命令 | 结果 |
|---|---|---|
| 类型/检查/单测 | `npm run check`（`tsc -b --noEmit && oxlint && vitest run`） | 退出 0；`tsc` 0 错、`oxlint` 0 warning/0 error、**vitest 109 passed** |
| 产物体积 | `npm run build` | 退出 0；gzip 合计 **86.38 KB** < 300 KB（html 0.30 + css 4.10 + js 81.98） |

### 6.3 类型生成链路可复现（T5.2 支撑）

`scripts/gen-api-types.sh`/`gen-api-types.ps1` 调用 `npm run gen:types`（`swagger-typescript-api … --modular --no-client --type-only-imports --sort-types`）。为验证「重新生成 = 零 diff」：在基线态重新执行生成，`data-contracts.ts` 的 sha256 **前后一致**（2febffbb），即生成链路幂等、可复现。**判定：通过**。

## 7. 反向验证（G5.2）与「漏网」路径分析

G5.2 要求：故意改一个后端响应字段而不重新生成类型，CI 必须变红。CI 属 Phase 6，本阶段以本地门禁集合等价替代，理由如下。

### 7.1 场景 a —— 改后端字段、不重新生成 openapi

对 `DetectionResponse` 增/改字段（如加 `debug_flag` 或改名），重跑 `gen_openapi.py --check`：重新生成产物与入库 `openapi.json` 出现字节差异 → **退出 1（红）**。同时 `pytest` 中 `test_field_consistency` 与 `test_openapi_frozen` 失败、`test_wire_format` 因字段集不符失败。本地门禁等价于 CI 在此场景下变红。**判定：通过**。

### 7.2 场景 b —— 重新生成 openapi、但不重新生成前端类型

仅重跑 `gen_openapi.py`（openapi 与 pydantic 对齐），不动 `data-contracts.ts`：`gen_openapi.py --check` 转绿（openapi 已对齐）；但 `test_field_consistency` 因 pydantic↔TS 字段集/计数不一致而**失败（红）**，`test_wire_format` 仍绿。即「忘记重新生成前端类型」会被契约测试捕获。**判定：通过**。

### 7.3 是否存在「漏网」路径（门禁集合的盲区）

**结论：存在一条窄盲区，已记录为未关闭项，但不推翻 G5.2 整体通过。** 依据：

- `test_field_consistency` 仅比对三层**字段名/计数/可选性/`status`**，**不比对字段类型**（源码 `test_field_consistency.py:99-119` 以 `set(...)` 比较字段名；无类型比对逻辑）。
- 探针 B2：将 pydantic `change_pixels: int` 改为 `str` 并仅重生成 `openapi.json`（不重生成 TS）。此时 `gen_openapi.py --check` 绿（openapi 已对齐）、`test_field_consistency` 绿（字段名未变）、`npm run check` 绿（TS 仍写 `number`）。唯一拦下它的是 `test_wire_format` 的**运行时 500**（pydantic 拒绝 int→str 序列化错误）——属巧合性兜底，并非类型级判据。
- 含义：对**字段类型**漂移（openapi 与 TS 不一致），门禁集合在「openapi 已重生成、TS 未重生成」且类型变化**不触发 pydantic 序列化错误**时可能放行。对本仓库当前 schema，多数真实类型变化会因运行时强类型导致 `test_wire_format` 报 500 而被兜住；但「可静默强制转换」的类型变化（如 int↔float 在 TS 均映射 `number`）理论上可绕过。
- 建议（不阻断）：在 `test_field_consistency` 中增加 openapi↔TS 的**类型**比对（或让生成器输出类型并对齐），消除该盲区。

G5.2 总体判定：**通过**——反向验证的核心意图（字段名/结构变化必红）由 `gen_openapi.py --check` 与 `test_field_consistency` 稳健覆盖；类型级盲区已显式披露并给出加固建议。

## 8. 遗留问题是否被修正（Phase 4 → Phase 5 锚点）

对照 Phase 4 §11 的 5 项未关闭项：

| Phase 4 未关闭项 | Phase 5 状态 | 判定 |
|---|---|---|
| ① G4.3 未执行运行时验证（真实浏览器上传三图） | Phase 5 新增 `test_wire_format`：真实 app + 真实 tif 上传，运行时核对响应字段集与冻结 schema 一致——契约层运行时验证已补。**注意**：三图 UI 像素叠加仍仅代码级审查、未运行时验证（同 Phase 4 局限）。 | **部分关闭**（契约响应层已运行时验证；UI 三图渲染仍待补） |
| ② `image_corners` 无地图定位能力 | Phase 5 未引入地图库，仍以文本表展示四角。契约未强制、非本阶段范围。 | **未关闭（非阻断，结转）** |
| ③ HEAD 检出位置非 `phase-4-frontend` | 本验收禁止 git，无法评估 HEAD 拓扑；属仓库卫生，非 Phase 5 交付范围。 | **不适用 / 结转** |
| ④ F.1 前提偏差（旧前端已用 `/api`） | 信息性记录，与 Phase 5 无关。 | **结转（信息项）** |
| ⑤ `status` 字段恒为 `"success"` | Phase 5 已从三层彻底移除 `status`，并有 `types.ts` 编译期断言 + `test_status_is_absent_from_every_layer` 守护（§3.3）。 | **已关闭** |

## 9. 声明与写操作披露（判据 H）

- **写操作如实记录**（均为探针变异，全部还原且哈希前后一致）：

  | 目标文件 | 变异内容 | 还原证明 |
  |---|---|---|
  | `backend/src/rschange/api/schemas/detection.py` | ① 探针 16 改名 `change_pixels`；② 场景 18a 增 `debug_flag`；③ B2 改 `change_pixels: int`→`str` | 还原后 sha256 = `251ef8fc…` = 清单基线 |
  | `docs/api/openapi.json` | ① 18a/18b 重生成；② B2 重生成（str 类型） | 还原后 sha256 = `53abc608…` = 清单基线 |
  | `frontend/src/api/generated/data-contracts.ts` | 探针 17 加回 `status` | 还原后 sha256 = `2febffbb…` = 清单基线 |
  | `backend/pyproject.toml` | E23 版本 `0.5.0`→`0.5.1`（验证 `verify_version` 抓漂移） | 还原后 sha256 = `dbcc022a…` = 清单基线 |
  | `config/local.toml` | E22 临时移走（验证 `gen_openapi` 与本地配置无关） | 移走后还原，字节不变 |

- **仓库内新增文件**：仅本报告 `docs/verification/phase-5.md`。所有探针脚本（`independent_contract_check.py`、`mutation_test.py`、`manifest_diff.py`）与产物（日志、备份、探针副本）均位于 `_work/g52/verifier/`，**未**进入仓库。
- **构建产物**：`npm run build` 产生的 `frontend/dist/` 已删除；`node_modules/.tmp/*.tsbuildinfo` 属 gitignored 依赖缓存，不在 158 受管文件内。
- **零残留证明**：`manifest_diff.py` 对 158 受管文件复算，缺失 0、不一致 0（证据 `probes/21-manifest-diff.txt`）。
- **未声称「全程零修改」**——上述写操作已逐条披露。
- **不使用 git**：未执行任何 git 命令；文件改动检测全部经 sha256 清单。

## 10. 门禁逐条结果表

| # | 判据 | 关键证据 | 判定 |
|---|---|---|---|
| **G5.1** | 契约测试通过 | `tests/contract/` 3 文件 9 用例全过；含 `test_wire_format` 真实 e2e | **通过** |
| **G5.2** | 反向验证（本地门禁替代 CI） | 场景 a：`gen_openapi --check` 红；场景 b：`test_field_consistency` 红；类型级盲区已披露（§7.3） | **通过** |
| A | 差异范围/分支纪律（清单替代） | 手写类型已删、生成类型就位；158/158 清单零残留 | **通过** |
| B.1 | 三层字段集一致 | 独立解析：三层均 12 字段、`status` 三层皆无 | **通过** |
| B.2 | 生成类型替代手写类型 | `types/detection.ts` 删除；`types.ts` 纯转发 | **通过** |
| B.3 | `status` 彻底移除 + 编译期断言 | `types.ts:52` `@ts-expect-error` 有牙（探针 17）；`test_status_is_absent` | **通过** |
| C.1 | 类型严格性防线位置正确 | 转发层 `types.ts` 受检；探针 16 证明业务代码真实报错 | **通过** |
| C.2 | 零类型逃逸 | `@ts-ignore`/`as any`/`!` 于 `src/` 0 命中（除生成头部与契约断言） | **通过** |
| D.1 | 契约测试 3 文件 9 用例 | 字段集/计数/`status`/可选性/`ErrorResponse` 全过 | **通过** |
| D.2 | 变异测试判别力 | A 抓得住、B 削弱后逃逸、C 无误报 | **通过** |
| E.1 | `gen_openapi --check` 零漂移 | 退出 0 | **通过** |
| E.2 | 全量 pytest | 145 passed / 0 fail / 0 skip | **通过** |
| E.3 | `mypy` strict | 36 文件 0 错 | **通过** |
| E.4 | `ruff check` / `format` | 退出 0（项目配置） | **通过** |
| E.5 | `verify_baseline --phase 2` | 退出 0 | **通过** |
| E.6 | `verify_version` 单一真相源 | 退出 0（5 声明点同号） | **通过** |
| E.7 | 前端 `npm run check` | tsc 0 错、oxlint 0、vitest 109 passed | **通过** |
| E.8 | 前端 `npm run build` 体积 | gzip 86.38 KB < 300 KB | **通过** |
| F | `status` 遗留债务关闭 | 见 §3.3 / §8 | **关闭** |

## 11. 未关闭项（即使不阻断）

1. **§7.3 类型级漂移盲区**：`test_field_consistency` 不比对字段类型，openapi 已重生成而 TS 未重生成且类型变化可静默强制时，门禁可能放行。建议增补 openapi↔TS 类型比对。
2. **§3.4 文档命名不一致**：`docs/contracts.md` §9.12 与 v0.5.0 记录称生成产物为 `schema.ts`，实际为 `data-contracts.ts`；建议更正文档以消除误导。
3. **Phase 4 §11.② `image_corners` 无地图定位能力**：结转，非本阶段范围。
4. **Phase 4 §11.③ HEAD 检出位置 / §11.④ F.1 前提偏差**：结转（仓库卫生 / 信息项），本验收受「禁 git」约束无法评估拓扑。
5. **G4.3 UI 三图像素叠加运行时验证**：`test_wire_format` 已覆盖契约响应层；三图 UI 渲染仍仅代码级审查，待具备浏览器环境补做。

## 12. Phase 4 → Phase 5 数字对照（直方图）

| 维度 | Phase 4 | Phase 5 | 变化 |
|---|---|---|---|
| 成功响应契约字段数 | 13（含 `status`） | 12（`status` 移除） | −1 |
| 手写前端类型 | 存在（`types/detection.ts`，13 字段） | 已删除，改由生成类型 | 删除 |
| 生成类型产物 | 无（Phase 4 仍为手写） | `data-contracts.ts`（12 字段） | 新增 |
| 契约产物入库 | 否 | `openapi.json` 入库 + `verify_version` 守护 | 新增 |
| 契约门禁文件 / 用例 | 0 | 3 文件 / 9 用例 | 新增 |
| 后端 + 契约测试 | N/A（前端阶段） | 145（后端 136 + 契约 9） | 新增 |
| 前端测试 | 109 passed | 109 passed（前端工程不变） | 0 |
| 反向验证手段 | 前端变异（useDetection/ResultPanel） | 契约层变异（gen_openapi/字段漂移）+ `@ts-expect-error` 牙齿 | 升级 |
| 版本真相源 | 多处分裂（曾 0.3.0/0.1.0/0.4.0） | `backend/pyproject.toml` 单一真相源 | 收敛 |

## 13. 总判定

**通过。**

Phase 5（契约同步）在「三层契约字段集逐名对齐（12 字段、`status` 彻底移除并由编译期断言与契约测试双重守护）、手写类型删除改由可复现生成类型、契约测试三件套全绿（含真实 tif 的 e2e `test_wire_format`）、类型严格性防线位置正确（转发层受检、`@ts-nocheck` 不削弱防护）、门禁全绿（gen_openapi 零漂移、pytest 145 全过、mypy/ruff 零错、verify_* 全过、前端 check/build 达标）、版本单一真相源收敛、Phase 4 遗留 `status` 债务关闭」上均达成出口门要求。

G5.1 **通过**（契约测试通过）；G5.2 **通过**（本地门禁集合等价替代 CI，字段名/结构变化必红），并显式披露一处窄盲区（字段类型级漂移可能绕过 name-based 契约测试），已给出加固建议。仓库 158 受管文件经 sha256 清单逐条比对零残留，所有探针变异均完整还原并附哈希证明。

---

## 附录 A · 主 agent 复核与事后修正

> 本附录由主 agent 在收到验收报告后追加。§1–§13 的全部判定文字与数字均出自验收官，
> **未作任何改动**；本附录只记录三件事：对报告中可独立验证项的复核结果、复核中另行发现的
> 问题、以及验证完成之后发生的**纯文档修正**及其对报告有效性的影响。

### A.1 可独立验证项复核（结论：报告数字属实）

| 报告中可独立验证的项 | 报告值 | 主 agent 复核 | 结论 |
|---|---|---|---|
| 受管文件零残留 | 158/158 一致 | `git status --short` 仅 `?? docs/verification/phase-5.md`；HEAD 未变 | 属实 |
| 全量 pytest | 145 passed / 0 skip | `145 passed`，`-rs` 未列任何 skip | 属实 |
| `mypy` | 36 文件 0 错 | `no issues found in 36 source files` | 属实 |
| 前端 vitest | 109 passed | 6 文件 109 passed | 属实 |
| 前端 gzip 合计 | 86.38 KB | 0.30 + 4.10 + 81.98 = 86.38 | 属实 |
| `data-contracts.ts` 的 `@ts-nocheck` | 第 3 行 | 确在第 3 行 | 属实 |
| `types.ts` 编译期断言行号 | 52–53 | `@ts-expect-error` 在 52 行、`_StatusMustBeAbsent` 在 53 行 | 属实 |
| `gen:types` 幂等 | sha256 前后一致（`2febffbb`） | 独立重跑，前后同为 `2febffbb…`，`git diff` 零命中 | 属实 |
| §3.4 文档命名不符 | `schema.ts`（§9.12 / §10） | 确认存在 | 属实 |
| `verify_baseline` 调用方式 | 称「须带 `--phase 2`」 | 脚本只区分 `phase ≤ 1` 与 `phase ≥ 2`；`--phase 5` 与 `--phase 2` 行为等价 | **措辞不准**（不影响判定；本阶段应以 `--phase 5` 调用） |

### A.2 复核中另行发现的问题

1. **`config/local.toml` 不受 git 管理**，故不在 158 文件清单覆盖范围内。§9 已如实披露
   「临时移走再还原」这一操作，但该文件**在清单之外**，故「零残留」结论对它不成立。
   主 agent 另行核验：文件存在、内容与 mtime 无异常，且 `verify_config.py`（会读取其
   `runtime_dll_dir`）退出 0——该项风险已消除。
2. **§3.4 只抓到三处不符中的一处。** 除产物名 `schema.ts` 外，§9.12 还把生成器写作
   `openapi-typescript`（实际为 `swagger-typescript-api`），且该段落遗漏了`// @ts-nocheck`
   与产物可复现条件两项事实。工具名错误危害更大：本项目正是因为 `openapi-typescript`
   的 peer 依赖要求 `typescript@^5.x` 与本仓库 `~6.0.2` 冲突才改用后者。

### A.3 验证之后的纯文档修正

上表复核完成后，主 agent 对 `docs/contracts.md` 做了**纯文档**修正（提交 `5480b6c`）：
更正 §9.12 与 §10 的产物名与生成器名；补充生成器选择约束、`@ts-nocheck` 与编译期防线的
位置关系、产物的可复现条件（固定键序 + 固定 LF）；并新增「已知覆盖边界」一条，
把 §7.3 的类型级盲区写进契约文档。

**该修正对报告有效性的影响：无。** 依据有二：

1. `docs/contracts.md` 不被任何测试或脚本解析（全仓库仅以注释与 docstring 引用其编号），
   故其文字不参与任何判据。
2. 修正后重跑全部门禁仍全绿：

| 门禁 | 修正后结果 |
|---|---|
| `pytest -o addopts="" -rs` | 145 passed / 0 skip |
| `mypy` | 36 文件 0 错 |
| `ruff check` / `ruff format --check` | All checks passed / 48 files already formatted |
| `gen_openapi.py --check` | 退出 0 |
| `verify_baseline.py --phase 5` | 通过（Phase 5 预期状态已达成） |
| `verify_bindings` / `verify_config` / `verify_version` | 均退出 0 |

因此 §1–§13 的判定适用于修正后的 L1 tip。

### A.4 验收对象与最终 tip 的对应

| 项 | 值 |
|---|---|
| 被检 tip（§1–§13 的全部证据来源） | `b40f01b`（工作树干净，158 文件基线） |
| §3.4 引用的行号 | `docs/contracts.md` §9.12 第 312 行 / §10 第 327 行（修正后 §10 位移至第 331 行，缺陷文字已消除） |
| 打 tag 时的 L1 tip | `5480b6c`（= 被检 tip + 纯文档修正） |

### A.5 总判定复核

**与验收官一致：通过。** G5.1 通过；G5.2 通过（本地门禁集合等价替代 CI，字段名与结构变化必红）。
§7.3 披露的「字段类型级漂移」窄盲区保留为未关闭项，其加固方向已写入 `docs/contracts.md` §9.12
「已知覆盖边界」，建议在 Phase 6 建 CI 时一并落地。
