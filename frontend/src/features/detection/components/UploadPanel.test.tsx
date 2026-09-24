/**
 * 上传交互与检测按钮的可用性测试。
 *
 * 核心判据是**按钮的禁用状态随文件选择变化**。这里用 `upload()` 走 dropzone 的
 * 隐藏 `<input type="file">`——真实 `File`、真实 `change` 事件，整条
 * dropzone → `onDrop` → `onChange` → 父级 `setState` 的链路都被覆盖。若换成
 * 直接给 `UploadPanel` 传 `before={file}` props，就只测了渲染、没测交互，
 * 「选文件没生效」这类真实缺陷照样漏过。
 *
 * 按钮的禁用分两种原因，本套件分别断言：
 *
 * * 未选齐（`ready === false`）→ 禁用 + 提示「请先选择前时相与后时相两张影像」
 * * 正在检测（`loading`）→ 禁用 + 具备 `aria-busy` + 提示「正在检测…」
 *
 * 两者不可混为一谈：前者用户该去补文件，后者该等。
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useCallback, useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { DetectionButton } from '@/features/detection/components/DetectionButton'
import { UploadPanel } from '@/features/detection/components/UploadPanel'

import { afterFile, beforeFile } from '@/test/fixtures'

/**
 * 占位计数器：不关心点击次数的用例用它占位。
 *
 * `vi.fn()` 不能写在组件体内——组件每次渲染都会新建一个 spy，计数永远归零，
 * 断言就成了永真的 0。计数状态归测试持有才稳定。
 */
const noopCount = (): void => {}

/**
 * 把 `UploadPanel` + `DetectionButton` 按 `DetectionPage` 的方式接线。
 *
 * 与生产代码同构：文件状态、`ready` 的推导、禁用逻辑都在这里按同样的形状写一遍，
 * 这样断言「选齐两份文件后按钮可用」检验的才是真实行为。`onDetectCount` 由
 * 调用方传入并在测试内累加，用来证明按钮真的能触发检测。
 */
function UploadHarness({
  loading = false,
  onDetectCount,
}: {
  loading?: boolean
  /** 每次点击「开始检测」时自增；由测试持有，避免在组件体内建 spy。 */
  onDetectCount: (next: number) => void
}) {
  const [before, setBefore] = useState<File | null>(null)
  const [after, setAfter] = useState<File | null>(null)
  const [rejectMessage, setRejectMessage] = useState<string | null>(null)
  /** 下一次点击应上报的序号。用 state 而非常量，使重复渲染不重置计数。 */
  const [clicks, setClicks] = useState(0)

  const handleDetect = useCallback((): void => {
    setClicks((previous) => {
      const next = previous + 1
      onDetectCount(next)
      return next
    })
  }, [onDetectCount])

  const ready = before !== null && after !== null

  return (
    <div>
      <UploadPanel
        before={before}
        after={after}
        onBeforeChange={setBefore}
        onAfterChange={setAfter}
        onReject={setRejectMessage}
        rejectMessage={rejectMessage}
        disabled={loading}
      />
      <DetectionButton ready={ready} loading={loading} onClick={handleDetect} />
      <p data-testid="ready">{ready ? 'ready' : 'not-ready'}</p>
      <p data-testid="before-name">{before === null ? '' : before.name}</p>
      <p data-testid="after-name">{after === null ? '' : after.name}</p>
      <p data-testid="detect-count">{String(clicks)}</p>
    </div>
  )
}

