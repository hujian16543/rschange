# Phase 3.1 验收报告 · preview 掩膜半透明叠加（热修）

> 独立验收官出具。证据来自真实命令输出与逐行源码核对，未作人工修饰。
> 唯一允许写入的文件即本文件（`docs/verification/phase-3.1.md`）；除此以外**未修改**仓库内任何其他文件。
> 严格边界：**禁止一切写操作类 git 命令**（`add` / `commit` / `branch` / `checkout` / `stash` / `merge` / `tag` 等）；本报告出具期间**未执行**任何上述命令，`git stash list` 为空。
> 只读 git 命令为本次判据所必需（差异范围核查与树一致性比对），已执行并如实列出于 §7.1：`git log`、`git rev-parse`、`git diff`、`git status`、`git branch`、`git tag`、`git rev-list`、`git merge-base`、`git stash list`。全部为只读，未改写任何引用或工作树。
> 反向验证（§3）**临时**改写过 `backend/src/rschange/io/preview.py` 中的 `_OVERLAY_ALPHA` 常量（`100` → `255` → `100`），该改动已完整恢复，恢复实证见 §3.4。

## 1. 验收对象与基准

| 项 | 内容 |
|---|---|
| 基线（热修前） | tag `v0.3.0` = `8fec430`（`merge: Phase 3 · 后端分层解耦（验收通过）`） |
| L2 任务提交 | 分支 `task-3.1.1-preview-alpha`，tip = `9fa1d35`（`task-3.1.1: preview 掩膜叠加改为真正的半透明`） |
| L1 合并提交 | 分支 `phase-3.1-preview-alpha`，tip = `98b1f22`（`merge: task-3.1.1 · preview 掩膜半透明叠加（--no-ff）`） |
| `98b1f22` 父提交 | `8fec430` 与 `9fa1d35`（`git rev-list --parents` 实测两父，`--no-ff` 成立） |
| 树一致性 | `9fa1d35^{tree}` = `98b1f22^{tree}` = `1a5bb6554a7dfd05974ca95883e1fe95531c0e36` |
| `main` 现状 | tip = `8fec430`；`98b1f22` **不是** `main` 的祖先（实测 `git merge-base --is-ancestor 98b1f22 main` 退出码 `1`），热修尚**未合入 `main`** |
| 被验工作树 | 工作树与 `9fa1d35` 逐字节一致（`git diff 9fa1d35` 输出为空；`preview.py` sha256 = `69b8658f…46976`） |
| 热修目标 | `io/preview.py` 掩膜叠加由「掩膜处不透明纯红（alpha=255）」改为「掩膜处按常量 `_OVERLAY_ALPHA` 与底图半透明混合」 |

> 锚点说明：`9fa1d35` 并非工作树 `HEAD`（`HEAD` = `main` = `8fec430`）。差异范围、diff 内容与树一致性均以 `v0.3.0` → `9fa1d35` 为准，已在 §2、§7 逐条落证据。

## 2. 判据 A：差异范围

命令 `git diff 8fec430 9fa1d35 --stat`、`--name-only`、`--numstat` 实际输出：

```
 backend/src/rschange/io/preview.py    | 23 ++++++++++++------
 backend/src/rschange/tests/test_io.py | 44 +++++++++++++++++++++++++++++------
 2 files changed, 53 insertions(+), 14 deletions(-)
```

`--name-only` 恰为两项：

```
backend/src/rschange/io/preview.py
backend/src/rschange/tests/test_io.py
```

`--numstat`：

```
16      7       backend/src/rschange/io/preview.py
37      7       backend/src/rschange/tests/test_io.py
```

**判定：通过。** 改动**仅限** `backend/src/rschange/io/preview.py` 与 `backend/src/rschange/tests/test_io.py`，**无第三个文件**（`docs/contracts.md`、`config/`、引擎侧、脚本一律未动）。

## 3. 判据 B：反向验证（判别力实证）

### 3.1 起点的值可确认

