#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# rschange 一键环境引导（Linux / macOS）
#
# 与 bootstrap.ps1 行为等价，步骤编号一一对应：
#   1 断言 uv 可用
#   2 断言解释器可被精确解析（防 conda 陷阱）
#   3 创建项目级 .venv
#   4 断言 .venv 解释器版本
#   5 按 uv.lock 安装依赖
#   6 生成 config/local.toml
#   7 打印下一步
#
# 设计约束：脚本内不得出现机器相关的绝对路径；解释器位置由 uv 解析。
# ---------------------------------------------------------------------------
set -euo pipefail

PYTHON_VERSION="${PYTHON_VERSION:-3.14.6}"
SKIP_SYNC="${SKIP_SYNC:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
VERSION_FILE="$REPO_ROOT/.python-version"
EXAMPLE_TOML="$REPO_ROOT/config/local.example.toml"
LOCAL_TOML="$REPO_ROOT/config/local.toml"

TOTAL_STEPS=7

step() { printf '\n[%s/%s] %s\n' "$1" "$TOTAL_STEPS" "$2"; }
ok()   { printf '      OK  %s\n' "$1"; }
fail() {
  printf '      FAIL  %s\n' "$1" >&2
  if [ -n "${2:-}" ]; then printf '      提示  %s\n' "$2" >&2; fi
  exit 1
}

interp_version() {
  "$1" -c "import sys; print('.'.join(str(x) for x in sys.version_info[:3]))" 2>/dev/null || return 1
}

printf '\nrschange 环境引导\n'
printf '仓库根：%s\n' "$REPO_ROOT"
printf '目标解释器：%s\n' "$PYTHON_VERSION"

cd "$REPO_ROOT"

# --- 1 ---------------------------------------------------------------------
step 1 "断言 uv 可用"
UV_BIN="${UV_BIN:-$(command -v uv || true)}"
[ -n "$UV_BIN" ] && [ -x "$UV_BIN" ] || fail "未找到 uv" "安装：curl -LsSf https://astral.sh/uv/install.sh | sh，或用 UV_BIN 指定绝对路径"
ok "uv  $("$UV_BIN" --version)"
ok "路径 $UV_BIN"

# --- 2 ---------------------------------------------------------------------
step 2 "断言解释器可被精确解析（防 conda 陷阱）"
[ -f "$VERSION_FILE" ] || fail ".python-version 不存在" "该文件必须存在且内容为精确版本号，例如 3.14.6"
PINNED="$(tr -d '[:space:]' < "$VERSION_FILE")"
[ "$PINNED" = "$PYTHON_VERSION" ] || fail ".python-version 内容为 [$PINNED]，与目标 [$PYTHON_VERSION] 不一致" "两者必须一致"
case "$PINNED" in
  [0-9]*.[0-9]*.[0-9]*) : ;;
  *) fail ".python-version 必须是三段精确版本号，当前为 [$PINNED]" "写宽松版本会让 uv 选中错误的解释器" ;;
esac
ok ".python-version = $PINNED"

if [ -x "$VENV_PYTHON" ]; then
  ok ".venv 已存在，解释器解析检查改由第 4 步执行"
else
  FOUND_EXE="$("$UV_BIN" python find "$PYTHON_VERSION" 2>/dev/null || true)"
  [ -n "$FOUND_EXE" ] || fail "uv 无法解析 Python $PYTHON_VERSION" "确认该解释器已安装"
  ok "uv 解析到 $FOUND_EXE"

  case "$FOUND_EXE" in
    *conda*) fail "解析结果落在 conda 环境内，该环境为空壳" ".python-version 必须为精确版本号，且 pyproject.toml 需设 python-preference = \"only-system\"" ;;
  esac

  FOUND_VER="$(interp_version "$FOUND_EXE" || true)"
  [ "$FOUND_VER" = "$PYTHON_VERSION" ] || fail "解析到的解释器实际版本为 $FOUND_VER，期望 $PYTHON_VERSION" "版本必须精确一致：_spatial 扩展的 ABI 验证基线是 3.14.6"
  ok "实际版本 $FOUND_VER（精确匹配）"
fi

# --- 3 ---------------------------------------------------------------------
step 3 "创建项目级 .venv"
if [ -x "$VENV_PYTHON" ]; then
  ok ".venv 已存在，跳过创建"
else
  "$UV_BIN" venv --python "$PYTHON_VERSION" || fail "uv venv 失败" ""
  ok "已创建 .venv"
fi

# --- 4 ---------------------------------------------------------------------
step 4 "断言 .venv 解释器版本"
[ -x "$VENV_PYTHON" ] || fail ".venv/bin/python 不存在" ""
VENV_VER="$(interp_version "$VENV_PYTHON" || true)"
[ "$VENV_VER" = "$PYTHON_VERSION" ] || fail ".venv 解释器版本为 $VENV_VER，期望 $PYTHON_VERSION" "删除 .venv 后重跑本脚本"
ok ".venv 解释器版本 $VENV_VER"

# --- 5 ---------------------------------------------------------------------
step 5 "按 uv.lock 安装依赖"
if [ "$SKIP_SYNC" = "1" ]; then
  ok "已指定 SKIP_SYNC=1，跳过"
else
  "$UV_BIN" sync --all-packages || fail "uv sync 失败" "常见原因：网络不可达、uv.lock 与 pyproject.toml 不同步（试 uv lock）"
  ok "uv sync 完成"
fi

# --- 6 ---------------------------------------------------------------------
step 6 "生成 config/local.toml"
if [ -f "$LOCAL_TOML" ]; then
  ok "config/local.toml 已存在，未覆盖"
else
  [ -f "$EXAMPLE_TOML" ] || fail "config/local.example.toml 不存在，无法生成模板" "该文件必须入库"
  cp "$EXAMPLE_TOML" "$LOCAL_TOML"
  ok "已从 local.example.toml 生成 config/local.toml（该文件已被 git 忽略）"
fi

# --- 7 ---------------------------------------------------------------------
step 7 "下一步"
printf '\n  环境就绪。后续命令一律走 uv：\n'
printf '    uv run python scripts/verify_baseline.py --phase 1\n'
printf '    uv run pytest\n'
printf '    uv run ruff check backend/\n'
printf '    uv run mypy\n\n'

exit 0
