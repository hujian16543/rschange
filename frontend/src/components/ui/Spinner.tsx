/**
 * 加载指示器。
 *
 * 单独抽成组件而非内联 `<svg>`：`Button` 的 loading 态与结果区的加载占位都要
 * 用它，且尺寸/语义属性只应在一个地方定义。
 */

/** 尺寸档位到图标像素值的映射。 */
const SIZE_PX = {
  sm: 14,
  md: 18,
  lg: 24,
} as const

export type SpinnerSize = keyof typeof SIZE_PX

export interface SpinnerProps {
  /** 图标边长档位，默认 `md`。 */
  size?: SpinnerSize
  /**
   * 无障碍名称。默认 `null` 表示装饰性图标（`aria-hidden`），适用于按钮内
   * 已由按钮文案表达进度的场景；独立使用时应传入可读文案。
   */
  label?: string | null
  /** 追加的类名，通常用于调色（如 `text-accent-fg`）。 */
  className?: string
}

/**
 * 旋转等待图标。
 *
 * 键盘/读屏可见性：当 `label` 为 `null` 时标 `aria-hidden`，避免读屏在每个
 * 按钮里重复念「加载中」；传入 `label` 时改用 `role="status"`，由该角色隐式
 * 承载 `aria-live="polite"`，进度变化会被播报。
 */
export function Spinner({ size = 'md', label = null, className = '' }: SpinnerProps) {
  const px = SIZE_PX[size]
  const decorative = label === null

  return (
    <svg
      className={`shrink-0 animate-spin ${className}`}
      width={px}
      height={px}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={decorative ? undefined : 'status'}
      aria-hidden={decorative ? true : undefined}
      aria-label={decorative ? undefined : label}
    >
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  )
}
