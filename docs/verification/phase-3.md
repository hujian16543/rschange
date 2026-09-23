# Phase 3 验收报告 · 后端分层解耦

> 独立验收官出具。证据来自真实命令输出与逐行源码核对，未作人工修饰。除本文件（`docs/verification/phase-3.md`）外，本阶段**未修改**仓库内任何其他文件（源码、测试、配置、脚本、契约文档一律未动）。
> 严格边界：**禁止一切写操作类 git 命令**（log/diff/add/commit/branch/checkout 等）；唯一允许写入的文件即本文件；禁止 `pip install`、禁止裸 `python`/`pip`、禁止降低或跳过任何门禁。
> 例外并如实披露：核对期间执行过一次**只读** `git status --porcelain`，用途仅限确认「除本文件外仓库无其它未提交写入」，未用于反查提交范围。
> 故本报告**未**独立反查提交哈希与提交范围（未执行 `log`/`diff` 类命令），被验范围与锚点以任务书为准。
> 临时复现脚本写在仓库外 `C:/Users/Hujian/WorkBuddy/2026-09-18-12-56-04/_stage/`，跑完已清理。

## 1. 验收对象与基准

| 项 | 内容 |
|---|---|
| 上一阶段 tag | `v0.2.1`（Phase 2.1 轮廓硬化，已验收） |
| 被验集成分支 | `phase-3-backend`，tip = `258bc64` |
| 稳定线 | `main` tip = `9d61985`（Phase 3 尚未合入，属预期） |
| 任务分支 | `task-3.1-src-layout` … `task-3.7-contract-freeze`（7 个，均 `--no-ff` 合入 L1） |
| 证据分支 | `verify-3-report`（即本报告） |
| 重构目标 | 旧 `src/backend/`（9 文件、约 356 行）迁移重构为 `backend/src/rschange/` 下的分层、可插拔、无硬编码路径、结构化日志、异常不外泄的包；保留算法意图，允许修正错误行为 |

## 2. 门禁逐条结果表

| # | 命令（任务书判据原文） | 关键原始输出（摘录） | 判定 |
|---|---|---|---|
| G3.1 | `uv run pytest -rs` | `135 passed, 2 warnings in 3.56s`；汇总行**无任何 skip/deselected/xfail**，总数 **135 ≥ 15** | **通过** |
| G3.2 | `uv run ruff check` | `All checks passed!` | **通过** |
| G3.2（补） | `uv run ruff format --check .` | `42 files already formatted` | **通过** |
| G3.2（补） | `uv run mypy` | `Success: no issues found in 36 source files` | **通过** |
| G3.3 | `uv run python scripts/verify_baseline.py --phase 3` | `§7.1 11/11`、`§7.2 2/2`、`§7.3 7/7`；结论「通过 —— Phase 3 预期状态已达成」 | **通过** |
| G3.3（旁证） | `uv run python scripts/verify_bindings.py` | `失败项合计 = 0 -> 通过` | 旁证通过 |
| G3.3（旁证） | `uv run python scripts/verify_config.py` | `判定项 6 项（跳过 0 项），不通过 0 项`，结论「通过」 | 旁证通过 |
| G3.3（旁证） | `ctest --test-dir engine/build/dev-win --output-on-failure` | `100% tests passed, out of 40`；`Total Test time = 7.97 sec` | 旁证通过（引擎零回归） |
| G3.4 | 独立复现见 §4（哈希前后一致 + 实跑） | `HASH_BEFORE == HASH_AFTER = 2a83860…`；新检测器 `detect_change` 跑通 | **通过** |
| G3.5 | `grep -rn "msys64" backend/` | 退出码 `1`，**0 命中** | **通过** |

## 3. 独立核对 A：D 系列缺陷是否消除

