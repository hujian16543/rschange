/**
 * 检测结果面板。
 *
 * 本组件是 T4.2 的核心交付点：旧前端只展示 10 个字段，这里必须补齐 T4.1 类型里
 * 已有的三个新增契约字段（§9.3）：
 *
 * * `changed_area_m2` —— 真实变化面积，本场景的**核心指标**，放在统计区首行并以
 *   `change` 强调色 + 更大字号突显，不埋在列表里。
 * * `pixel_area_m2` —— 单像元面积，作为解释「像元数 → 面积」换算依据的次要信息。
 * * `detector` —— 实际使用的算法名，结果溯源用。同一份影像换了算法结论会变，
 *   不知道用的哪个算法，这份结果就不可复现。
 */

import { useCallback, useMemo } from 'react'

import { imageUrl } from '@/api/client'
import { Card, StatList, StatRow } from '@/components/ui'
import {
  formatArea,
  formatAreaExact,
  formatInteger,
  formatPixelArea,
  formatRate,
  formatThreshold,
} from '@/features/detection/format'
import type { DetectionResponse, LonLat } from '@/types/detection'

export interface ResultPanelProps {
  /** 检测成功响应（§9.3）。 */
  result: DetectionResponse
}

/** 预览图条目的原始形态，`url` 允许缺失。 */
interface PreviewItem {
  /** 稳定 key，兼作语义标识。 */
  key: 'before' | 'after' | 'diff'
  /** 图注。 */
  caption: string
  /** 图片地址；后端可能返回 `null`。 */
  url: string | null
}

/** 已取到 URL 的预览图条目。 */
interface AvailablePreview {
  key: PreviewItem['key']
  caption: string
  url: string
}

/**
 * 类型谓词：筛出已取到 URL 的条目。
 *
 * 判据是 `imageUrl`（`null` 与空串都归为「无」）而非单纯的 `!== null`：
 * 契约（§9.3）允许这三个字段为 `null`，但空串同样是「没有预览图」的一种表达，
 * 若只判 `null`，空串会一路传到 `<img src="">`，浏览器按当前页面地址发起请求，
 * 结果是可见的破图加一次无意义的网络往返。
 *
 * 显式声明为谓词而非内联箭头函数，是为了让收窄后的类型有个可命名的落点，
 * 也避免内联谓词在 `readonly` 数组上触发「谓词类型不可赋值给参数类型」的报错。
 */
function isAvailable(item: PreviewItem): item is AvailablePreview {
  return imageUrl(item.url) !== null
}

/**
 * 检测结果展示。
 *
 * 布局分三块：核心指标 → 三图对比 → 明细统计。核心指标置顶是刻意的——用户打开
 * 结果第一眼要的是「变了多少」，而不是像元数或阈值。
 */
export function ResultPanel({ result }: ResultPanelProps) {
  /**
   * 三张预览图；任一缺失则整块不渲染，避免出现破图占位。
   *
   * 先用 `imageUrl` 把 `null` 与空串统一归一为「无」，再用类型谓词过滤出可用
   * 条目，`url` 被收窄为 `string`，下游无需再断言——`Array.prototype.every`
   * 不会收窄原数组元素类型，故不用它做守卫。
   */
  const previews = useMemo<readonly AvailablePreview[]>(() => {
    const candidates: PreviewItem[] = [
      { key: 'before', caption: '前时相', url: imageUrl(result.image_before_url) },
      { key: 'after', caption: '后时相', url: imageUrl(result.image_after_url) },
      { key: 'diff', caption: '变化检测（红色为变化区域）', url: imageUrl(result.image_diff_url) },
    ]

    return candidates.filter(isAvailable)
  }, [result.image_before_url, result.image_after_url, result.image_diff_url])

  const allPreviewsAvailable = previews.length === 3

  return (
    <div className="space-y-section">
      <ChangedAreaHighlight result={result} />

      {allPreviewsAvailable && (
        <Card title="影像对比" headingLevel={3}>
          <div className="grid gap-section sm:grid-cols-3">
            {previews.map((item) => (
              <PreviewFigure
                key={item.key}
                caption={item.caption}
                url={item.url}
                highlight={item.key === 'diff'}
              />
            ))}
          </div>
        </Card>
      )}

      <Card title="统计明细" headingLevel={3}>
        <StatList>
          <StatRow label="变化像元" value={formatInteger(result.change_pixels)} />
          <StatRow label="影像总像元" value={formatInteger(result.total_pixels)} />
          <StatRow label="变化率" value={formatRate(result.change_rate)} emphasis="change" />
          <StatRow
            label="单像元面积"
            value={formatPixelArea(result.pixel_area_m2)}
            hint="由影像分辨率反算，用于把像元数换算为真实面积"
          />
          <StatRow label="判定阈值" value={formatThreshold(result.threshold)} />
          <StatRow
            label="检测算法"
            value={result.detector}
            emphasis="primary"
            hint="本次结果由该算法产出，用于结果溯源"
          />
        </StatList>
      </Card>

      <GeoJsonActions result={result} corners={result.image_corners} />
    </div>
  )
}

export interface ChangedAreaHighlightProps {
  /** 检测成功响应。 */
  result: DetectionResponse
}

