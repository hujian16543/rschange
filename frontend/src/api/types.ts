/**
 * 契约类型的唯一入口。
 *
 * 这两个别名**不是手写类型定义**，而是生成产物的转发：字段集、可空性与字段类型
 * 全部由 `./generated/data-contracts.ts` 决定，此处无法与之漂移——后端若重命名
 * 或删除了 schema，这里在编译期即报错。
 *
 * 为什么需要这一层：生成类型经 `import ... from './generated/data-contracts'`
 * 取用，直接在八个调用点重复长路径会让「契约类型叫什么」散落各处。转发层把命名
 * 收在一处，同时保持「没有任何手写字段」这一性质。
 *
 * 契约来源：`docs/api/openapi.json` ← `backend/src/rschange/api/schemas/detection.py`
 * 重新生成：`bash scripts/gen-api-types.sh`（或 `pwsh scripts/gen-api-types.ps1`）
 *
 * 注意生成类型与旧手写类型的两处语义差异——它们都是**契约的真实形态**，
 * 不是生成器的缺陷：
 *
 * 1. `geojson` / `image_*_url` / `image_corners` 在 schema 中带默认值，因此是
 *    **可选**（`?`）而非仅可空。消费方必须同时处理 `undefined` 与 `null`。
 *    旧手写类型声称它们必填，掩盖了这一点。
 * 2. `image_corners` 由 `LonLat[]`（定长元组 `[number, number]`）退化为
 *    `number[][]`：OpenAPI 表达不了定长元组，后端 schema 只有
 *    `list[list[float]]`。代价是解构出的元素在 `noUncheckedIndexedAccess` 下
 *    变成 `number | undefined`，消费方需自行判空。这是 Phase 5 明确接受的取舍。
 */

import type { DetectionResponse, ErrorResponse } from './generated/data-contracts'

export type { DetectionResponse, ErrorResponse }

/**
 * 编译期契约断言：`status` 必须**不存在**于成功响应中。
 *
 * 这不是冗余。删除一个字段比新增一个字段更容易被无声地回退——`v0.5.0` 的契约
 * 收缩（13 → 12 字段）若在后续阶段被误恢复，运行时不会有任何报错，前端只会
 * 多读到一个人畜无害的 `"success"`，而契约文档与实现就此分叉。
 *
 * 机制：`@ts-expect-error` 只在**确实发生错误**时被消费。`status` 不存在时，
 * 索引访问报错、指令被消费，编译通过；一旦 `status` 回到 schema 里，该行不再
 * 报错，指令变成「未使用」——`tsc` 随即失败。断言因此是自校验的：它无法在
 * 条件失效后继续通过。
 *
 * **上面那句 `import type` 是本断言成立的前提。** 首版只写了
 * `export type { DetectionResponse } from '...'`——那是纯转发，被转发的名字
 * **不在本文件作用域内**，于是 `DetectionResponse['status']` 报的是「找不到名字」
 * 这一恒真错误，`@ts-expect-error` 一直在消费它。断言看着通过，实则永不生效。
 * 用探针（把 `status` 加回生成文件后重跑 `tsc`）才发现：本该报错的场景下
 * `tsc` 依然退出 0。**没有反向验证的断言就是装饰。**
 *
 * `tests/contract/` 从 Python 侧覆盖同一判据，两者一在编译期、一在测试期。
 */
// @ts-expect-error status 已于 v0.5.0 从契约移除；此指令若报「未使用」即表示它被加了回来
export type _StatusMustBeAbsent = DetectionResponse['status']