describe('UploadPanel 选择文件', () => {
  it('初始两期均未选，按钮禁用', () => {
    render(<UploadHarness onDetectCount={noopCount} />)

    expect(screen.getByTestId('ready')).toHaveTextContent('not-ready')
    expect(screen.getByRole('button', { name: '开始检测' })).toBeDisabled()
  })

  it('只选前时相时按钮保持禁用', async () => {
    const user = userEvent.setup()
    render(<UploadHarness onDetectCount={noopCount} />)

    await user.upload(screen.getByLabelText(/选择前时相影像/), beforeFile())

    expect(screen.getByTestId('before-name')).toHaveTextContent('before.tif')
    expect(screen.getByTestId('after-name')).toHaveTextContent('')
    expect(screen.getByTestId('ready')).toHaveTextContent('not-ready')
    expect(screen.getByRole('button', { name: '开始检测' })).toBeDisabled()
  })

  it('只选后时相时按钮仍禁用（顺序无关）', async () => {
    const user = userEvent.setup()
    render(<UploadHarness onDetectCount={noopCount} />)

    await user.upload(screen.getByLabelText(/选择后时相影像/), afterFile())

    expect(screen.getByTestId('after-name')).toHaveTextContent('after.tif')
    expect(screen.getByTestId('ready')).toHaveTextContent('not-ready')
    expect(screen.getByRole('button', { name: '开始检测' })).toBeDisabled()
  })

  it('两期都选齐后按钮变为可用', async () => {
    const user = userEvent.setup()
    render(<UploadHarness onDetectCount={noopCount} />)

    await user.upload(screen.getByLabelText(/选择前时相影像/), beforeFile())
    await user.upload(screen.getByLabelText(/选择后时相影像/), afterFile())

    expect(screen.getByTestId('ready')).toHaveTextContent('ready')
    expect(screen.getByRole('button', { name: '开始检测' })).toBeEnabled()
  })

  it('选齐后点击按钮真的触发检测', async () => {
    const user = userEvent.setup()
    let clicks = 0
    render(<UploadHarness onDetectCount={(next) => (clicks = next)} />)

    await user.upload(screen.getByLabelText(/选择前时相影像/), beforeFile())
    await user.upload(screen.getByLabelText(/选择后时相影像/), afterFile())

    await user.click(screen.getByRole('button', { name: '开始检测' }))

    expect(clicks).toBe(1)
    expect(screen.getByTestId('detect-count')).toHaveTextContent('1')
  })

  it('未选齐时即使被强行点击也不触发检测', async () => {
    const user = userEvent.setup()
    let clicks = 0
    render(<UploadHarness onDetectCount={(next) => (clicks = next)} />)

    // 原生 disabled 已拦住鼠标点击；这一步确认它不是「看起来禁用」而已。
    await user.click(screen.getByRole('button', { name: '开始检测' }))

    expect(clicks).toBe(0)
    expect(screen.getByTestId('detect-count')).toHaveTextContent('0')
  })

  it('选中文件后展示文件名与体积', async () => {
    const user = userEvent.setup()
    render(<UploadHarness onDetectCount={noopCount} />)

    await user.upload(screen.getByLabelText(/选择前时相影像/), beforeFile())

    // 文件名出现在面板内（宿主另有同名的测试用回显，故限定在分组内查询）。
    const group = screen.getByRole('group', { name: '影像输入' })
    expect(within(group).getByText('before.tif')).toBeInTheDocument()
    // fixture 默认 4096 字节 → KB 档，用于让用户确认选对了文件。
    expect(within(group).getByText('4 KB')).toBeInTheDocument()
  })

  it('点击「清除」后文件被移除，按钮退回禁用', async () => {
    const user = userEvent.setup()
    render(<UploadHarness onDetectCount={noopCount} />)

    await user.upload(screen.getByLabelText(/选择前时相影像/), beforeFile())
    await user.upload(screen.getByLabelText(/选择后时相影像/), afterFile())
    expect(screen.getByRole('button', { name: '开始检测' })).toBeEnabled()

    await user.click(screen.getByRole('button', { name: '清除前时相影像' }))

    expect(screen.getByTestId('before-name')).toHaveTextContent('')
    expect(screen.getByRole('button', { name: '开始检测' })).toBeDisabled()
  })

  it('已选态提供「更换」按钮（键盘用户不必先清除再重选）', async () => {
    const user = userEvent.setup()
    render(<UploadHarness onDetectCount={noopCount} />)

    await user.upload(screen.getByLabelText(/选择前时相影像/), beforeFile())

    expect(screen.getByRole('button', { name: '更换前时相影像' })).toBeInTheDocument()
  })
})

/**
 * 拒收路径的测试方式说明（重要）。
 *
 * jsdom 的 `user.upload()` 直接给 input 派发 `change` 事件，**绕过**了
 * dropzone 的 `accept` / `maxSize` 过滤——`react-dropzone` 的校验发生在它自己
 * 的 `onDrop` 里，而 `user.upload` 不走那条路径。因此用 `user.upload` 传一个
 * `.txt` 文件，dropzone 会把它当正常文件放行，断言「应被拒收」必然失败。
 *
 * 于是把拒收拆成两段各自可验的部分：
 *
 * 1. **约束确实配上了**——断言 input 的 `accept` 属性（由 dropzone 依 `accept`
 *    配置生成）。这是「浏览器层面就会过滤掉 .txt」的可验证证据。
 * 2. **拒收后的展示**——`rejectMessage` 是父级传入的展示文案，直接以受控
 *    props 渲染，检验 `role="alert"`、文案、以及「清空即消失」的行为。
 *
 * 刻意**不**假造一个 `FileRejection` 去喂 `onDrop`：那需要绕过 dropzone 内部
 * 状态，测出来的是假实现的行为，不如把两段分别测实。
 */
