# Phase 4 验收报告 · 前端工程化

> 独立验收官出具。证据来自真实命令输出、逐行源码核对与亲手变异实验，未作人工修饰。
> 本报告**只读**被测代码；唯一写入的文件即本文件（`docs/verification/phase-4.md`）。
> **写操作如实披露**：为核验严格选项生效，新建并删除过一个探针文件 `frontend/src/__probe.ts`；为核验测试判别力，对两个源文件做过变异并**完整还原**（哈希前后一致，见 §4.5）。除此之外未改动仓库内任何其他文件。
> **只读 git 命令清单**：`log`、`diff`、`branch`、`rev-parse`、`rev-list`、`cat-file`、`hash-object`、`write-tree`、`status`、`reflog`、`tag`。**禁止**一切写操作类 git 命令，本次未执行（无 `add`/`commit`/`checkout`/`merge`/`tag`/`reset`）。
> **未执行运行时验证**：G4.3 要求真实浏览器 + 运行中的后端上传 before/after 并核对三图。本环境不具备该条件，故 G4.3 **仅作代码级审查**，不作运行时判定（见 §3.3 与 §7）。

## 1. 验收对象与基准

| 项 | 内容 |
|---|---|
| 上一阶段 tag | `v0.3.1` = `2c9e0a8`（Phase 3.1 preview 掩膜半透明，已验收） |
| 被验集成分支 | `phase-4-frontend`，tip = `2bfb419` |
| L2 任务分支 | `task-4.1-ts-strict` = `535d952`；`task-4.2-restructure` = `da2d33c`；`task-4.4-test-a11y` = `fcb3e37`（3 个，均 `--no-ff` 合入 L1） |
| T4.3 状态 | 已被用户裁定跳过（TanStack Query 未引入），故 L2 数为 3 而非手册所写的 4。**已核实**：`git rev-list --no-merges v0.3.1..phase-4-frontend` = **3**，`git rev-list --merges v0.3.1..phase-4-frontend` = **3** |
| HEAD 实际位置 | `main` = `2c9e0a8`。工作树与索引内容**恰等于** `phase-4-frontend` 的树（见 §2.3） |
| 重构目标 | 旧前端（`C:\Users\Hujian\source\My_Project\Remote_Sensing_Change_Detection\src\frontend\`）重构为分层结构，与 v0.3.0 后端契约（13 字段 + `code` 错误码）严格对齐 |

### 1.1 关于 HEAD 与工作树状态（须显式记录）

验收开始时，仓库 HEAD 停在 `main`（`2c9e0a8`），而非任务书所述的分支 `phase-4-frontend`。工作树与索引中全部 `frontend/` 内容以「新增/删除」形式处于**暂存但未提交**状态。独立核验结论：

- `git write-tree`（索引树）= `18b73504252e9150e085081d5a406a3ef345558d`
- `git rev-parse phase-4-frontend^{tree}` = `18b73504252e9150e085081d5a406a3ef345558d`

**两者哈希完全相同**。即：工作树 + 索引承载的内容与 `phase-4-frontend` 的 L1 交付**逐字节一致**。L1 提交 `2bfb419` 及其三个 L2 在对象库中完整存在（§2.2 已核）。HEAD 指向 `main` 属**检出位置问题**，不影响交付内容，不构成判据不通过。所有门禁命令均在 `frontend/` 下对这份内容执行。

## 2. 差异范围与分支纪律（判据 A）

### 2.1 差异仅限 `frontend/`

```
$ git diff v0.3.1 2bfb419 --name-only | awk -F/ '{print $1}' | sort -u
frontend

$ git diff v0.3.1 2bfb419 --stat | tail -1
 44 files changed, 8179 insertions(+)
```

顶层目录集合**只有** `frontend`。后端（`backend/`）、引擎（`engine/`）、契约（`docs/contracts.md`）、配置（`config/`）均未被 Phase 4 触碰。**判定：通过**。

### 2.2 三个 L2 合并提交均为 `--no-ff`

```
$ for c in f16446e 911c926 2bfb419; do git rev-list --parents -n1 $c; done
f16446e 2c9e0a8 535d952     ← task-4.1 合入（2 父）
911c926 f16446e da2d33c     ← task-4.2 合入（2 父）
2bfb419 911c926 fcb3e37     ← task-4.4 合入（2 父）
```

三个合并提交**均为 2 个父提交**，即 `--no-ff` 合并，保留了任务分支的拓扑。三个 L2 tip 本身（`535d952` / `da2d33c` / `fcb3e37`）经 `git log --format="%h parents:%p"` 核实均为**单父的任务提交**，非合并提交。分支纪律正确。**判定：通过**。

### 2.3 工作树与 L1 一致

```
$ git diff 2bfb419 -- frontend/ --stat
(空)

