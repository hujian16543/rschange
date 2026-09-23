"""变化检测路由。

    POST /api/detect                     两期影像 → 变化检测结果
    GET  /api/image/{filename}            提供预览图

路由函数只做三件事：解析入参、调用下层、返回 schema。领域异常一律**不在此层
捕获**——由 `api/errors.py` 的全局处理器统一映射，因此本文件里没有一处
`try/except ... HTTPException(detail=str(e))`。

旧实现（`routers/detection.py`）的三处修正
------------------------------------------

1. **`GET /api/image/{filename}` 的目录穿越**。旧代码写
   `os.path.join(UPLOAD_DIR, filename)`，而 `os.path.join("/base", "/etc/passwd")`
   返回 `"/etc/passwd"`——**基目录被整个丢弃**。`{"filename": "..%2F..%2F..."}`
   这类请求因此可以读到仓库内任意文件（`config/local.toml` 含本机绝对路径）。
   现按「纯文件名 + resolve 后仍在允许目录内」两道判定拦截。

2. **上传体积无上限**。`config.MAX_UPLOAD_SIZE` 声明了 500 MB 却从未被读取，
   边读边写盘，实际上限由反向代理决定（旧 `nginx.conf` 缺 `client_max_body_size`，
   默认 1 MB）。现按 `runtime.max_upload_mb` 边收边计，超限即删除半成品文件。

3. **在事件循环里跑 CPU 密集任务**。旧代码在 `async def` 路由里直接调用
   `run_detection`，整段检测（读栅格 + CVA + 形态学 + 出图 + 矢量化）期间事件
   循环被阻塞，同一进程内的其他请求全部排队。现经 `run_in_threadpool` 下放。
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, Final

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from rschange.api.deps import RuntimeContext, get_context
from rschange.api.schemas.detection import DetectionResponse, ErrorResponse
from rschange.errors import UnsupportedFormatError, UploadTooLargeError
from rschange.logging import get_logger
from rschange.pipeline import DetectionRequest, PreviewKind, detect_change

__all__ = ["ALLOWED_EXTENSIONS", "IMAGE_URL_PREFIX", "router"]

router = APIRouter()
_logger = get_logger(__name__)

#: 预览图 URL 前缀。响应中的三个 `image_*_url` 与 `GET` 路由共用它。
IMAGE_URL_PREFIX: Final[str] = "/api/image"

#: 接受的上传后缀。`.png` 保留在白名单内：GDAL 能按内容签名打开它，只是没有
#: 地理参考，随后由 `CrsError` 给出「影像缺少坐标系」这一**可理解**的 400，
#: 而不是在此处笼统地报「不支持的文件类型」。
ALLOWED_EXTENSIONS: Final[frozenset[str]] = frozenset({".tif", ".tiff", ".png"})

#: 读取上传流的分块大小。
_CHUNK_BYTES: Final[int] = 1024 * 1024


def _validate_extension(upload: UploadFile) -> None:
    """@throws UnsupportedFormatError 后缀不在白名单内"""
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = "、".join(sorted(ALLOWED_EXTENSIONS))
        raise UnsupportedFormatError(
            f"不支持的文件类型：{upload.filename!r}（后缀 {suffix!r}）",
            public_message=f"不支持的文件类型，仅接受 {allowed}",
        )


async def _save_upload(upload: UploadFile, destination: Path, max_bytes: int) -> int:
    """流式保存上传文件，边写边计体积，返回写入字节数。

    中途失败（含超限、客户端断开、磁盘满）时删除目标文件：留下半个 TIFF 会让
    下一次请求读到它，并抛出难以理解的 GDAL 报错——把「上传中断」伪装成
    「影像损坏」。

    @throws UploadTooLargeError 超过 `max_bytes`
    """
    written = 0
    try:
        with destination.open("wb") as handle:
            while chunk := await upload.read(_CHUNK_BYTES):
                written += len(chunk)
                if written > max_bytes:
                    raise UploadTooLargeError(
                        f"上传文件 {upload.filename!r} 超过上限 {max_bytes} 字节",
                        public_message=(
                            f"上传文件过大：单个文件不得超过 {max_bytes // (1024 * 1024)} MB"
                        ),
                    )
                handle.write(chunk)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return written


def _artifact_path(name: str, context: RuntimeContext) -> Path | None:
    """把 URL 中的文件名解析为磁盘路径；不合法或不存在时返回 `None`。

    两道判定都必须保留，单独任何一道都有绕过余地：

    * **纯文件名** —— 不含路径分隔符、不等于 `..`、不以 `.` 开头。这道判定拦掉
      全部相对路径与绝对路径（含 `os.path.join` 丢弃基目录的那一类）。
    * **resolve 后仍在允许目录内** —— 符号链接、Windows 短文件名、大小写差异
      都可能让「纯文件名」指向目录之外，故仍要按解析后的真实路径复核。
    """
    if not name or name != Path(name).name or name.startswith("."):
        return None
    if ".." in name or "/" in name or "\\" in name:
        return None

    for base in (context.settings.outputs_dir, context.settings.uploads_dir):
        try:
            root = base.resolve()
            candidate = (root / name).resolve()
            candidate.relative_to(root)
        except OSError, ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


@router.post(
    "/detect",
    response_model=DetectionResponse,
    summary="执行两期影像的变化检测",
    responses={
        400: {"model": ErrorResponse, "description": "输入影像不满足要求"},
        413: {"model": ErrorResponse, "description": "上传文件过大"},
        500: {"model": ErrorResponse, "description": "内部错误"},
    },
)
async def detect(
    before: Annotated[UploadFile, File(description="前一期影像（.tif / .tiff / .png）")],
    after: Annotated[UploadFile, File(description="后一期影像（.tif / .tiff / .png）")],
    context: Annotated[RuntimeContext, Depends(get_context)],
) -> DetectionResponse:
    """接收两期影像，执行变化检测并返回统计量、GeoJSON 与三张预览图。"""
    _validate_extension(before)
    _validate_extension(after)

    settings = context.settings
    job_id = uuid.uuid4().hex
    uploads = settings.uploads_dir
    uploads.mkdir(parents=True, exist_ok=True)

    # 落盘时统一用 .tif：GDAL 按内容签名识别驱动，后缀只影响可读性，
    # 统一后缀使产物命名规则稳定（旧实现同样如此）。
    before_path = uploads / f"{job_id}_before.tif"
    after_path = uploads / f"{job_id}_after.tif"

    try:
        await _save_upload(before, before_path, settings.runtime.max_upload_bytes)
        await _save_upload(after, after_path, settings.runtime.max_upload_bytes)
    except BaseException:
        # 两个文件同批产生，失败时一并清理；只清自己那个会留下孤儿。
        before_path.unlink(missing_ok=True)
        after_path.unlink(missing_ok=True)
        raise

    _logger.info(
        "收到检测请求",
        job_id=job_id,
        before=before.filename,
        after=after.filename,
    )

    request = DetectionRequest(
        job_id=job_id,
        before_path=before_path,
        after_path=after_path,
        output_dir=settings.outputs_dir,
    )

    # 下放到线程池：整条流水线是 CPU 密集的同步代码，直接在事件循环里跑会阻塞
    # 同进程内所有其他请求。
    outcome = await run_in_threadpool(
        detect_change,
        request,
        detector=context.detector,
        postprocessor=context.postprocessor,
        settings=settings,
    )

    by_kind = {preview.kind: preview.path.name for preview in outcome.previews}

    def image_url(kind: PreviewKind) -> str | None:
        name = by_kind.get(kind)
        return f"{IMAGE_URL_PREFIX}/{name}" if name else None

    return DetectionResponse(
        change_pixels=outcome.change_pixels,
        total_pixels=outcome.total_pixels,
        change_rate=outcome.change_rate,
        threshold=outcome.threshold,
        detector=outcome.detector,
        pixel_area_m2=outcome.pixel_area_m2,
        changed_area_m2=outcome.changed_area_m2,
        geojson=outcome.geojson,
        image_before_url=image_url("before"),
        image_after_url=image_url("after"),
        image_diff_url=image_url("diff"),
        image_corners=outcome.image_corners,
    )


@router.get(
    "/image/{filename}",
    summary="提供预览图",
    response_class=FileResponse,
    responses={404: {"model": ErrorResponse, "description": "文件不存在"}},
)
async def serve_image(
    filename: str,
    context: Annotated[RuntimeContext, Depends(get_context)],
) -> FileResponse:
    """返回 `outputs/` 或 `uploads/` 下的产物文件。

    文件名按「纯文件名」判定，故任何带路径分隔符的请求都直接 404——包括旧实现
    会被读到的绝对路径。
    """
    path = _artifact_path(filename, context)
    if path is None:
        _logger.warning("产物不存在或文件名不合法", filename=filename)
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path)
