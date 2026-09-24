/**
 * 错误 → 用户可读提示的映射。
 *
 * 契约依据：`docs/contracts.md` §9.5（状态码/错误码映射）与 §9.4。
 * **必须按 `code` 分支**，不得匹配 `detail` 文案——`detail` 是脱敏展示串，
 * 措辞随版本变化，只有 `code` 是稳定契约。
 */

import { ApiError, NetworkError } from '@/api/client'

/** 提示的展示形态。 */
export interface ErrorPresentation {
  /** 一句话说明发生了什么。 */
  title: string
  /**
   * 可恢复的下一步动作。
   *
   * 与 `title` 分开是因为二者的受众不同：`title` 说明现象，`advice` 指导操作。
   * 无条件展示一句「请重试」会稀释真正有用的信息，故按错误码给出针对性建议。
   */
  advice: string
  /** 是否属于「重试可能有用」的瞬时故障。 */
  retryable: boolean
}

/**
 * 已知错误码到提示的映射（§9.5 的 12 个领域码 + 2 个补充码）。
 *
 * 未列出的码（服务端新增领域异常时会出现）走 `UNKNOWN_API_ERROR` 兜底，
 * 并且提示里会带上原始 `code`，便于用户报障时定位。
 */
const CODE_MESSAGE: Record<string, Omit<ErrorPresentation, 'retryable'> & { retryable?: boolean }> = {
  // ---- 输入类：用户可自行修正 ----
  unsupported_format: {
    title: '影像格式不受支持',
    advice: '仅支持 .tif、.tiff、.png 三种扩展名，请重新选择文件。',
    retryable: false,
  },
  upload_too_large: {
    title: '影像超过体积上限',
    advice: '单文件上限由服务端 runtime.max_upload_mb 配置决定，请先裁剪或压缩影像。',
    retryable: false,
  },
  raster_read_error: {
    title: '影像无法读取',
    advice: '文件可能损坏或不是有效栅格，请确认两期影像均可正常打开。',
    retryable: false,
  },
  crs_error: {
    title: '影像坐标系有问题',
    advice: '两期影像需具备有效且一致的投影信息，请检查数据源。',
    retryable: false,
  },
  input_validation_error: {
    title: '影像不符合处理要求',
    advice: '请确认两期影像的尺寸与波段数一致，且均含有有效像元。',
    retryable: false,
  },
  unknown_detector: {
    title: '检测算法未注册',
    advice: '服务端配置指向了未注册的检测器，需联系管理员检查 detector 配置项。',
    retryable: false,
  },
  request_validation_error: {
    title: '请求参数不符合要求',
    advice: '请确认已同时选择前时相与后时相两张影像后重试。',
    retryable: false,
  },

  // ---- 服务端类：用户改输入无用，重试或找管理员 ----
  engine_load_error: {
    title: '检测引擎加载失败',
    advice: '服务端未能加载空间计算引擎，请联系管理员检查引擎路径与依赖。',
    retryable: true,
  },
  engine_error: {
    title: '检测引擎执行出错',
    advice: '引擎在处理过程中中断，可稍后重试；若持续出现请联系管理员。',
    retryable: true,
  },
  raster_write_error: {
    title: '结果写盘失败',
    advice: '服务端无法写入产物目录，请联系管理员检查磁盘空间与目录权限。',
    retryable: true,
  },
  processing_error: {
    title: '影像处理失败',
    advice: '处理流程中途出错，可稍后重试；若持续出现请提供影像样本以便排查。',
    retryable: true,
  },
  config_error: {
    title: '服务端配置有误',
    advice: '服务端配置项缺失或非法，需联系管理员修正配置后重启服务。',
    retryable: false,
  },
  internal_error: {
    title: '服务端内部错误',
    advice: '服务端发生未预期异常，详细堆栈已记入服务端日志，可稍后重试。',
    retryable: true,
  },

  // ---- 传输层 ----
  http_404: {
    title: '请求的资源不存在',
    advice: '接口地址可能已变更，请确认前端与后端版本一致。',
    retryable: false,
  },
  invalid_response: {
    title: '服务端返回的数据不符合契约',
    advice: '前后端契约可能不一致，请联系管理员核对版本。',
    retryable: false,
  },
}

/** 兜底：未知错误码。 */
function unknownCodePresentation(code: string): ErrorPresentation {
  return {
    title: '检测失败',
    advice: `服务端返回了未预期的错误（错误码 ${code}），请重试或联系管理员。`,
    retryable: true,
  }
}

/**
 * 把任意异常整理成可展示的提示。
 *
 * 三类分流，因为恢复动作完全不同：
 *
 * 1. `NetworkError` —— 请求没到服务端，用户该做的是**启动后端**。
 * 2. `ApiError` —— 服务端明确拒绝，按 `code` 给针对性建议。
 * 3. 其他 —— 前端自身异常（如渲染期抛错），不假设成因，提示报障。
 *
 * @param error hook 抛出的原始异常（`unknown`）
 * @returns 展示用提示；`error` 为 `null` 时返回 `null`
 */
export function describeError(error: unknown): ErrorPresentation | null {
  if (error === null || error === undefined) return null

  if (error instanceof NetworkError) {
    return {
      title: '无法连接到检测服务',
      advice: '请确认后端服务已在 http://localhost:8000 启动，然后重试。',
      retryable: true,
    }
  }

  if (error instanceof ApiError) {
    const known = CODE_MESSAGE[error.code]
    if (known !== undefined) {
      return {
        title: known.title,
        advice: known.advice,
        retryable: known.retryable ?? false,
      }
    }
    return unknownCodePresentation(error.code)
  }

  if (error instanceof Error) {
    return {
      title: '发生未预期的错误',
      advice: `${error.message}。若反复出现，请将浏览器控制台的报错一并反馈。`,
      retryable: true,
    }
  }

  return {
    title: '发生未预期的错误',
    advice: '请重试；若反复出现，请反馈复现步骤。',
    retryable: true,
  }
}