热修后 `_OVERLAY_ALPHA` 的实际值：

```
$ grep -n "_OVERLAY_ALPHA: Final" backend/src/rschange/io/preview.py
56:_OVERLAY_ALPHA: Final[int] = 100
```

工作树与提交一致（无未提交漂移）：

```
$ git rev-parse 9fa1d35^{tree}
1a5bb6554a7dfd05974ca95883e1fe95531c0e36
$ git diff 9fa1d35 --stat
（空输出）
$ sha256sum backend/src/rschange/io/preview.py
69b8658f27d8c65c510fb8eb3cc9039cc062c15f9e71579748ba2c86b1c46976
```

### 3.2 临时改回旧行为（`_OVERLAY_ALPHA = 255`）

将第 56 行常量由 `100` 改写为 `255`（复现 `v0.3.0` 的不透明纯红行为）后：

```
$ grep -n "_OVERLAY_ALPHA: Final" backend/src/rschange/io/preview.py
56:_OVERLAY_ALPHA: Final[int] = 255

$ uv run pytest backend/src/rschange/tests/test_io.py -o addopts="" -q -k overlay
...
>       assert int(masked[4, 6][1]) != 0 and int(masked[4, 6][2]) != 0, "半透明不应遮蔽底图"
E       AssertionError: 半透明不应遮蔽底图
E       assert (0 != 0)
E        +  where 0 = int(np.uint8(0))

backend\src\rschange\tests\test_io.py:277: AssertionError
=========================== short test summary info ===========================
FAILED backend/src/rschange/tests/test_io.py::TestSaveRgbPng::test_mask_overlay_is_semi_transparent_red
FAILED backend/src/rschange/tests/test_io.py::TestSaveRgbPng::test_mask_overlay_preserves_background
2 failed, 23 deselected in 1.06s
```

**实际结果：变红。** 通过用例数 `0`；失败用例名为
`TestSaveRgbPng::test_mask_overlay_is_semi_transparent_red` 与
`TestSaveRgbPng::test_mask_overlay_preserves_background`。

### 3.3 恢复原值（`_OVERLAY_ALPHA = 100`）

```
$ grep -n "_OVERLAY_ALPHA: Final" backend/src/rschange/io/preview.py
56:_OVERLAY_ALPHA: Final[int] = 100

$ uv run pytest backend/src/rschange/tests/test_io.py -o addopts="" -q -k overlay
..                                                                       [100%]
2 passed, 23 deselected in 0.89s
```

**实际结果：变绿。** 通过用例数 `2`，失败用例数 `0`。

### 3.4 恢复实证（必须项）

恢复后逐项核对：

| 核对项 | 命令 | 实测 | 判定 |
|---|---|---|---|
| 常量已复原 | `grep -n "_OVERLAY_ALPHA: Final"` | `100` | 已还原 |
| 文件逐字节还原 | `sha256sum preview.py` | `69b8658f27d8c65c510fb8eb3cc9039cc062c15f9e71579748ba2c86b1c46976`，与临时改动前备份**完全相同** | 已还原 |
| 无残留漂移 | `git diff 9fa1d35 --stat` | 空输出 | 已还原 |
| 全量套件复绿 | `uv run pytest -o addopts="" -q` | `136 passed, 2 warnings in 4.23s` | 已恢复全绿 |

临时备份文件 `/tmp/preview_backup.py` 已删除。

**判定：通过。** 断言具备真实判别力——回退到 `alpha=255` 时**两个** overlay 用例均失败，恢复 `alpha=100` 时全部通过；不存在「回退后仍全绿」的无效断言情形。

## 4. 判据 C：契约与语义一致性

### 4.1 `docs/contracts.md` §9.3 `image_diff_url`

§9.3（`:200-218`）对 `image_diff_url` 的全部描述为一行：

```
| `image_diff_url` | `str \| None` | 变化叠加预览图 URL |
```

