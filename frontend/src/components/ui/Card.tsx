/**
 * 面板容器原语。
 *
 * 侧边栏与结果区都要「白底 + 圆角 + 细边框 + 可选标题」这套外壳，抽成组件
 * 以免两处各写一遍 Tailwind 串而慢慢漂移。
 */

import type { ReactNode } from 'react'

/** 层级到标签名的映射。查表比三元链更容易在扩展时保持穷尽。 */
const HEADING_TAG = {
  1: 'h1',
  2: 'h2',
  3: 'h3',
} as const

export interface CardProps {
  /** 面板标题；不传则只渲染内容区。 */
  title?: ReactNode
  /**
   * 标题右侧的附加内容（按钮、徽标等）。
   * 仅在传了 `title` 时有意义。
   */
  titleAction?: ReactNode
  /**
   * 标题关联的层级。默认 `h2`——面板通常是页面 `<h1>` 下的一级分区。
   *
   * 允许 `1` 是为了「整页只有一个面板」的场景（如空态、加载态），此时面板标题
   * 就是页面主标题；传 `1` 的页面里不得再出现第二个 `h1`。
   */
  headingLevel?: 1 | 2 | 3
  /** 面板内容。 */
  children: ReactNode
  /** 追加的类名，通常用于宽度/外边距调整。 */
  className?: string
}

/**
 * 白底圆角面板。
 *
 * 标题用真实标题标签而非样式化的 `<div>`：读屏的标题导航依赖标题标签，
 * 只改字号不会产生可导航的标题。
 */
export function Card({
  title,
  titleAction,
  headingLevel = 2,
  children,
  className = '',
}: CardProps) {
  const Heading = HEADING_TAG[headingLevel]

  return (
    <section
      className={`rounded-surface border border-border bg-surface p-4 shadow-panel ${className}`}
    >
      {title !== undefined && (
        <div className="mb-section flex items-center justify-between gap-2">
          <Heading className="text-body font-semibold text-text-primary">{title}</Heading>
          {titleAction}
        </div>
      )}
      {children}
    </section>
  )
}
