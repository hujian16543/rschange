# 契约 · 引擎（_spatial）与 HTTP 接口

> **冻结时点**：引擎部分自 Phase 2 · `v0.2.0`（`v0.2.1` 修订）冻结；HTTP 接口部分自 Phase 3 · `v0.3.0` 冻结。
> **适用对象**：backend（`rschange`）全部分层代码——引擎绑定（`_spatial` 扩展）与 HTTP 接口（FastAPI 应用、路由、schema、异常处理器）。
> **变更方式**：本文件所述条目为冻结项。引擎部分条目未被本轮改动；HTTP 部分条目变更须走 §8 的契约变更流程。

## 1. 范围与依赖方向

| 条目 | 约定 |
|---|---|
| 契约范围 | 本文件是 C++ 引擎对 Python 侧**唯一**的契约来源 |
| 依赖方向 | `backend` → `_spatial`（绑定层）→ `libspatial`（引擎核心）→ GDAL。反向依赖**禁止** |
| 绑定层职责 | `engine/bindings/module.cpp` 只做「Python 对象 ↔ C++ 类型」的转换与参数校验。出现多分支业务逻辑即为越界，应下沉到 `engine/src/` |
| 直接调用 | **禁止** backend 绕过 `_spatial` 直接加载 `libspatial.dll`，或另行实现引擎已有的算法 |

## 2. 模块身份与加载前提

| 条目 | 约定 |
|---|---|
| 模块名 | `_spatial` |
| Windows 产物 | `_spatial.cp314-win_amd64.pyd` |
| Linux 产物 | `_spatial.cpython-314-x86_64-linux-gnu.so` |
| ABI 标签 | `cp314`。**必须**与本机 CPython 3.14 的 ABI 一致 |
| 扩展所在目录 | 配置项 `engine.build_dir`，**必须**与 CMake 预设的 `binaryDir` 一致 |
| 原生依赖 | 配置项 `engine.runtime_dll_dir`（Windows 必填；Linux 由 `LD_LIBRARY_PATH` 提供）。GDAL 3.12.3 与 MinGW 运行时同处 `msys64/mingw64/bin` |
| 加载方式 | 由 `scripts/engine_env.py` 统一完成：登记 DLL 搜索路径 → 把扩展目录插入 `sys.path` → `import _spatial` |

**禁止混用两套 CPython 运行时。** 本机并存两份同名同版本的 CPython 3.14：python.org 版（运行时 `python314.dll`）与 MSYS2 自带版（运行时 `libpython3.14.dll`）。二者 ABI 名称相同但 DLL 不同，混用会在 `import` 时直接访问违例（`0xC0000005`，无 Python 层异常）。CMake 配置期已加运行时一致性校验，违反即 `FATAL_ERROR`。

## 3. 函数契约

模块对外暴露四个函数，均为模块级函数，无类与全局状态。

### 3.1 `print_gdal_version() -> None`

打印底层 GDAL 版本号到 `stdout`，返回值恒为 `None`。供诊断使用。

### 3.2 `read_raster(path) -> tuple`

| 项 | 约定 |
|---|---|
| 参数 | `path`：文件路径。必须存在且为 GDAL 可识别的栅格格式 |
| 返回 | 六元组 `(array, width, height, bands, geo_transform, projection)` |
| `array` | `numpy.ndarray`，shape `(bands, height, width)`，dtype `uint16`。像素缓冲所有权随数组移交，Python 侧可零拷贝持有 |
| `width` / `height` | `int`，像素列数 / 行数 |
| `bands` | `int`，波段数 |
| `geo_transform` | `list[float]`，六个元素，GDAL 顺序 `(x0, dx, rx, y0, ry, dy)` |
| `projection` | `str`，完整 WKT |

### 3.3 `write_raster(path, mask, geo, projection) -> None`

| 项 | 约定 |
|---|---|
| `path` | 目标路径。父目录**必须**已存在，本函数不创建目录 |
| `mask` | 见 §4。可为 2D `(H, W)` 或 3D `(B, H, W)`，dtype 必须 `uint8` |
| `geo` | 长度必须为 6 的浮点序列 |
| `projection` | WKT 字符串；空字符串表示不写投影 |
| 返回 | `None` |

