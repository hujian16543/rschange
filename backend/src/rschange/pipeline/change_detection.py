"""变化检测用例编排。

七个步骤，各步一个函数，编排函数只负责按序调用与组装结果：

    1  _read_pair        读取两期栅格
    2  _validate_pair    校验两期影像可比
    3  _detect           调用检测算法        ← 注入 ChangeDetector
    4  _clean            调用后处理器        ← 注入 MaskPostprocessor
    5  _write_previews   渲染三张预览图
    6  _vectorize        矢量化 + 重投影 + 影像四角
    7  _assemble         组装结果

旧实现把同样七件事塞进 `services/detection.py` 的单个 114 行函数 `run_detection`，
中间量（栅格元组、阈值、两张掩膜、三条 PNG 路径、GeoJSON 字符串、四角坐标）
在同一个作用域里互相可见，任何一步的顺序调整都可能静默影响后面几步。

依赖注入
--------
`detect_change` 的 `detector` 与 `postprocessor` 是**必填关键字参数**。本模块
在**运行期**不 import `detectors/` 与 `postprocess/` 的任何名字——协议只用于
类型标注，故写在 `if TYPE_CHECKING:` 之下。判据（阶段出口门 G3.4）：新增一种
检测算法只改 `detectors/`，本文件哈希不变。装配点在 `api/deps.py`。

对 `spatial` 的引用写成 `spatial.read_raster(...)` 而不是 `from rschange.spatial
import read_raster`：后者在**导入期**触发 PEP 562 的模块级 `__getattr__`，于是
只要 import 本模块就会加载 `_spatial` 扩展。前者只在函数被调用时才加载，让
「引擎未构建也能跑配置与 schema 类测试」的性质得以保留。

与旧实现的行为差异
------------------
* `job_id` 与输出目录由调用方显式给出。旧实现从路径反推
  （`os.path.basename(before_path).replace("_before.tif", "")`），文件命名一变，
  job_id 就会带上 `_after` 之类的后缀，三张预览图的 URL 随之全部失效。
* 两期影像的 `geo_transform` 与投影不一致时**显式报错**。旧实现静默沿用前一期
  的地理参考，对两幅不同定位的影像做逐像元比较，产出的掩膜与面积都无意义。
* 预览图目录由本层创建。旧实现依赖上传目录恰好已存在。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from rschange import spatial
from rschange.errors import InputValidationError, ProcessingError
from rschange.io.preview import save_rgb_png
from rschange.io.reproject import image_corners, reproject_geojson
from rschange.logging import get_logger

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    from rschange.config import Settings
    from rschange.detectors.base import ChangeDetector, DetectionResult
    from rschange.postprocess.base import MaskPostprocessor
    from rschange.spatial.raster import Raster

__all__ = [
    "DetectionOutcome",
    "DetectionRequest",
    "PreviewImage",
    "PreviewKind",
    "detect_change",
]

_logger = get_logger(__name__)

#: 预览图的种类，决定文件名后缀。
PreviewKind = Literal["before", "after", "diff"]

#: `geo_transform` 比较容差。两期影像读自不同文件，浮点表示可能出现末位差异，
#: 但那不构成「定位不同」；真正不同的偏移量远大于此。
_GEOTRANSFORM_TOL: float = 1e-9


@dataclass(frozen=True, slots=True)
class DetectionRequest:
    """一次变化检测请求的输入。

    `output_dir` 与 `job_id` 显式给出，不从文件路径反推——产物 URL 由 `job_id`
    拼出，而产物落在 `output_dir` 下，两者一旦与路径命名耦合，改命名即改契约。
    """

    job_id: str
    before_path: Path
    after_path: Path
    output_dir: Path


@dataclass(frozen=True, slots=True)
class PreviewImage:
    """一张已写出的预览图。"""

    kind: PreviewKind
    """取值 `before` / `after` / `diff`。"""

    path: Path


@dataclass(frozen=True, slots=True)
class DetectionOutcome:
    """变化检测结果。

    面积以平方米给出：`pixel_area_m2` 是单像元面积，`changed_area_m2` 是变化
    像元数乘以它。两者同 `docs/contracts.md` §5 对 `area_m2` 的定义，即取
    `|dx × dy|`，与 GeoJSON 中 Feature 的属性面积同源，可直接互相核对。
    """

    job_id: str
    detector: str
    """实际使用的算法名。可插拔之后，响应中回带算法名使结果可追溯。"""

    threshold: float
    change_pixels: int
    total_pixels: int
    change_rate: float
    pixel_area_m2: float
    changed_area_m2: float
    geojson: str
    image_corners: list[list[float]]
    previews: tuple[PreviewImage, ...]
    mask: NDArray[np.bool_]
    """后处理后的掩膜。供测试直接断言，也便于后续按需写出栅格产物。"""


def _read_pair(request: DetectionRequest, settings: Settings | None) -> tuple[Raster, Raster]:
    """步骤 1：读取两期栅格。

    @throws RasterReadError 任一期读取失败
    """
    before = spatial.read_raster(request.before_path, settings)
    after = spatial.read_raster(request.after_path, settings)
    _logger.info(
        "影像已读取",
        job_id=request.job_id,
        bands=before.bands,
        height=before.height,
        width=before.width,
    )
    return before, after


def _validate_pair(before: Raster, after: Raster) -> None:
    """步骤 2：校验两期影像可比。

    三项检查都指向同一个后果：逐像元比较必须建立在「同一网格、同一坐标系」的
    前提上。少了任何一项，产出的掩膜在数值上仍然成立，但它的空间含义是错的。

    @throws InputValidationError 形状、地理变换或投影不一致
    """
    if before.shape != after.shape:
        raise InputValidationError(
            f"两期影像形状不一致：before {before.shape}，after {after.shape}",
            public_message="两期影像的尺寸或波段数不一致",
        )

    if any(
        abs(left - right) > _GEOTRANSFORM_TOL
        for left, right in zip(before.geo_transform, after.geo_transform, strict=True)
    ):
        raise InputValidationError(
            f"两期影像地理变换不一致：before {before.geo_transform}，after {after.geo_transform}",
            public_message="两期影像的地理定位不一致，无法逐像元比较",
        )

    if before.projection != after.projection:
        raise InputValidationError(
            "两期影像投影不一致，无法逐像元比较",
            public_message="两期影像的坐标系不一致",
        )


def _detect(detector: ChangeDetector, before: Raster, after: Raster) -> DetectionResult:
    """步骤 3：调用注入的检测算法。

    本函数**不判断**用哪个算法——算法由调用方给出。旧实现在此处硬编码
    `cva_detect(before, after)`，替换算法必须修改编排代码。

    @throws InputValidationError 算法自身校验不通过
    """
    result = detector.detect(before.array, after.array)
    _logger.info(
        "变化检测完成",
        detector=detector.name,
        threshold=result.threshold,
        changed_pixels=result.changed_pixels,
        total_pixels=result.total_pixels,
    )
    return result


def _clean(postprocessor: MaskPostprocessor, result: DetectionResult) -> NDArray[np.bool_]:
    """步骤 4：调用注入的后处理器。

    @throws ProcessingError 后处理器改变了掩膜形状（违反 `MaskPostprocessor`
        的保形约定）
    """
    mask = postprocessor.apply(result.mask)
    if mask.shape != result.mask.shape:
        raise ProcessingError(
            f"后处理器 {postprocessor.name!r} 改变了掩膜形状：{result.mask.shape} -> {mask.shape}",
            public_message="后处理结果尺寸异常",
        )
    return mask


def _write_previews(
    request: DetectionRequest,
    before: Raster,
    after: Raster,
    mask: NDArray[np.bool_],
) -> tuple[PreviewImage, ...]:
    """步骤 5：渲染「前 / 后 / 差异」三张预览图。

    差异图以**后一期影像**为底、叠加红色掩膜——这与旧实现一致：变化的视觉
    对照需要能看清变化发生在什么地物上。

    @throws RasterWriteError 写出失败
    """
    request.output_dir.mkdir(parents=True, exist_ok=True)

    sources: tuple[tuple[PreviewKind, Raster, NDArray[np.bool_] | None], ...] = (
        ("before", before, None),
        ("after", after, None),
        ("diff", after, mask),
    )

    written: list[PreviewImage] = []
    for kind, source, overlay in sources:
        path = request.output_dir / f"{request.job_id}_{kind}.png"
        save_rgb_png(source.array, path, mask=overlay)
        written.append(PreviewImage(kind=kind, path=path))

    _logger.info(
        "预览图已写出",
        job_id=request.job_id,
        output_dir=str(request.output_dir),
        count=len(written),
    )
    return tuple(written)


def _vectorize(mask: NDArray[np.bool_], raster: Raster) -> tuple[str, list[list[float]]]:
    """步骤 6：矢量化、重投影、算影像四角。

    三步都依赖同一份地理参考，故合并为一步——拆开会让「用了哪一期的 geo」这个
    问题在每个调用点各出现一次。

    掩膜为 `bool`，`spatial.mask_to_geojson` 内的 `as_mask` 负责转成引擎要求的
    `uint8`；此处禁止自行 `astype` 后绕过该转换，否则浮点掩膜这类错误不会被拦下。

    @throws CrsError 影像缺少可解析的坐标系
    """
    geojson_raw = spatial.mask_to_geojson(mask, raster.geo_transform)
    geojson = reproject_geojson(geojson_raw, raster.projection)
    corners = image_corners(raster.geo_transform, raster.width, raster.height, raster.projection)
    return geojson, corners


def _assemble(
    *,
    request: DetectionRequest,
    raster: Raster,
    detector: ChangeDetector,
    result: DetectionResult,
    mask: NDArray[np.bool_],
    geojson: str,
    corners: list[list[float]],
    previews: tuple[PreviewImage, ...],
) -> DetectionOutcome:
    """步骤 7：组装结果。

    面积与变化率都在此由掩膜与地理参考导出，不在前面的步骤里提前算好——避免
    同一个量在两处各算一遍而口径不同。
    """
    change_pixels = int(mask.sum())
    total_pixels = int(mask.size)
    pixel_area = raster.pixel_area

    return DetectionOutcome(
        job_id=request.job_id,
        detector=detector.name,
        threshold=float(result.threshold if result.threshold is not None else 0.0),
        change_pixels=change_pixels,
        total_pixels=total_pixels,
        change_rate=change_pixels / total_pixels if total_pixels > 0 else 0.0,
        pixel_area_m2=pixel_area,
        changed_area_m2=change_pixels * pixel_area,
        geojson=geojson,
        image_corners=corners,
        previews=previews,
        mask=mask,
    )


def detect_change(
    request: DetectionRequest,
    *,
    detector: ChangeDetector,
    postprocessor: MaskPostprocessor,
    settings: Settings | None = None,
) -> DetectionOutcome:
    """执行完整的七步变化检测流程。

    参数
    ----
    request
        输入与产物落点。
    detector
        检测算法。必填——本层不提供默认值，默认算法由装配层
        （`api/deps.py`）从 `detectors.registry` 解析后注入。
    postprocessor
        掩膜后处理器。必填，理由同上。
    settings
        配置。为 `None` 时由 `spatial` 层自行取进程级单例。

    返回
    ----
    `DetectionOutcome`，含阈值、像素统计、面积、GeoJSON、预览图路径与后处理掩膜。

    @throws RasterReadError 影像读取失败
    @throws InputValidationError 两期影像不可比，或算法校验不通过
    @throws CrsError 影像缺少可解析的坐标系
    @throws RasterWriteError 预览图写出失败
    """
    before, after = _read_pair(request, settings)
    _validate_pair(before, after)

    result = _detect(detector, before, after)
    mask = _clean(postprocessor, result)
    previews = _write_previews(request, before, after, mask)
    geojson, corners = _vectorize(mask, before)

    outcome = _assemble(
        request=request,
        raster=before,
        detector=detector,
        result=result,
        mask=mask,
        geojson=geojson,
        corners=corners,
        previews=previews,
    )
    _logger.info(
        "变化检测流程结束",
        job_id=request.job_id,
        detector=outcome.detector,
        changed_pixels=outcome.change_pixels,
        changed_area_m2=outcome.changed_area_m2,
    )
    return outcome
