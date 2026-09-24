/**
 * 检测失败提示。
 *
 * 契约依据（§9.4/§9.5）：后端错误体是 `{detail, code}`，`code` 才是机器可读的
 * 分支依据。本组件**不做**文案匹配，只消费 `describeError` 归一化后的结构，
 * 因此后端改措辞不会影响前端分支。
 *
 * 与旧前端的差异：旧版是一段 `{error}` 文本（`error` 已被压成 `string`），
 * 现在错误按「现象 + 建议动作」两段展示，并给出后端原始 `detail` 供取证。
 */

import { useCallback, useState } from 'react'

import { Button } from '@/components/ui'
import { describeError } from '@/features/detection/errors'

export interface ErrorAlertProps {
  /** 原始异常（hook 的 `error`，类型为 `unknown`）。 */
  error: unknown
  /** 用户点击「重试」时调用；不传则不渲染重试按钮。 */
  onRetry?: () => void
}

/**
 * 错误提示框。
 *
 * 用 `role="alert"` 让读屏立即播报（隐式 `aria-live="assertive"`）——检测失败是
 * 用户必须立刻知晓的中断性事件。视觉上用 `danger` 语义色，与结果区的 `change`
 * 红色区分：前者是「操作失败」，后者是「变化区域」。
 */
export function ErrorAlert({ error, onRetry }: ErrorAlertProps) {
  /** 后端原始 `detail` 的展开状态。默认折叠，避免技术细节压过可读建议。 */
  const [showDetail, setShowDetail] = useState(false)

  const toggleDetail = useCallback((): void => {
    setShowDetail((previous) => !previous)
  }, [])

  const presentation = describeError(error)
  if (presentation === null) return null

  /** 原始文案：`Error` 才有 `message`，其余类型不展示详情按钮。 */
  const rawDetail = error instanceof Error ? error.message : null

  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-control border border-danger-border bg-danger-muted px-3 py-2"
    >
      <AlertGlyph />

      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-body font-medium text-danger-strong">{presentation.title}</p>
        <p className="text-caption text-text-secondary">{presentation.advice}</p>

        {rawDetail !== null && (
          <>
            <button
              type="button"
              onClick={toggleDetail}
              aria-expanded={showDetail}
              className="text-caption text-text-muted underline underline-offset-2 hover:text-text-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger"
            >
              {showDetail ? '收起技术细节' : '查看技术细节'}
            </button>
            {showDetail && (
              <p className="break-all rounded-control bg-surface px-2 py-1 font-mono text-caption text-text-muted">
                {rawDetail}
              </p>
            )}
          </>
        )}

        {onRetry !== undefined && presentation.retryable && (
          <Button size="sm" variant="secondary" onClick={onRetry}>
            重试
          </Button>
        )}
      </div>
    </div>
  )
}

/** 警示图标。 */
function AlertGlyph() {
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="mt-0.5 shrink-0 text-danger"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" />
      <path d="M12 8v4" />
      <path d="M12 16h.01" />
    </svg>
  )
}
