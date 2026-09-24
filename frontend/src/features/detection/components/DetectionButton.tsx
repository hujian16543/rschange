/**
 * 检测触发按钮。
 *
 * 薄封装：把领域的「两期是否齐全」「是否在跑」映射到 `Button` 原语的
 * `disabled` / `loading`，本身不含样式细节。
 *
 * 禁用理由必须说清：仅置灰而不解释，用户会反复点击。这里把原因作为可见副文案
 * 渲染，并用 `aria-describedby` 挂到按钮上，读屏聚焦时一并播报。
 */

import { useId } from 'react'

import { Button } from '@/components/ui'

export interface DetectionButtonProps {
  /** 是否两期影像都已选齐。未齐时禁用。 */
  ready: boolean
  /** 是否正在检测。进行中时禁用并显示进度态。 */
  loading: boolean
  /** 点击触发检测。 */
  onClick: () => void
}

/**
 * 「开始检测」按钮。
 *
 * 禁用条件：未选齐两期影像（`ready === false`）或正在检测（`loading`）。
 * 前者是可修复的前置条件（提示去选文件），后者是进行中（提示等待），
 * 故两者的副文案不同。
 */
export function DetectionButton({ ready, loading, onClick }: DetectionButtonProps) {
  const hintId = useId()

  /** 当前禁用原因；空串表示可点击，不渲染副文案。 */
  const disabledReason = loading
    ? '正在检测，请等待本次结果返回'
    : ready
      ? ''
      : '请先选择前时相与后时相两张影像'

  return (
    <div className="space-y-1.5">
      <Button
        variant="primary"
        size="lg"
        className="w-full"
        disabled={!ready}
        loading={loading}
        loadingText="检测中…"
        onClick={onClick}
        aria-describedby={disabledReason === '' ? undefined : hintId}
      >
        开始检测
      </Button>

      {disabledReason !== '' && (
        <p id={hintId} className="text-caption text-text-muted">
          {disabledReason}
        </p>
      )}
    </div>
  )
}
