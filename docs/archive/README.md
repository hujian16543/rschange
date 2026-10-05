# 重构过程文档归档

> 本目录归档 rschange 重构（Phase 1–7）的**过程决策文档**，供回溯「某一阶段为什么这样拆、按什么顺序做、由谁做」。
>
> **这些文档是历史记录，不是规范。** 它们描述的分支模型、派单方式与目录结构在收口（`v1.0.0`）时已部分被淘汰；一切以仓库当前状态与 `docs/ARCHITECTURE.md` / `docs/DEVELOPMENT.md` / `docs/CONTRIBUTING.md` 为准。

## 文件索引

| 归档文件 | 原文件名 | 内容 |
|---|---|---|
| [`refactor-plan.md`](refactor-plan.md) | `Remote_Sensing_重构方案.md` | 总方案：目标架构、七阶段拆解、每阶段的判定与出口门、跨阶段接口冻结清单。 |
| [`migration-map.md`](migration-map.md) | `Remote_Sensing_迁移映射与阶段拆解.md` | 旧仓库 → 新仓库的**文件级与命令级**对照表，以及阶段间依赖顺序。 |
| [`execution-handbook.md`](execution-handbook.md) | `Remote_Sensing_执行手册_分支与派单.md` | 执行手册：三档分支模式（完整 / 精简 / 最简）、每个任务的派单说明与验收要求。 |

## 阅读前须知（三条）

1. **分支模型的现状差异**：手册 §1.1 / §2.2 原文要求「L2 任务分支合入即删」。本仓库实际改为**分支一律保留不删**（回退粒度最细，且引用清单是 `.git` 目录损坏事故恢复的依据，见 `docs/verification/phase-6.md` 附录 A.3）。现行约定以 `docs/CONTRIBUTING.md` §1 为准。
2. **含作者本机绝对路径**：三份文档在撰写时以作者开发机为坐标系，正文中出现形如 `C:/Users/<user>/...` 或 `C:\Users\<user>\...` 的路径共 13 处（`refactor-plan.md` 10 处、`execution-handbook.md` 2 处、`migration-map.md` 1 处）。这些路径**不构成**任何可移植性要求；仓库的可移植性约束是「产品代码与配置不得出现机器相关绝对路径」，由 `backend/src/rschange/tests/test_architecture.py` 的 `test_backend_has_no_machine_local_paths`（G3.5）守护。归档时**未**改动原文，以保留决策留痕。
3. **文档分类编号的现状差异**：方案原文未预见「文档分册（`docs/` 下 algorithm / contracts / ARCHITECTURE / DEVELOPMENT / MIGRATION / verification）」，以 `docs/` 现存的六类文档为准。
