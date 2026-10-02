/**
 * 变化检测接口的前端类型定义。
 *
 * 契约来源：`docs/contracts.md` §9.3（成功响应）与 §9.4/§9.5（错误响应），
 * 权威实现为 `backend/src/rschange/api/schemas/detection.py`。字段一经冻结，
 * 增删须走契约变更流程（§8），前端类型必须同步。
 */

/**
 * `image_corners` 的单个角点，形如 `[经度, 纬度]`。
 *
 * 声明为定长元组而非 `number[]`：契约固定为四角四点，定长元组能让下游解构
 * `const [lon, lat] = corner` 直接得到 `number`，在 `noUncheckedIndexedAccess`
 * 下也无需再判空。
 */
export type LonLat = [number, number]

/**
 * `POST /api/detect` 的成功响应（§9.3，共 12 个字段）。
 *
 * 与旧前端的差异：新增 `detector` / `pixel_area_m2` / `changed_area_m2`
 * 三个字段。前者用于结果追溯（可插拔检测器下，必须知道这份结果是哪个算法
 * 算出来的），后两者给出以平方米计的真实面积。
 *
 * `status` 字段已于 `v0.5.0` 移除（原为第 13 个字段）：它恒为 `"success"`，
 * 不携带任何信息。
 */
export interface DetectionResponse {
  /** 变化像元数（后处理后） */
  change_pixels: number
  /** 影像总像元数（恒 > 0） */
  total_pixels: number
  /** 变化像元占比，取值 [0, 1] */
  change_rate: number
  /** 检测算法使用的判定阈值 */
  threshold: number
  /** 实际使用的检测算法名，用于结果追溯 */
  detector: string
  /** 单像元面积（平方米，恒 > 0） */
  pixel_area_m2: number
  /** 真实变化面积（平方米）= `change_pixels × pixel_area_m2` */
  changed_area_m2: number
  /** 变化区域的 GeoJSON `FeatureCollection`（坐标已为 WGS84 经纬度） */
  geojson: string | null
  /** 前一期影像预览图 URL */
  image_before_url: string | null
  /** 后一期影像预览图 URL */
  image_after_url: string | null
  /** 变化叠加预览图 URL */
  image_diff_url: string | null
  /** 影像四角经纬度，顺序为**左上、右上、右下、左下**，用于地图定位 */
  image_corners: LonLat[] | null
}

/**
 * `GET /api/image/{filename}` 返回 404 时使用的错误码。
 *
 * 见 §9.5 补充行：`HTTPException` 由 `_http_error` 接管，`code` 取 `http_<状态码>`。
 * 声明为字面量类型，便于调用方在 `switch` 中获得穷尽性检查。
 */
export type ImageNotFoundCode = 'http_404'

/**
 * 后端错误码（§9.5 §9.8，与 `rschange.errors` 一一对应）。
 *
 * 前端**按 `code` 分支**决定提示文案与可恢复动作，不得依赖 `detail` 文案匹配：
 * `detail` 是脱敏后的展示串，措辞随版本变化，而 `code` 是稳定契约。
 *
 * 该联合类型是「已知码」的清单；服务端新增领域异常时会引入新码，故解析层仍
 * 允许任意 `string` 通行（见 `ApiError.code`），未知码走兜底分支展示即可。
 */
export type ApiErrorCode =
  | 'internal_error'
  | 'config_error'
  | 'crs_error'
  | 'engine_error'
  | 'engine_load_error'
  | 'input_validation_error'
  | 'processing_error'
  | 'raster_read_error'
  | 'raster_write_error'
  | 'unknown_detector'
  | 'unsupported_format'
  | 'upload_too_large'
  | 'request_validation_error'

/**
 * 后端错误响应体的数据部分（§9.4）。
 *
 * 旧前端的错误处理只读 `detail`，拿不到 `code`，只能用文案匹配错误类型——文案
 * 是脱敏展示串，随时可能改写，据此分支必然失效。本类型把 `code` 提升为一等公民。
 */
export interface ApiErrorPayload {
  /** 脱敏后的错误描述（仅供展示，禁止用于分支判断） */
  detail: string
  /** 机器可读错误码（snake_case） */
  code: string
}
