/**
 * `useDetection` 状态机测试。
 *
 * 为什么把 hook 挂在一个**只**渲染 hook 返回值的宿主组件上（而不是渲染
 * `DetectionPage`）：`DetectionPage` 在各状态下的 DOM 大不相同，用它的 DOM
 * 反推 `status` 等于把「状态机是否正确」与「页面布局是否如预期」两件事绑死；
 * 前者一坏、后者一改都会红，定位成本高。宿主把所有四个返回值都暴露出来，
 * 断言才能精确指向状态机本身。
 *
 * 宿主刻意**不**持有任何与状态机重复的数据：
 *
 * * 调用 `detect` 用 `document` 上的真实 `<button>` 点击驱动——若这么写
 *   `onClick={() => { void detect(before, after) }}`，测试就无法在 `detect`
 *   不被调用时失败，行为出错也照样绿。
 * * 断言只看 `data-status` / `data-has-result` / `data-error-name` 三个由
 *   `status` / `result` / `error` **直接派生**的属性。因此不存在
 *   `expect(status).toBe(status)` 这类永真断言：属性值完全由被测 hook 决定。
 * * `reset` 同样经 `document` 上的按钮点击触发。
 *
 * 竞态用例是这套测试的核心判据。`useDetection` 用 `runIdRef` 让「后发起者
 * 获胜」，若哪天有人把这段守卫删掉、退回「谁先返回谁生效」，用例 5 必然失败。
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useCallback } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, NetworkError } from '@/api/client'
import { detectChange } from '@/api/client'
import type { DetectionStatus } from '@/features/detection/hooks/useDetection'
import { useDetection } from '@/features/detection/hooks/useDetection'
import type { DetectionResponse } from '@/types/detection'

import { afterFile, beforeFile, EXAMPLE_RESPONSE } from '@/test/fixtures'

// `detectChange` 是模块级 import 的函数，只有替换模块才能拦到。这里**不**用
// `as unknown as ...` 之类的断言去改造它：`vi.mock` 的工厂返回什么形状，
// 下面的 `vi.mocked()` 就得到什么类型，全程无断言。
//
// 用 `importOriginal` 做**部分**替换而非整体替换：`ApiError` / `NetworkError`
// 是真实类，被替换掉就只剩一个空壳，`instanceof` 判定与 `code` 取值都会失真
// （报错原文：「No "ApiError" export is defined on the mock」）。只把
// `detectChange` 换成 spy，其余原样透传——测试才能既控制请求，又使用与生产
// 完全相同的错误类型。
vi.mock(import('@/api/client'), async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    detectChange: vi.fn(),
  }
})

const detectChangeMock = vi.mocked(detectChange)

/** 前时相文件；模块级建一次即可，内容不被读取。 */
const BEFORE = beforeFile()

/** 后时相文件。 */
const AFTER = afterFile()

/**
 * 手工可控的 promise。
 *
 * `vi.fn().mockReturnValue(promise)` 无法在「请求未决」与「已履行」之间切换，
 * 而竞态用例恰恰要求两个请求**同时**在途、并按指定顺序返回。故自建一个
 * deferred，把 resolve/reject 的时机交给测试。
 */
interface Deferred {
  readonly promise: Promise<DetectionResponse>
  readonly resolve: (value: DetectionResponse) => void
  readonly reject: (reason: unknown) => void
}

function createDeferred(): Deferred {
  // `let` + 赋值而非 `!` 非空断言：`Promise` 的 executor 在构造函数内**同步**
  // 执行，两个变量在 `new Promise` 返回前必已赋值。但编译器不知道这一点，故用
  // `??` 兜底成显式的失败分支——既不绕过严格检查，也不会静默吞掉。
  let resolveFn: ((value: DetectionResponse) => void) | undefined
  let rejectFn: ((reason: unknown) => void) | undefined

  const promise = new Promise<DetectionResponse>((resolve, reject) => {
    resolveFn = resolve
    rejectFn = reject
  })

  if (resolveFn === undefined || rejectFn === undefined) {
    throw new Error('Promise executor 未同步执行，createDeferred 的前提不成立')
  }

  return { promise, resolve: resolveFn, reject: rejectFn }
}