$ git diff --stat            # 工作树 vs 索引
(空)
```

工作树相对 `2bfb419` 在 `frontend/` 下**零差异**，工作树相对索引**零差异**，无未跟踪残留文件。**判定：通过**。

## 3. 契约对齐（判据 B，核心）

权威定义：`backend/src/rschange/api/schemas/detection.py`（`DetectionResponse`）与 `docs/contracts.md` §9.3。

### 3.1 13 字段逐一对应

`frontend/src/types/detection.ts:25-52` 的 `DetectionResponse` 字段（按声明顺序）：

| # | 前端字段 | 后端字段（`detection.py:55-74`） | 契约 §9.3 | 一致 |
|---|---|---|---|---|
| 1 | `change_pixels: number` | `change_pixels: int` | ✓ | ✓ |
| 2 | `total_pixels: number` | `total_pixels: int` | ✓ | ✓ |
| 3 | `change_rate: number` | `change_rate: float` | ✓ | ✓ |
| 4 | `threshold: number` | `threshold: float` | ✓ | ✓ |
| 5 | `detector: string` | `detector: str` | ✓ | ✓ |
| 6 | `pixel_area_m2: number` | `pixel_area_m2: float` | ✓ | ✓ |
| 7 | `changed_area_m2: number` | `changed_area_m2: float` | ✓ | ✓ |
| 8 | `geojson: string \| null` | `geojson: str \| None` | ✓ | ✓ |
| 9 | `image_before_url: string \| null` | `image_before_url: str \| None` | ✓ | ✓ |
| 10 | `image_after_url: string \| null` | `image_after_url: str \| None` | ✓ | ✓ |
| 11 | `image_diff_url: string \| null` | `image_diff_url: str \| None` | ✓ | ✓ |
| 12 | `image_corners: LonLat[] \| null` | `image_corners: list[list[float]] \| None` | ✓ | ✓ |
| 13 | `status: string` | `status: str` | ✓ | ✓ |

计数 = **13**，名称逐一对应，**无缺失、无多余、无拼写错误**。可空性（`| null`）与后端 `| None` 逐条一致。类型映射：`int`/`float` → `number`，`str` → `string`，`list[list[float]]` → 定长元组数组。**判定：通过**。

### 3.2 `image_corners` 类型与顺序

- 类型：`LonLat[] | null`，其中 `export type LonLat = [number, number]`（`detection.ts:16`）。
- 后端契约（`detection.py:70-73`）：`list[list[float]] | None`，描述「影像四角经纬度，顺序为左上、右上、右下、左下」。
- 顺序的**渲染侧佐证**：`ResultPanel.tsx:261` `const CORNER_LABELS = ['左上', '右上', '右下', '左下'] as const`，按索引与 `corners` 配对（`ResultPanel.tsx:272-281`）；测试 `ResultPanel.test.tsx:244-258` 断言左上角配对为 `117.00000°, 36.14472°`（fixture 第一个角点）。
- **判断**：类型与契约一致。定长元组 `[number, number]` 比 `number[]` **更严格**（长度固定为 2），在 `noUncheckedIndexedAccess` 下解构 `const [lon, lat] = corner` 直接得 `number`。顺序与契约一致。**判定：通过**。

### 3.3 错误契约：按 `code` 分支而非 `detail` 文案

**(a) 前端错误码联合类型 vs 后端异常类 `code` 属性**（逐条比对）：

`frontend/src/types/detection.ts:71-84` 的 `ApiErrorCode` 共 **13** 项；`backend/src/rschange/errors.py` 的异常类 `code` 类属性共 **12** 个（外加 `api/errors.py` 的动态码）：

| 后端来源 | `code` 值 | 前端 `ApiErrorCode` 含 | 一致 |
|---|---|---|---|
| `RsChangeError`（基类，`errors.py:56`） | `internal_error` | ✓ | ✓ |
| `ConfigError`（:80） | `config_error` | ✓ | ✓ |
| `CrsError`（:95） | `crs_error` | ✓ | ✓ |
| `EngineError`（:102） | `engine_error` | ✓ | ✓ |
| `EngineLoadError`（:109） | `engine_load_error` | ✓ | ✓ |
| `InputValidationError`（:173） | `input_validation_error` | ✓ | ✓ |
| `ProcessingError`（:180） | `processing_error` | ✓ | ✓ |
| `RasterReadError`（:121） | `raster_read_error` | ✓ | ✓ |
| `RasterWriteError`（:128） | `raster_write_error` | ✓ | ✓ |
| `UnknownDetectorError`（:162） | `unknown_detector` | ✓ | ✓ |
| `UnsupportedFormatError`（:136） | `unsupported_format` | ✓ | ✓ |
| `UploadTooLargeError`（:150） | `upload_too_large` | ✓ | ✓ |
| `api/errors.py:96`（422 校验） | `request_validation_error` | ✓ | ✓ |
| `api/errors.py:153`（`HTTPException`） | `http_<status>` 动态码 | ✓（字面量 `ImageNotFoundCode = 'http_404'`，`detection.ts:60`） | ✓ |

后端 12 个异常类**一个不漏**地出现在前端联合类型中；补充码 `request_validation_error` 亦已声明。`http_<status>` 为动态码，前端以 `ImageNotFoundCode = 'http_404'`（契约 §9.6 的具体 404 场景）覆盖，其余 `http_*` 由解析层的动态回退处理（见下）。

**(b) 前端是否按 `code` 分支**：

- 解析层：`api/client.ts:145-155` 从响应体解析 `{detail, code}`，`code` 缺失时用 `payload?.code ?? \`http_${response.status}\`` 合成稳定回退码，保证 `ApiError.code` 恒为非空字符串（`:151-153`）。形状不符时（`:159-161`）抛 `invalid_response`。
- 展示层：`features/detection/errors.ts:32-113` 的 `CODE_MESSAGE` 是 **`code` → 文案** 的映射表，`describeError`（`:136-172`）以 `CODE_MESSAGE[error.code]` 查表（`:148`），未命中走 `unknownCodePresentation(error.code)` 兜底（`:156`）。**全程不读 `detail` 做分支**——`detail` 仅作为取证信息经 `rawDetail`（`ErrorAlert.tsx:43`）折叠展示。
- 反向验证：`grep -rn "\.code"` 于旧前端 `src/` **0 命中**，确认旧前端确实未使用 `code`（§6 佐证）。

