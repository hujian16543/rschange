# Phase 1 验收报告 · 环境与仓库奠基

> 证据来自真实命令输出，未作人工修饰。校验在独立构建目录中完成，
> 通过后整体投放至目标路径。

## 1. 阶段出口门判定

| # | 判据 | 结论 | 证据 |
|---|---|---|---|
| G1.1 | 移走 `.venv` 后 `scripts/bootstrap.ps1` 一次跑通 | **通过** | 退出码 `0`；`.venv` 已重建 |
| G1.2 | `backend/` 内无硬编码 `msys64` 路径 | **通过** | 命中 `0` 处 |
| G1.3 | 工作区干净；`.venv` / `config/local.toml` / `build/` 均未入库 | **通过** | 受控文件 `48` 个；泄漏 `0` 项 |
| G1.4 | `verify_baseline.py --phase 1` 输出 §7.1 全 PASS、§7.2/§7.3 全 FAIL | **通过** | 退出码 `0` |
| G1.5 | `.venv\Scripts\python.exe --version` = `3.14.6` | **通过** | 实测 `3.14.6` |

**总判定**：**通过** —— 允许打 tag `v0.1.0`。

## 2. G1.1 真实输出

```text
        # 静态检查
    uv run mypy                                          # 类型检查

  编译 C++ 引擎（Phase 2 起）：
    powershell -ExecutionPolicy Bypass -File scripts/build-engine.ps1

Using CPython 3.14.6 interpreter at: C:\Users\Hujian\DevCode\python\python3.14\python.exe
Creating virtual environment at: .venv
Activate with: .venv\Scripts\activate
Resolved 49 packages in 2ms
   Building rschange @ file:///C:/Users/Hujian/WorkBuddy/2026-09-18-12-56-04/_build/Remote_sensing/backend
      Built rschange @ file:///C:/Users/Hujian/WorkBuddy/2026-09-18-12-56-04/_build/Remote_sensing/backend
Prepared 1 package in 645ms
Installed 43 packages in 488ms
 + annotated-doc==0.0.5
 + annotated-types==0.8.0
 + anyio==4.15.1
 + ast-serialize==0.11.2
 + certifi==2026.7.22
 + click==8.5.0
 + colorama==0.4.6
 + coverage==7.16.1
 + fastapi==0.141.1
 + h11==0.16.0
 + httpcore==1.0.9
 + httptools==0.8.0
 + httpx==0.28.1
 + idna==3.20
 + iniconfig==2.3.0
 + librt==0.15.0
 + mypy==2.3.1
 + mypy-extensions==1.1.0
 + nanobind==3.0.1
 + numpy==2.5.3
 + packaging==26.3
 + pathspec==1.1.1
 + pillow==12.3.0
 + pluggy==1.6.0
 + pydantic==2.13.5
 + pydantic-core==2.46.5
 + pydantic-settings==2.15.0
 + pygments==2.21.0
 + pyproj==3.8.0
 + pytest==9.1.1
 + pytest-cov==7.1.0
 + python-dotenv==1.2.3
 + python-multipart==0.0.32
 + pyyaml==6.0.3
 + rschange==0.1.0 (from file:///C:/Users/Hujian/WorkBuddy/2026-09-18-12-56-04/_build/Remote_sensing/backend)
 + ruff==0.16.8
 + scipy==1.18.1
 + starlette==1.6.0
 + typing-extensions==4.16.0
 + typing-inspection==0.4.4
 + uvicorn==0.53.0
 + watchfiles==1.2.0
 + websockets==17.1
```

## 3. G1.4 黄金基线校验真实输出

