/* eslint-disable */
/* tslint:disable */
// @ts-nocheck
/*
 * ---------------------------------------------------------------
 * ## THIS FILE WAS GENERATED VIA SWAGGER-TYPESCRIPT-API        ##
 * ##                                                           ##
 * ## AUTHOR: acacode                                           ##
 * ## SOURCE: https://github.com/acacode/swagger-typescript-api ##
 * ---------------------------------------------------------------
 */

/** Body_detect_api_detect_post */
export interface BodyDetectApiDetectPost {
  /**
   * After
   * 后一期影像（.tif / .tiff / .png）
   */
  after: File | Blob;
  /**
   * Before
   * 前一期影像（.tif / .tiff / .png）
   */
  before: File | Blob;
}

/**
 * DetectionResponse
 * 一次变化检测的结果。
 * @example {"change_pixels":7209,"change_rate":0.1100006103515625,"changed_area_m2":720900,"detector":"cva","geojson":"{\"type\": \"FeatureCollection\", \"features\": [...]}","image_after_url":"/api/image/8f3c1d9e_after.png","image_before_url":"/api/image/8f3c1d9e_before.png","image_corners":[[117,36.144718],[117.028456,36.144715],[117.028448,36.121634],[117,36.121638]],"image_diff_url":"/api/image/8f3c1d9e_diff.png","pixel_area_m2":100,"threshold":5.916767423962816,"total_pixels":65536}
 */
export interface DetectionResponse {
  /**
   * Changed Area M2
   * 真实变化面积（平方米）= change_pixels × pixel_area_m2
   * @min 0
   */
  changed_area_m2: number;
  /**
   * Pixel Area M2
   * 单像元面积（平方米）
   * @exclusiveMin 0
   */
  pixel_area_m2: number;
  /**
   * Change Pixels
   * 变化像元数（后处理后）
   * @min 0
   */
  change_pixels: number;
  /**
   * Change Rate
   * 变化像元占比，取值 [0, 1]
   * @min 0
   * @max 1
   */
  change_rate: number;
  /**
   * Detector
   * 实际使用的检测算法名，用于结果追溯
   */
  detector: string;
  /**
   * Geojson
   * 变化区域的 GeoJSON FeatureCollection（坐标已为 WGS84 经纬度）
   */
  geojson?: string | null;
  /**
   * Image After Url
   * 后一期影像预览图 URL
   */
  image_after_url?: string | null;
  /**
   * Image Before Url
   * 前一期影像预览图 URL
   */
  image_before_url?: string | null;
  /**
   * Image Corners
   * 影像四角经纬度，顺序为左上、右上、右下、左下，用于地图定位
   */
  image_corners?: number[][] | null;
  /**
   * Image Diff Url
   * 变化叠加预览图 URL
   */
  image_diff_url?: string | null;
  /**
   * Threshold
   * 检测算法使用的判定阈值
   */
  threshold: number;
  /**
   * Total Pixels
   * 影像总像元数
   * @exclusiveMin 0
   */
  total_pixels: number;
}

/**
 * ErrorResponse
 * 错误响应体。
 *
 * 与 `rschange.errors.RsChangeError.to_payload()` 的输出结构一致：`detail` 为
 * **脱敏后**的描述，`code` 为机器可读错误码（供前端分支，不随文案变化）。
 *
 * 本模型只用于 OpenAPI 文档，不参与序列化——异常响应由 `api/errors.py` 的
 * 全局处理器直接产出 `JSONResponse`，不经过 pydantic 校验。
 * @example {"code":"input_validation_error","detail":"两期影像的尺寸或波段数不一致"}
 */
export interface ErrorResponse {
  /**
   * Code
   * 机器可读错误码，见 docs/contracts.md
   */
  code: string;
  /**
   * Detail
   * 脱敏后的错误描述
   */
  detail: string;
}

/** HTTPValidationError */
export interface HTTPValidationError {
  /** Detail */
  detail?: ValidationError[];
}

/** ValidationError */
export interface ValidationError {
  /** Context */
  ctx?: object;
  /** Input */
  input?: any;
  /** Location */
  loc: (string | number)[];
  /** Message */
  msg: string;
  /** Error Type */
  type: string;
}