### 3.4 `mask_to_geojson(mask, geo) -> str`

| 项 | 约定 |
|---|---|
| `mask` | 见 §4，**必须**为 2D `(H, W)`。3D 输入（含退化的 `(1, H, W)`）抛 `ValueError` |
| `geo` | 长度必须为 6 的浮点序列 |
| 返回 | GeoJSON `FeatureCollection` 的 JSON 字符串（紧凑格式，非缩进） |
| 语义 | 见 §5 |

## 4. 数组契约

掩膜参数的类型由绑定层声明为：

```text
numpy.ndarray[dtype=uint8, order='C', writable=False]
```

| 条目 | 约定 |
|---|---|
| dtype | 掩膜**必须** `uint8`；`read_raster` 的影像数组恒为 `uint16` |
| 维度 | 掩膜**必须**是 2 维或 3 维。其他维度抛 `ValueError` |
| 内存布局 | **必须** C 连续 |
| 可写性 | 只读数组与可写数组都**接受**。调用方**禁止**为满足接口而复制数组 |
| 隐式转换 | **禁止**。dtype 或布局不符即抛 `TypeError`；调用方**必须**自行 `astype` / `ascontiguousarray` 后传入 |

隐式转换之所以被禁止：转换器若回退到转换，`mask_to_geojson(magnitude, geo)` 这类「漏掉二值化」的错误不会报错——引擎会把每个非零像素当作变化像素，返回一份貌似合理的错误结果；浮点值还会被截断（`300.0` → `44`，仍非零）。

## 5. `mask_to_geojson` 的语义约定

| 条目 | 约定 |
|---|---|
| 连通性 | 4 邻域 |
| `label` | 从 1 起递增，按各连通域**首次出现的 raster-scan 位置（先行后列）**排序。该顺序与容器迭代序无关，任何平台、任何标准库实现下都相同 |
| Feature 数 | 等于**非退化**连通域数。一个连通域**恰好**产出一个 Feature |
| Polygon 环序 | 首环为外环，其余为洞环。环按 Polygon 约定闭合（首尾点相同） |
| 环的顶点 | **像素角点格点** `(r, c)`，`row ∈ [0, H]`、`col ∈ [0, W]`；格点 `(r, c)` 是像素 `(r, c)` 的**左上角**，故取值范围比像素下标多一行一列。相邻顶点由水平或竖直的直线段相连，段长可为多个像素；环上不留共线的冗余顶点 |
| 环的绕向 | 外环有向面积为**正**，洞环为**负**。两者符号相反，这既是判别依据，也保证导出到经纬度后外环为逆时针，符合 RFC 7946 对 Polygon 外环方向的要求 |
| 洞环取样 | 洞的边界是边图分解中与外环不相接的另一条独立环，**无需**对背景做洪泛搜索。一像素的洞同样是合法内环 |
| 退化剔除 | 只剩一种情形：**成员像素少于 3 个**（轮廓层即返回空环），既不产出 Feature，也不抛异常。顶点共线在像素角点基准下不再是退化来源 |
| 简化 | 闭曲线 Douglas-Peucker，容差取 `GeoJsonOptions::simplify_tolerance` 默认值 **0.0，即不简化**。容差非正时原样返回，使几何面积精确守恒由构造保证 |
| `properties` 字段 | 恰为 `label` (int)、`pixel_count` (int)、`area_m2` (float) 三项。**禁止**增删或改名 |
| `area_m2` 定义 | `pixel_count × 单像元面积`，单像元面积 = `abs(geo[1] × geo[5])` |
| 坐标换算 | `lon = geo[0] + col·geo[1] + row·geo[2]`，`lat = geo[3] + col·geo[4] + row·geo[5]`。几何顶点取**像素角点**：`(0, 0)` 对应影像左上角，`(H, W)` 对应右下角 |
| 几何面积 | 默认容差 0 下，几何面积（外环减洞环）**精确等于** `area_m2`，偏差仅为浮点表示级。见 §5.1 |
| 输出确定性 | 同一输入在任意平台、任意标准库实现下输出**逐字节一致** |

