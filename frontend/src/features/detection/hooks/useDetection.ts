/**
 * 变化检测的业务状态机。
 *
 * 保持轻封装：**不引入** TanStack Query。这里的交互是「用户点一次 → 一次请求
 * → 展示结果」的命令式流程，没有缓存、去重、重试、后台刷新等需求，引一个
 * 数据同步库只会把 42 行状态逻辑变成一整套配置。
 *
 * 与旧前端的差异：旧版把异常压成 `string` 存进 `error`，调用方拿不到 `code`，
 * 只能按文案分支。本版把异常**原样**保留（`unknown`），由 `ErrorAlert` 做
 * `instanceof` 判定后按 `code` 分派——文案是脱敏展示串，不可作为分支依据。
 */

import { useCallback, useRef, useState } from 'react'

import { detectChange } from '@/api/client'
import type { DetectionResponse } from '@/types/detection'

/** 状态机取值。 */
export type DetectionStatus = 'idle' | 'loading' | 'success' | 'error'

export interface UseDetectionResult {
  /** 当前状态。 */
  status: DetectionStatus
  /** 成功时的响应；其余状态为 `null`。 */
  result: DetectionResponse | null
  /**
   * 失败时的原始异常。
   *
   * 类型为 `unknown` 而非 `Error`：`fetch` 抛出的东西不保证是 `Error`
   * （理论上可以是任意值），消费方必须先收窄再取属性。
   */
  error: unknown
  /** 发起检测。重复调用时后发起的请求获胜。 */
  detect: (before: File, after: File) => Promise<void>
  /** 回到 `idle` 并清空结果与错误。 */
  reset: () => void
}

/**
 * 变化检测状态管理。
 *
 * 竞态处理：每次调用 `detect` 递增 `runIdRef`，响应回来时只有自己仍是
 * 最新一轮才落状态。这样连点两次时，先返回的旧响应不会覆盖后发起的请求，
 * 也保证组件卸载后不再 `setState`。
 */
export function useDetection(): UseDetectionResult {
  const [status, setStatus] = useState<DetectionStatus>('idle')
  const [result, setResult] = useState<DetectionResponse | null>(null)
  const [error, setError] = useState<unknown>(null)

  /** 已发起的请求序号；仅最新一轮有权写入状态。 */
  const runIdRef = useRef(0)

  const detect = useCallback(async (before: File, after: File): Promise<void> => {
    runIdRef.current += 1
    const runId = runIdRef.current

    setStatus('loading')
    setError(null)
    setResult(null)

    try {
      const data = await detectChange(before, after)
      if (runId !== runIdRef.current) return
      setResult(data)
      setStatus('success')
    } catch (caught: unknown) {
      if (runId !== runIdRef.current) return
      setError(caught)
      setStatus('error')
    }
  }, [])

  const reset = useCallback((): void => {
    // 递增序号使在途请求的结果作废：重置后旧的响应不应把界面拉回 success。
    runIdRef.current += 1
    setStatus('idle')
    setResult(null)
    setError(null)
  }, [])

  return { status, result, error, detect, reset }
}
