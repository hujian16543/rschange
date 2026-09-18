#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# rschange 清理脚本（Linux / macOS）
#
# 清理构建产物与缓存。**不清理 .venv**——删了会迫使重新下载全部依赖，
# 而版本由 uv.lock 锁定，删除不带来正确性收益。
#
# 用法：
#   bash scripts/clean.sh            # 全部
#   bash scripts/clean.sh engine     # 仅引擎
#   bash scripts/clean.sh frontend   # 仅前端
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
TARGET="${1:-all}"

cd "$REPO_ROOT"

targets=()
case "$TARGET" in
  all)
    targets=(engine/build build frontend/dist .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage)
    ;;
  engine)
    targets=(engine/build build)
    ;;
  frontend)
    targets=(frontend/dist frontend/node_modules/.vite)
    ;;
  *)
    printf '未知目标：%s（可选 all / engine / frontend）\n' "$TARGET" >&2
    exit 1
    ;;
esac

printf 'rschange 清理\n仓库根：%s\n' "$REPO_ROOT"

removed=0
for rel in "${targets[@]}"; do
  if [ -e "$rel" ]; then
    rm -rf "$rel"
    printf '  已删除  %s\n' "$rel"
    removed=$((removed + 1))
  fi
done

while IFS= read -r -d '' dir; do
  case "$dir" in
    */.venv/*|*/node_modules/*) continue ;;
  esac
  rm -rf "$dir"
  removed=$((removed + 1))
done < <(find . -type d -name __pycache__ -print0 2>/dev/null || true)

printf '完成，共清理 %s 项。.venv 未动。\n' "$removed"
exit 0
