/**
 * 结果区加载骨架。
 *
 * 形状刻意与 `ResultPanel` 对应（核心指标卡 → 统计行 → 三图对比），这样结果
 * 返回时布局不跳，用户也预期得到「马上会出现哪些块」。
 *
 * 为什么不直接复用 `ResultPanel` 加 `loading` 开关：那会把骨架的空数据塞进
 * 一份必须满足契约的 `DetectionResponse`，等于伪造一份假结果。骨架是独立的
 * 展示形态，不复用业务渲染路径。
 */

import { Card, Skeleton } from '@/components/ui'

/** 统计明细的占位行数，与 `ResultPanel` 的 6 条 `StatRow` 对齐。 */
const STAT_ROWS = 6

export function ResultSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="正在检测"
      className="space-y-section"
      data-testid="result-skeleton"
    >
      {/*
        可见文案兼播报文案。骨架块本身 `aria-hidden`，读屏只会看到这一句，
        故它必须自足地说明「在做什么」。
      */}
      <p className="sr-only">正在读取影像并计算变化区域，请稍候…</p>

      {/* 核心指标卡：标题条 + 大号数值 */}
      <Card headingLevel={3}>
        <Skeleton className="h-3 w-24" />
        <Skeleton className="mt-2 h-7 w-40" />
        <Skeleton className="mt-2 h-3 w-56" />
      </Card>

      {/* 统计明细：一组「标签 — 数值」行 */}
      <Card headingLevel={3}>
        <div className="space-y-2">
          {Array.from({ length: STAT_ROWS }, (_, index) => (
            <div key={index} className="flex items-center justify-between gap-3">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-3 w-24" />
            </div>
          ))}
        </div>
      </Card>

      {/* 三图对比 */}
      <Card headingLevel={3}>
        <div className="grid gap-section sm:grid-cols-3">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
      </Card>
    </div>
  )
}