**(c) 测试判别力佐证**：`ErrorAlert.test.tsx:66-86` 断言四个**不同 `code`** 给出四段**不同**文案（`expect(new Set(titles).size).toBe(4)`），若实现退化为「所有错误同一句通用文案」该用例即红。`useDetection.test.tsx:220,227` 断言异常对象被**原样保留**（`errorName()` 为 `ApiError`）而非压成 `string`。

**判定：通过**。

### 3.4 反向验证：`detector` / `pixel_area_m2` / `changed_area_m2` 真的被渲染

旧前端（`types/detection.ts`）仅 10 字段，缺这三个。新前端在 `ResultPanel.tsx` 的具体渲染语句：

| 字段 | 渲染语句 | 位置 |
|---|---|---|
| `changed_area_m2` | `{formatArea(result.changed_area_m2)}` | `ResultPanel.tsx:155` |
| `changed_area_m2`（原始 m² 提示） | `title={formatAreaExact(result.changed_area_m2)}` | `ResultPanel.tsx:153` |
| `changed_area_m2`（换算解释串） | `= ${formatInteger(result.change_pixels)} 像元 × ${formatPixelArea(result.pixel_area_m2)}` | `ResultPanel.tsx:158` |
| `pixel_area_m2` | `value={formatPixelArea(result.pixel_area_m2)}` | `ResultPanel.tsx:117` |
| `detector` | `value={result.detector}` | `ResultPanel.tsx:123` |

三者**均被真的渲染**，非仅类型声明。测试以**人工核对过的字面量**守护：`ResultPanel.test.tsx:46`（`getByText('cva')`）、`:65`（`getByText('100 m²')`）、`:80`（`getByText('72.09 公顷')`），且 `:50-58`、`:68-73` 断言随字段值变化（防渲染常量）。**判定：通过**。

## 4. 类型严格性（判据 C）

### 4.1 严格选项确实开启

`frontend/tsconfig.app.json:23` `"strict": true`；`:24` `"noUncheckedIndexedAccess": true`。另有 `noUnusedLocals`（:25）、`noUnusedParameters`（:26）、`noFallthroughCasesInSwitch`（:27）、`noImplicitOverride`（:28）。**判定：通过**。

### 4.2 零类型逃逸

```
$ grep -rnE "@ts-ignore|@ts-expect-error|@ts-nocheck|\bas any\b|as unknown as" frontend/src
features/detection/hooks/useDetection.test.tsx:38:// `as unknown as ...` 之类的断言去改造它：…
```

唯一命中位于**注释**（`useDetection.test.tsx:38` 说明为何**不**使用该断言）。`@ts-ignore` / `@ts-expect-error` / `@ts-nocheck` / `as any` / `as unknown as` 于 `src/` 全量**0 命中**。

非空断言 `!`：`grep -rnE "!\.|!\)|!;|\]!"` 于 `src/` 0 命中。反向证据：`UploadPanel.tsx:145-156` 对 `accepted[0]` / `rejections[0]` / `errors[0]` 逐一显式判 `undefined`（并附注释「靠 `!` 或 `as` 绕过是禁止的」）；`ResultPanel.tsx:273` 对 `CORNER_LABELS[index]` 用 `?? \`角点 ${index + 1}\`` 兜底（注释明示**不**用 `!`）；`useDetection.test.tsx:79-91` 用 `??` 与显式 throw 替代非空断言。**判定：通过**。