/**
 * 核心指标卡：真实变化面积。
 *
 * 单独成块而非并入统计列表，因为它是本场景唯一「一眼要看懂」的数字。
 * 主值按量级换单位（`72.09 公顷`），`title` 保留原始平方米数（`720,900 m²`）
 * 以便与契约锚点核对——换单位不能丢掉取证能力。
 */
function ChangedAreaHighlight({ result }: ChangedAreaHighlightProps) {
  return (
    <Card headingLevel={3}>
      <p className="text-caption text-text-muted">真实变化面积</p>
      <p
        className="mt-0.5 text-2xl font-semibold tabular-nums text-change"
        title={formatAreaExact(result.changed_area_m2)}
      >
        {formatArea(result.changed_area_m2)}
      </p>
      <p className="mt-1 text-caption text-text-muted">
        {`= ${formatInteger(result.change_pixels)} 像元 × ${formatPixelArea(result.pixel_area_m2)}`}
      </p>
    </Card>
  )
}

export interface PreviewFigureProps {
  /** 图注。 */
  caption: string
  /** 图片地址；调用方保证非空。 */
  url: string
  /** 是否以变化区域的红色描边强调（diff 图）。 */
  highlight: boolean
}

/**
 * 单张预览图。
 *
 * `<img>` 必须带 `alt`：这里用图注作为等价描述（图片内容即该时相影像，
 * 图注已说明是哪个时相），而非留空 `alt=""`——留空会被读屏整块跳过，
 * 用户不知道这里有几张图。
 */
function PreviewFigure({ caption, url, highlight }: PreviewFigureProps) {
  return (
    <figure className="space-y-1">
      <figcaption className="text-caption text-text-muted">{caption}</figcaption>
      <img
        src={url}
        alt={caption}
        loading="lazy"
        className={[
          'w-full rounded-control border bg-surface-raised object-contain',
          highlight ? 'border-change-border' : 'border-border',
        ].join(' ')}
      />
    </figure>
  )
}

export interface GeoJsonActionsProps {
  /** 检测成功响应。 */
  result: DetectionResponse
  /** 四角经纬度；用于展示成像范围。 */
  corners: LonLat[] | null
}

/**
 * GeoJSON 下载与成像范围展示。
 *
 * 旧前端拿 `geojson` 却完全没用上。这里做两件事：提供下载（`Blob` + `URL.createObjectURL`），
 * 以及展示成像范围四角，使用户能把结果与底图对上位置。
 *
 * `geojson` 为 `null` 时不渲染下载按钮——后端在无变化区域时会返回 `null`，
 * 此时按一个点了没反应的按钮比没有按钮更糟。
 */
function GeoJsonActions({ result, corners }: GeoJsonActionsProps) {
  const download = useCallback((): void => {
    const blob = new Blob([result.geojson ?? ''], { type: 'application/geo+json' })
    const href = URL.createObjectURL(blob)

    const anchor = document.createElement('a')
    anchor.href = href
    anchor.download = 'change-regions.geojson'
    anchor.click()

    // 立即回收：对象 URL 会持有 blob 直到页面卸载，长会话里会持续占内存。
    URL.revokeObjectURL(href)
  }, [result.geojson])

  const hasGeoJson = result.geojson !== null && result.geojson !== ''

  if (!hasGeoJson && corners === null) return null

  return (
    <Card title="矢量与范围" headingLevel={3}>
      <div className="space-y-section">
        {hasGeoJson && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-control border border-change-border bg-change-muted px-2 py-0.5 text-caption text-change-strong">
              变化区域已矢量化
            </span>
            <button
              type="button"
              onClick={download}
              className="rounded-control border border-border bg-surface px-3 py-1.5 text-caption text-text-secondary transition-colors hover:border-border-strong hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              下载 GeoJSON
            </button>
          </div>
        )}

        {corners !== null && <CornersTable corners={corners} />}
      </div>
    </Card>
  )
}

export interface CornersTableProps {
  /** 四角经纬度，顺序为左上、右上、右下、左下。 */
  corners: LonLat[]
}

/** 角点名称，与契约顺序（左上、右上、右下、左下）一一对应。 */
const CORNER_LABELS = ['左上', '右上', '右下', '左下'] as const

/**
 * 成像范围四角经纬度。
 *
 * `index` 访问 `CORNER_LABELS` 在 `noUncheckedIndexedAccess` 下返回
 * `string | undefined`，故取不到名字时退化为「角点 N」，而不是用 `!` 断言。
 */
function CornersTable({ corners }: CornersTableProps) {
  return (
    <StatList>
      {corners.map((corner, index) => {
        const label = CORNER_LABELS[index] ?? `角点 ${index + 1}`
        return (
          <StatRow
            key={label}
            label={label}
            value={formatCoordinate(corner)}
          />
        )
      })}
    </StatList>
  )
}

/**
 * 经纬度展示。
 *
 * `LonLat` 是定长元组 `[lon, lat]`，解构即得 `number`——这正是 T4.1 把它
 * 声明为元组而非 `number[]` 的收益（见 `types/detection.ts` 注释），
 * 在 `noUncheckedIndexedAccess` 下也无需再判空。
 */
function formatCoordinate(corner: LonLat): string {
  const [lon, lat] = corner
  return `${lon.toFixed(5)}°, ${lat.toFixed(5)}°`
}
