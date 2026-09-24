/**
 * 「标签 — 数值」行的展示原语。
 *
 * 结果统计、检测元信息都用这个形状。`emphasis` 控制数值是否高亮，使调用方不必
 * 自己拼颜色类；数值固定用等宽数字（`tabular-nums`），多行对齐时小数点才不跳。
 */

import type { ReactNode } from 'react'

export interface StatRowProps {
  /** 左侧标签。 */
  label: string
  /** 右侧数值。 */
  value: ReactNode
  /**
   * 数值强调档位。
   *
   * * `none`：常规文字色
   * * `change`：变化区域红，用于变化面积/变化率这类核心指标
   * * `primary`：主色蓝，用于算法名等次要强调
   */
  emphasis?: 'none' | 'change' | 'primary'
  /** 悬浮补充说明，如换算前的原始值。 */
  hint?: string
}

const VALUE_CLASS = {
  none: 'text-text-primary',
  change: 'text-change font-semibold',
  primary: 'text-accent font-medium',
} as const

/** 单条统计行。 */
export function StatRow({ label, value, emphasis = 'none', hint }: StatRowProps) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 text-text-muted" title={hint}>
        {label}
      </dt>
      <dd className={`text-right tabular-nums ${VALUE_CLASS[emphasis]}`} title={hint}>
        {value}
      </dd>
    </div>
  )
}

export interface StatListProps {
  /** 一组 `StatRow`。 */
  children: ReactNode
  /** 追加的类名。 */
  className?: string
}

/**
 * 统计行容器。
 *
 * 用 `<dl>` 包裹而非一组 `<div>`：`<dl>` 让「标签 → 数值」的配对关系进入
 * 无障碍树，读屏能读出「变化面积 72.09 公顷」这一整体，而不是两个孤立文本。
 */
export function StatList({ children, className = '' }: StatListProps) {
  return (
    <dl className={`space-y-1.5 text-body ${className}`}>
      {children}
    </dl>
  )
}
