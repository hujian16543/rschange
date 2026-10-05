#!/usr/bin/env bash
#
# 从冻结的 OpenAPI 契约产物生成前端 TypeScript 类型。
#
# 用法：
#     bash scripts/gen-api-types.sh
#
# 契约的两段流水线：
#
#     backend/src/rschange/api/schemas/*.py
#         │  scripts/gen_openapi.py            （门禁：gen_openapi.py --check）
#         ▼
#     docs/api/openapi.json                   （冻结入库）
#         │  scripts/gen-api-types.sh          （门禁：CI 步骤「契约类型零漂移（openapi → TS）」）
#         ▼
#     frontend/src/api/generated/data-contracts.ts
#
# 两段各有独立门禁，缺一段就会留下「产物更新了但下游没跟上」的窗口——那正是
# Phase 5 出口门 G5.2 要拦的情形。
#
# 生成参数集中在 frontend/package.json 的 `gen:types`，本脚本只负责切目录并调用，
# 避免同一组参数在两处漂移。
#
# 依赖：frontend/node_modules/swagger-typescript-api
# 选它而非 openapi-typescript 的理由：后者 peer 要求 `typescript@^5.x`，与本项目的
# `typescript ~6.0.2` 冲突，装它需要 --force 或 --legacy-peer-deps；而
# swagger-typescript-api 自身依赖 `typescript@^6.0.3`，与本项目同线，无需任何覆盖。
#
# 本脚本**不**做漂移校验：校验由 `scripts/gen_openapi.py --check`（守第一段）与
# `tests/contract/`（守第二段）承担，每道门禁只有一个归属处。
set -euo pipefail

# 路径只用 bash 内建推导：本机 PATH 上的 dirname 可能不可用。
REPO_ROOT="$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd)"
FRONTEND="$REPO_ROOT/frontend"

if [ ! -f "$REPO_ROOT/docs/api/openapi.json" ]; then
    echo "[FAIL] 契约产物不存在：docs/api/openapi.json" >&2
    echo "       修复：uv run python scripts/gen_openapi.py" >&2
    exit 1
fi

if [ ! -d "$FRONTEND/node_modules/swagger-typescript-api" ]; then
    echo "[FAIL] 未安装 swagger-typescript-api" >&2
    echo "       修复：cd frontend && npm install" >&2
    exit 1
fi

cd -- "$FRONTEND"
npm run --silent gen:types
