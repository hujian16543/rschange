"""文档路径引用自检：文档写出的仓库相对引用必须指向真实存在的文件。

用法：
    python scripts/verify_doc_paths.py [--root <仓库根>]

判据：
    1. 扫描范围 = 仓库根 `*.md` 与 `docs/**/*.md`；**排除** `docs/archive/`
       （归档文档，其 README 已声明为非规范并保留原文）与 `docs/verification/`
       （冻结的验收报告，出具后不得改动），亦排除构建与依赖目录。
    2. 文档中形如 `docs/x.md` / `scripts/y.py` / `backend/.../z.toml` 的引用，
       除 ALLOWLIST 列明者外，**必须**指向真实存在的文件。
    3. 退出码 0 = 通过；1 = 存在失效引用。

设计依据：
    本脚本由 v1.0.1 热修引入。v1.0.0 交付物中有 9 处失效引用（`docs/CONTRIBUTING.md`
    3 处——文件实际在仓库根；`tests/test_*.py` 6 处——实际在 `backend/src/rschange/tests/`），
    成因是收口阶段的判据集里没有「文档路径可解析」这一项。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 引用的书写形态：以已知顶层目录起头、以已知扩展名结尾，且两侧不粘连其他标识符字符。
_REF = re.compile(
    r"(?<![\w./-])((?:docs|scripts|backend|frontend|engine|docker|config|tests)/"
    r"[A-Za-z0-9_./-]*\.(?:tsx|ts|md|py|toml|json|yml|yaml|hpp|cpp|sh|ps1|txt|css|html))"
    r"(?![A-Za-z0-9])"
)

# 扫描时跳过的目录：归档（保留原文）· 冻结报告 · 构建与依赖产物。
_SKIP_DIRS = frozenset({"docs/archive", "docs/verification"})
_PRUNE = frozenset(
    {"node_modules", ".venv", ".git", "dist", "build", "_deps", "__pycache__", ".mypy_cache"}
)

# 故意不存在的引用及其理由。新增条目**必须**写明理由，否则视为缺陷。
ALLOWLIST: dict[str, str] = {
    "scripts/xxx.py": "占位符写法（§7.3 说明 `sys.path[0] = scripts/` 时用的示意路径）",
    "docs/verification/phase-N.md": "占位符写法（阶段号通配，见 CONTRIBUTING 的回退策略）",
    "backend/src/rschange/detectors/ndvi_diff.py": "教学示例要求读者**新建**的文件（DEVELOPMENT §7.1）",
    "backend/src/rschange/tests/test_ndvi_diff.py": "教学示例要求读者**新建**的文件（DEVELOPMENT §7.5）",
    "frontend/src/types/detection.ts": "Phase 5 已删除的手写类型，文中作沿革说明（contracts.md 变更记录）",
}


def _iter_markdown(root: Path) -> list[Path]:
    """返回待扫描的 Markdown 文件，按相对路径排序。"""
    found: list[Path] = []
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root)
        if any(part in _PRUNE for part in rel.parts):
            continue
        if any(rel.as_posix().startswith(skip + "/") for skip in _SKIP_DIRS):
            continue
        found.append(path)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="文档路径引用自检")
    parser.add_argument("--root", default=None, help="仓库根目录（默认取脚本所在仓库）")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]

    files = _iter_markdown(root)
    total = 0
    skipped = 0
    failures: list[tuple[str, str]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            continue
        rel = path.relative_to(root).as_posix()
        for lineno, line in enumerate(text.splitlines(), 1):
            for token in _REF.findall(line):
                total += 1
                if token in ALLOWLIST:
                    skipped += 1
                    continue
                if not (root / token).exists():
                    failures.append((token, f"{rel}:{lineno}"))

    print("文档路径引用自检：文档写出的仓库相对引用必须指向真实存在的文件")
    print("=" * 80)
    print(f"扫描文件  {len(files)} 个（已排除 {' · '.join(sorted(_SKIP_DIRS))} 及构建/依赖目录）")
    print(f"引用总数  {total} 条，其中允许例外 {skipped} 条（ALLOWLIST，理由见脚本内注释）")
    print()

    if failures:
        print("失效引用：")
        for token, place in failures:
            print(f"  [缺] {token}  <- {place}")
        print()

    print(f"判定项 {total} 条（跳过 {skipped} 条），不通过 {len(failures)} 条")
    if failures:
        print("结论：不通过 —— 上述引用在仓库内不存在；修正路径，或在 ALLOWLIST 中写明理由")
        return 1
    print("结论：通过 —— 全部引用均指向真实存在的文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