### A.1 D1（CORS `*` + credentials 并存）
- 旧 `src/backend/main.py:26-27`：`allow_origins=["*"]` 与 `allow_credentials=True` 并存——浏览器规范下白名单实际失效。
- 新 `backend/src/rschange/api/app.py:128-129`：`allow_origins=list(resolved.settings.runtime.allowed_origins)`（取自配置，非 `"*"`），`allow_credentials=False`。
- 新 `backend/src/rschange/config.py:123-144`：`RuntimeSettings.allowed_origins` 配 `field_validator("_reject_wildcard")`，含 `"*"` 即启动期抛 `ValueError`（:139-143）。
- 结论：**已消除**。修复方式 = 凭据置 `False` + 通配符在配置校验层被拒（D1 在启动期暴露，而非生产静默退化）。

### A.2 D2（生产代码残留 `print`）
- 旧 `src/backend/detectors/postprocessor.py:21`：`print(f"[DEBUG] 后处理前: …")`。
- 在 `backend/` 全量 grep `print(`（`grep -rn "print(" backend/`）命中 2 行：
  - `backend/src/rschange/postprocess/morphology.py:19` —— 位于模块 docstring 的叙述（「删除调试 `print`」），非执行语句；
  - `backend/src/rschange/tests/test_architecture.py:75` —— 测试内的字符串字面量（用于断言 `_spatial` 是否已在 `sys.modules`），非执行 `print` 调用。
- 实际残留的 `print(` **执行语句数 = 0**。
- 结论：**已消除**。

### A.3 D5（全局唯一 DLL 路径解析点 + 路径来自配置）
- 旧 `src/backend/main.py:5-10` 与 `services/detection.py:11-16`：各自硬编码 `C:\Users\Hujian\DevCode\msys64\mingw64\bin` 并 `os.add_dll_directory` / `sys.path.insert`。
- 新 `backend/src/rschange/spatial/loader.py` 为**唯一**加载点（模块 docstring:1-16 明示）。在 `backend/` 内 grep `os.add_dll_directory` / `sys.path.insert` / `libgdal` / `msys64`：
  - `os.add_dll_directory` 仅出现在 `loader.py:70-71`（及 docstring :11、:33）；
  - `sys.path.insert` 仅 `loader.py:74`；
  - `libgdal`、`msys64` **0 命中**（路径本身不存在于 backend/ 任何文件）。
- 路径来源：`load_extension`（`loader.py:86-108`）取 `settings.build_dir` 与 `settings.runtime_dll_dir`，二者均经 `config.py:247-275` 的 `resolve()` 由配置解析（默认相对仓库根，无硬编码）。
- 结论：**已消除**。DLL 路径解析集中一处且来自配置，无第二处旁路。

### A.4 D7（异常不外泄）
- 旧 `src/backend/routers/detection.py`：`except Exception as e: raise HTTPException(500, detail=str(e))`，泄露内部信息。
- 新 `backend/src/rschange/api/errors.py` 兜底处理器 `_unexpected_error`（:102-127）：响应体固定为 `{"detail": "内部错误", "code": "internal_error"}`（:124-127），完整栈仅进日志（:118-123）。`install_exception_handlers` 注册 `Exception` 兜底（:163）。
- **实测**：仓库外脚本构造 app + 会抛 `RuntimeError` 的路由 + `TestClient(..., raise_server_exceptions=False)` 请求，真实响应体：
  ```
  STATUS 500
  BODY_RAW {"detail":"内部错误","code":"internal_error"}
  HAS_STR_EXC False   # 响应体不含 str(exc)/异常类型名/栈/内部路径
  ```
  触发用的异常文案为 `/abs/path/data/secret.db: connection refused`，未出现在响应体。
- 结论：**已消除**。500 响应体脱敏，不含异常消息、类型名、栈、内部路径。

### A.5 D3 / D6（Phase 2 已修，本轮确认未回归）
- D3（属性面积重复计）：`verify_baseline.py §7.2`「属性面积合计 720900.0」与旧引擎 1441800.0 对比，本轮 §7.2 `2/2` 通过，未回归。
- D6（`unordered_map` 迭代序不确定）：§7.3「多区域 Feature 顺序 == scipy 顺序」`[100,200,35,138,185,5]` 一致，本轮 §7.3 `7/7` 通过，未回归。

