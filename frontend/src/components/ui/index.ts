/**
 * 通用 UI 原语出口。
 *
 * 集中导出使业务组件只依赖 `@/components/ui` 一个路径，后续拆分/改名不影响
 * 调用方。本目录内所有组件都是**展示型**：不认识检测领域类型，也不知道
 * HTTP 的存在。
 */

export { Button } from '@/components/ui/Button'
export type { ButtonProps, ButtonSize, ButtonVariant } from '@/components/ui/Button'

export { Card } from '@/components/ui/Card'
export type { CardProps } from '@/components/ui/Card'

export { ErrorBoundary } from '@/components/ui/ErrorBoundary'
export type { DefaultFallbackProps, ErrorBoundaryProps } from '@/components/ui/ErrorBoundary'

export { Skeleton } from '@/components/ui/Skeleton'
export type { SkeletonProps } from '@/components/ui/Skeleton'

export { Spinner } from '@/components/ui/Spinner'
export type { SpinnerProps, SpinnerSize } from '@/components/ui/Spinner'

export { StatList, StatRow } from '@/components/ui/StatRow'
export type { StatListProps, StatRowProps } from '@/components/ui/StatRow'