### 5.1 几何面积与 `area_m2` 的一致性

几何顶点取**像素角点**，环沿相邻像素之间的缝行进，故环围出的多边形恰好等于成员像素的并集：

    几何面积（像素单位） == 成员像素个数

乘单像元面积即 `area_m2`。**容差取默认值 0 时两者恒等**，偏差只来自浮点表示（坐标量级 5×10⁵ × 4×10⁶，双精度乘积的绝对误差约 10⁻⁴ m²）。

实测（默认容差 0）：

| 样本 | 上报面积合计 | 几何面积合计 | 偏差 |
|---|---|---|---|
| `change_mask`（7209 像素，单区域） | 720 900 m² | 720 900 m² | 0.00 % |
| `multi_region_mask`（6 区域，含小区域） | 66 300 m² | 66 300 m² | 0.00 % |

`scripts/verify_baseline.py` 的 §7.3 设有判据「几何面积 == 上报面积（像素角点基准）」，偏差上限 `1e-6 %`。几何面积由 `shapely` 独立算出，不依赖被测代码。

#### Phase 2 的历史偏差（已修正）

Phase 2 取**像素中心**，故外环是**内接**多边形：`n × n` 实心方块的外环面积是 `(n−1)²` 像素单位，而 `area_m2` 是 `n² × 单像元面积`。偏差随区域变小而放大：

| 样本 | 上报面积合计 | 几何面积合计 | 偏差 |
|---|---|---|---|
| `change_mask` | 720 900 m² | 699 800 m² | −2.93 % |
| `multi_region_mask` | 65 800 m² | 54 200 m² | −17.63 % |
| 其中最小的区域（35 像素） | 3 500 m² | 2 400 m² | −31.4 % |

#### 行为变更的影响

* `area_m2` 仍是面积的**权威值**。取正容差时几何面积不再与它一致（实测圆盘容差 1.0 时偏 +0.19 %，小区域偏差更大），此时面积统计**必须**取 `properties.area_m2`。
* `multi_region_mask` 夹具的 `line_e`（1 像素宽竖条）在旧基准下顶点共线、有向面积为 0，被当作退化轮廓整条剔除；新基准下它是合法的 1×5 矩形（500 m²），**必须**产出 Feature。**该夹具的 Feature 数由 5 变为 6**，label 序列由 `1,2,3,4,5` 变为 `1,2,3,4,5,6`。
* 夹具元数据已由 `scripts/make_multi_region_fixture.py` 重新生成；`.raw` 掩膜字节不变，仅 JSON 期望值变化。

## 6. 异常契约

参数类错误一律 `ValueError`，类型/布局不符一律 `TypeError`，环境与 IO 类错误一律 `RuntimeError`。

| 情形 | 类型 | 异常消息（实测） |
|---|---|---|
| 掩膜维度不是 2 或 3 | `ValueError` | `掩膜必须是 2D (H, W) 或 3D (B, H, W) 的 uint8 数组，实得 1 维` |
| `mask_to_geojson` 收到 3D 掩膜 | `ValueError` | `mask_to_geojson 只接受 2D (H, W) 的 uint8 掩膜，实得 3D (B, H, W)` |
| `geo` 长度不是 6 | `ValueError` | `geo_transform 必须是 6 个浮点数，实得 5 个` |
| 掩膜 dtype 或布局不符 | `TypeError` | `mask_to_geojson(): incompatible function arguments. ...` |
| 文件不存在或格式不受支持 | `RuntimeError` | `read_raster: 无法打开 <path>：... No such file or directory` |
| 写入目标不可创建 | `RuntimeError` | `write_raster: 创建失败 <path>：Attempt to create new tiff file ... failed` |

## 7. 校验