## 4. 独立核对 B：分层与依赖方向

### B.1 分层目录与依赖边
`backend/src/rschange/` 分层：`config` / `errors` / `logging` / `spatial`（引擎封装）/ `detectors`（算法，含 `registry`）/ `postprocess`（后处理）/ `io`（预览、重投影）/ `pipeline`（编排）/ `api`（FastAPI 应用、路由、schema、异常处理器）。

运行期依赖边（谁 import 谁，`grep -rn "from rschange\|import rschange"` 核对）：
- `pipeline/change_detection.py` → `rschange.spatial`、`rschange.errors`、`rschange.io.preview`、`rschange.io.reproject`、`rschange.logging`。
- `api/` → `rschange.config`、`rschange.api.*`、`rschange.pipeline`、`rschange.errors`、`rschange.logging`、`rschange.spatial`。
- `api/deps.py` → `rschange.detectors.registry`、`rschange.postprocess.MorphologyPostprocessor`（唯一的「协议↔实现」接合处）。
- `detectors/`、`postprocess/`、`spatial/`、`io/`、`config/`、`errors/`、`logging/` 之间无回指 `pipeline` 或 `api`。

**依赖方向单向、无环**；装配点严格收敛于 `api/deps.py`（见下 B.2）。

### B.2 pipeline 如何「不知道具体算法」
`backend/src/rschange/pipeline/change_detection.py`：
- 运行期 import（:45-49）仅 `rschange.spatial`、`rschange.errors`、`rschange.io.preview`、`rschange.io.reproject`、`rschange.logging`；**不 import `detectors/` 或 `postprocess/` 的任何名字**。
- 类型仅用于标注，置于 `TYPE_CHECKING`（:51-58）：`from rschange.detectors.base import ChangeDetector, DetectionResult` 与 `from rschange.postprocess.base import MaskPostprocessor`。
- `detect_change`（:298-304）签名：
  ```python
  def detect_change(
      request: DetectionRequest,
      *,
      detector: ChangeDetector,
      postprocessor: MaskPostprocessor,
      settings: Settings | None = None,
  ) -> DetectionOutcome:
  ```
  `detector` / `postprocessor` 是**必填注入参数**，非模块级查找。步骤 3 `_detect`（:175-191）仅调用 `detector.detect(...)`，不判断用哪个算法（docstring :178-179 明示「旧实现在此处硬编码 `cva_detect(...)`」）。
- 装配在 `api/deps.py:53-76` 的 `build_context()`：从 `registry.resolve()` 取算法、构造 `MorphologyPostprocessor`，注入 `RuntimeContext`。

结论：pipeline 在运行期对具体检测器/后处理器零依赖，满足判据。

## 5. 独立核对 C：G3.4 可插拔独立复现

方法：仓库外脚本 `plugtest.py` 在**不修改 `pipeline/change_detection.py`** 的前提下，定义新 `ChangeDetector` 实现、注册进 `registry`、用真实基线夹具跑通一次 `detect_change`，并对该文件取前后 `sha256`。

原始输出：
```
HASH_BEFORE 2a83860639258c02606d096bc814b3d883022c219a83a9ba566f5bceeb3721f4
REGISTERED plugtest; available= ('cva', 'plugtest')
RESOLVE plugtest -> plugtest
RESOLVE default -> cva
DETECT_OK detector= plugtest
DETECT_OK changed_pixels= 7209 total= 65536
DETECT_OK changed_area_m2= 720900.0
DETECT_OK previews= ('before', 'after', 'diff')
HASH_AFTER 2a83860639258c02606d096bc814b3d883022c219a83a9ba566f5bceeb3721f4
HASH_SAME True
```

结论：新增算法后 `pipeline/change_detection.py` 哈希**不变**（前=后），且新检测器成功驱动完整流水线（产物与基线一致，7209 像素 / 720900 m²）。**G3.4 成立**，非仅测试断言。

