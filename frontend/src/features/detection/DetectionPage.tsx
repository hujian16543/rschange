/**
 * 变化检测功能页。
 *
 * 承载该功能的全部状态与编排：上传态、检测态、结果与错误。应用根组件
 * （`App.tsx`）只负责把它摆进布局，不感知任何业务细节——这样功能可被整体
 * 复用到别的壳里，也与旧前端「业务逻辑写在 `App.tsx`」的做法分道扬镳。
 *
 * 布局：左侧结果区（滚动），右侧固定宽度侧边栏（输入 + 操作 + 错误）。
 */

import { useCallback, useState } from 'react'

import { Card } from '@/components/ui'
import { DetectionButton } from '@/features/detection/components/DetectionButton'
import { ErrorAlert } from '@/features/detection/components/ErrorAlert'
import { ResultPanel } from '@/features/detection/components/ResultPanel'
import { ResultSkeleton } from '@/features/detection/components/ResultSkeleton'
import { UploadPanel } from '@/features/detection/components/UploadPanel'
import { useDetection } from '@/features/detection/hooks/useDetection'

/**
 * 变化检测主界面。
 *
 * 侧边栏固定 `--spacing-sidebar`（`w-sidebar`）宽度：结果区图片需要稳定的
 * 可用宽度，若两侧都用弹性宽度，预览图会随窗口尺寸跳动。
 */
export function DetectionPage() {
  const [before, setBefore] = useState<File | null>(null)
  const [after, setAfter] = useState<File | null>(null)
  /** 选文件阶段的本地校验提示（扩展名/体积），与 API 错误分开管。 */
  const [rejectMessage, setRejectMessage] = useState<string | null>(null)

  const { status, result, error, detect, reset } = useDetection()

  const ready = before !== null && after !== null
  const loading = status === 'loading'

  /**
   * 触发检测。
   *
   * `ready` 判空后仍需在闭包内再判一次：`DetectionButton` 已用 `disabled`
   * 拦住未齐全的情况，但类型系统不知道这个因果关系，且 disabled 只约束 UI
   * 层——把非空收窄写在真正使用变量处，才不会在重构时悄悄失守。
   */
  const handleDetect = useCallback((): void => {
    if (before === null || after === null) return
    void detect(before, after)
  }, [before, after, detect])

  const handleReset = useCallback((): void => {
    reset()
  }, [reset])

  return (
    <div className="flex h-full w-full bg-surface-sunken">
      {/* 主区域：结果展示 */}
      <main className="flex-1 overflow-y-auto p-panel" aria-label="检测结果">
        <div className="mx-auto max-w-4xl">
          {status === 'idle' && <EmptyState />}

          {status === 'loading' && <LoadingState />}

          {status === 'success' && result !== null && (
            <>
              <ResultPanel result={result} />
              <div className="mt-section">
                <button
                  type="button"
                  onClick={handleReset}
                  className="rounded-control border border-border bg-surface px-3 py-1.5 text-body text-text-secondary transition-colors hover:border-border-strong hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  重新检测
                </button>
              </div>
            </>
          )}
        </div>
      </main>

      {/* 侧边栏：输入与操作 */}
      <aside
        className="w-sidebar shrink-0 overflow-y-auto border-l border-border bg-surface p-4 shadow-sidebar"
        aria-label="检测输入"
      >
        <div className="space-y-section">
          <UploadPanel
            before={before}
            after={after}
            onBeforeChange={setBefore}
            onAfterChange={setAfter}
            onReject={setRejectMessage}
            rejectMessage={rejectMessage}
            disabled={loading}
          />

          <DetectionButton ready={ready} loading={loading} onClick={handleDetect} />

          {status === 'error' && (
            <ErrorAlert error={error} onRetry={ready ? handleDetect : undefined} />
          )}
        </div>
      </aside>
    </div>
  )
}

/** 空态：说明这个页面是做什么的，并指出第一步操作。 */
function EmptyState() {
  return (
    <Card title="遥感变化检测" headingLevel={1}>
      <p className="text-body text-text-secondary">
        在右侧依次选择同一区域的前时相与后时相影像，然后点击「开始检测」。
      </p>
      <ul className="mt-section list-inside list-disc space-y-1 text-caption text-text-muted">
        <li>支持 .tif / .tiff / .png，单文件不超过 500 MB</li>
        <li>两期影像需具有一致的尺寸与坐标系</li>
        <li>结果中的变化区域将以红色叠加显示，并可导出 GeoJSON</li>
      </ul>
    </Card>
  )
}

/**
 * 加载态占位。
 *
 * 面板标题说明阶段，正文骨架块（`ResultSkeleton`）提前占住结果区高度，
 * 避免结果返回时页面大幅跳动。
 */
function LoadingState() {
  return (
    <Card title="正在检测" headingLevel={1}>
      <p className="text-body text-text-secondary">
        正在读取影像并计算变化区域，请稍候…
      </p>
      <div className="mt-section">
        <ResultSkeleton />
      </div>
    </Card>
  )
}