该行仅约定**字段名、类型与「是叠加预览图 URL」**，**未**约定掩膜叠加的不透明度语义（既不提 alpha，也不提「不透明/半透明」，亦不提像素混合口径）。对全文检索 `alpha` / `叠加` / `不透明` / `半透明` / `overlay`：

- `alpha`：**0 命中**（全文无该词）；
- `叠加`：仅 §9.3 `image_diff_url` 行本身（「变化叠加预览图 URL」）；
- `不透明` / `半透明` / `overlay`：**各 0 命中**。

热修后行为（掩膜处按 `_OVERLAY_ALPHA=100` 半透明混合）依然满足「变化叠加预览图 URL」这一唯一约定——字段名、类型、可空性与 URL 语义均未变，仅 PNG 内部像素的混合方式变化。

### 4.2 变更记录章节（§10）

§10（`:307-315`）现有条目止于 `v0.3.0`（2026-09-23）；`v0.3.0` 条目内容为 HTTP 接口契约冻结与 D1/D2/D5/D7 系列修复，**不涉及**预览图叠加语义。热修未触及任何已冻结条款。

**判定：通过 —— 无需更新契约。** 理由：契约**从未**描述掩膜叠加的不透明度语义，故本次改动不使任何契约条款失效或失真；§9.3 的字段级约定（`str | None`、叠加预览图 URL）改后仍成立。§10 变更记录无需追加条目（该项仅记录契约本身的变更，本次契约文本零变更）。若产品层面希望把「半透明」上升为对外承诺，**应当**另立契约条款并记入 §10 —— 此为可选增强，非本次热修的缺失。

> 附：契约文本零改动已由 §2 的 `--name-only` 独立佐证（`docs/contracts.md` 不在差异清单内）。

### 4.3 `preview.py` 模块 docstring 是否同步

热修后 docstring 已从旧表述更新。旧文（`v0.3.0`）写作：

```
保持不变的两处（**有意**）
* **拉伸口径**：…
* **掩膜叠加方式**：`Image.new("RGBA", size, (255, 0, 0, 100))` 的初始 alpha 随后
  被 `putalpha(mask)` **整体覆盖**，因此实际效果是「掩膜处不透明纯红」，而不是
  半透明叠加——`alpha=100` 是无效参数。…故保留原样并在此记录。
```

新文（`9fa1d35`）改写为：

```
保持不变的一处（**有意**）
--------------------------
* **拉伸口径**：…

掩膜叠加的 alpha（v0.3.1 修正）
-------------------------------
旧实现写作 `Image.new("RGBA", size, (255, 0, 0, 100))`，但紧随其后的
`putalpha(mask)` 把 alpha 通道**整体替换**为 `mask * 255`，故 `100` 从未生效，
实际效果是「掩膜处不透明纯红」（alpha=255）。该行为已由用户裁定修正为
**真正的半透明叠加**：alpha 取 `mask * _OVERLAY_ALPHA`，掩膜处保留常量
`_OVERLAY_ALPHA`（默认 100，约 39% 不透明），非掩膜处 alpha=0 即完全透出底图。
```

核对要点：
1. 「保持不变」由「两处」改为「一处」，掩膜叠加项**已从保持不变清单移除**——不再声称「保留原样」；
2. 新增独立小节明确记录旧行为缺陷、用户裁定与新语义，与新实现（`preview.py:132-138`）逐字对应；
3. 残留的旧行为描述仅作为**历史对照**（「旧实现写作…」），用于解释差异来源，并非对当前行为的陈述。

**判定：通过。** docstring 已反映新行为，不存在仍描述旧行为为当前行为的情形。

## 5. 判据 D：门禁复跑（现场执行实测）