| 判据组 | 校验工具 | 覆盖内容 |
|---|---|---|
| 契约条款 | `scripts/verify_bindings.py` | 函数齐备、写读一致、异常类型、掩膜类型与布局严格性、`properties` 字段名、非方形的坐标范围 |
| 算法锚点 | `scripts/verify_baseline.py` | 《重构方案》§7.1 / §7.2 / §7.3，含 §5.1 的几何面积一致性 |
| 配置一致性 | `scripts/verify_config.py` | 模板示例值 == `default.toml` == CMake 预设的 `binaryDir`；`legacy_*` 必须为空；Windows 上 `local.toml` 的 `runtime_dll_dir` 非空 |
| HTTP 契约与分层结构 | `backend/src/rschange/tests/` 下的 pytest 套件 | `test_api.py` 管 HTTP 边界（路由、错误映射、目录穿越、CORS、体积上限）；`test_architecture.py` 管分层方向、可插拔（G3.4）与 backend 内禁止机器本地路径（G3.5）；`test_pipeline.py` 管七步编排与基线锚点 |

四者刻意分档：`verify_bindings.py` 管接口契约，`verify_baseline.py` 管算法语义，`verify_config.py` 管配置与预设的一致性，三者均为仓库级脚本，不依赖 backend 装配即可运行；pytest 套件管 HTTP 契约与分层结构，依赖 FastAPI 应用与运行时上下文。把 HTTP 判据并入前三档会引入 backend 装配依赖，破坏脚本的无后端可跑性质，故另立一档。

## 8. 契约变更流程

1. 在本文件记录变更点与理由，并更新 §10 变更记录。
2. 同步 `engine/tests/` 中对应的 C++ 判据。
3. 同步 `scripts/verify_bindings.py` 中对应的契约判据。
4. 走新的阶段分支与 tag，**禁止**在既有 tag 上追加变更。
5. HTTP 契约变更（响应字段名、错误码、状态码）须同步 `backend/src/rschange/api/schemas/` 与 `backend/src/rschange/tests/test_api.py`；若前端已消费，须同步前端类型与解析逻辑。

禁止事项：

* 改 `properties` 字段名而不改 backend 与前端。
* 以「向后兼容」为名同时保留两种语义。
* 在绑定层增删语义（如默认参数、隐式单位换算）。
* 以「向后兼容」为名在 HTTP 响应中同时返回两种字段名（如旧字段与新字段并存）。
* HTTP 响应字段改名而不同步 `schemas/` 与 `test_api.py`、前端消费方。

## 9. HTTP 接口契约

本族契约覆盖 `backend/src/rschange/api/` 下的 FastAPI 应用工厂、路由、schema 与全局异常处理器。业务路由统一挂载于前缀 `API_PREFIX = "/api"` 之下（`app.py:46`）。异常响应由 `api/errors.py` 的全局处理器统一产出，路由层**不**捕获领域异常。

### 9.1 端点清单

| 路径 | 方法 | 用途 | 成功状态码 |
|---|---|---|---|
| `/api/detect` | POST | 接收两期影像，执行变化检测，返回统计量、GeoJSON 与三张预览图 URL | 200 |
| `/api/image/{filename}` | GET | 返回 `outputs/` 或 `uploads/` 下的产物文件（预览图） | 200 |
| `/` | GET | 服务信息（meta，非检测契约核心） | 200 |

### 9.2 `POST /api/detect` 请求契约

* 内容类型：`multipart/form-data`。
* 文件字段名：必须恰好两个——`before`（前一期影像）、`after`（后一期影像）。字段名与 `routers/detection.py` 的 `detect()` 形参名一字不差。
* 扩展名白名单：`ALLOWED_EXTENSIONS = frozenset({".tif", ".tiff", ".png"})`，即 `.tif`、`.tiff`、`.png`。后缀不在其中抛 `UnsupportedFormatError`（400）。
* 体积上限：配置来源 `runtime.max_upload_mb`（默认 `500`）；接口以字节比较，经 `RuntimeSettings.max_upload_bytes` 计算（`max_upload_bytes = max_upload_mb × 1024 × 1024`），单文件上限即 `settings.runtime.max_upload_bytes`。
* 超限处理：抛 `UploadTooLargeError` → HTTP 413，错误码 `upload_too_large`。
* 是否边收边计：**是**。分块读取（块大小 `_CHUNK_BYTES = 1024 × 1024`），每写入一块即累计字节；一旦超过上限立即中断，并删除已写入的半成品文件，不把任意大小的请求体落到磁盘。

### 9.3 成功响应 schema —— `DetectionResponse`