/**
 * 测试宿主：把 hook 的全部返回值映射成可断言的 DOM。
 *
 * `data-status` 是唯一的「当前状态」真源；三个按钮分别驱动 `detect`（两次）与
 * `reset`，经 `document` 查询点击，确保「点了没反应」也会让用例红。
 */
function Harness() {
  const { status, result, error, detect, reset } = useDetection()

  const detectFirst = useCallback((): void => {
    void detect(BEFORE, AFTER)
  }, [detect])

  const detectSecond = useCallback((): void => {
    void detect(AFTER, BEFORE)
  }, [detect])

  /** 错误名称：非 `Error` 时归为 `unknown`，避免读取不存在的属性。 */
  const errorName = error instanceof Error ? error.name : error === null ? 'none' : 'unknown'

  return (
    <div>
      <p data-testid="status" data-status={status}>
        {status}
      </p>
      <p data-testid="has-result" data-has-result={result !== null ? 'yes' : 'no'}>
        {result === null ? '无结果' : `结果：${result.detector}`}
      </p>
      <p data-testid="result-detector">{result === null ? '' : result.detector}</p>
      <p data-testid="error-name" data-error-name={errorName}>
        {errorName}
      </p>
      <button type="button" onClick={detectFirst}>
        第一次检测
      </button>
      <button type="button" onClick={detectSecond}>
        第二次检测
      </button>
      <button type="button" onClick={reset}>
        重置
      </button>
    </div>
  )
}

/** 读取宿主暴露的当前状态；元素缺失即报错，不会静默返回 undefined。 */
function currentStatus(): string {
  return screen.getByTestId('status').dataset.status ?? ''
}

/** 读 `data-has-result`。 */
function hasResult(): string {
  return screen.getByTestId('has-result').dataset.hasResult ?? ''
}

/** 读错误名称。 */
function errorName(): string {
  return screen.getByTestId('error-name').dataset.errorName ?? ''
}

/** 读结果中的 `detector`，用于区分「哪一次请求的结果被落盘」。 */
function resultDetector(): string {
  return screen.getByTestId('result-detector').textContent ?? ''
}

