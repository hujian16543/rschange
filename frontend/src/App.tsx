/**
 * 应用根组件。
 *
 * 做三件事：声明页面级的语言/标题语义、把功能页摆进布局、并给它套一层错误
 * 边界。业务状态全部在 `features/detection/DetectionPage` 里——旧前端把状态、
 * 布局、业务混在 `App.tsx` 52 行里，任何功能改动都要动根组件，分层重构正是
 * 要切断这条耦合。
 *
 * 边界挂在**壳层**而非功能内部：功能页自己出错时，包在它外面的边界才有机会
 * 接管；放在 `DetectionPage` 内部则边界与被保护内容是同一棵子树，一错俱错。
 * 今后若有第二个功能页，同一层再挂一个边界即可，互不牵连。
 *
 * Phase 4 的 T4.1 曾把此处留成最小可运行形态以产出真实构建产物支撑 G4.2 的
 * 体积核验；T4.2 按其占位注释的指向完成界面迁移；T4.4 补上错误边界。
 */

import { ErrorBoundary } from '@/components/ui'
import { DetectionPage } from '@/features/detection'

export default function App() {
  return (
    <ErrorBoundary>
      <DetectionPage />
    </ErrorBoundary>
  )
}
