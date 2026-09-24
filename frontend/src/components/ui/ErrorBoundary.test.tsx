/**
 * `ErrorBoundary` 测试。
 *
 * 判据分三层，缺一层都会留下盲区：
 *
 * 1. **真的捕获了**——抛错子组件被替换为降级 UI。这是与「React 卸载整棵树
 *    变白屏」的唯一区别，也是本组件存在的理由。
 * 2. **兄弟内容仍活着**——边界只替换children，不替换同级的其它节点。若实现
 *    把降级 UI 挂到了整页根上，这条会红；而只测第 1 层发现不了。
 * 3. **能恢复**——点「重试」后重新挂载子树。
 *
 * 关于 React 会把捕获到的错误打到控制台：测试里用 `console.error` 的 spy 压掉，
 * 否则每跑一次就刷一大段红色堆栈，真出问题时反而看不见。spy 同时也充当
 * 「错误确实上报了」的证据。
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import type { MockInstance } from 'vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ErrorBoundary } from '@/components/ui/ErrorBoundary'

/**
 * `console.error` 的 spy 类型。
 *
 * 显式标注为 `MockInstance<typeof console.error>`，而不是
 * `ReturnType<typeof vi.spyOn>`：后者的泛型参数已被擦成宽泛签名，`mock.calls`
 * 的元素退化为 `any[]`，取值时触发 `noImplicitAny`。标注了具体函数类型，
 * `calls` 就带上了 `[message?: any, ...optionalParams: any[]]` 的形状。
 */
type ConsoleErrorSpy = MockInstance<typeof console.error>

/**
 * 抛错子组件。
 *
 * `shouldThrow` 由外部状态控制：这是「重试后能恢复」的必要条件——如果组件
 * 无条件抛错，点重试只会再炸一次，无法区分「恢复逻辑没生效」与「错误仍在」。
 */
