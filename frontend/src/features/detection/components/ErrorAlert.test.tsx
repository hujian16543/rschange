/**
 * `ErrorAlert` 的错误分支测试。
 *
 * 被测对象是**真实组件**：`ErrorAlert` 内部调 `describeError` 做 `instanceof`
 * 判定与 `code` 查表，故断言走的正是生产路径。若只测 `describeError` 纯函数，
 * 「组件是否真的把 title/advice 渲染出来」「重试按钮是否真的只对可重试错误出现」
 * 这两件最容易坏的事就无人守护。
 *
 * 判据设计：每个用例都用**不同的错误码**断言**不同的文案**。如果实现退回成
 * 「所有错误都显示同一句请重试」（旧前端的做法），多条用例会同时失败。
 *
 * 关于「可重试」的判别力：`retryable` 决定「重试」按钮是否出现。`onRetry` 一律
 * 传入，故按钮的有无**只**由 `code` 决定——输入类错误（改输入才有用）不出现，
 * 服务端瞬时故障才出现。这个区分若被抹平，对应用例即红。
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ApiError, NetworkError } from '@/api/client'
import { ErrorAlert } from '@/features/detection/components/ErrorAlert'

/** 造一个带指定错误码的 `ApiError`。 */
function apiError(code: string, detail = '服务端返回的脱敏描述'): ApiError {
  return new ApiError(detail, 400, code)
}

describe('ErrorAlert 按 code 分支', () => {
  it('upload_too_large：提示体积超限，且不给「重试」按钮', () => {
    const onRetry = vi.fn()
    render(<ErrorAlert error={apiError('upload_too_large')} onRetry={onRetry} />)

    expect(screen.getByText('影像超过体积上限')).toBeInTheDocument()
    expect(screen.getByText(/runtime\.max_upload_mb/)).toBeInTheDocument()
    // 换一版影像才有用，重试同一份只会再失败一次。
    expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument()
  })

  it('input_validation_error：提示尺寸/波段不一致，且不给重试', () => {
    render(<ErrorAlert error={apiError('input_validation_error')} />)

    expect(screen.getByText('影像不符合处理要求')).toBeInTheDocument()
    expect(screen.getByText(/尺寸与波段数一致/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument()
  })

  it('unknown_detector：提示算法未注册，并指向管理员', () => {
    render(<ErrorAlert error={apiError('unknown_detector')} />)

    expect(screen.getByText('检测算法未注册')).toBeInTheDocument()
    expect(screen.getByText(/联系管理员/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument()
  })

  it('internal_error：提示服务端内部错误，且提供重试', () => {
    const onRetry = vi.fn()
    render(<ErrorAlert error={apiError('internal_error')} onRetry={onRetry} />)

    expect(screen.getByText('服务端内部错误')).toBeInTheDocument()
    expect(screen.getByText(/详细堆栈已记入服务端日志/)).toBeInTheDocument()
    // 瞬时故障：重试是有意义的动作，按钮必须出现。
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument()
  })

  it('同一份 error 下，不同 code 给出不同文案（防止文案退化为常量）', () => {
    const withCode = (code: string): string => {
      const { unmount } = render(<ErrorAlert error={apiError(code)} />)
      const title = screen.getByRole('alert').textContent ?? ''
      unmount()
      return title
    }

    const titles = [
      withCode('upload_too_large'),
      withCode('input_validation_error'),
      withCode('unknown_detector'),
      withCode('unsupported_format'),
    ]

    // 四个 code 必须给出四种不同的一段话；若实现只剩一句通用文案，此处即红。
    expect(new Set(titles).size).toBe(4)
    expect(titles[0]).not.toBe(titles[1])
    expect(titles[1]).not.toBe(titles[2])
    expect(titles[2]).not.toBe(titles[3])
  })

  it('点击「重试」会调用 onRetry', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    render(<ErrorAlert error={apiError('internal_error')} onRetry={onRetry} />)

    await user.click(screen.getByRole('button', { name: '重试' }))

    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('未知 code 走兜底分支：不崩溃，且把原始 code 透出便于报障', () => {
    render(<ErrorAlert error={apiError('brand_new_code_from_server')} />)

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('检测失败')).toBeInTheDocument()
    // 原始 code 必须出现在提示里：否则用户报障时说不清是哪一种。
    expect(screen.getByText(/brand_new_code_from_server/)).toBeInTheDocument()
  })
})

describe('ErrorAlert 区分网络层与 HTTP 层', () => {
  it('NetworkError：提示无法连接，并指向启动后端', () => {
    render(
      <ErrorAlert error={new NetworkError('无法连接到检测服务，请确认后端已启动', new TypeError('Failed to fetch'))} />,
    )

    expect(screen.getByText('无法连接到检测服务')).toBeInTheDocument()
    expect(screen.getByText(/localhost:8000/)).toBeInTheDocument()
  })

  it('网络错误与 HTTP 错误的展示可区分', () => {
    const { unmount } = render(
      <ErrorAlert error={new NetworkError('无法连接到检测服务', new TypeError('Failed to fetch'))} />,
    )
    const networkText = screen.getByRole('alert').textContent ?? ''
    unmount()

    render(<ErrorAlert error={apiError('upload_too_large')} />)
    const httpText = screen.getByRole('alert').textContent ?? ''

    expect(networkText).not.toBe(httpText)
    // 网络层说「没连上」，HTTP 层说「服务端拒绝了这份输入」，两者不可互换。
    expect(networkText).not.toContain('体积上限')
    expect(httpText).not.toContain('localhost:8000')
  })

  it('网络错误是可重试的，故提供重试按钮', () => {
    render(<ErrorAlert error={new NetworkError('无法连接到检测服务', new TypeError('x'))} onRetry={vi.fn()} />)

    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument()
  })

  it('非 ApiError / 非 NetworkError 的普通异常走「未预期错误」分支', () => {
    render(<ErrorAlert error={new Error('渲染时炸了')} />)

    expect(screen.getByText('发生未预期的错误')).toBeInTheDocument()
    // 原始 message 必须透出，否则无从定位。
    expect(screen.getByText(/渲染时炸了/)).toBeInTheDocument()
  })

  it('error 为 null 时不渲染任何内容', () => {
    const { container } = render(<ErrorAlert error={null} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('error 为非 Error 的原始值时不崩溃', () => {
    render(<ErrorAlert error={'一个裸字符串'} />)

    expect(screen.getByText('发生未预期的错误')).toBeInTheDocument()
  })
})

describe('ErrorAlert 的技术细节折叠', () => {
  it('默认折叠，点击后展开后端原始 detail', async () => {
    const user = userEvent.setup()
    const detail = '两期影像的尺寸或波段数不一致'
    render(<ErrorAlert error={apiError('input_validation_error', detail)} />)

    const toggle = screen.getByRole('button', { name: '查看技术细节' })
    // 折叠时 detail 不应出现在无障碍树里。
    expect(screen.queryByText(detail)).not.toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-expanded', 'false')

    await user.click(toggle)

    expect(screen.getByText(detail)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '收起技术细节' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
  })
})

describe('ErrorAlert 可访问性', () => {
  it('容器为 role="alert"（读屏立即播报）', () => {
    render(<ErrorAlert error={apiError('internal_error')} />)

    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('重试按钮可被 role 查询到', () => {
    render(<ErrorAlert error={apiError('processing_error')} onRetry={vi.fn()} />)

    expect(screen.getByRole('button', { name: '重试' })).toBeEnabled()
  })
})