| # | 命令 | 实际输出（摘录） | 判定 |
|---|---|---|---|
| G1 | `uv run pytest -o addopts="" -q` | `136 passed, 2 warnings in 4.23s`（`--collect-only` 同报 `136 tests collected`） | **通过** |
| G2 | `uv run mypy` | `Success: no issues found in 36 source files` | **通过** |
| G3 | `uv run ruff check .` | `All checks passed!` | **通过** |
| G4 | `uv run ruff format --check .` | `42 files already formatted` | **通过** |
| G5 | `uv run python scripts/verify_baseline.py --phase 3` | `§7.1 不变量 11/11 通过`、`§7.2 缺陷基线 2/2 通过`、`§7.3 语义断言 7/7 通过`；结论 `通过 —— Phase 3 预期状态已达成` | **通过** |
| G6 | `uv run python scripts/verify_bindings.py` | `失败项合计 = 0  ->  通过` | **通过** |
| G7 | `uv run python scripts/verify_config.py` | `判定项 6 项（跳过 0 项），不通过 0 项`；结论 `通过 —— 分层配置、CMake 预设与本机模板互相一致` | **通过** |

`verify_baseline.py --phase 3` 关键行原始数值（与 Phase 3 验收锚点逐位一致）：

```
7.1  Otsu 阈值                               5.9168                        5.9168                        PASS
7.1  变化像素（原始）                        7209                          7209                          PASS
7.1  变化像素（后处理后）                    7209                          7209                          PASS
7.1  变化率                                  0.110001                      0.110001                      PASS
7.1  真实变化面积 m²                         720900.0                      720900.0                      PASS
7.2  属性面积合计 m²                         720900.0                      720900.0                      PASS
7.3  多区域 Feature 顺序 == scipy 顺序       [100, 200, 35, 138, 185, 5]   [100, 200, 35, 138, 185, 5]   PASS
```

七项门禁**全部通过**，无一项降级、跳过或放宽。用例总数由 `v0.3.0` 时的 135 增至 **136**（净增 `+1`），与 §7 的用例净变更核算一致。

## 6. 判据 E：回归核查

### 6.1 完整 diff（`git diff 8fec430 9fa1d35 -- backend/src/rschange/io/preview.py`）

```diff
diff --git a/backend/src/rschange/io/preview.py b/backend/src/rschange/io/preview.py
index 04e4778..b7b67c5 100644
--- a/backend/src/rschange/io/preview.py
+++ b/backend/src/rschange/io/preview.py
@@ -10,14 +10,18 @@
 现按波段数分支：1 波段复制为三通道，≥3 波段取前三，2 波段明确拒绝——两个通道
 既拼不出彩色，也没法解释成灰度，静默取前两个只会产出偏色的图。
 
-保持不变的两处（**有意**）
+保持不变的一处（**有意**）
 --------------------------
 * **拉伸口径**：2 / 98 分位线性拉伸到 0–255，`hi - lo < 1e-6` 时令 `hi = lo + 1`
   以避免除零。该项直接决定输出像素值，改动会让所有历史预览图不可比。
-* **掩膜叠加方式**：`Image.new("RGBA", size, (255, 0, 0, 100))` 的初始 alpha 随后
-  被 `putalpha(mask)` **整体覆盖**，因此实际效果是「掩膜处不透明纯红」，而不是
-  半透明叠加——`alpha=100` 是无效参数。把它改成真正的半透明会让输出图肉眼
-  可见地变化，那属于产品决策而非缺陷修复，故保留原样并在此记录。
+
+掩膜叠加的 alpha（v0.3.1 修正）
+-------------------------------
+旧实现写作 `Image.new("RGBA", size, (255, 0, 0, 100))`，但紧随其后的
+`putalpha(mask)` 把 alpha 通道**整体替换**为 `mask * 255`，故 `100` 从未生效，
+实际效果是「掩膜处不透明纯红」（alpha=255）。该行为已由用户裁定修正为
+**真正的半透明叠加**：alpha 取 `mask * _OVERLAY_ALPHA`，掩膜处保留常量
+`_OVERLAY_ALPHA`（默认 100，约 39% 不透明），非掩膜处 alpha=0 即完全透出底图。
 """
 
 from __future__ import annotations
@@ -48,6 +52,9 @@ _MIN_DYNAMIC_RANGE: Final[float] = 1e-6
 #: 掩膜叠加色。
 _OVERLAY_RGB: Final[tuple[int, int, int]] = (255, 0, 0)
 
+#: 掩膜叠加的不透明度 (0–255)。掩膜处按此 alpha 与底图混合，非掩膜处完全透出底图。
+_OVERLAY_ALPHA: Final[int] = 100
+
 
 def stretch_percentiles(band: NDArray[np.float32]) -> NDArray[np.float32]:
     """单波段 2–98 分位线性拉伸到 0–255。
@@ -121,9 +128,11 @@ def save_rgb_png(
     image = Image.fromarray(np.transpose(rgb, (1, 2, 0)).astype(np.uint8))
 
     if mask is not None:
-        overlay = Image.new("RGBA", image.size, (*_OVERLAY_RGB, 100))
         image = image.convert("RGBA")
-        mask_image = Image.fromarray((mask * 255).astype(np.uint8))
+        overlay = Image.new("RGBA", image.size, (*_OVERLAY_RGB, 0))
+        # 掩膜处取 _OVERLAY_ALPHA，非掩膜处为 0（完全透明）。与旧实现的差别在于
+        # 旧代码在此写入 mask * 255，使 alpha 恒为 0 或 255，构造时的 alpha 被丢弃。
+        mask_image = Image.fromarray((mask * _OVERLAY_ALPHA).astype(np.uint8))
         mask_image = mask_image.resize(image.size, Image.Resampling.NEAREST)
         overlay.putalpha(mask_image)
         image = Image.alpha_composite(image, overlay)
```

