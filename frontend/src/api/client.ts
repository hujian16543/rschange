/**
 * 变化检测 HTTP 客户端。
 *
 * 契约来源：`docs/contracts.md` §9。三个约定必须守住：
 *
 * 1. 基址取相对路径 `/api`，由 Vite dev server 代理到 `http://localhost:8000`
 *    （见 `vite.config.ts`）。**禁止**硬编码主机名——旧前端用了 `http://localhost:8000`
 *    字面串，部署到同源反代后必然失效。
 * 2. 错误响应体为 `{detail, code}`（§9.4）。`detail` 是脱敏文案仅供展示，`code`
 *    才是机器可读的分支依据，必须随错误一并抛给调用方。
 * 3. 网络层异常（`fetch` reject）与 HTTP 层错误（响应到达但状态码非 2xx）性质不同：
 *    前者是「没连上」，后者是「连上了但服务端拒绝」。两者用不同错误类区分，调用方
 *    才能给出可操作的提示。
 */

import type { ApiErrorPayload, DetectionResponse } from '@/types/detection'

/** 业务路由前缀，与后端 `app.py` 的 `API_PREFIX` 一致（§9）。 */
const API_BASE = '/api'

/**
 * 后端返回错误响应时抛出的异常。
 *
 * 继承 `Error` 并附加三个结构化字段，使调用方能**按 `code` 分支**而不是靠文案
 * 匹配（旧前端的做法，已确认是错误行为）：
 *
 * ```ts
 * catch (e) {
 *   if (e instanceof ApiError && e.code === 'upload_too_large') { ... }
 * }
 * ```
 */
export class ApiError extends Error {
  /** HTTP 状态码；网络层失败时为 `0`。 */
  readonly status: number
  /** 机器可读错误码（snake_case，§9.5）。未知码原样透传，由调用方兜底展示。 */
  readonly code: string

  constructor(message: string, status: number, code: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

/**
 * 请求未抵达服务端时抛出的异常（DNS 失败、连接被拒、请求被中断等）。
 *
 * 与 `ApiError` 分开，是因为恢复动作完全不同：`ApiError` 提示用户改输入，
 * 本类提示用户检查服务是否在运行。
 */
export class NetworkError extends Error {
  /**
   * 原始异常（可能不是 `Error` 实例，故为 `unknown`）。
   *
   * `Error` 基类自 ES2022 起已有 `cause`，故此处必须标注 `override`
   * （`noImplicitOverride`）；类型收窄为 `unknown` 是安全的——父类声明为
   * `unknown`，子类比父类更具体才需报错，这里恰好等宽。
   */
  override readonly cause: unknown

  constructor(message: string, cause: unknown) {
    super(message)
    this.name = 'NetworkError'
    this.cause = cause
  }
}

/** 是否为「对象且非 null」，用于在 `unknown` 上安全地做属性探测。 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/**
 * 从任意 `unknown` 中提取 `{detail, code}`。
 *
 * 响应体来自网络，形状不可信，故逐字段做类型守卫后再取值；两个字段都缺失时
 * 调用方回退到基于状态码的通用文案。此处**不使用** `as` 断言：一旦后端换了
 * 形状，这里返回 `null`，调用方走兜底分支，而不是把 `undefined` 当成 `string`
 * 用下去。
 */
function parseErrorPayload(raw: unknown): ApiErrorPayload | null {
  if (!isRecord(raw)) return null

  const { detail, code } = raw
  if (typeof detail !== 'string' || typeof code !== 'string') return null

  return { detail, code }
}

/**
 * 判断一个 `unknown` 是否满足 `DetectionResponse` 的**关键**字段约束。
 *
 * 只校验数值字段与 `detector`：URL 与 `geojson` 允许为 `null`，`image_corners`
 * 结构较深，交由消费方按需判空。目的不是做完整运行时校验，而是拦住
 * 「后端返回了一个形状完全不对的东西」这种情形。
 */
function isDetectionResponse(raw: unknown): raw is DetectionResponse {
  if (!isRecord(raw)) return false

  const { change_pixels, total_pixels, change_rate, threshold, detector, pixel_area_m2, changed_area_m2 } =
    raw

  return (
    typeof change_pixels === 'number' &&
    typeof total_pixels === 'number' &&
    typeof change_rate === 'number' &&
    typeof threshold === 'number' &&
    typeof detector === 'string' &&
    typeof pixel_area_m2 === 'number' &&
    typeof changed_area_m2 === 'number'
  )
}

/**
 * 上传两期影像，执行变化检测。
 *
 * @param before 前一期影像文件
 * @param after 后一期影像文件
 * @returns 检测结果（§9.3）
 * @throws {NetworkError} 请求未能抵达服务端
 * @throws {ApiError} 服务端返回非 2xx（含 `code`，见 §9.5）
 */
export async function detectChange(
  before: File,
  after: File,
): Promise<DetectionResponse> {
  const form = new FormData()
  form.append('before', before)
  form.append('after', after)

  let response: Response
  try {
    response = await fetch(`${API_BASE}/detect`, { method: 'POST', body: form })
  } catch (cause) {
    throw new NetworkError('无法连接到检测服务，请确认后端已启动', cause)
  }

  if (!response.ok) {
    // 错误体的读取本身也可能失败（如响应被截断），失败时退回通用文案。
    let payload: ApiErrorPayload | null = null
    try {
      payload = parseErrorPayload(await response.json())
    } catch {
      payload = null
    }

    const detail = payload?.detail ?? `请求失败（HTTP ${response.status}）`
    // 无 `code` 时用状态码合成一个稳定的回退码，保证 `code` 恒为非空字符串，
    // 调用方无需为「错误对象没有 code」再写一层分支。
    const code = payload?.code ?? `http_${response.status}`

    throw new ApiError(detail, response.status, code)
  }

  const data: unknown = await response.json()
  if (!isDetectionResponse(data)) {
    throw new ApiError('服务端返回的数据格式不符合契约', response.status, 'invalid_response')
  }

  return data
}

/** 由预览图 URL 构造可直接用于 `<img src>` 的地址。 */
export function imageUrl(url: string | null): string | null {
  return url === null || url === '' ? null : url
}