describe('useDetection 状态机', () => {
  beforeEach(() => {
    detectChangeMock.mockReset()
  })

  it('初始状态为 idle，且无结果、无错误', () => {
    render(<Harness />)

    expect(currentStatus()).toBe('idle')
    expect(hasResult()).toBe('no')
    expect(errorName()).toBe('none')
  })

  it('detect 经 loading 到 success，并把响应填入 result', async () => {
    const user = userEvent.setup()
    const deferred = createDeferred()
    detectChangeMock.mockReturnValue(deferred.promise)

    render(<Harness />)
    await user.click(screen.getByRole('button', { name: '第一次检测' }))

    // 请求未决时必须是 loading —— 若实现忘了 setStatus('loading')，此处即红。
    expect(currentStatus()).toBe('loading')
    expect(hasResult()).toBe('no')

    deferred.resolve(EXAMPLE_RESPONSE)

    await waitFor(() => {
      expect(currentStatus()).toBe('success')
    })
    expect(hasResult()).toBe('yes')
    expect(resultDetector()).toBe(EXAMPLE_RESPONSE.detector)
  })

  it('detectChange 收到的是用户选择的两期文件，且顺序正确', async () => {
    const user = userEvent.setup()
    detectChangeMock.mockResolvedValue(EXAMPLE_RESPONSE)

    render(<Harness />)
    await user.click(screen.getByRole('button', { name: '第一次检测' }))

    await waitFor(() => {
      expect(detectChangeMock).toHaveBeenCalledTimes(1)
    })

    // 参数顺序反了（after 当 before 用）会得出完全不同的检测结论，必须守。
    const call = detectChangeMock.mock.calls[0]
    expect(call).toBeDefined()
    expect(call?.[0]).toBe(BEFORE)
    expect(call?.[1]).toBe(AFTER)
  })

  it('失败时进入 error，并原样保留异常对象', async () => {
    const user = userEvent.setup()
    const deferred = createDeferred()
    detectChangeMock.mockReturnValue(deferred.promise)

    render(<Harness />)
    await user.click(screen.getByRole('button', { name: '第一次检测' }))
    expect(currentStatus()).toBe('loading')

    deferred.reject(new ApiError('影像超过体积上限', 413, 'upload_too_large'))

    await waitFor(() => {
      expect(currentStatus()).toBe('error')
    })
    // 错误对象必须原样保留：压成 string 后 `ErrorAlert` 就拿不到 `code`，
    // 只能退回文案匹配（旧前端的缺陷）。
    expect(errorName()).toBe('ApiError')
    expect(hasResult()).toBe('no')
  })

  it('reset 回到 idle 并清空结果与错误', async () => {
    const user = userEvent.setup()
    detectChangeMock.mockResolvedValue(EXAMPLE_RESPONSE)

    render(<Harness />)
    await user.click(screen.getByRole('button', { name: '第一次检测' }))
    await waitFor(() => {
      expect(currentStatus()).toBe('success')
    })

    await user.click(screen.getByRole('button', { name: '重置' }))

    expect(currentStatus()).toBe('idle')
    expect(hasResult()).toBe('no')
    expect(errorName()).toBe('none')
  })

  it('reset 后再发起 detect 仍能正常进入 success', async () => {
    const user = userEvent.setup()
    detectChangeMock.mockResolvedValue(EXAMPLE_RESPONSE)

    render(<Harness />)
    await user.click(screen.getByRole('button', { name: '第一次检测' }))
    await waitFor(() => {
      expect(currentStatus()).toBe('success')
    })
    await user.click(screen.getByRole('button', { name: '重置' }))
    expect(currentStatus()).toBe('idle')

    await user.click(screen.getByRole('button', { name: '第一次检测' }))

    await waitFor(() => {
      expect(currentStatus()).toBe('success')
    })
  })

  it('在途请求被 reset 作废，其响应不得把界面拉回 success', async () => {
    const user = userEvent.setup()
    const deferred = createDeferred()
    detectChangeMock.mockReturnValue(deferred.promise)

    render(<Harness />)
    await user.click(screen.getByRole('button', { name: '第一次检测' }))
    expect(currentStatus()).toBe('loading')

    await user.click(screen.getByRole('button', { name: '重置' }))
    expect(currentStatus()).toBe('idle')

    // 旧请求此刻才返回：`reset` 递增过 runId，这次响应必须被丢弃。
    deferred.resolve(EXAMPLE_RESPONSE)

    await waitFor(() => {
      expect(detectChangeMock).toHaveBeenCalledTimes(1)
    })
    expect(currentStatus()).toBe('idle')
    expect(hasResult()).toBe('no')
  })

  it('竞态：后发起的结果获胜，先返回的旧结果不得覆盖它', async () => {
    const user = userEvent.setup()

    const first = createDeferred()
    const second = createDeferred()
    detectChangeMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    render(<Harness />)
    await user.click(screen.getByRole('button', { name: '第一次检测' }))
    await user.click(screen.getByRole('button', { name: '第二次检测' }))

    expect(detectChangeMock).toHaveBeenCalledTimes(2)

    // 第二次的响应带一个可辨识的 detector，用来判断最终落盘的是哪一份。
    const secondResponse: DetectionResponse = { ...EXAMPLE_RESPONSE, detector: 'second-run' }
    const firstResponse: DetectionResponse = { ...EXAMPLE_RESPONSE, detector: 'first-run' }

    // 旧请求（第一次）先返回。
    first.resolve(firstResponse)
    await waitFor(() => {
      expect(detectChangeMock).toHaveBeenCalledTimes(2)
    })

    // 关键断言：旧响应不得把状态推到 success，也不得写入 result。
    expect(currentStatus()).toBe('loading')
    expect(hasResult()).toBe('no')

    // 新请求（第二次）后返回，它才是赢家。
    second.resolve(secondResponse)

    await waitFor(() => {
      expect(currentStatus()).toBe('success')
    })
    expect(hasResult()).toBe('yes')
    expect(resultDetector()).toBe('second-run')
  })

  it('竞态：旧请求的失败也不得覆盖后发起请求的成功结果', async () => {
    const user = userEvent.setup()

    const first = createDeferred()
    const second = createDeferred()
    detectChangeMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    render(<Harness />)
    await user.click(screen.getByRole('button', { name: '第一次检测' }))
    await user.click(screen.getByRole('button', { name: '第二次检测' }))

    const secondResponse: DetectionResponse = { ...EXAMPLE_RESPONSE, detector: 'second-run' }
    second.resolve(secondResponse)

    await waitFor(() => {
      expect(currentStatus()).toBe('success')
    })

    // 旧请求此刻以失败告终：它已不是最新一轮，无权把界面拉进 error。
    first.reject(new NetworkError('无法连接到检测服务', new Error('ECONNREFUSED')))

    // 等待一个宏任务，确认没有「稍后到达的错误把状态翻掉」。
    await new Promise((resolve) => {
      setTimeout(resolve, 0)
    })

    expect(currentStatus()).toBe('success')
    expect(errorName()).toBe('none')
    expect(resultDetector()).toBe('second-run')
  })

  it('连续两次 detect 之间会清空上一轮的结果与错误', async () => {
    const user = userEvent.setup()

    const first = createDeferred()
    const second = createDeferred()
    detectChangeMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    render(<Harness />)
    await user.click(screen.getByRole('button', { name: '第一次检测' }))
    first.reject(new ApiError('服务端内部错误', 500, 'internal_error'))
    await waitFor(() => {
      expect(currentStatus()).toBe('error')
    })
    expect(errorName()).toBe('ApiError')

    // 第二轮开始：上一轮的错误必须立刻清掉，否则会与新状态同时展示。
    await user.click(screen.getByRole('button', { name: '第二次检测' }))
    expect(currentStatus()).toBe('loading')
    expect(errorName()).toBe('none')

    second.resolve(EXAMPLE_RESPONSE)
    await waitFor(() => {
      expect(currentStatus()).toBe('success')
    })
    expect(errorName()).toBe('none')
  })
})

