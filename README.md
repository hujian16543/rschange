# 遥感变化检测平台（Remote Sensing Change Detection）

基于 CVA（变化向量分析）+ Otsu 阈值 + Moore 邻域边界追踪的遥感影像变化检测平台。
C++ 空间引擎（GDAL + nanobind）负责栅格 IO 与矢量导出，Python 负责编排与 Web 服务，React 负责界面。

> 本仓库为重构版本。旧的 Demo 仓库保留为只读参考，其历史不并入本仓库。

---

## 快速开始（Windows）

```powershell
# 1. 配置 Python 环境（幂等，可重复执行）
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1

# 2. 校验黄金基线（重构前后数值必须一致）
uv run python scripts/verify_baseline.py --phase 1
```

Linux / macOS：

```bash
bash scripts/bootstrap.sh
uv run python scripts/verify_baseline.py --phase 1
```

**前置条件**：`uv >= 0.12`、`git >= 2.40`。Python 解释器由 uv 解析，无需手工安装。

---

## 环境约定（必须遵守）

| 约定 | 原因 |
|---|---|
| 一律用 `uv run <cmd>`，禁止裸 `python` / 裸 `pip` | 裸命令可能指向空壳 conda 环境 |
| `.python-version` 必须是精确三段版本号（如 `3.14.6`） | 写宽松的 `3.14` 会让 uv 解析到错误的解释器 |
| 依赖只改 `pyproject.toml`，版本由 `uv.lock` 锁定 | 单一真相源，避免清单失同步 |
| 本机路径只写在 `config/local.toml`（已被 git 忽略） | 禁止在源码中出现机器相关绝对路径 |
| 分支名用连字符，禁止斜杠 | 本机 git 无法写入嵌套引用名，斜杠分支会静默丢失提交 |

---

## 目录结构

```
engine/     C++ 空间引擎（GDAL 栅格 IO、连通域标记、边界追踪、矢量导出）
backend/    Python 后端（FastAPI + rschange 包，uv 工作区成员）
frontend/   React 前端
scripts/    环境引导、构建、基线校验
config/     配置三件套（default / local.example / local）
docs/       架构、迁移对照、契约、验收证据
tests/      API 与契约测试
data/       上传与输出目录（内容不入库）
```

---

## 常用命令

```bash
uv sync --all-packages          # 按 uv.lock 同步依赖
uv run pytest                   # 测试
uv run ruff check backend/      # 静态检查
uv run mypy                     # 类型检查
uv run python scripts/verify_baseline.py --phase 1   # 基线锚点校验
```

`verify_baseline.py` 的 `--phase` 参数决定「期望状态」：

| 取值 | 期望 | 用途 |
|---|---|---|
| `1` | §7.1 全通过、§7.2/§7.3 全失败 | Phase 1：缺陷尚未修复，**失败才是正确结果** |
| `2` 及以上 | 全部通过 | Phase 2 起：缺陷已修复 |

---

## 文档

| 文档 | 内容 |
|---|---|
| `docs/baseline.md` | 黄金基线：数字、血缘、隐式契约 |
| `docs/ARCHITECTURE.md` | 架构与数据流（Phase 7 完成） |
| `docs/MIGRATION.md` | 旧仓库 → 本仓库的文件级对照（Phase 7 完成） |
| `docs/DEVELOPMENT.md` | 如何新增一个检测算法（Phase 7 完成） |
| `docs/verification/` | 各阶段验收证据 |

---

## 许可证

私有项目，未开放许可。
