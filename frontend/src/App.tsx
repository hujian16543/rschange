/**
 * 应用根组件。
 *
 * Phase 4 的 T4.1 只负责工程骨架与契约层（类型 + API 客户端）；界面在 T4.2 按
 * `features/detection/` 的目录骨架重建。此处保持最小可运行形态，使 `vite build`
 * 能产出真实产物以支撑 G4.2 的体积核验。
 */
export default function App() {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-gray-100">
      <h1 className="text-lg font-semibold text-gray-800">遥感变化检测平台</h1>
      <p className="text-sm text-gray-500">前端骨架已就绪，界面迁移见 T4.2。</p>
    </div>
  )
}
