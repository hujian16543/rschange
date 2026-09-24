/**
 * 通用按钮原语。
 *
 * 与业务无关：不认识 `File`，也不认识「检测」这件事，只负责样式档位与
 * 可用性语义。业务侧（`DetectionButton`）负责把领域状态映射成本组件的 props。
 *
 * 无障碍约定：
 *
 * * 始终渲染 `<button type="button">`，不提供 `div` 变体——带 `onClick` 的
 *   `<div>` 键盘不可达，且没有隐式按钮角色。
 * * `loading` 时置 `aria-busy="true"` 并把原生 `disabled` 一起打开：原生
 *   `disabled` 保证鼠标点不动，`aria-busy` 让读屏知道是「忙」而不是「不可用」。
 * * 焦点环用 `focus-visible:ring-*`，只在键盘导航时出现，鼠标点击不弹环。
 */

import type { ButtonHTMLAttributes, ReactNode } from 'react'

import { Spinner } from '@/components/ui/Spinner'

/** 视觉档位。`primary` 用于主操作，`secondary` 用于次级操作，`ghost` 用于弱操作。 */
const VARIANT_CLASS = {
  primary:
    'bg-accent text-accent-fg hover:bg-accent-strong active:bg-accent-strong shadow-panel',
  secondary:
    'bg-surface text-text-secondary border border-border hover:bg-surface-raised hover:border-border-strong',
  ghost:
    'bg-transparent text-text-secondary hover:bg-surface-raised hover:text-text-primary',
} as const

export type ButtonVariant = keyof typeof VARIANT_CLASS

/** 尺寸档位到内边距/字号的映射。 */
const SIZE_CLASS = {
  sm: 'px-2.5 py-1 text-caption gap-1',
  md: 'px-3 py-1.5 text-body gap-1.5',
  lg: 'px-4 py-2.5 text-body gap-2',
} as const

export type ButtonSize = keyof typeof SIZE_CLASS

/**
 * 继承原生按钮属性，使调用方可以传 `aria-*`、`title`、`data-*` 等透传属性。
 *
 * 去掉 `type`：本组件固定 `type="button"`，不允许调用方改成 `submit`
 * 意外触发表单提交，故从可传属性里排除。
 */
export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type'> {
  /** 视觉档位，默认 `primary`。 */
  variant?: ButtonVariant
  /** 尺寸档位，默认 `md`。 */
  size?: ButtonSize
  /**
   * 是否处于进行中状态。为 `true` 时按钮不可点、前置旋转图标，
   * 并把 `aria-busy` 置真。
   */
  loading?: boolean
  /** 进行中时替换的文案；不传则沿用 `children`。 */
  loadingText?: string
  /** 前置图标；`loading` 时被旋转图标替换。 */
  icon?: ReactNode
  /** 按钮内容。 */
  children: ReactNode
}

/**
 * 通用按钮。
 *
 * `disabled` 与 `loading` 任一为真即不可交互；两者对读屏的语义不同，
 * 故分别映射到 `disabled`/`aria-disabled` 与 `aria-busy`。
 */
export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  loadingText,
  icon,
  disabled = false,
  className = '',
  children,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading

  return (
    <button
      type="button"
      disabled={isDisabled}
      aria-busy={loading ? true : undefined}
      aria-disabled={isDisabled ? true : undefined}
      className={[
        'inline-flex items-center justify-center rounded-control font-medium',
        'transition-colors select-none',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1',
        'disabled:cursor-not-allowed disabled:opacity-50',
        VARIANT_CLASS[variant],
        SIZE_CLASS[size],
        className,
      ].join(' ')}
      {...rest}
    >
      {loading ? <Spinner size="sm" /> : icon}
      {loading && loadingText !== undefined ? loadingText : children}
    </button>
  )
}
