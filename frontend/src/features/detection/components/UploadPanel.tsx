/**
 * 两期影像上传面板。
 *
 * 与旧版（`UploadPanel.tsx` 72 行）的差异：
 *
 * 1. 上传槽位拆成同文件内的 `FileSlot`，但把「已选文件」与「未选文件」两个
 *    分支都做成可操作控件——旧版只有空态是 dropzone，选中后只剩一个清除按钮，
 *    键盘用户无法替换文件，只能先清除再重选。本版已选态提供「更换」按钮，
 *    经 dropzone 的 `open()` 重新唤起文件选择框。
 * 2. 拒收（扩展名不符、超过 `maxSize`）不再静默丢弃：旧版 `onDrop` 只处理
 *    `accepted`，被拒文件毫无反馈，用户会以为「点了没反应」。本版把
 *    `onDropRejected` 的错误码映射成可读原因并回调给父级。
 * 3. 扩展名白名单与后端 `ALLOWED_EXTENSIONS`（§9.2）对齐：`.tif` / `.tiff` / `.png`。
 *    旧版漏了 `.png`，导致后端接受的 PNG 在前端选不了。
 */

import type { ReactNode } from 'react'
import { useCallback, useId, useMemo } from 'react'
import type { FileRejection } from 'react-dropzone'
import { useDropzone } from 'react-dropzone'

import { Button } from '@/components/ui'

/** 与后端 `ALLOWED_EXTENSIONS`（§9.2）逐项对齐。 */
const ACCEPTED_EXTENSIONS = ['.tif', '.tiff', '.png'] as const

/** MIME → 扩展名映射。`image/tiff` 是 .tif/.tiff 的实际上报类型。 */
const DROPZONE_ACCEPT = {
  'image/tiff': ['.tif', '.tiff'],
  'image/png': ['.png'],
} as const

/** 单文件体积上限（字节），与 §9.2 的默认 `max_upload_mb = 500` 对齐。 */
const MAX_FILE_BYTES = 500 * 1024 * 1024

/** 人类可读的扩展名清单，用于提示文案。 */
const EXTENSION_HINT = ACCEPTED_EXTENSIONS.join(' / ')

/**
 * dropzone 的拒收错误码 → 中文原因。
 *
 * 只翻译内置码（`ErrorCode` 枚举的四个值）；未知码回退到库自带的英文
 * `message`，保证新增错误类型时至少有信息可看，而不是吞掉。
 */
const REJECTION_REASON: Record<string, string> = {
  'file-invalid-type': `文件类型不支持（仅接受 ${EXTENSION_HINT}）`,
  'file-too-large': '文件超过 500 MB 上限',
  'file-too-small': '文件为空',
  'too-many-files': '一次只能选择一个文件',
}

export interface UploadPanelProps {
  /** 前时相影像；未选为 `null`。 */
  before: File | null
  /** 后时相影像；未选为 `null`。 */
  after: File | null
  /** 前时相变更回调；清除时传 `null`。 */
  onBeforeChange: (file: File | null) => void
  /** 后时相变更回调；清除时传 `null`。 */
  onAfterChange: (file: File | null) => void
  /**
   * 本地校验失败时的提示（扩展名/体积），`null` 表示清除。
   *
   * 与后端错误分开传递：这是**选文件阶段**的问题，尚未发请求，混进 API 错误区
   * 会让人误以为请求已经发出去了。
   */
  onReject: (reason: string | null) => void
  /** 本地校验失败的提示文案；`null` 表示无。 */
  rejectMessage: string | null
  /** 是否禁用交互（检测进行中）。 */
  disabled?: boolean
}

/**
 * 两期影像上传面板。
 *
 * 两个槽位用 `<fieldset disabled>` 统一禁用：置 `disabled` 后内部所有表单控件
 * （含 dropzone 的隐藏 `<input type="file">`）一并不可交互，无需逐个处理。
 * 注意 `<fieldset>` 需配合 `<legend>` 才能被读屏正确播报分组名。
 */
export function UploadPanel({
  before,
  after,
  onBeforeChange,
  onAfterChange,
  onReject,
  rejectMessage,
  disabled = false,
}: UploadPanelProps) {
  return (
    <fieldset disabled={disabled} className="space-y-section disabled:opacity-60">
      <legend className="mb-2 text-body font-semibold text-text-primary">影像输入</legend>

      <FileSlot
        label="前时相影像"
        hint="before"
        file={before}
        onChange={onBeforeChange}
        onReject={onReject}
      />
      <FileSlot
        label="后时相影像"
        hint="after"
        file={after}
        onChange={onAfterChange}
        onReject={onReject}
      />

      {rejectMessage !== null && (
        <p role="alert" className="text-caption text-danger">
          {rejectMessage}
        </p>
      )}
    </fieldset>
  )
}

export interface FileSlotProps {
  /** 槽位名称，如「前时相影像」。 */
  label: string
  /** 与后端字段名对应的短标识，用于提示补充说明。 */
  hint: string
  /** 当前已选文件。 */
  file: File | null
  /** 文件变更回调。 */
  onChange: (file: File | null) => void
  /** 拒收回调。 */
  onReject: (reason: string | null) => void
}