### 6.2 逐块意图说明

| 块 | 位置 | 改动 | 意图 |
|---|---|---|---|
| ① | docstring `:13-24` | 「保持不变的两处」→「一处」；删去掩膜叠加方式条目；新增「掩膜叠加的 alpha（v0.3.1 修正）」小节 | 文档同步。掩膜叠加不再是「有意保持不变」项；新小节记录缺陷成因、用户裁定与新语义。纯注释，无运行期影响 |
| ② | 模块常量 `:52-56` | 新增 `_OVERLAY_ALPHA: Final[int] = 100` 与类型注释 | 把不透明度提为**具名常量**（原先为散落在调用处的字面量 `100`）。使不透明度单一来源、可被测试导入断言，且带类型注解与文档串 |
| ③ | `save_rgb_png` 掩膜分支 `:130-135` | 两处语句**互换顺序**（先 `convert("RGBA")` 再构造 `overlay`）；`overlay` 初值 alpha 由 `100` 改为 `0`；新增一行解释性注释；`mask * 255` 改为 `mask * _OVERLAY_ALPHA` | 语义修正的核心。`overlay` 初值 alpha 取 `0`（非掩膜处完全透明）；`putalpha` 写入 `mask * _OVERLAY_ALPHA`，掩膜处得 `_OVERLAY_ALPHA`、非掩膜处得 `0`，故 `alpha_composite` 得到真正的半透明混合。语句互换仅为可读性（先转换底图再构造叠加层），不影响结果 |

### 6.3 未改动项逐条确认

| 确认项 | 依据 | 结论 |
|---|---|---|
| 拉伸口径（2 / 98 分位、`hi - lo < 1e-6` 抬高）**未被改动** | `_STRETCH_LOW = 2.0`、`_STRETCH_HIGH = 98.0`、`_MIN_DYNAMIC_RANGE = 1e-6` 与 `stretch_percentiles` 函数体均不在 diff 中；对 diff 的 `[-+]` 行检索 `_STRETCH_LOW|_STRETCH_HIGH|percentile|RGB_BANDS|np.repeat|bands ==|bands >=` **命中 0 行** | **未改动**（无回归） |
| 波段数分支逻辑（1 波段 `np.repeat`、≥3 取前三、2 波段拒绝）**未被改动** | `_to_rgb` 函数体（`bands == 1` / `bands >= RGB_BANDS` / `else raise`）完全不在 diff 中；同类检索命中 0 行 | **未改动**（无回归） |
| 3D 维度校验、掩膜形状校验、`RasterWriteError` 包装、`resize(..., NEAREST)`、`alpha_composite`、`convert("RGB")` **未被改动** | 上述语句均未出现在 diff 的 `-`/`+` 行 | **未改动** |
| 除 alpha 语义外无其他行为变化 | diff 全部改动落于：docstring（注释）、新增常量（初始值 `100`，仅被掩膜分支读取）、掩膜分支内的 alpha 相关三行。`save_rgb_png` 在 `mask is None` 时的路径**完全未触及** | **确认** |

