/**
 * 加载骨架原语。
 *
 * 解决的问题：结果返回前若结果区是空白，页面会先塌下去再被内容撑开，产生明显
 * 的高度跳动；用户也无从判断「是在算，还是卡住了」。骨架块提前占住与结果同
 * 构的高度，把等待过程变成可预期的。
 *
 * 无障碍约定（与 `Spinner` 分工明确）：
 *
 * * 骨架块本身是**纯视觉**的：每块都标 `aria-hidden`，否则读屏会把一串空
 *   `div` 逐个播报，噪声大于信息。
 * * 「正在加载」这件事由调用方提供的**唯一**一个 `status` 节点承载（见
 *   `ResultSkeleton` 里的 `role="status"`）。这样读屏只播报一次。
 */

export interface SkeletonProps {
  /** 追加的类名，仅用于调尺寸（如 `h-4 w-24`）；视觉样式由本组件固定。 */
  className?: string
}

/**
 * 单个骨架块。
 *
 * 用 `animate-pulse`（透明度呼吸）而非骨架屏常见的流光效果：本项目令牌里
 * 没有渐变资源，呼吸只需要一个动画类，产物更小。
 */
export function Skeleton({ className = '' }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-control bg-surface-raised ${className}`}
    />
  )
}
