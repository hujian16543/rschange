/**
 * 变化检测功能出口。
 *
 * 应用层只从此处导入，不深入 `components/` 或 `hooks/` 子目录——
 * 功能内部的文件组织可以自由调整而不影响外部。
 */

export { DetectionPage } from '@/features/detection/DetectionPage'

export { DetectionButton } from '@/features/detection/components/DetectionButton'
export type { DetectionButtonProps } from '@/features/detection/components/DetectionButton'

export { ErrorAlert } from '@/features/detection/components/ErrorAlert'
export type { ErrorAlertProps } from '@/features/detection/components/ErrorAlert'

export { ResultPanel } from '@/features/detection/components/ResultPanel'
export type { ResultPanelProps } from '@/features/detection/components/ResultPanel'

export { UploadPanel } from '@/features/detection/components/UploadPanel'
export type { UploadPanelProps } from '@/features/detection/components/UploadPanel'

export { useDetection } from '@/features/detection/hooks/useDetection'
export type { DetectionStatus, UseDetectionResult } from '@/features/detection/hooks/useDetection'

export { describeError } from '@/features/detection/errors'
export type { ErrorPresentation } from '@/features/detection/errors'

export {
  formatArea,
  formatAreaExact,
  formatInteger,
  formatPixelArea,
  formatRate,
  formatThreshold,
} from '@/features/detection/format'