## 6. 独立核对 D：契约文档与实现一致性

### D.1 §9.3 `DetectionResponse` 逐字段对照 `schemas/detection.py`
| 契约字段（§9.3:204-218） | 实现（`schemas/detection.py`） | 一致 |
|---|---|---|
| `change_pixels: int ge=0` | :55 `int = Field(..., ge=0)` | 是 |
| `total_pixels: int gt=0` | :56 `int = Field(..., gt=0)` | 是 |
| `change_rate: float ge=0,le=1` | :57 `float = Field(..., ge=0, le=1)` | 是 |
| `threshold: float` | :58 `float = Field(...)` | 是 |
| `detector: str` | :59 `str = Field(...)` | 是 |
| `pixel_area_m2: float gt=0` | :60 `float = Field(..., gt=0)` | 是 |
| `changed_area_m2: float ge=0` | :61-63 `float = Field(..., ge=0)` | 是 |
| `geojson: str\|None default None` | :64-66 | 是 |
| `image_before_url/_after_url/_diff_url: str\|None` | :67-69 | 是 |
| `image_corners: list[list[float]]\|None` | :70-73 | 是 |
| `status: str default "success"` | :74 `str = Field(default="success")` | 是 |

全部 13 字段名、类型、约束、默认值逐项吻合。**无不一致**。

### D.2 §9.5 状态码/错误码表 对照 `errors.py` 全部异常类
`errors.py` 共 12 个领域异常（`__all__`，:29-42）。逐条比对 http_status / code：

| 异常类 | 契约 §9.5 | 实现 `errors.py` | 一致 |
|---|---|---|---|
| `RsChangeError` | 500 / `internal_error` | 基类 :55-57（500/`internal_error`） | 是 |
| `ConfigError` | 500 / `config_error` | :77-81（继承 500） | 是 |
| `CrsError` | 400 / `crs_error` | :94-96 | 是 |
| `EngineError` | 500 / `engine_error` | :99-103（继承 500） | 是 |
| `EngineLoadError` | 500 / `engine_load_error` | :106-110 | 是 |
| `InputValidationError` | 400 / `input_validation_error` | :172-174 | 是 |
| `ProcessingError` | 500 / `processing_error` | :177-181（继承 500） | 是 |
| `RasterReadError` | 400 / `raster_read_error` | :120-122 | 是 |
| `RasterWriteError` | 500 / `raster_write_error` | :125-129（继承 500） | 是 |
| `UnknownDetectorError` | 400 / `unknown_detector` | :161-163 | 是 |
| `UnsupportedFormatError` | 400 / `unsupported_format` | :135-137 | 是 |
| `UploadTooLargeError` | 413 / `upload_too_large` | :149-151 | 是 |

补充两行（422 `_validation_error`、500 兜底 `internal_error`）亦与 `errors.py` / `api/errors.py:124-127` 一致。**无不一致**。

### D.3 §9.6 目录穿越「两道判定」对照 `routers/detection.py:_artifact_path`
实现（:100-124）：
- 判定一（纯文件名）：:110 `if not name or name != Path(name).name or name.startswith("."): return None`；:112-113 `if ".." in name or "/" in name or "\\" in name: return None`。
- 判定二（resolve 复核）：:115-123 对 `outputs_dir` / `uploads_dir` 各算 `root = base.resolve()`、`candidate = (root / name).resolve()`，要求 `candidate.relative_to(root)`，`OSError`/`ValueError` 跳过，二者均不匹配返回 `None`。

两道判定**均存在**且语义与 §9.6:256-259 逐项一致。**无不一致**。

## 7. 独立核对 E：无硬编码路径（G3.5 扩展）