### 4.3 独立验证严格选项真的生效（探针）

新建 `frontend/src/__probe.ts`：

```ts
export function probeIndex(values: number[]): void {
  const first: number = values[0]
  void first
}
```

```
$ npx tsc -b
src/__probe.ts(5,9): error TS2322: Type 'number | undefined' is not assignable to type 'number'.
  Type 'undefined' is not assignable to type 'number'.
EXIT=2
```

探针**如期报错**，证 `noUncheckedIndexedAccess` 实际生效（而非仅写在配置里）。随后删除探针：

```
$ rm -f src/__probe.ts
$ ls src/__probe.ts
ls: cannot access 'src/__probe.ts': No such file or directory
$ npx tsc -b            # 探针删除后
EXIT=0
```

探针报错原文如上，探针**已删除**，删除后 `tsc -b` 回归 0 错误。**判定：通过**。

## 5. 测试质量（判据 D）

### 5.1 用例数与通过数

```
$ npx vitest run
 ✓ src/features/detection/components/ResultPanel.test.tsx (26 tests)
 ✓ src/features/detection/components/ErrorAlert.test.tsx (16 tests)
 ✓ src/components/ui/ErrorBoundary.test.tsx (11 tests)
 ✓ src/features/detection/components/UploadPanel.test.tsx (32 tests)
 ✓ src/features/detection/hooks/useDetection.test.tsx (12 tests)
 ✓ src/features/detection/DetectionPage.test.tsx (12 tests)
 Test Files  6 passed (6)
      Tests  109 passed (109)
```

按文件：ResultPanel 26、ErrorAlert 16、ErrorBoundary 11、UploadPanel 32、useDetection 12、DetectionPage 12，合计 **109**，全部通过。测试代码 1917 行，非测试源 2176 行，测试/源比约 **0.88**。

### 5.2 永真断言检查

检索 `toBeDefined()` / `toBeTruthy()` / `toBeFalsy()` → **0 命中**。`toBeNull()` / `not.toBeNull()` 命中 5 处，逐条判定：

| 位置 | 上下文 | 判定 |
|---|---|---|
| `ResultPanel.test.tsx:137` `expect(alt).not.toBeNull()` | 同块内已有 `:138 expect(alt).not.toBe('')`，且 `:145-147` 另有精确 alt 断言 | 有强断言支撑 |
| `ResultPanel.test.tsx:250` `expect(row).not.toBeNull()` | 其后 `:251-253` 用 `within(row).getByText('117.00000°, 36.14472°')` 精确核对 | 有强断言支撑 |
| `ResultPanel.test.tsx:292` `expect(list).not.toBeNull()` | 断言 `closest('dl')` 非空，用于证明语义标签；同 `describe` 内无更强断言，但 `dl` 语义本身即弱可断言项 | 单独一句，但断言目标（语义标签存在）本身即该用例的全部意图 |
| `useDetection.test.tsx:206` `expect(call).toBeDefined()` | 其前 `:201` 已断言 `toHaveBeenCalledTimes(1)`，其后 `:207-208` 精确断言 `call?.[0]`/`call?.[1]` | 有强断言支撑 |
| `UploadPanel.test.tsx:231` `expect(input.getAttribute('multiple')).toBeNull()` | 与 `:230 expect(input).not.toBeChecked()` 同块；断言「未设 multiple」本身即判据 | 该用例的核心断言 |

**结论**：无「仅此一句且无支撑」的孤立弱断言。上述 5 处或为强断言的前置守卫，或本身即该用例的判据。**判定：通过**。

### 5.3 期望值是否现算

期望值均为**人工核对过的字面量**，来自 fixture 独立导出的常量，而非从被测结果现算：

- `fixtures.ts:46` `EXAMPLE_AREA_DISPLAY = '72.09 公顷'`；`:49 EXAMPLE_PIXEL_AREA_DISPLAY = '100 m²'`；`:52 EXAMPLE_THRESHOLD_DISPLAY = '5.9168'`；`:55 EXAMPLE_RATE_DISPLAY = '11.00%'`。这些是**字面量常量**，锚定契约 §9.10 的真实值（`changed_area_m2 = 720900 m² = 7209 × 100.0`）。
- 对照**反面模式**：`expect(text).toContain(String(result.changed_area_m2))` 这类现算（渲染结果与格式化函数互相印证）**未出现**。`ResultPanel.test.tsx:122` 的一处形如 `` `= ${EXAMPLE_CHANGE_PIXELS.toLocaleString('en-US')} 像元 × ${EXAMPLE_PIXEL_AREA_DISPLAY}` `` 含构造，但两个分量均为**人工核对的常量**（`EXAMPLE_CHANGE_PIXELS = 7209`），非从 `result` 现算，且该串在组件内由 `formatInteger`/`formatPixelArea` 独立产出——两者若错位仍会红。
- 测试文件头注释（`ResultPanel.test.tsx:9-13`）显式声明该设计原则。