/**
 * 单个影像槽位。
 *
 * 空态渲染 dropzone 拖放区（`getRootProps` 自带 `role="presentation"` 之外，
 * 也会接管键盘 Enter/Space）；已选态渲染文件名 + 「更换」/「清除」。
 */
function FileSlot({ label, hint, file, onChange, onReject }: FileSlotProps) {
  const labelId = useId()
  const descriptionId = useId()

  const handleDrop = useCallback(
    (accepted: File[], rejections: FileRejection[]): void => {
      // `noUncheckedIndexedAccess` 下 `accepted[0]` 的类型是 `File | undefined`，
      // 必须显式判空才能使用——这是本项的硬约束，靠 `!` 或 `as` 绕过是禁止的。
      const first = accepted[0]
      if (first !== undefined) {
        onReject(null)
        onChange(first)
        return
      }

      const rejection = rejections[0]
      if (rejection === undefined) return

      const firstError = rejection.errors[0]
      if (firstError === undefined) return

      onReject(
        `${rejection.file.name}：${REJECTION_REASON[firstError.code] ?? firstError.message}`,
      )
    },
    [onChange, onReject],
  )

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop: handleDrop,
    accept: DROPZONE_ACCEPT,
    maxFiles: 1,
    maxSize: MAX_FILE_BYTES,
    multiple: false,
  })

  const handleClear = useCallback((): void => {
    onReject(null)
    onChange(null)
  }, [onChange, onReject])

  const handleReplace = useCallback((): void => {
    onReject(null)
    open()
  }, [onReject, open])

  /**
   * 文件输入上同时给出 `aria-label` 与 `aria-describedby`。
   *
   * `aria-labelledby` 指向可见标签在 dropzone 场景下会被 `getRootProps` 的
   * 展开顺序影响，故用固定字符串更稳；描述串说明可选格式，替代肉眼读提示。
   */
  const inputAria = useMemo(
    () => ({
      'aria-label': `选择${label}（${EXTENSION_HINT}）`,
      'aria-describedby': descriptionId,
    }),
    [label, descriptionId],
  )

  return (
    <div className="space-y-1">
      <span id={labelId} className="block text-caption font-medium text-text-secondary">
        {label}
        <span className="ml-1 font-normal text-text-muted">({hint})</span>
      </span>

      {file === null ? (
        <div
          {...getRootProps()}
          aria-labelledby={labelId}
          className={[
            'flex cursor-pointer flex-col items-center gap-1 rounded-control border-2 border-dashed',
            'px-3 py-4 text-center transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
            isDragActive
              ? 'border-accent bg-accent-muted text-accent'
              : 'border-border bg-surface-raised text-text-muted hover:border-border-strong',
          ].join(' ')}
        >
          <input {...getInputProps(inputAria)} />
          <UploadGlyph />
          <span className="text-caption">拖拽或点击选择 {EXTENSION_HINT}</span>
        </div>
      ) : (
        <div className="flex items-center gap-1.5 rounded-control border border-border bg-surface-raised px-3 py-2">
          <FileGlyph />
          <span
            className="min-w-0 flex-1 truncate text-caption text-text-secondary"
            title={file.name}
          >
            {file.name}
          </span>
          <span className="shrink-0 tabular-nums text-caption text-text-muted">
            {formatFileSize(file.size)}
          </span>
          {/* 已选态仍需一个 file input 承载「更换」；`open()` 唤起它。
              置 `sr-only` 而非 `hidden`，保证可被脚本点击。 */}
          <input {...getInputProps(inputAria)} className="sr-only" />
          <Button size="sm" variant="ghost" onClick={handleReplace} aria-label={`更换${label}`}>
            更换
          </Button>
          <Button size="sm" variant="ghost" onClick={handleClear} aria-label={`清除${label}`}>
            清除
          </Button>
        </div>
      )}

      {/* 稳定的描述锚点：读屏聚焦输入时播报可选格式。 */}
      <span id={descriptionId} className="sr-only">
        {`${label}接受的文件格式：${EXTENSION_HINT}，单文件不超过 500 MB`}
      </span>
    </div>
  )
}

/** 体积展示：MB 为主，小于 1 MB 时退到 KB。 */
function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** 上传图标（内联 SVG，避免为一个图标引入整包图标库）。 */
function UploadGlyph(): ReactNode {
  return (
    <svg
      width={18}
      height={18}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <path d="M17 8l-5-5-5 5" />
      <path d="M12 3v12" />
    </svg>
  )
}

/** 文件图标。 */
function FileGlyph(): ReactNode {
  return (
    <svg
      width={14}
      height={14}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0 text-text-muted"
      aria-hidden="true"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
    </svg>
  )
}

/** 本地校验常量出口，供测试与文档引用。 */
export { ACCEPTED_EXTENSIONS, MAX_FILE_BYTES }