- G3.5 主判据：`grep -rn "msys64" backend/` 退出码 1，**0 命中**（§2）。
- 扩展核对的同类问题——`config/default.toml`（入库默认配置，在 `backend/` 之外）不得含本机路径：`grep -nE "msys64|C:/|/Users/|/home/|D:/" config/default.toml` 退出码 1，**0 命中**；该文件内全部路径为相对（`./data`、`./engine/build/dev-win` 等），`runtime_dll_dir` 留空（`""`），本机值由 `config/local.toml`（git 忽略）提供。
- 结论：**无硬编码本机路径**。

## 8. 独立核对 F：与旧仓库功能等价性（抽验）

### F.1 算法意图保留（CVA + Otsu）
- 旧 `src/backend/detectors/cva.py`：`magnitude = sqrt(sum((after-before)^2, axis=0))` + 自写直方图/Otsu。
- 新 `backend/src/rschange/detectors/cva.py`：`CvaDetector.detect`（:110-129）逐行保留欧氏距离（:126-127）与直方图/Otsu 实现路径（:44-102，docstring :11-23 明示「刻意保留原路径，不换实现」）。
- 等价性实证：`verify_baseline.py §7.1`「Otsu 阈值 5.9168 / 5.9168」「变化像素 7209 / 7209」**逐项 PASS**，证明数值行为零漂移。

### F.2 行为差异（判定为「修正」）
1. **常量输入的未定义行为（修正）**：旧 `cva.py:23-28` `bin_width = bin_edges[1]-bin_edges[0]`，当 `magnitude` 全常量时 `vmin==vmax` ⇒ `bin_width==0`，`(data-vmin)/bin_width` 为 `0/0`，`astype(np.int64)` 行为未定义（旧文件末行 :65 注释「缺点，格式不灵通」）。新 `histogram`（cva.py:55-59）显式 `if not (vmax > vmin)` 把全部样本归入首箱。实测：本机 numpy 上旧/新恰都得 0.0（旧因 `nan→0` 的偶然），但旧路径属跨版本未定义，新为确定性。**判定：修正**（消除未定义行为，基线不漂移）。
2. **两期影像形状不一致（修正）**：旧 `services/detection.py:74-88` 不校验即 `cva_detect(before, after)`，形状不符时触发原始 `ValueError: operands could not be broadcast…`（泄露内部信息）。新 `CvaDetector.detect`（cva.py:115-124）显式 `InputValidationError("两期影像的尺寸或波段数不一致")`，由全局处理器映射为 400。实测：`NEW_SHAPE_CHECK InputValidationError public= 两期影像的尺寸或波段数不一致` vs `OLD_SHAPE_CHECK ValueError operands could not be broadcast together with shapes (3,256,…)`。**判定：修正**（干净领域错误 vs 原始崩溃/信息泄露）。
3. **后处理连通性与参数（修正）**：旧 `postprocessor.py:11-20` 的 `min_size=30` 写死为函数默认、连通性依赖 `scipy.ndimage.label` 默认值（恰好 4 邻域但隐式）。新 `MorphologyPostprocessor`（morphology.py:47 `_CONNECTIVITY=1`、:80 显式 `generate_binary_structure(2,1)`、:55-62 参数提为构造来源 `config.postprocess`）。**判定：修正**（配置化 + 防止默认值变化导致与引擎 4 邻域口径不一致）。

未发现将「修正」误判为等价、或引入「回归」的算法行为差异。

## 9. 与 Phase 2.1 锚点对比表

> Phase 2.1 列数值来源：`docs/verification/phase-2.1.md` §2（G2/G3/G4/G5/G6/G7）、§10。

