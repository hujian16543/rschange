"""请求与响应模型（pydantic）。

字段描述直接影响 OpenAPI 质量：Phase 5 的前端 TypeScript 类型由 OpenAPI
自动生成，故每个字段都应当带 `Field(description=...)`，响应模型应当声明
`json_schema_extra` 示例。漏写描述不报错，但会以「前端类型没有注释」的形式
在 Phase 5 付出代价。

响应字段是**跨阶段契约**：Phase 3 冻结后写入 `docs/contracts.md`，
变更须走契约变更流程。
"""