**判定：通过**。

### 5.4 变异测试（判别力的亲手证明）

备份并记录变异前哈希：

```
$ sha256sum useDetection.ts ResultPanel.tsx
165dbd552e22a804f524fd658c32836445b4eeaa789eae5b06e6fe80fef63862  useDetection.ts
59d34e8ccccd106e3a71be2148a3bb4509daddd10ee17be7ab4a79a0044b7ef1  ResultPanel.tsx
$ git hash-object useDetection.ts ResultPanel.tsx
598e7c00e91303f802ff5cf190d866eb21431f81   （useDetection.ts）
dc36fbc82fe95fd59af1a2186335f26f00d5eaa4   （ResultPanel.tsx）
```

**变异 1 —— 竞态守卫恒假**（`useDetection.ts`）：

将两处 `if (runId !== runIdRef.current) return` 分别改为 `if (runId === runIdRef.current) { void 0 }`（守卫恒不生效）。

```
$ npx vitest run
 Test Files  1 failed | 5 passed (6)
      Tests  3 failed | 106 passed (109)
```

**3 个用例变红**，含：
- `竞态：后发起的结果获胜，先返回的旧结果不得覆盖它`（`useDetection.test.tsx:313-314` 断言 `currentStatus()` 为 `loading`、`hasResult()` 为 `no`，实得旧响应已把状态推到 `success`）；
- `竞态：旧请求的失败也不得覆盖后发起请求的成功结果`（`:352` `expected 'error' to be 'success'`）；
- `在途请求被 reset 作废，其响应不得把界面拉回 success`。

**还原校验**：

```
$ cp /tmp/useDetection.bak.ts useDetection.ts
$ sha256sum useDetection.ts
165dbd552e22a804f524fd658c32836445b4eeaa789eae5b06e6fe80fef63862  ← 与变异前一致
$ git hash-object useDetection.ts
598e7c00e91303f802ff5cf190d866eb21431f81  ← 与变异前一致
$ git diff --stat useDetection.ts
(空)
```

**变异 2 —— `changed_area_m2` 渲染错接**（`ResultPanel.tsx`）：

将 `ResultPanel.tsx:155` 的 `{formatArea(result.changed_area_m2)}` 改为 `{formatArea(result.pixel_area_m2)}`（核心指标卡错接单像元面积）。

```
$ npx vitest run
      Tests  6 failed | 103 passed (109)
```

**6 个用例变红**：`渲染 pixel_area_m2`、`pixel_area_m2 随数值变化`、`渲染 changed_area_m2`、`changed_area_m2 的单位换算`、`变化面积保留原始平方米原值`、`统计字段在预览图缺失时仍完整渲染`。

**还原校验**：

```
$ cp /tmp/ResultPanel.bak.tsx ResultPanel.tsx
$ sha256sum ResultPanel.tsx
59d34e8ccccd106e3a71be2148a3bb4509daddd10ee17be7ab4a79a0044b7ef1  ← 与变异前一致
$ git hash-object ResultPanel.tsx
dc36fbc82fe95fd59af1a2186335f26f00d5eaa4  ← 与变异前一致
$ git diff --stat ResultPanel.tsx
(空)
```

**还原后全量复检**：`npx vitest run` → `Test Files 6 passed (6)`、`Tests 109 passed (109)`；`git diff --stat`（工作树 vs 索引）为空。

**结论**：两处关键逻辑均被测试**有效覆盖**（变异必红），且**每一处变异都已完整还原并校验哈希**。**判定：通过**。

## 6. 门禁与产物体积（判据 E）

### 6.1 `npm run check`（G4.1）

```
$ npm run check
> tsc -b --noEmit && oxlint && vitest run
Found 0 warnings and 0 errors.
Finished in 12ms on 31 files with 116 rules using 20 threads.
 Test Files  6 passed (6)
      Tests  109 passed (109)
```

分项：`npx tsc -b` → 0 错误（EXIT=0）；`npx oxlint` → `Found 0 warnings and 0 errors`（31 文件 / 116 规则）；`vitest run` → 109 通过。**全绿且 vitest 确实运行。判定：通过**。

### 6.2 `npm run build` 与 gzip 体积（G4.2）

```
$ npm run build
dist/index.html                   0.41 kB │ gzip:  0.30 kB
dist/assets/index-CWgSjsAg.css   16.38 kB │ gzip:  4.10 kB
dist/assets/index-DrjcCLoG.js   258.90 kB │ gzip: 81.97 kB
✓ built in 113ms
```

独立核算（对 `dist/` 逐文件 `gzip -9` 取字节）：

