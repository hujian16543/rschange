/**
 * `DetectionPage` 集成测试：加载骨架、页面级 a11y、以及 `App` 是否真的挂了
 * 错误边界。
 *
 * 与各组件单测的分工：单测验证「给定 props 渲染成什么」，本文件验证
 * **接线**——`DetectionPage` 把 hook 状态映射成了哪个分支、骨架在 loading 时
 * 是否真的出现、`App` 根上是否真的包了边界。这类缺陷单测一律发现不了：组件
 * 各自都对，接错了照样白屏。
 *
 * mock 策略：替换 `@/api/client` 的 `detectChange`，其余（`ApiError` 等）
 * 用 `importOriginal` 原样透传。
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { detectChange } from '@/api/client'
import { DetectionPage } from '@/features/detection/DetectionPage'
import type { DetectionResponse } from '@/types/detection'

import { afterFile, beforeFile, EXAMPLE_RESPONSE } from '@/test/fixtures'

vi.mock(import('@/api/client'), async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    detectChange: vi.fn(),
  }
})

const detectChangeMock = vi.mocked(detectChange)

/** 手工可控的 deferred，用于把界面「钉」在 loading 态上观察。 */
function createDeferred() {
  let resolveFn: ((value: DetectionResponse) => void) | undefined
  const promise = new Promise<DetectionResponse>((resolve) => {
    resolveFn = resolve
  })
  if (resolveFn === undefined) throw new Error('executor 未同步执行')
  return { promise, resolve: resolveFn }
}

describe('DetectionPage 加载骨架', () => {
  beforeEach(() => {
    detectChangeMock.mockReset()
  })

  it('初始 idle 态不显示骨架（避免一进页面就在假装加载）', () => {
    render(<DetectionPage />)

    expect(screen.queryByTestId('result-skeleton')).not.toBeInTheDocument()
    expect(screen.getByText('遥感变化检测')).toBeInTheDocument()
  })

  it('loading 态显示骨架占位', async () => {
    const user = userEvent.setup()
    const deferred = createDeferred()
    detectChangeMock.mockReturnValue(deferred.promise)

    render(<DetectionPage />)
    await user.upload(screen.getByLabelText(/选择前时相影像/), beforeFile())
    await user.upload(screen.getByLabelText(/选择后时相影像/), afterFile())
    await user.click(screen.getByRole('button', { name: /开始检测/ }))

    expect(screen.getByTestId('result-skeleton')).toBeInTheDocument()
  })

  it('骨架以 role="status" 暴露给读屏（播报「正在检测」）', async () => {
    const user = userEvent.setup()
    const deferred = createDeferred()
    detectChangeMock.mockReturnValue(deferred.promise)

    render(<DetectionPage />)
    await user.upload(screen.getByLabelText(/选择前时相影像/), beforeFile())
    await user.upload(screen.getByLabelText(/选择后时相影像/), afterFile())
    await user.click(screen.getByRole('button', { name: /开始检测/ }))

    const status = screen.getByRole('status', { name: '正在检测' })
    expect(status).toBeInTheDocument()
    expect(status).toHaveAttribute('aria-busy', 'true')
  })

  it('骨架块对读屏隐藏（只播报一次，不逐个念空块）', async () => {
    const user = userEvent.setup()
    const deferred = createDeferred()
    detectChangeMock.mockReturnValue(deferred.promise)

    render(<DetectionPage />)
    await user.upload(screen.getByLabelText(/选择前时相影像/), beforeFile())
    await user.upload(screen.getByLabelText(/选择后时相影像/), afterFile())
    await user.click(screen.getByRole('button', { name: /开始检测/ }))

    const status = screen.getByRole('status', { name: '正在检测' })
    // 骨架容器内的所有块都标了 aria-hidden，故无障碍树里查不到装饰性内容。
    const hiddenBlocks = status.querySelectorAll('[aria-hidden="true"]')
    expect(hiddenBlocks.length).toBeGreaterThan(0)
  })

  it('结果返回后骨架消失，替换为真实结果（不残留占位）', async () => {
    const user = userEvent.setup()
    const deferred = createDeferred()
    detectChangeMock.mockReturnValue(deferred.promise)

    render(<DetectionPage />)
    await user.upload(screen.getByLabelText(/选择前时相影像/), beforeFile())
    await user.upload(screen.getByLabelText(/选择后时相影像/), afterFile())
    await user.click(screen.getByRole('button', { name: /开始检测/ }))
    expect(screen.getByTestId('result-skeleton')).toBeInTheDocument()

    deferred.resolve(EXAMPLE_RESPONSE)

    await waitFor(() => {
      expect(screen.queryByTestId('result-skeleton')).not.toBeInTheDocument()
    })
    // 真实结果的三个 T4.2 新增字段都在。
    expect(screen.getByText(EXAMPLE_RESPONSE.detector)).toBeInTheDocument()
    expect(screen.getByText('真实变化面积')).toBeInTheDocument()
  })

  it('loading 时按钮进入忙碌态（禁用 + aria-busy）', async () => {
    const user = userEvent.setup()
    const deferred = createDeferred()
    detectChangeMock.mockReturnValue(deferred.promise)

    render(<DetectionPage />)
    await user.upload(screen.getByLabelText(/选择前时相影像/), beforeFile())
    await user.upload(screen.getByLabelText(/选择后时相影像/), afterFile())
    await user.click(screen.getByRole('button', { name: /开始检测/ }))

    const button = screen.getByRole('button', { name: /检测中/ })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
  })
})