补充核对：`_OVERLAY_RGB` 仍定义于 `:53` 且仅在 `:132` 使用一次，配色未变（仍为纯红 `(255, 0, 0)`）；掩膜为空的渲染路径与掩膜外的像素均不受影响——后者由 `test_mask_overlay_preserves_background` 的 `np.array_equal(masked[:, :4], plain[:, :4])` 断言逐位守护（`test_io.py:273`）。

**判定：通过。**

### 6.4 测试侧 diff 的净用例变化

`test_io.py` 的改动为 `37` 增 / `7` 删：

- 用例 `test_mask_overlay_is_opaque_red` **改名并重写**为 `test_mask_overlay_is_semi_transparent_red`（断言由 `(255, 0, 0)` 改为 `(100, 0, 0)` 与掩膜外 `(0, 0, 0)`）；
- **新增** `test_mask_overlay_preserves_background`（判别性证据：掩膜外与无掩膜基准逐位相同；掩膜内绿蓝通道衰减为 `255 - _OVERLAY_ALPHA` 而非归零）；
- 导入由 `RGB_BANDS, stretch_percentiles` 扩为 `_OVERLAY_ALPHA, RGB_BANDS, stretch_percentiles`。

净增 `+1` 用例，与门禁实测的 `135 → 136` 吻合。

## 7. 方法与独立性声明

### 7.1 本次执行的命令清单

只读 git 命令（全部无写副作用）：
`git log --oneline`、`git rev-parse`（含 `^{tree}`）、`git diff`（`--stat` / `--name-only` / `--numstat` / 全文 / 路径限定）、`git status --short`、`git branch`（含 `-a` / `--contains`）、`git tag`（含 `--points-at`）、`git rev-list --parents`、`git merge-base --is-ancestor`、`git stash list`（空）。

测试与门禁命令（一律 `uv run`，UV 可执行文件 `C:\Users\Hujian\CIL\uv\uv.exe`）：
`pytest -o addopts="" -q`、`pytest ... -k overlay`、`pytest --collect-only`、`mypy`、`ruff check .`、`ruff format --check .`、`python scripts/verify_baseline.py --phase 3`、`python scripts/verify_bindings.py`、`python scripts/verify_config.py`。

辅助命令：`grep`（源码/契约检索）、`sha256sum`（还原比对）、`cp` / `rm`（临时备份与回收）。

### 7.2 写操作披露（必须如实）

- **未执行**任何 git 写操作（`add` / `commit` / `branch` / `checkout` / `merge` / `tag` / `stash` / `reset` / `restore` 等一律未运行）；`git stash list` 为空可佐证无 stash 残留。
- 判据 B 要求**临时**改写 `backend/src/rschange/io/preview.py` 的 `_OVERLAY_ALPHA`。该临时改动已按 §3.4 完整恢复，并有三重实证（常量值、sha256 与备份相同、`git diff 9fa1d35` 为空）。
- 除本文件与上述临时改动外，**未写入**任何其他文件。
- 本报告**不**声称「全程未执行任何 git 命令」；只读 git 命令已执行并在 §7.1 逐条列出。

### 7.3 判据来源

本报告的全部判据、数字与结论均来自**本次现场执行**的实际输出，未采信任何转述。测试数、门禁结果、`verify_*` 数字、diff 内容与哈希均逐条复现。