| 指标 | Phase 2.1 锚点 | Phase 3 实测 | 漂移判定 |
|---|---|---|---|
| CTest 用例数 | 40（§2 G2） | 40/40 | 零漂移（引擎未改动） |
| §7.1 / §7.2 / §7.3 | 11/11、2/2、7/7（§2 G3） | 11/11、2/2、7/7 | 零漂移 |
| `verify_bindings` 失败项 | 0（§2 G4） | 0 | 零漂移 |
| `verify_config` 判定项 | 6/6（§2 G5） | 6/6 | 零漂移 |
| `ruff check` | `All checks passed!`（7 文件，§2 G6） | `All checks passed!`（全仓库） | 稳定 |
| `ruff format --check` | `7 files already formatted`（§2 G7） | `42 files already formatted` | 范围扩大至 backend+scripts（重构引入） |
| Python 后端 pytest | 无（Phase 2.1 无后端包） | 135 passed、0 skip | 新增达成 |
| `mypy` strict | 无（后端未建立） | 36 源文件 0 错误 | 新增达成 |
| backend/ 内 `msys64` 字面串 | 不适用（旧 backend 内含；见 A.3） | 0 命中 | 缺陷已消除（D5） |
| 可插拔（新增算法不改 pipeline） | 不适用 | `pipeline` 哈希不变 + 实跑通过 | 新增达成（G3.4） |

## 10. 未通过项 / 存疑项

**不通过项：无。**

**存疑 / 澄清项（非缺陷，记录以免误判）**：
- **S1（澄清，非缺陷）**：`ruff check` 按 `pyproject.toml:61-74` 的 `src = ["backend/src","scripts"]` + `extend-exclude = ["docs"]` 配置运行（无参调用等价于检查当前目录但被 `docs` 排除）。任务书 G3.2 原文为 `uv run ruff check`（无路径），本报告严格按原文执行并通过；若将来收紧为显式 `ruff check backend/ scripts/`，结果一致。
- **S2（信息项）**：`local.toml` 含本机绝对路径 `C:/Users/Hujian/DevCode/msys64/mingw64/bin`（验证 D5/E 时确认），但该文件属 git 忽略的本机覆盖层，不在 G3.5 的 `backend/` 检查范围，亦不在入库 `default.toml`——不构成本机路径泄漏。
- **S3（非阻断，建议）**：G3.4 复现脚本成功跑通真实 `detect_change`，依赖 `_spatial` 已构建且 `local.toml` 提供 `runtime_dll_dir`；若 CI 在无 `local.toml` 的环境下复跑本复现，须以环境变量 `RSCHANGE_ENGINE__RUNTIME_DLL_DIR` 提供 DLL 目录，否则 `load_extension` 会在启动期抛 `ConfigError`（预期行为，非缺陷）。

## 11. 总判定

# 通过

依据：门禁 G3.1（`pytest` 135 passed、0 skip）— G3.2（`ruff check` / `ruff format --check .` / `mypy` 全零错误）— G3.3（`verify_baseline` §7.1 11/11 §7.2 2/2 §7.3 7/7，旁证 `verify_bindings` 0 失败、`verify_config` 6/6、`ctest` 40/40 零回归）— G3.4（独立复现 `pipeline` 哈希前后一致且新检测器实跑通过）— G3.5（`backend/` 内 `msys64` 0 命中）全部通过；独立核对 A（D1/D2/D5/D7 已消除、D3/D6 未回归）、B（依赖单向无环、pipeline 运行期零依赖具体算法）、C（可插拔实跑验证）、D（契约 §9.3/§9.5/§9.6 与实现逐项一致）、E（无硬编码路径）、F（算法意图保留、3 处差异均判定为修正）全部确认；与 Phase 2.1 锚点无回归。

## 12. 已知遗留问题清单

| 项 | 状态 | 责任阶段 |
|---|---|---|
| S3：G3.4 独立复现依赖 `local.toml` 的 `runtime_dll_dir`；CI 无本机覆盖时需用环境变量提供 | 预期前提（非缺陷） | CI 流水线须保证 DLL 目录可用 |
| S1：`ruff check` 无参调用依赖配置隐含范围 | 正常（与任务书原文一致） | 终验记录 |
| 后端 `_spatial` 契约复用约束（禁止改签名） | 约束生效中 | Phase 5 及以后 |
| 旧 `git` 提交范围未独立反查（git 被禁，锚点取自任务书） | 方法限制，非缺陷 | 终验若有需要另行裁定 |