| 产物 | 原始（字节） | gzip（字节） |
|---|---|---|
| `index.html` | 412 | 316 |
| `assets/index-CWgSjsAg.css` | 16381 | 4119 |
| `assets/index-DrjcCLoG.js` | 258909 | 80633 |
| **合计** | **275702** | **85068** |

总 gzip = 85068 字节 = **83.07 KB** < **300 KB**。JS 单文件 gzip 81.97 KB，CSS 4.10 KB，HTML 0.30 KB，**总积充裕达标**。**判定：通过**。

### 6.3 三图对比（G4.3）—— 未执行运行时验证

**未执行运行时验证**：本环境无真实浏览器 + 运行中的后端，无法上传 before/after 并核对三图的实际像素叠加结果。改为**代码级审查**：

- 三图渲染路径：`ResultPanel.tsx:79-108` 由 `image_before_url` / `image_after_url` / `image_diff_url` 构造三个 `PreviewItem`（`caption` 分别为「前时相」「后时相」「变化检测（红色为变化区域）」），经 `filter(isAvailable)` 后**仅当三个 URL 全部可用**（`previews.length === 3`，`:89`）才渲染三图网格。
- URL 归一化：`api/client.ts:167-169` 的 `imageUrl` 把 `null` **与空串**统一归为「无」（`:168` `url === null || url === '' ? null : url`）；`ResultPanel.tsx:61-63` 的 `isAvailable` 谓词据此过滤，避免空串传入 `<img src="">` 触发浏览器对当前页地址的无意义请求（`:50-59` 注释说明）。
- **可能的证伪点**：本项目 Phase 4 前端**未引入地图库**（`package.json` 无 leaflet/mapbox 等），`image_corners` 仅以文本表格展示（`ResultPanel.tsx:269-284`），不在地图上定位。这与契约「用于地图定位」的表述存在**能力缺口**，但契约未强制前端绘图，且 Phase 4 出口门未要求地图。**记为未关闭项（见 §8），不判 G4.3 不通过**。
- 代码级审查未发现能**证伪**三图对比正确性的实现缺陷：三个 URL 独立取值、独立过滤、无交叉赋值；测试 `ResultPanel.test.tsx:150-159` 断言 `src` 一一对应到响应字段，`变异 2` 证明字段错接会被捕获。

**判定**：**不作运行时判定**（未执行）。代码级审查未发现缺陷，记为「未执行运行时验证」。

## 7. 旧前端问题是否真的被修正（判据 F）

### F.1 硬编码 URL → 相对路径 `/api`

- 旧前端：`api/client.ts` 用 `const BASE = '/api'`，`fetch(\`${BASE}/detect\`)`；全 `src/`（排除 `.svg` 资源）grep `localhost:[0-9]+` / `http://` **0 命中**，`vite.config.ts` 用 dev proxy。
- **如实记录**：任务书称「旧代码里可能写死 host」，实际核查旧前端**已是相对路径 `/api`**，该问题在旧前端**不存在**（无从修正）。此判据的「修正」不成立，但新前端**同样正确**地使用相对路径，未引入退化。
- 新前端：`api/client.ts:19` `const API_BASE = '/api'`，`:136` `fetch(\`${API_BASE}/detect\`, …)`；`vite.config.ts:16-21` 将 `/api` 代理至 `http://localhost:8000`（仅出现在**构建配置**中，非运行期硬编码）。**判定：通过（新代码正确，但此问题旧代码本不存在）**。

### F.2 错误处理只读 `detail` → 解析并使用 `code`

- 旧前端：`api/client.ts` 错误分支 `if (j.detail) msg = String(j.detail)`，`throw new Error(msg)`——**只读 `detail`，不使用 `code`**；`grep -rn "\.code"` 旧 `src/` **0 命中**。旧 `useDetection.ts` 进一步把异常压成 `string`（`setError(e instanceof Error ? e.message : '未知错误')`）。
- 新前端：`api/client.ts:33-45` 定义 `ApiError` 携带 `status` 与 **`code`**；`:143-155` 解析 `{detail, code}` 并抛 `ApiError`；`errors.ts:148` 以 `error.code` 查表分支；`useDetection.ts:49,69` 保留**原始异常对象**（`unknown`）而非压成 `string`。
- **判定：通过**，并有 `ErrorAlert.test.tsx:66-86`、`useDetection.test.tsx:227` 守护。

### F.3 只显示 10 个字段 → 显示 13 个

