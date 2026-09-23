# 引擎契约 · `_spatial` Python 扩展

> **冻结时点**：Phase 2 · `v0.2.0`
> **适用对象**：backend（`rschange`）及一切通过 Python 使用空间引擎的代码。
> **变更方式**：本文件所述条目为冻结项，变更须走 §8 的契约变更流程。

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

三者刻意分档：`verify_bindings.py` 管接口契约，`verify_baseline.py` 管算法语义，`verify_config.py` 管配置与预设的一致性。把类型约束写进 §7.3 会让判定基准纠缠；配置类判据与算法无关，另立一项。

## 8. 契约变更流程

1. 在本文件记录变更点与理由，并更新 §9 变更记录。
2. 同步 `engine/tests/` 中对应的 C++ 判据。
3. 同步 `scripts/verify_bindings.py` 中对应的契约判据。
4. 走新的阶段分支与 tag，**禁止**在既有 tag 上追加变更。

禁止事项：

* 改 `properties` 字段名而不改 backend 与前端。
* 以「向后兼容」为名同时保留两种语义。
* 在绑定层增删语义（如默认参数、隐式单位换算）。

## 9. 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| `v0.2.0` | 2026-09-19 | 首次冻结。含对掩膜参数禁止隐式转换（`nb::noconvert`）与 `mask_to_geojson` 拒绝退化 3D 的约定 |
| `v0.2.1` | 2026-09-23 | 几何基准由像素中心改为**像素角点**（沿像素边界追踪），几何面积与 `area_m2` 一致（§5.1）；默认简化容差 `2.0` → `0.0`，非正即不简化；退化剔除只剩「成员像素少于 3 个」，一像素宽结构不再是退化几何（`multi_region_mask` 的 Feature 数 5 → 6）；`gdal_registration_count()` 收归内部头，不再进入 DLL 导出表；配置模板示例值与 `default.toml`、CMake 预设对齐 |