## 8. 未通过项

**不通过项：无。**

## 9. 未关闭项 / 风险（含非阻断项）

| # | 项 | 性质 | 说明 |
|---|---|---|---|
| R1 | 热修**尚未合入 `main`**，且未打 tag | 流程未闭合（非缺陷） | `main` tip 仍为 `8fec430`；`98b1f22` 仅为 `phase-3.1-preview-alpha` 分支 tip。`git merge-base --is-ancestor 98b1f22 main` 退出码 `1`。本报告仅对被验提交 `9fa1d35` / `98b1f22` 出具判定，**不**代表 `main` 已含该热修 |
| R2 | 工作树存在**已暂存的未提交改动**（`preview.py` 与 `test_io.py`，`git status` 显示 `M `） | 状态提示（非缺陷） | 内容与 `9fa1d35` **逐字节一致**（`git diff 9fa1d35` 为空、sha256 相同），故不影响判定；但投放/出 tag 前**应当**确认工作树洁净，避免在 `8fec430` 基础上带着游离改动操作 |
| R3 | 不透明度常量 `_OVERLAY_ALPHA = 100` **未暴露为配置项** | 设计取舍（非缺陷，记录） | 半透明程度为模块常量，产品若要可调需另行提为配置。本次用户裁定为「真半透明」，未要求可配，故不构成缺失 |
| R4 | 掩膜形状与影像不符时**先校验再渲染**，但 `overlay` 尺寸依赖 `image.size`（`= (W, H)`），掩膜经 `NEAREST` 重采样对齐 | 已正确处理（澄清） | 掩膜形状校验（`:118-122`）在 `convert("RGBA")` 之前，故不存在形状不匹配导致的错位；`:136` 的 `resize` 在形状已严格相等时为恒等映射，不引入采样偏差 |
| R5 | 30 个本地分支（含各 `task-*` / `verify-*` / `phase-*`）未清理 | 仓库卫生（非缺陷） | 与本次热修无关，纯记录 |

## 10. 总判定

# 通过

依据：
- **A 差异范围**：改动仅限 `preview.py` 与 `test_io.py` 两个文件，无第三个文件（`git diff --name-only` 实测）。
- **B 反向验证**：`_OVERLAY_ALPHA` 临时改为 `255` 时两个 overlay 用例**变红**（`2 failed, 23 deselected`）；改回 `100` 时**变绿**（`2 passed`）；恢复后 sha256 与备份相同、`git diff 9fa1d35` 为空、全量套件 `136 passed`。断言具备真实判别力。
- **C 契约与语义**：`docs/contracts.md` **从未**描述掩膜叠加的不透明度语义（全文 `alpha` 0 命中），故**无需更新契约**，§9.3 字段级约定改后仍成立；`preview.py` docstring 已同步反映新行为。
- **D 门禁复跑**：七项门禁现场实测全部通过——`pytest` 136 passed、`mypy` 0 错误（36 源文件）、`ruff check` All checks passed、`ruff format --check` 42 files already formatted、`verify_baseline --phase 3` §7.1 11/11 §7.2 2/2 §7.3 7/7、`verify_bindings` 失败 0、`verify_config` 6/6。
- **E 回归核查**：拉伸口径（2/98 分位）与波段数分支逻辑（1 复制 / ≥3 取前三 / 2 拒绝）**均未被触碰**（diff 内同类检索命中 0 行）；除 alpha 语义外无其他行为变化；`mask is None` 路径完全未触及。
- **F 声明纪律**：已如实披露本次执行的写操作（`_OVERLAY_ALPHA` 临时改动及其完整恢复、临时备份文件的创建与删除）与只读 git 命令清单。

**遗留风险（不阻断本次判定）**：热修尚未合入 `main`、未出 tag（R1）；工作树存在与 `9fa1d35` 内容一致的未提交改动（R2）。二者属流程闭合项，**应当**在投放前处理。