- 旧前端：`types/detection.ts` 仅 10 字段（`change_pixels`…`status`，无 `detector`/`pixel_area_m2`/`changed_area_m2`）；`components/ResultPanel.tsx` 仅渲染 `change_pixels`、`total_pixels`、`change_rate`、`threshold` 四个统计值 + 三图（旧 `ResultPanel.tsx:32-35`），`geojson` 未被使用。
- 新前端：13 字段齐全（§3.1），`ResultPanel.tsx` 渲染 6 条统计（含 `detector` `:123`、`pixel_area_m2` `:117`）+ 核心指标卡（`changed_area_m2` `:155`）+ GeoJSON 下载（`:214-225`）+ 四角表（`:269-284`）。
- **判定：通过**。

## 8. 可访问性（判据 G）

| 要求 | 证据 | 判定 |
|---|---|---|
| 交互元素为语义标签 | `Button.tsx:9-13` 明示「始终渲染 `<button type="button">`，不提供 `div` 变体」；`ResultPanel.tsx:239`、`ErrorAlert.tsx:58`、`DetectionPage.tsx:67` 均为原生 `<button>`；组件内**无** `onClick` 挂在 `div` 上的用法 | 通过 |
| 图片有非空 `alt` | `ResultPanel.tsx:186` `alt={caption}`（caption 为「前时相」等）；测试 `ResultPanel.test.tsx:128-140` 断言三图全部 `alt` 非 null 且非空串 | 通过 |
| 错误提示 `role="alert"` | `ErrorAlert.tsx:47` `role="alert"`；`UploadPanel.tsx:110` 拒收提示 `role="alert"`；`ErrorBoundary.tsx:107` 降级 UI `role="alert"` | 通过 |
| loading 态有 `disabled` / `aria-busy` | `Button.tsx:87-88` `disabled={isDisabled}` + `aria-busy={loading ? true : undefined}`；`DetectionPage.tsx:96` 传 `loading`；测试 `DetectionPage.test.tsx:131-133` 断言 `toBeDisabled()` + `aria-busy="true"`；`ResultSkeleton.tsx:20-22` `role="status"` + `aria-busy="true"` + 非空 `aria-label` | 通过 |
| 上传控件有可查询 label / `aria-label` | `UploadPanel.tsx:189-195` `inputAria` 含 `aria-label: \`选择${label}（${EXTENSION_HINT}）\`` 与 `aria-describedby`；`:217,235` 应用到 input；`:207` dropzone `aria-labelledby={labelId}`；测试 `DetectionPage.test.tsx:62` 以 `getByLabelText(/选择前时相影像/)` 查询成功 | 通过 |
| focus 样式可见 | `Button.tsx:93` `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent`；`ResultPanel.tsx:242`、`ErrorAlert.tsx:62`、`UploadPanel.tsx:211`、`DetectionPage.tsx:70`、`ErrorBoundary.tsx:119` 均有 `focus-visible:ring-*` | 通过 |

**补充证据**：`StatList` 用 `<dl>` 承载标签-数值配对（`StatRow.tsx:62`），进入无障碍树；`DetectionPage.tsx:57,83` 为 `<main>` / `<aside>` 提供 `aria-label`；`UploadPanel.tsx:91` 用 `<fieldset disabled>` + `<legend>` 统一禁用与分组。**判定：通过**。

## 9. 报告声明与写操作披露（判据 H）

- **写操作如实记录**：① 新建并删除探针 `frontend/src/__probe.ts`（§4.3，已删除，删除后 `tsc -b` 归零）；② 对 `useDetection.ts` 与 `ResultPanel.tsx` 各做一次变异并**完整还原**，两次均以 `sha256sum` + `git hash-object` 校验前后一致、`git diff` 为空（§5.4）。除此之外未修改仓库内任何文件。
- **未声称**「全程未修改任何文件」——已如实列出上述写操作。
- **只读 git 命令**：`log`、`diff`、`branch`、`rev-parse`、`rev-list`、`cat-file`、`hash-object`、`write-tree`、`status`、`reflog`、`tag`。未执行任何写操作类 git 命令。
- **未执行运行时验证**：G4.3 无真实浏览器 + 运行中后端，已明确标注（§1 与 §6.3）。
- 未触碰交付处 `C:\Users\Hujian\source\My_Project\Remote_sensing`（仅**只读**读取旧前端 `Remote_Sensing_Change_Detection/src/frontend/` 作对比，未写入）。

## 10. 门禁逐条结果表