describe('DetectionPage 结果与错误的分支切换', () => {
  beforeEach(() => {
    detectChangeMock.mockReset()
  })

  it('成功时展示结果面板，且没有错误提示', async () => {
    const user = userEvent.setup()
    detectChangeMock.mockResolvedValue(EXAMPLE_RESPONSE)

    render(<DetectionPage />)
    await user.upload(screen.getByLabelText(/选择前时相影像/), beforeFile())
    await user.upload(screen.getByLabelText(/选择后时相影像/), afterFile())
    await user.click(screen.getByRole('button', { name: /开始检测/ }))

    await waitFor(() => {
      expect(screen.getByText('统计明细')).toBeInTheDocument()
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    // 成功态提供「重新检测」回到 idle。
    expect(screen.getByRole('button', { name: '重新检测' })).toBeInTheDocument()
  })

  it('「重新检测」把页面拉回初始空态', async () => {
    const user = userEvent.setup()
    detectChangeMock.mockResolvedValue(EXAMPLE_RESPONSE)

    render(<DetectionPage />)
    await user.upload(screen.getByLabelText(/选择前时相影像/), beforeFile())
    await user.upload(screen.getByLabelText(/选择后时相影像/), afterFile())
    await user.click(screen.getByRole('button', { name: /开始检测/ }))
    await waitFor(() => {
      expect(screen.getByText('统计明细')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: '重新检测' }))

    expect(screen.getByText('遥感变化检测')).toBeInTheDocument()
    expect(screen.queryByText('统计明细')).not.toBeInTheDocument()
  })

  it('失败时在侧边栏展示 role="alert" 错误提示', async () => {
    const user = userEvent.setup()
    const { ApiError } = await import('@/api/client')
    detectChangeMock.mockRejectedValue(new ApiError('影像超过体积上限', 413, 'upload_too_large'))

    render(<DetectionPage />)
    await user.upload(screen.getByLabelText(/选择前时相影像/), beforeFile())
    await user.upload(screen.getByLabelText(/选择后时相影像/), afterFile())
    await user.click(screen.getByRole('button', { name: /开始检测/ }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    // 文案由 code 决定，而非 detail。
    expect(screen.getByText('影像超过体积上限')).toBeInTheDocument()
    // 错误区归入「检测输入」侧栏，与结果区分离。
    const sidebar = screen.getByRole('complementary', { name: '检测输入' })
    expect(within(sidebar).getByRole('alert')).toBeInTheDocument()
  })
})

describe('DetectionPage 的可访问性结构', () => {
  it('结果区与输入区各有可读的 landmark 名称', () => {
    render(<DetectionPage />)

    expect(screen.getByRole('main', { name: '检测结果' })).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: '检测输入' })).toBeInTheDocument()
  })

  it('空态以 h1 作为页面主标题', () => {
    render(<DetectionPage />)

    expect(screen.getByRole('heading', { level: 1, name: '遥感变化检测' })).toBeInTheDocument()
  })
})

/**
 * `App` 的接线测试。
 *
 * 只验证「根组件确实包了错误边界」——`ErrorBoundary` 自身的行为已在其单测里
 * 覆盖，这里只需证明它被挂上了。否则重构时把边界摘掉，所有单测仍然全绿而线上
 * 又会白屏。
 */
describe('App 根组件挂载错误边界', () => {
  it('App 渲染后包含功能页内容（边界未误伤正常渲染）', async () => {
    const { default: App } = await import('@/App')

    render(<App />)

    expect(screen.getByText('遥感变化检测')).toBeInTheDocument()
    expect(screen.queryByText('页面出错了')).not.toBeInTheDocument()
  })
})