function Bomb({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error('子组件在渲染期炸了')
  return <p>子组件正常渲染</p>
}

describe('ErrorBoundary 捕获渲染期异常', () => {
  /** 吞掉 React 打到控制台的错误堆栈，避免淹没真实失败信息。 */
  let consoleErrorSpy: ConsoleErrorSpy

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    consoleErrorSpy.mockRestore()
  })

  it('子组件抛错时展示降级 UI，而非整树崩溃', () => {
    render(
      <ErrorBoundary>
        <Bomb shouldThrow />
      </ErrorBoundary>,
    )

    // 降级 UI 出现……
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('页面出错了')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument()
    // ……且抛错的子树已被替换掉（不再渲染）。
    expect(screen.queryByText('子组件正常渲染')).not.toBeInTheDocument()
  })

  it('边界之外的兄弟内容仍然存活（只降级子树，不波及整页）', () => {
    render(
      <div>
        <header>页面外壳</header>
        <ErrorBoundary>
          <Bomb shouldThrow />
        </ErrorBoundary>
        <footer>页脚</footer>
      </div>,
    )

    expect(screen.getByText('页面外壳')).toBeInTheDocument()
    expect(screen.getByText('页脚')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('边界内多个子节点出错时整块降级，但边界外不受影响', () => {
    render(
      <div>
        <p>保留的内容</p>
        <ErrorBoundary>
          <Bomb shouldThrow />
          <p>这也不会渲染</p>
        </ErrorBoundary>
      </div>,
    )

    expect(screen.getByText('保留的内容')).toBeInTheDocument()
    expect(screen.queryByText('这也不会渲染')).not.toBeInTheDocument()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('子组件不抛错时原样渲染，不出现降级 UI', () => {
    render(
      <ErrorBoundary>
        <Bomb shouldThrow={false} />
      </ErrorBoundary>,
    )

    expect(screen.getByText('子组件正常渲染')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('错误被上报到 console.error（留痕可定位）', () => {
    render(
      <ErrorBoundary>
        <Bomb shouldThrow />
      </ErrorBoundary>,
    )

    expect(consoleErrorSpy).toHaveBeenCalled()
    // 用 `mock.calls.map` 取出首参再比对，避免在未标注类型的参数上触发
    // `noImplicitAny`；`map` 的回调签名由 `calls` 的元素类型推出，无需手写。
    const tags = consoleErrorSpy.mock.calls.map((call) => call[0])
    expect(tags).toContain('[ErrorBoundary] 渲染期异常')
  })

  it('降级 UI 展示异常信息（技术细节里可读到原始 message）', () => {
    render(
      <ErrorBoundary>
        <Bomb shouldThrow />
      </ErrorBoundary>,
    )

    expect(screen.getByText('子组件在渲染期炸了')).toBeInTheDocument()
    expect(screen.getByText('技术细节')).toBeInTheDocument()
  })
})

describe('ErrorBoundary 的恢复', () => {
  let consoleErrorSpy: ConsoleErrorSpy

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    consoleErrorSpy.mockRestore()
  })

  it('点击「重试」后重新挂载子树；错误消失则恢复正常内容', async () => {
    const user = userEvent.setup()

    /**
     * 受控切换：点「重试」时把 `shouldThrow` 置假，模拟「瞬时故障已过去」。
     * 这样就能区分「重试真的重新挂载了子树」（内容回来了）与「只是把降级 UI
     * 藏起来」（内容仍不在）。
     */
    function Recoverable() {
      const [shouldThrow, setShouldThrow] = useState(true)

      if (shouldThrow) {
        return (
          <ErrorBoundary
            fallback={(error, reset) => (
              <div role="alert">
                <p>{error.message}</p>
                <button
                  type="button"
                  onClick={() => {
                    setShouldThrow(false)
                    reset()
                  }}
                >
                  修复并重试
                </button>
              </div>
            )}
          >
            <Bomb shouldThrow />
          </ErrorBoundary>
        )
      }

      return (
        <ErrorBoundary>
          <Bomb shouldThrow={false} />
        </ErrorBoundary>
      )
    }

    render(<Recoverable />)
    expect(screen.getByRole('alert')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '修复并重试' }))

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByText('子组件正常渲染')).toBeInTheDocument()
  })

  it('使用内置降级 UI 时，「重试」把边界重置为初始态', async () => {
    const user = userEvent.setup()

    /**
     * 抛错开关由**测试**持有，而非组件内部状态。
     *
     * 前两版分别用模块级 `let` 与 `useRef` 让组件「自己只抛一次」，都栽在
     * 标志位的生命周期上：`useRef` 会被 `reset()` 后的重挂载复用，模块级 `let`
     * 会被 React 的重复渲染提前翻掉。把开关交给测试，就能在点击「重试」前明确
     * 把 `shouldThrow` 置假——于是「降级 UI 消失」只可能是 `reset()` 真的重新
     * 挂载了子树，而不可能是别的巧合。
     */
    let shouldThrow = true

    function Toggle() {
      if (shouldThrow) throw new Error('暂时坏了')
      return <p>已恢复</p>
    }

    render(
      <ErrorBoundary>
        <Toggle />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()

    // 修好之后再点重试：若 `reset` 没接通，降级 UI 会一直留着，断言即红。
    shouldThrow = false
    await user.click(screen.getByRole('button', { name: '重试' }))

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByText('已恢复')).toBeInTheDocument()
  })
})

describe('ErrorBoundary 自定义 fallback', () => {
  let consoleErrorSpy: ConsoleErrorSpy

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    consoleErrorSpy.mockRestore()
  })

  it('传入 fallback 时用它渲染，而非内置降级 UI', () => {
    render(
      <ErrorBoundary fallback={(error) => <p>自定义降级：{error.message}</p>}>
        <Bomb shouldThrow />
      </ErrorBoundary>,
    )

    expect(screen.getByText('自定义降级：子组件在渲染期炸了')).toBeInTheDocument()
    // 内置 UI 的标题不应出现——两者互斥。
    expect(screen.queryByText('页面出错了')).not.toBeInTheDocument()
  })

  it('fallback 收到的是 Error 实例（非 Error 抛出物会被包装）', () => {
    /** 抛一个非 Error 的值：`throw` 语法本身允许任意类型。 */
    function ThrowsString(): never {
      // eslint 风格约束：这里刻意抛非 Error，用于验证边界的归一化。
      throw '一个裸字符串'
    }

    render(
      <ErrorBoundary fallback={(error) => <p>收到：{error.message}</p>}>
        <ThrowsString />
      </ErrorBoundary>,
    )

    // 归一化后仍能安全读 `message`，不会因访问字符串的 `.message` 而再抛一次。
    expect(screen.getByText('收到：一个裸字符串')).toBeInTheDocument()
  })

  it('fallback 的 reset 可把边界拉回正常渲染', async () => {
    const user = userEvent.setup()
    let shouldThrow = true

    function Toggle() {
      if (shouldThrow) throw new Error('暂时坏了')
      return <p>已恢复</p>
    }

    render(
      <ErrorBoundary
        fallback={(_error, reset) => (
          <button
            type="button"
            onClick={() => {
              shouldThrow = false
              reset()
            }}
          >
            恢复
          </button>
        )}
      >
        <Toggle />
      </ErrorBoundary>,
    )

    await user.click(screen.getByRole('button', { name: '恢复' }))

    expect(screen.getByText('已恢复')).toBeInTheDocument()
  })
})