describe('UploadPanel 拒收约束与提示', () => {
  it('文件输入的 accept 只放行 .tif / .tiff / .png（与 §9.2 白名单一致）', () => {
    render(<UploadHarness onDetectCount={noopCount} />)

    const input = screen.getByLabelText(/选择前时相影像/)
    const accept = input.getAttribute('accept') ?? ''

    expect(accept).toContain('.tif')
    expect(accept).toContain('.tiff')
    expect(accept).toContain('.png')
    // 白名单之外的类型不得出现——旧前端漏了 .png，这里守住「一个不漏也不多」。
    expect(accept).not.toContain('.txt')
    expect(accept).not.toContain('.jpg')
  })

  it('文件输入声明单选（一次只能选一个文件）', () => {
    render(<UploadHarness onDetectCount={noopCount} />)

    const input = screen.getByLabelText(/选择前时相影像/)
    // dropzone 在 maxFiles=1 时会显式标 multiple，读屏据此播报。
    expect(input).not.toBeChecked()
    expect(input.getAttribute('multiple')).toBeNull()
  })

  it('拒收提示为 role="alert" 并展示原因', () => {
    render(
      <UploadPanel
        before={null}
        after={null}
        onBeforeChange={noopCount}
        onAfterChange={noopCount}
        onReject={noopCount}
        rejectMessage="notes.txt：文件类型不支持（仅接受 .tif / .tiff / .png）"
      />,
    )

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('notes.txt')
    expect(alert).toHaveTextContent('.tif / .tiff / .png')
  })

  it('rejectMessage 为 null 时不渲染拒收提示', () => {
    render(
      <UploadPanel
        before={null}
        after={null}
        onBeforeChange={noopCount}
        onAfterChange={noopCount}
        onReject={noopCount}
        rejectMessage={null}
      />,
    )

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('拒收提示与上传槽位同处「影像输入」分组内（不会误认为请求已发出）', () => {
    render(
      <UploadPanel
        before={null}
        after={null}
        onBeforeChange={noopCount}
        onAfterChange={noopCount}
        onReject={noopCount}
        rejectMessage="notes.txt：文件类型不支持"
      />,
    )

    const group = screen.getByRole('group', { name: '影像输入' })
    expect(within(group).getByRole('alert')).toBeInTheDocument()
  })

  it('清除文件时会一并清掉拒收提示（onReject(null)）', async () => {
    const user = userEvent.setup()
    const onReject = vi.fn()
    render(
      <UploadPanel
        before={beforeFile()}
        after={null}
        onBeforeChange={noopCount}
        onAfterChange={noopCount}
        onReject={onReject}
        rejectMessage="先前的一条拒收提示"
      />,
    )

    await user.click(screen.getByRole('button', { name: '清除前时相影像' }))

    expect(onReject).toHaveBeenCalledWith(null)
  })
})

describe('DetectionButton 的禁用与加载态', () => {
  it('未选齐时禁用，并说明原因', () => {
    render(<DetectionButton ready={false} loading={false} onClick={vi.fn()} />)

    const button = screen.getByRole('button', { name: /开始检测/ })
    expect(button).toBeDisabled()
    expect(screen.getByText('请先选择前时相与后时相两张影像')).toBeInTheDocument()
    // 原因用 aria-describedby 挂到按钮上，读屏聚焦时一并播报。
    expect(button).toHaveAccessibleDescription('请先选择前时相与后时相两张影像')
  })

  it('选齐且空闲时可点，且不渲染禁用原因', () => {
    render(<DetectionButton ready loading={false} onClick={vi.fn()} />)

    expect(screen.getByRole('button', { name: /开始检测/ })).toBeEnabled()
    expect(screen.queryByText('请先选择前时相与后时相两张影像')).not.toBeInTheDocument()
  })

  it('loading 时禁用', () => {
    render(<DetectionButton ready loading onClick={vi.fn()} />)

    expect(screen.getByRole('button', { name: /检测中/ })).toBeDisabled()
  })

  it('loading 时按钮具 aria-busy（读屏知道是「忙」而非「不可用」）', () => {
    render(<DetectionButton ready loading onClick={vi.fn()} />)

    const button = screen.getByRole('button', { name: /检测中/ })
    expect(button).toHaveAttribute('aria-busy', 'true')
    expect(button).toHaveAttribute('aria-disabled', 'true')
  })

  it('loading 时文案切换为进行中，并说明禁用原因是「正在检测」', () => {
    render(<DetectionButton ready loading onClick={vi.fn()} />)

    expect(screen.getByText('检测中…')).toBeInTheDocument()
    expect(screen.getByText('正在检测，请等待本次结果返回')).toBeInTheDocument()
    // 不再是「请先选择…」——两种禁用原因的文案必须分开。
    expect(screen.queryByText('请先选择前时相与后时相两张影像')).not.toBeInTheDocument()
  })

  it('loading 时点击不触发 onClick', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(<DetectionButton ready loading onClick={onClick} />)

    await user.click(screen.getByRole('button', { name: /检测中/ }))

    expect(onClick).not.toHaveBeenCalled()
  })

  it('未选齐时点击不触发 onClick', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(<DetectionButton ready={false} loading={false} onClick={onClick} />)

    await user.click(screen.getByRole('button', { name: /开始检测/ }))

    expect(onClick).not.toHaveBeenCalled()
  })

  it('就绪时点击恰好触发一次', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(<DetectionButton ready loading={false} onClick={onClick} />)

    await user.click(screen.getByRole('button', { name: /开始检测/ }))

    expect(onClick).toHaveBeenCalledTimes(1)
  })
})