```text
============================================================================================================
rschange 黄金基线校验  ·  仓库根 C:\Users\Hujian\WorkBuddy\2026-09-18-12-56-04\_build\Remote_sensing
引擎目录 C:\Users\Hujian\source\My_Project\Remote_Sensing_Change_Detection\build
期望模式 Phase 1：§7.1 应通过，§7.2/7.3 应失败
============================================================================================================
组    判定项                                   期望                        实际                        结果    备注
------------------------------------------------------------------------------------------------------------
7.1  影像形状                                  [3, 256, 256]             [3, 256, 256]             PASS  
7.1  影像 dtype                              uint16                    uint16                    PASS  
7.1  geo_transform                         [500000.0000, 10.0000, 0  [500000.0000, 10.0000, 0  PASS  
7.1  投影含标记                                 UTM zone 50N              True                      PASS  
7.1  宽/高/波段                                256/256/3                 256/256/3                 PASS  
7.1  Otsu 阈值                               5.9168                    5.9168                    PASS  
7.1  变化像素（原始）                              7209                      7209                      PASS  
7.1  变化像素（后处理后）                            7209                      7209                      PASS  
7.1  变化率                                   0.110001                  0.110001                  PASS  
7.1  真实变化面积 m²                             720900.0                  720900.0                  PASS  
7.1  每个环首尾闭合                               True                      True                      PASS  
7.2  GeoJSON Feature 个数                    1                         2                         FAIL  旧引擎实际输出 2（缺陷：单连通域被劈成多段弧）
7.2  属性面积合计 m²                             720900.0                  1441800.0                 FAIL  旧引擎实际输出 1441800.0（缺陷：面积重复计 2 倍）
7.3  Feature 数 == 连通域个数                    1                         2                         FAIL  连通域个数由 scipy 独立计算，不依赖被测代码
7.3  面积合计 == 像素数 × 单像元面积                   720900.0                  1441800.0                 FAIL  
7.3  多区域 label 分配顺序确定                      —                         —                         SKIP  当前 fixture 为单连通域，无法覆盖；Phase 2 补多区域样本后启用
7.3  多边形可被 GEOS 解析且不自交                     —                         —                         SKIP  需 shapely，Phase 2 引入后启用；环闭合本身已归入 §7.1 不变量
------------------------------------------------------------------------------------------------------------
  §7.1 不变量           11/11 通过
  §7.2 缺陷基线          0/2 通过
  §7.3 语义断言          0/2 通过

期望：§7.1 全通过 且 §7.2/§7.3 全失败
结论：通过 —— Phase 1 预期状态已达成
```

## 4. G1.3 工作区状态

```text
(空)
```

## 5. 环境实测

```text
fastapi 0.141.1
numpy 2.5.3
scipy 1.18.1
pyproj 3.8.0
pillow 12.3.0
nanobind 3.0.1
```

## 6. 提交链

```text
*   bb32d11 (HEAD -> phase-1-bootstrap) merge: task-1.4 基线校验工具
|\  
| * 49d62b1 (task-1.4-baseline-tool) test(baseline): 黄金基线校验工具与清理脚本
|/  
*   4f66f6f merge: task-1.3 分层配置
|\  
| * 30985a7 (task-1.3-config) feat(config): 分层配置（默认值入库 + 本机模板）
|/  
*   cfd3ad2 merge: task-1.2 uv 环境
|\  
| * 2bec1a6 (task-1.2-uv-env) build(uv): 建立 uv workspace 与环境引导脚本
|/  
*   5e98761 merge: task-1.1 仓库卫生
|\  
| * cd9c65e (task-1.1-repo-hygiene) chore(hygiene): 仓库卫生五件套
|/  
* 313cf88 (main) chore(scaffold): 初始化目录骨架与占位文件
```

```text
main  313cf88  chore(scaffold): 初始化目录骨架与占位文件
phase-1-bootstrap  bb32d11  merge: task-1.4 基线校验工具
task-1.1-repo-hygiene  cd9c65e  chore(hygiene): 仓库卫生五件套
task-1.2-uv-env  2bec1a6  build(uv): 建立 uv workspace 与环境引导脚本
task-1.3-config  30985a7  feat(config): 分层配置（默认值入库 + 本机模板）
task-1.4-baseline-tool  49d62b1  test(baseline): 黄金基线校验工具与清理脚本
```

## 7. 遗留与后续约束

| 项 | 状态 | 责任阶段 |
|---|---|---|
| `config/local.toml` 的 `engine.build_dir` 指向旧仓库 `build/` | 临时态，Phase 1 专用 | Phase 2 改为 `./engine/build` |
| `config/local.toml` 的 `baseline.fixtures_dir` 指向旧仓库 fixture | 临时态，Phase 1 专用 | Phase 2 改为 `./engine/tests/fixtures` |
| §7.2 缺陷 A4（Moore 追踪致单连通域被劈成多弧、面积重复计） | 未修复，`§7.2` 当前为 FAIL | Phase 2 · `task-2.4-contour` |
| §7.2 缺陷 A6（2D 写盘尺寸错误） | 未修复 | Phase 2 · `task-2.7-bindings` |
| §7.3 多区域 label 定序、GEOS 自交校验 | 未启用（fixture 为单连通域） | Phase 2 |
| `backend/src/rschange/` 子包目录 | 仅占位 | Phase 3 · `task-3.1-src-layout` |
| 前端、Docker、CI 流水线 | 仅目录占位 | Phase 4 / Phase 5 |

## 8. 关于 §7.1 / §7.3 的分组归口（本次修订）

「每个环首尾闭合」在旧引擎上即已成立——它输出的是两段闭合弧，而非开口折线。
因此该项属于**不变量**，归入 §7.1；先前被误置于 §7.3，会把「修复前的正确行为」
误判为「缺陷基线」。修订后的 Phase 1 期望为：§7.1 全部通过、§7.2 与 §7.3 全部失败。
