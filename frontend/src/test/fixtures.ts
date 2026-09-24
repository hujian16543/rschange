/**
 * 测试夹具：与契约**逐字段**对齐的响应与错误。
 *
 * 为什么不用「随便填一份能过类型检查的对象」：本套件的判据是「字段被真的渲染
 * 出来」。若夹具里的 `detector` 写成一个不含辨识度的值（如 `"x"`），或
 * `changed_area_m2` 填成整数恰好在各档位边界上，断言就可能碰巧通过——那样的
 * 测试对回归无判别力。故此处一律取 `backend/src/rschange/api/schemas/
 * detection.py` 的 `_EXAMPLE` 与 `docs/contracts.md` §9.10 的**真实锚点值**，
 * 让断言里的期望串与真实产物一致，字段缺失/错位必然被抓。
 *
 * 与 §9.10 的锚点对应关系：
 *
 * | 字段 | 值 | 出处 |
 * |---|---|---|
 * | `change_pixels` | `7209` | 真实夹具 256×256 影像 |
 * | `total_pixels` | `65536` | 256 × 256 |
 * | `change_rate` | `0.1100006103515625` | 7209 / 65536 |
 * | `threshold` | `5.916767423962816` | Otsu 阈值 |
 * | `pixel_area_m2` | `100.0` | 10 m 分辨率 |
 * | `changed_area_m2` | `720900.0` | 7209 × 100.0 |
 *
 * `geojson` / 三个 `image_*_url` / `image_corners` 一律**不**在类型里写死为
 * `null`，而是独立声明为 `string | null` 的常量：调用方需要 `null` 场景时
 * 直接覆盖字段（如 `{ ...EXAMPLE_RESPONSE, geojson: null }`），无需另造一份
 * 夹具，避免多份夹具随时间漂移。
 */

import type { DetectionResponse } from '@/types/detection'

/** 契约锚点：变化像元数。 */
export const EXAMPLE_CHANGE_PIXELS = 7209

/** 契约锚点：变化面积（平方米）。 */
export const EXAMPLE_CHANGED_AREA_M2 = 720900.0

/** 契约锚点：单像元面积（平方米）。 */
export const EXAMPLE_PIXEL_AREA_M2 = 100.0

/** 契约锚点：检测算法名。 `cva` 是当前唯一的注册检测器。 */
export const EXAMPLE_DETECTOR = 'cva'

/** 契约锚点：Otsu 阈值。 */
export const EXAMPLE_THRESHOLD = 5.916767423962816

/** `changed_area_m2` 经 `formatArea` 换算后的主展示串：`< 1e6 m²` → 公顷。 */
export const EXAMPLE_AREA_DISPLAY = '72.09 公顷'

/** `pixel_area_m2` 经 `formatPixelArea` 后的展示串。 */
export const EXAMPLE_PIXEL_AREA_DISPLAY = '100 m²'

/** `threshold` 经 `formatThreshold`（4 位小数）后的展示串。 */
export const EXAMPLE_THRESHOLD_DISPLAY = '5.9168'

/** `change_rate` 经 `formatRate`（×100，2 位小数）后的展示串。 */
export const EXAMPLE_RATE_DISPLAY = '11.00%'

/** 一份完整的成功响应，13 个字段一个不少。 */
export const EXAMPLE_RESPONSE: DetectionResponse = {
  change_pixels: EXAMPLE_CHANGE_PIXELS,
  total_pixels: 65536,
  change_rate: 0.1100006103515625,
  threshold: EXAMPLE_THRESHOLD,
  detector: EXAMPLE_DETECTOR,
  pixel_area_m2: EXAMPLE_PIXEL_AREA_M2,
  changed_area_m2: EXAMPLE_CHANGED_AREA_M2,
  geojson: '{"type": "FeatureCollection", "features": []}',
  image_before_url: '/api/image/8f3c1d9e_before.png',
  image_after_url: '/api/image/8f3c1d9e_after.png',
  image_diff_url: '/api/image/8f3c1d9e_diff.png',
  image_corners: [
    [117.0, 36.144718],
    [117.028456, 36.144715],
    [117.028448, 36.121634],
    [117.0, 36.121638],
  ],
  status: 'success',
}

/**
 * 边界形态的响应：可空字段全部取「无」。
 *
 * 覆盖 §9.3 允许的全部空值：`geojson` 为 `null`（后端在无变化区域时如此返回）、
 * 三张预览图为 `null`（预览生成失败）、`image_corners` 为空数组（长度为零，
 * 而非 `null`——两种「没有角点」的写法都要能扛住）。
 */
export const RESPONSE_WITH_NULLS: DetectionResponse = {
  ...EXAMPLE_RESPONSE,
  geojson: null,
  image_before_url: null,
  image_after_url: null,
  image_diff_url: null,
  image_corners: [],
}

/**
 * 构造两期影像的 `File` 对象。
 *
 * 走真实 `File` 而非鸭子类型对象：`UploadPanel` 用 `file.name` / `file.size`
 * 渲染，`client.ts` 会把它们塞进 `FormData`，只有真 `File` 才能同时满足——
 * 用 `{name, size}` 字面量过类型，测试就失去了对「文件被正确传递」的判别力。
 */
export function makeImageFile(name: string, bytes = 4096): File {
  return new File([new Uint8Array(bytes)], name, { type: 'image/tiff' })
}

/** 前时相影像（占位字节，内容不被前端读取）。 */
export function beforeFile(): File {
  return makeImageFile('before.tif')
}

/** 后时相影像。 */
export function afterFile(): File {
  return makeImageFile('after.tif')
}