逐字段（共 **12** 个，字段名与 `schemas/detection.py` 一字不差）：

| 字段名 | 类型 | 含义 |
|---|---|---|
| `change_pixels` | `int`（`ge=0`） | 变化像元数（后处理后） |
| `total_pixels` | `int`（`gt=0`） | 影像总像元数 |
| `change_rate` | `float`（`ge=0, le=1`） | 变化像元占比，取值 `[0, 1]` |
| `threshold` | `float` | 检测算法使用的判定阈值 |
| `detector` | `str` | 实际使用的检测算法名，用于结果追溯 |
| `pixel_area_m2` | `float`（`gt=0`） | 单像元面积（平方米） |
| `changed_area_m2` | `float`（`ge=0`） | 真实变化面积（平方米）= `change_pixels × pixel_area_m2` |
| `geojson` | `str \| None`（默认 `None`） | 变化区域 GeoJSON `FeatureCollection`（坐标已为 WGS84 经纬度） |
| `image_before_url` | `str \| None` | 前一期影像预览图 URL |
| `image_after_url` | `str \| None` | 后一期影像预览图 URL |
| `image_diff_url` | `str \| None` | 变化叠加预览图 URL |
| `image_corners` | `list[list[float]] \| None` | 影像四角经纬度，顺序为左上、右上、右下、左下，用于地图定位 |

`status` 字段已于 `v0.5.0` 移除（原为第 13 个字段）。它恒为 `"success"`，即不携带任何信息——错误响应走 HTTP 状态码与 `ErrorResponse`——保留它只会让消费方误以为存在多种成功状态。

### 9.4 错误响应 schema —— `ErrorResponse`

* 形状：`{"detail": str, "code": str}`。422 情形下额外含 `"errors": list`（见 9.5）。
* `code` 命名约束（snake_case validator 确切规则）：必须全部小写（`value == value.lower()`），且去除下划线后必须为字母数字串（`value.replace("_", "").isalnum()` 为真）。即：**禁止**大写字母、**禁止**连字符 `/` 点等非字母数字字符；下划线允许作为单词分隔。
* 字段可空性：`detail` 与 `code` 均为必填，无默认值。`ErrorResponse` 仅为 OpenAPI 文档模型，实际错误体由 `api/errors.py` 直接产出 `JSONResponse`，不经 pydantic 校验。

### 9.5 状态码映射表

领域异常（逐条列出 `errors.py` 全部 12 个类，一个不漏）：

| 异常类 | HTTP 状态码 | 错误码 `code` |
|---|---|---|
| `RsChangeError`（基类） | 500 | `internal_error` |
| `ConfigError` | 500 | `config_error` |
| `CrsError` | 400 | `crs_error` |
| `EngineError`（基类） | 500 | `engine_error` |
| `EngineLoadError` | 500 | `engine_load_error` |
| `InputValidationError` | 400 | `input_validation_error` |
| `ProcessingError` | 500 | `processing_error` |
| `RasterReadError` | 400 | `raster_read_error` |
| `RasterWriteError` | 500 | `raster_write_error` |
| `UnknownDetectorError` | 400 | `unknown_detector` |
| `UnsupportedFormatError` | 400 | `unsupported_format` |
| `UploadTooLargeError` | 413 | `upload_too_large` |

补充两行（非 `errors.py` 类，但属统一错误形状）：

* **422**（请求校验失败，`RequestValidationError`）：保留 422 状态码；`detail` 归一为 `"请求参数不符合要求"`，`code` 为 `"request_validation_error"`，并附加 `errors` 结构化列表。
* **500**（未预期异常，`Exception` 兜底处理器）：响应体为**固定字符串** `{"detail": "内部错误", "code": "internal_error"}`。**禁止**含 `str(exc)`、异常类型名、任何栈帧信息与内部路径；完整栈仅进日志。

另：`HTTPException`（如 `GET /api/image` 的 404、框架的 405 等）由 `_http_error` 接管，`code` 取 `http_<状态码>`（如 404 → `"http_404"`），状态码与 `headers` 原样保留。

### 9.6 `GET /api/image/{filename}` 契约

