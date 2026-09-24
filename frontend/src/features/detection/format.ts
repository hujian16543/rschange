/**
 * 结果数值的展示格式化。
 *
 * 全部为纯函数，便于 T4.4 直接单测。**不使用** `toLocaleString` 做单位换算：
 * `toLocaleString` 的分组/小数分隔符随运行环境的 locale 变化，同一份结果在不同
 * 机器上会渲染成不同字符串，回归测试无法断言。分组统一用 `Intl.NumberFormat('en-US')`，
 * 小数一律用 `toFixed` 并在末位截断多余的零。
 */

/** 面积换算基准：1 公顷 = 10000 m²。 */
const M2_PER_HECTARE = 10_000

/** 面积换算基准：1 km² = 1_000_000 m²。 */
const M2_PER_KM2 = 1_000_000

/** 千分位分组器。显式指定 `en-US` 以固定分隔符，见文件头说明。 */
const grouped = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })

/**
 * 整数千分位分组。
 *
 * @param value 待格式化的数值
 * @returns 形如 `7,209` 的字符串
 */
export function formatInteger(value: number): string {
  return grouped.format(value)
}

/**
 * 面积的主展示串。
 *
 * 按量级自动选单位，避免把 `720900 m²` 这种 6 位数直接甩给用户：
 *
 * | 量级 | 单位 | 样例 |
 * |---|---|---|
 * | `< 10000 m²` | m² | `9,999 m²` |
 * | `< 1e6 m²` | 公顷 | `72.09 公顷` |
 * | `>= 1e6 m²` | km² | `1.50 km²` |
 *
 * @param areaM2 面积（平方米）
 * @returns 带单位的展示串
 */
export function formatArea(areaM2: number): string {
  if (!Number.isFinite(areaM2) || areaM2 < 0) return '—'

  if (areaM2 < M2_PER_HECTARE) {
    return `${grouped.format(areaM2)} m²`
  }

  if (areaM2 < M2_PER_KM2) {
    return `${trimTrailingZeros((areaM2 / M2_PER_HECTARE).toFixed(2))} 公顷`
  }

  return `${trimTrailingZeros((areaM2 / M2_PER_KM2).toFixed(2))} km²`
}

/**
 * 同时给出 m² 原值与换算值的辅助串，用于悬浮提示。
 *
 * 主展示串换了单位后原始平方米数就丢了，而契约锚点（`720900 m²`）是核对
 * 结果的依据，故以 `title` 形式保留，做到「主视图好读、取证可查」。
 *
 * @param areaM2 面积（平方米）
 * @returns 形如 `720,900 m²` 的字符串
 */
export function formatAreaExact(areaM2: number): string {
  if (!Number.isFinite(areaM2) || areaM2 < 0) return '—'
  return `${grouped.format(areaM2)} m²`
}

/**
 * 单像元面积展示。
 *
 * 该值通常带小数（如 `100.0 m²`），且量级很小，换算成公顷反而不可读，
 * 故直接以 m² 展示、保留两位小数，不做量级切换。
 *
 * @param pixelAreaM2 单像元面积（平方米）
 * @returns 形如 `100.00 m²` 的字符串
 */
export function formatPixelArea(pixelAreaM2: number): string {
  if (!Number.isFinite(pixelAreaM2) || pixelAreaM2 <= 0) return '—'
  return `${trimTrailingZeros(pixelAreaM2.toFixed(2))} m²`
}

/**
 * 变化率百分比。
 *
 * 契约给定 `change_rate` 取值 `[0, 1]`（§9.3），故乘 100 后拼 `%`。
 * 保留两位小数，与旧前端一致。
 *
 * @param rate 变化率，取值 `[0, 1]`
 * @returns 形如 `11.00%` 的字符串
 */
export function formatRate(rate: number): string {
  if (!Number.isFinite(rate)) return '—'
  return `${(rate * 100).toFixed(2)}%`
}

/**
 * 判定阈值展示。
 *
 * Otsu 阈值量级约在个位数（契约锚点 `5.9168`），4 位小数足以区分不同影像，
 * 再多只会增加视觉噪声。
 *
 * @param threshold 检测判定阈值
 * @returns 形如 `5.9168` 的字符串
 */
export function formatThreshold(threshold: number): string {
  if (!Number.isFinite(threshold)) return '—'
  return threshold.toFixed(4)
}

/**
 * 去掉定点小数字符串末尾多余的零（`72.10` → `72.1`，`72.00` → `72`）。
 *
 * 直接 `parseFloat(value).toString()` 也能达到同样效果，但会把 `1000000`
 * 之类的大数转成指数记法（`1e+6`），故改用字符串裁剪。
 */
function trimTrailingZeros(value: string): string {
  if (!value.includes('.')) return value

  const trimmed = value.replace(/0+$/, '')
  return trimmed.endsWith('.') ? trimmed.slice(0, -1) : trimmed
}
