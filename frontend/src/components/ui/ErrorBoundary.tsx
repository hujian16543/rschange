/**
 * 渲染期异常边界。
 *
 * 解决的问题：React 18 起，渲染期抛出的异常会让**整棵** React 树被卸载，
 * 用户看到白屏且无法自救。边界把「功能坏了」限制在功能内部——壳仍在，用户
 * 能读到发生了什么，并能试着恢复。
 *
 * 为什么必须写成 class：函数组件没有对应的 hook。React 官方仅提供
 * `getDerivedStateFromError`（渲染降级 UI）与 `componentDidCatch`（上报）两个
 * class 生命周期，`use` + Suspense 处理的是「挂起」而非「抛错」，不能替代。
 *
 * 边界**不**捕获：事件处理器、`setTimeout`/`requestAnimationFrame` 回调、
 * 服务端渲染、边界自身的错误。这些场景各自的失败路径不同（如事件处理器抛错
 * 不会卸载 React 树），本组件不假装覆盖。
 */

import type { ErrorInfo, ReactNode } from 'react'
import { Component } from 'react'

/**
 * `getDerivedStateFromError` 的返回值。
 *
 * 只存**是否出错**与错误对象，不存展示文案：文案由 `render` 依 `error` 现算，
 * 避免把展示细节塞进状态后与 `error` 失去同步。
 */
interface ErrorBoundaryState {
  /** 触发降级的异常；正常时为 `null`。 */
  error: Error | null
}

export interface ErrorBoundaryProps {
  /** 被保护的内容。 */
  children: ReactNode
  /**
   * 降级 UI 的自定义渲染函数；不传则用内置降级 UI。
   *
   * 传函数而非节点，是因为降级 UI 通常需要 `error` 与 `onReset` 两个入参，
   * 传已渲染的节点则无法把二者交给调用方。
   */
  fallback?: (error: Error, reset: () => void) => ReactNode
}

/**
 * 错误边界。
 *
 * 恢复动作只做一件事：清空 `error` 让子树重新挂载（React 在错误后已丢弃旧
 * 子树，`state.error` 转 `null` 即触发一次全新挂载）。若导致异常的原因未消失，
 * 子树会再次抛错、边界再次降级，不会无限递归——React 保证同一位置的重复
 * 抛错只走一次边界流程。
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { error: null }

  /**
   * 渲染期同步调用，返回值直接成为新 state。
   *
   * 收窄为 `Error`：`throw` 可以抛任意值，但降级 UI 要展示 `message`/`stack`，
   * 故非 `Error` 的抛出物在这里包一层，保证 `state.error` 恒有 `message`。
   */
  static getDerivedStateFromError(thrown: unknown): ErrorBoundaryState {
    return { error: thrown instanceof Error ? thrown : new Error(String(thrown)) }
  }

  /**
   * 提交期调用，用于上报。
   *
   * 错误必须留痕：降级 UI 是给用户看的，控制台的原始错误对象配组件栈才够
   * 定位。此处只做 `console.error`——本项目无远端上报通道，假装上报反而会
   * 掩盖「没有可观测性」这个事实。
   */
  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[ErrorBoundary] 渲染期异常', error, info.componentStack)
  }

  private readonly reset = (): void => {
    this.setState({ error: null })
  }

  override render(): ReactNode {
    const { error } = this.state
    if (error === null) return this.props.children

    if (this.props.fallback !== undefined) return this.props.fallback(error, this.reset)

    return <DefaultFallback error={error} onReset={this.reset} />
  }
}

export interface DefaultFallbackProps {
  /** 已归一化的异常。 */
  error: Error
  /** 点击「重试」时调用。 */
  onReset: () => void
}

/**
 * 内置降级 UI。
 *
 * `role="alert"`：这是打断性的、用户必须知晓的事件，与 `ErrorAlert` 同一约定。
 * 展开技术细节用原生 `<details>`：这里刻意**不**复用 `ErrorAlert`——那个组件
 * 属于 detection 功能，而边界是通用原语，反向依赖会把 `components/ui` 拖进
 * 业务层。
 */
function DefaultFallback({ error, onReset }: DefaultFallbackProps) {
  return (
    <div
      role="alert"
      className="m-panel rounded-surface border border-danger-border bg-danger-muted p-4 shadow-panel"
    >
      <h1 className="text-body font-semibold text-danger-strong">页面出错了</h1>
      <p className="mt-1 text-caption text-text-secondary">
        渲染这个界面时发生了未预期的错误。可以点击下方按钮重试；若反复出现，
        请把技术细节一并反馈。
      </p>

      <button
        type="button"
        onClick={onReset}
        className="mt-section rounded-control border border-border bg-surface px-3 py-1.5 text-caption text-text-primary transition-colors hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        重试
      </button>

      <details className="mt-section text-caption text-text-muted">
        <summary className="cursor-pointer underline underline-offset-2">技术细节</summary>
        <pre className="mt-1 overflow-x-auto rounded-control bg-surface px-2 py-1 font-mono text-caption text-text-secondary">
          {error.message}
        </pre>
      </details>
    </div>
  )
}