* 成功：返回 `FileResponse`；`media_type` 由文件扩展名推断，产物预览图为 PNG，典型响应 `Content-Type: image/png`。
* 404 条件：`filename` 不合法或文件不存在，返回 404，`detail` 为 `"文件不存在"`，`code` 为 `"http_404"`。
* 目录穿越防护（确切判定，两道，见 `routers/detection.py:_artifact_path`，任一不满足即返回 `None` → 404）：
  1. **纯文件名判定**：`name` 非空；`Path(name).name == name`（不含路径分隔）；不以 `.` 开头；不含 `..`；不含 `/` 或 `\`。
  2. **resolve 复核**：对 `outputs_dir` 与 `uploads_dir` 逐个，计算 `root = base.resolve()`、`candidate = (root / name).resolve()`，要求 `candidate.relative_to(root)` 成立（解析后的真实路径仍位于基目录内）；任何 `OSError` / `ValueError` 或不在其内则跳过；两者均不匹配返回 `None`。
  * 两道都必须保留：单独任何一道都有绕过余地（符号链接、Windows 短文件名、大小写差异可让「纯文件名」指向目录外）。

### 9.7 CORS 契约

* 白名单来源：`runtime.allowed_origins`（默认 `["http://localhost:5173", "http://127.0.0.1:5173"]`）。
* 凭据：`allow_credentials=False`（本服务不使用 Cookie 会话）。
* `"*"` 处理：配置校验 `RuntimeSettings._reject_wildcard` **禁止** `allowed_origins` 含 `"*"`；应用层 `allow_origins` 直接取配置列表。理由（D1 缺陷修复）：`"*"` 与凭据并存会使浏览器白名单**实际失效**（任何来源都可通过），故两者互斥、通配符在启动期即被拦截。

### 9.8 错误码清单

与 9.5 合并，不重复书写。错误码集合 = 9.5 表中全部 `code` 值；新增领域异常须新增专属 `code`（类属性），**禁止**复用既有 `code`。

### 9.9 配置依赖

HTTP 层依赖的配置项（路径）：

| 配置路径 | 用途 |
|---|---|
| `runtime.allowed_origins` | CORS 白名单 |
| `runtime.max_upload_mb` / `runtime.max_upload_bytes` | 上传体积上限 |
| `runtime.data_dir` → 派生 `uploads_dir`、`outputs_dir` | 上传与产物落点 |
| `runtime.host` / `runtime.port` | 服务绑定（`main()` 使用） |
| `engine.runtime_dll_dir` / `engine.build_dir` | 引擎定位（经错误路径可达） |
| `logging.level` / `logging.format` | 日志装配 |
| `postprocess.min_size` / `postprocess.structure_size` | `build_context` 装配后处理器 |

结构性禁令：

* backend 内**禁止**出现机器本地路径字面串（如 `msys64`、`C:/Users/...` 形式）；守护由 `test_architecture.py` 承担（G3.5）。
* 配置模型 `extra="forbid"`：TOML 出现未声明键即启动期报错。

### 9.10 不变式锚点

HTTP 层不得漂移的基线数值（出处：真实夹具 `before.tif` / `after.tif`，256×256，UTM 50N；含 `DetectionResponse._EXAMPLE` 与 §5.1，守护见 `test_pipeline.py`）：

| 锚点 | 值 |
|---|---|
| Otsu 阈值 `threshold` | `5.916767423962816`（契约示例写作 `5.9168`） |
| 变化像素 | `7209 / 65536` |
| 真实面积 `changed_area_m2` | `720900 m²`（= 7209 × 100.0） |
| 影像形状 | `(3, 256, 256)`，`dtype uint16` |

### 9.11 可插拔约定

* 新增检测算法：只在 `detectors/` 下实现 `ChangeDetector` 协议并向 `registry` 注册；后处理器在 `postprocess/` 下实现 `MaskPostprocessor`。
* **不需要**修改 `pipeline/change_detection.py`：编排层在运行期不 import `detectors/` 与 `postprocess/` 的具体名字，`detector` / `postprocessor` 为必填注入参数，类型标注仅在 `TYPE_CHECKING` 下。
* 判据（`test_architecture.py` 守护，阶段出口门 G3.4）：新增算法后 `pipeline/change_detection.py` 文件哈希不变。

### 9.12 契约产物与漂移检测

* **机器可读形态**：`docs/api/openapi.json`（OpenAPI `3.1.0`），由 `scripts/gen_openapi.py` 从 `create_app()` 生成，**冻结入库**。生成使用桩算法与桩后处理器（`build_context` 的显式注入口），不触及 `_spatial`，故**无需 GDAL 环境即可复现**。
* 该文件的 `info.version` 取自 `rschange.__version__`，后者取自 `backend/pyproject.toml`。版本号一致性由 `scripts/verify_version.py` 第 5 项守护。
* **前端类型**：`frontend/src/api/generated/schema.ts` 由该文件经 `scripts/gen-api-types.ps1` / `.sh`（`openapi-typescript`）生成，**入库**；`frontend/src/api/types.ts` 只是生成 schema 的转发别名，不含手写字段。原手写类型 `frontend/src/types/detection.ts` 已删除。
* **漂移检测**（阶段出口门 G5.2 的载体）：
  * `uv run python scripts/gen_openapi.py --check` —— 重新生成并与入库文件逐字节比对，不一致即退出码 `1`。
  * `tests/contract/` 内的用例承担同一判据，另加「三方字段一致性」（pydantic 模型字段 == OpenAPI schema 属性 == 前端生成 schema 字段名）。
* **反向验证**：故意改动后端响应字段而**不**重新生成契约产物时，上述门禁**必须**变红。不红即说明契约未真正生效，判不通过。

## 10. 变更记录

> 本节在 `v0.3.0` 之前编号为 **§9**。按旧编号引用本节的报告（例如 `docs/verification/phase-2.1.md` 的「记入 `docs/contracts.md` §9」）指向本节。同一版本内新增的 HTTP 契约占用 §9，故本节顺延。

| 版本 | 日期 | 变更 |
|---|---|---|
| `v0.2.0` | 2026-09-19 | 首次冻结。含对掩膜参数禁止隐式转换（`nb::noconvert`）与 `mask_to_geojson` 拒绝退化 3D 的约定 |
| `v0.2.1` | 2026-09-23 | 几何基准由像素中心改为**像素角点**（沿像素边界追踪），几何面积与 `area_m2` 一致（§5.1）；默认简化容差 `2.0` → `0.0`，非正即不简化；退化剔除只剩「成员像素少于 3 个」，一像素宽结构不再是退化几何（`multi_region_mask` 的 Feature 数 5 → 6）；`gdal_registration_count()` 收归内部头，不再进入 DLL 导出表；配置模板示例值与 `default.toml`、CMake 预设对齐 |
| `v0.3.0` | 2026-09-23 | HTTP 接口契约首次冻结（§9）；D1 修复：CORS 通配符 `"*"` 与凭据并存使白名单失效，改为逐列来源 + `allow_credentials=False` 并在配置期拒绝 `"*"`；上传体积上限由 nginx 层隐式 1 MB 改为应用层显式可配（`runtime.max_upload_mb`，默认 500 MB，边收边计、超限即删半成品）；`GET /api/image/{filename}` 目录穿越防护（纯文件名 + resolve 复核两道）；异常不再外泄（领域异常→脱敏 `public_message`，未预期异常 500 固定串「内部错误」）；新增 `backend/src/rschange/tests/` pytest 套件承担 HTTP 契约与分层结构判据 |
| `v0.5.0` | 2026-10-02 | **契约收缩**：移除 `DetectionResponse.status`，成功响应字段 13 → 12（该字段恒为 `"success"`，不携带信息，错误一律走状态码与 `ErrorResponse`）；**版本号收敛**为 `backend/pyproject.toml` 单一真相源，`rschange.__version__` 改读发行版元数据（原字面量停在 `0.3.0`，与仓库实际版本漂移且会冻入契约产物），新增 `scripts/verify_version.py` 守护；**契约产物入库**：`docs/api/openapi.json` 与 `frontend/src/api/generated/schema.ts`（§9.12），前端手写类型删除，改由 OpenAPI 生成。注：`v0.4.0`（Phase 4 前端工程化）未改动本契约。 |
