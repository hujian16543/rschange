# ============================================================
# rschange 清理脚本
#
# 清理构建产物与缓存。**不清理 .venv**——那会迫使重新下载全部依赖，
# 而依赖版本由 uv.lock 锁定，删除 .venv 不带来任何正确性收益。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\clean.ps1           # 全部
#   powershell -ExecutionPolicy Bypass -File scripts\clean.ps1 -Engine   # 仅引擎
#   powershell -ExecutionPolicy Bypass -File scripts\clean.ps1 -Frontend # 仅前端
# ============================================================
[CmdletBinding()]
param(
    [switch]$Engine,
    [switch]$Frontend
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

$all = -not ($Engine -or $Frontend)

$targets = @()
if ($all -or $Engine) {
    $targets += @(
        "engine\build",
        "build"
    )
}
if ($all -or $Frontend) {
    $targets += @(
        "frontend\dist",
        "frontend\node_modules\.vite"
    )
}
if ($all) {
    $targets += @(
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "htmlcov",
        ".coverage"
    )
}

Write-Host "rschange 清理" -ForegroundColor White
Write-Host ("仓库根：{0}" -f $RepoRoot) -ForegroundColor DarkGray

$removed = 0
foreach ($rel in $targets) {
    $path = Join-Path $RepoRoot $rel
    if (Test-Path $path) {
        Remove-Item $path -Recurse -Force
        Write-Host ("  已删除  {0}" -f $rel) -ForegroundColor Yellow
        $removed++
    }
}

# __pycache__ 递归清理
Get-ChildItem $RepoRoot -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\\.venv\\' -and $_.FullName -notmatch '\\node_modules\\' } |
    ForEach-Object {
        Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        $removed++
    }

Write-Host ("完成，共清理 {0} 项。.venv 未动。" -f $removed) -ForegroundColor Green
exit 0