| # | 判据 | 关键证据 | 判定 |
|---|---|---|---|
| G4.1 | `npm run check` 全绿 | `tsc -b` 0 错误、`oxlint` 0 warning/0 error、`vitest` 109 passed | **通过** |
| G4.2 | `npm run build` 产物 < 300 KB gzip | 总 gzip = 85068 字节（83.07 KB） | **通过** |
| G4.3 | 手工上传三图对比正确 | **未执行运行时验证**；代码级审查未发现缺陷（三图独立取值/过滤/无交叉；测试断言 src 一一对应） | **不作运行时判定** |
| A | 差异仅限 `frontend/` | `git diff v0.3.1 2bfb419 --name-only` 顶层目录仅 `frontend` | **通过** |
| A | 3 个 L2 均 `--no-ff` | 三个合并提交均 2 父：`f16446e`/`911c926`/`2bfb419` | **通过** |
| A | 工作树与 L1 一致 | `git diff 2bfb419 -- frontend/` 为空；索引树 = `phase-4-frontend` 树 = `18b7350…` | **通过** |
| B.1 | 13 字段逐一对应 | `detection.ts:25-52` 13 字段 vs `detection.py:55-74` 一一对应 | **通过** |
| B.2 | `image_corners` 类型/顺序 | `LonLat = [number, number]`；`CORNER_LABELS` 左上/右上/右下/左下 | **通过** |
| B.3 | 按 `code` 分支 | 13 码覆盖后端 12 类 + 2 补充码；`errors.ts:148` 查 `code`；旧前端 `.code` 0 命中 | **通过** |
| B.4 | 三新增字段真被渲染 | `ResultPanel.tsx:117,123,153,155,158` | **通过** |
| C.1 | `strict` + `noUncheckedIndexedAccess` 开启 | `tsconfig.app.json:23-24` | **通过** |
| C.2 | 零类型逃逸 | `@ts-ignore`/`as any`/`!` 等 0 命中（唯一命中在注释） | **通过** |
| C.3 | 探针证严格选项生效 | `error TS2322`，探针已删除 | **通过** |
| D.1 | 用例数与通过数 | 109 passed / 6 files（26+16+11+32+12+12） | **通过** |
| D.2 | 无孤立弱断言 | `toBeDefined/Truthy/Falsy` 0 命中；5 处 `toBeNull` 均有支撑 | **通过** |
| D.3 | 期望为人工字面量 | `fixtures.ts:46-55` 字面量常量，非现算 | **通过** |
| D.4 | 变异测试 | 变异 1 红 3 例、变异 2 红 6 例；两处均已还原且哈希一致 | **通过** |
| E | 门禁现场输出 | 见 §6 | **通过** |
| F.1 | 相对路径 `/api` | `client.ts:19`；旧前端本已是 `/api`（如实记录） | **通过** |
| F.2 | 解析并使用 `code` | `ApiError.code`；`errors.ts:148` | **通过** |
| F.3 | 显示 13 字段 | 见 B.4 | **通过** |
| G | 可访问性 6 项 | 见 §8 | **通过** |
| H | 报告不过度声明 | 写操作已披露；未声称未修改文件 | **通过** |

## 11. 未关闭项（即使不阻断）

1. **G4.3 未执行运行时验证**：无真实浏览器 + 运行中后端，三图对比的**实际像素结果**未被验证。代码级审查未发现缺陷，但「存在仅运行时才暴露的问题」不能排除。**建议**：在具备浏览器与后端的环境补做一次手工上传（before/after 各一份真实夹具），核对三图与 `changed_area_m2 = 720900 m²`。
2. **`image_corners` 无地图定位能力**：契约 §9.3 表述为「用于地图定位」，新前端仅以文本表格展示四角经纬度（`ResultPanel.tsx:269-284`），未引入地图库。契约未强制、Phase 4 出口门未要求，**不构成不通过**，但属与契约表述的能力缺口，宜在后续阶段明确「是否需要在图上定位」。
3. **HEAD 检出位置非 `phase-4-frontend`**：验收时 HEAD 停在 `main`，`frontend/` 内容以暂存态存在。内容经树哈希确认与 L1 逐字节一致（§1.1），不影响交付，但**属仓库卫生瑕疵**，建议投放前将 `phase-4-frontend` 正式检出/合入并落 tag。
4. **F.1 前提偏差**：任务书称旧前端「硬编码 host」，实测旧前端已是相对路径 `/api`。新前端行为正确，但该「旧问题」实不存在，记录以免后续误引。
5. **`status` 字段恒为 `"success"`**：前后端均保留该无信息量字段（契约 `detection.py:17-18` 明示为契约收缩的遗留），非 Phase 4 引入，属既有契约债务。

## 12. 总判定

**通过。**

Phase 4（前端工程化）在「契约对齐（13 字段 + `code` 错误分支）、类型严格性（`strict` + `noUncheckedIndexedAccess`，探针实证生效，零逃逸）、测试判别力（109 用例，两处变异必红且还原无恙）、门禁全绿（`npm run check`）、产物体积（总 gzip 83.07 KB < 300 KB）、差异范围纪律（仅 `frontend/`，3 个 `--no-ff` L2）、旧前端三处问题修正、可访问性六项」上均达成出口门要求。

唯一未达成运行时验证的 G4.3 已在报告中显式标注为「未执行」，并已作代码级审查——该判据**既不判通过也不判不通过**，作为未关闭项移交后续阶段补做。除此之外，无任何判据不通过。
