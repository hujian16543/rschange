# 从冻结的 OpenAPI 契约产物生成前端 TypeScript 类型。
#
# 用法：
#     pwsh scripts/gen-api-types.ps1
#
# 契约的两段流水线：
#
#     backend/src/rschange/api/schemas/*.py
#         │  scripts/gen_openapi.py            （门禁：gen_openapi.py --check）
#         ▼
#     docs/api/openapi.json                   （冻结入库）
#         │  scripts/gen-api-types.ps1         （门禁：tests/contract/）
#         ▼
#     frontend/src/api/generated/data-contracts.ts
#
# 生成参数集中在 frontend/package.json 的 `gen:types`，本脚本只负责切目录并调用，
# 避免同一组参数在两处漂移。
#
# 依赖：frontend/node_modules/swagger-typescript-api
# 选它而非 openapi-typescript 的理由：后者 peer 要求 `typescript@^5.x`，与本项目的
# `typescript ~6.0.2` 冲突，装它需要 --force 或 --legacy-peer-deps；而
# swagger-typescript-api 自身依赖 `typescript@^6.0.3`，与本项目同线，无需任何覆盖。

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Frontend = Join-Path $RepoRoot 'frontend'

if (-not (Test-Path (Join-Path $RepoRoot 'docs/api/openapi.json'))) {
    Write-Error "契约产物不存在：docs/api/openapi.json`n       修复：uv run python scripts/gen_openapi.py"
    exit 1
}

if (-not (Test-Path (Join-Path $Frontend 'node_modules/swagger-typescript-api'))) {
    Write-Error "未安装 swagger-typescript-api`n       修复：cd frontend; npm install"
    exit 1
}

Push-Location $Frontend
try {
    npm run --silent gen:types
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