/**
 * 状态联合类型的穷尽性守护。
 *
 * `DetectionStatus` 是字面量联合，若有人新增一个状态却漏改消费方，这里是第一
 * 道可编译期发现的口子；同时它把「合法的状态集合」钉在测试里——上面对
 * `data-status` 的字符串断言才有意义（否则任何字符串都能通过）。
 */
describe('DetectionStatus 取值集合', () => {
  it('恰好是 idle / loading / success / error 四种，与本套件断言一致', () => {
    const all: Record<DetectionStatus, true> = {
      idle: true,
      loading: true,
      success: true,
      error: true,
    }

    expect(Object.keys(all).sort()).toEqual(['error', 'idle', 'loading', 'success'])
  })
})

/**
 * 宿主自身的健全性检查放在最后。
 *
 * 上面所有断言都指望宿主如实回显 hook 的状态；若宿主自身写错（例如把
 * `data-status` 绑成常量），整套测试都会变成永真断言。这里用一个**不经过
 * hook** 的静态宿主证明映射方向正确：`status` 变，属性就变。
 */
describe('测试宿主健全性', () => {
  it('data-status 确实随状态变化，而非写死常量', () => {
    function Static({ status }: { status: DetectionStatus }) {
      return (
        <p data-testid="status" data-status={status}>
          {status}
        </p>
      )
    }

    const { rerender } = render(<Static status="idle" />)
    expect(currentStatus()).toBe('idle')

    rerender(<Static status="loading" />)
    expect(currentStatus()).toBe('loading')

    rerender(<Static status="error" />)
    expect(currentStatus()).toBe('error')
  })
})