describe('UploadPanel 检测进行中时整体禁用', () => {
  it('disabled 时 fieldset 禁用，文件输入不可交互', () => {
    render(
      <UploadPanel
        before={null}
        after={null}
        onBeforeChange={vi.fn()}
        onAfterChange={vi.fn()}
        onReject={vi.fn()}
        rejectMessage={null}
        disabled
      />,
    )

    // `<fieldset disabled>` 会连带禁用内部所有表单控件，无需逐个处理。
    expect(screen.getByLabelText(/选择前时相影像/)).toBeDisabled()
    expect(screen.getByLabelText(/选择后时相影像/)).toBeDisabled()
  })

  it('未 disabled 时文件输入可交互', () => {
    render(
      <UploadPanel
        before={null}
        after={null}
        onBeforeChange={vi.fn()}
        onAfterChange={vi.fn()}
        onReject={vi.fn()}
        rejectMessage={null}
      />,
    )

    expect(screen.getByLabelText(/选择前时相影像/)).toBeEnabled()
  })

  it('检测进行中（loading）时按钮与文件输入同时不可交互', () => {
    render(<UploadHarness loading onDetectCount={noopCount} />)

    expect(screen.getByRole('button', { name: /检测中/ })).toBeDisabled()
    expect(screen.getByLabelText(/选择前时相影像/)).toBeDisabled()
  })
})

describe('可访问性：交互元素可被 role / label 查询到', () => {
  it('检测按钮可被 role 查询到', () => {
    render(<UploadHarness onDetectCount={noopCount} />)

    expect(screen.getByRole('button', { name: /开始检测/ })).toBeInTheDocument()
  })

  it('两个上传控件可被 aria-label 关联查询', () => {
    render(<UploadHarness onDetectCount={noopCount} />)

    // aria-label 里带上了接受格式，读屏不必再去找别处的提示。
    expect(screen.getByLabelText('选择前时相影像（.tif / .tiff / .png）')).toBeInTheDocument()
    expect(screen.getByLabelText('选择后时相影像（.tif / .tiff / .png）')).toBeInTheDocument()
  })

  it('上传控件可被可见标签关联查询（按文字即可定位）', () => {
    render(<UploadHarness onDetectCount={noopCount} />)

    expect(screen.getByLabelText(/选择前时相影像/)).toBeInTheDocument()
    expect(screen.getByLabelText(/选择后时相影像/)).toBeInTheDocument()
  })

  it('上传控件以 aria-describedby 关联格式说明', () => {
    render(<UploadHarness onDetectCount={noopCount} />)

    const input = screen.getByLabelText(/选择前时相影像/)
    expect(input).toHaveAccessibleDescription(/接受的文件格式：\.tif \/ \.tiff \/ \.png/)
  })

  it('分组有 legend，读屏能播报「影像输入」这一组', () => {
    render(<UploadHarness onDetectCount={noopCount} />)

    expect(screen.getByRole('group', { name: '影像输入' })).toBeInTheDocument()
  })

  it('已选态的「更换」「清除」按钮均有具名 aria-label', async () => {
    const user = userEvent.setup()
    render(<UploadHarness onDetectCount={noopCount} />)

    await user.upload(screen.getByLabelText(/选择前时相影像/), beforeFile())

    expect(screen.getByRole('button', { name: '更换前时相影像' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '清除前时相影像' })).toBeInTheDocument()
  })
})
