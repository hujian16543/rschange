/**
 * 应用根组件。
 *
 * 只做两件事：声明页面级的语言/标题语义，并把功能页摆进来。业务状态全部在
 * `features/detection/DetectionPage` 里——旧前端把状态、布局、业务混在
 * `App.tsx` 52 行里，任何功能改动都要动根组件，分层重构正是要切断这条耦合。
 *
 * Phase 4 的 T4.1 曾把此处留成最小可运行形态以产出真实构建产物支撑 G4.2 的
 * 体积核验；T4.2 按其占位注释的指向完成界面迁移。
 */

import { DetectionPage } from '@/features/detection'

export default function App() {
  return <DetectionPage />
}
