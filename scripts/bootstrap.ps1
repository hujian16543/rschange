<#
.SYNOPSIS
    rschange 一键环境引导（Windows / PowerShell）。

.DESCRIPTION
    从零把本仓库的 Python 环境配置到可运行状态。全部操作均可重复执行（幂等）。

    设计约束（必须遵守）：
      1. 本脚本内不得出现任何机器相关的绝对路径。解释器位置由 uv 解析，
         脚本只校验「解析结果是否精确等于 .python-version 指定的版本」。
      2. 禁止调用裸 python / 裸 pip —— 两者都可能指向 CIL\conda 的空环境。
      3. 任何一步不满足预期即 exit 1，不得继续后续步骤。
         尤其：解释器版本不精确匹配时必须在装依赖之前中止，
         因为 _spatial 扩展的 ABI 基线是 3.14.6，版本漂移会让基线断言失真。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1

.EXAMPLE
    # 跳过 uv sync（.venv 已就绪时用于快速复检）
    powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1 -SkipSync
#>
[CmdletBinding()]
param(
    # 目标 Python 版本。必须以精确三段版本号给出，例如 3.14.6。
    # 只写 3.14 会让 uv 解析到 CIL\conda 的 3.14.7 空环境。
    [string]$PythonVersion = "3.14.6",

    [switch]$SkipSync
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$TotalSteps  = 7
$RepoRoot    = Split-Path -Parent $PSScriptRoot
$VenvDir     = Join-Path $RepoRoot ".venv"
$VenvPython  = Join-Path $VenvDir "Scripts\python.exe"
$VersionFile = Join-Path $RepoRoot ".python-version"
$ExampleToml = Join-Path $RepoRoot "config\local.example.toml"
$LocalToml   = Join-Path $RepoRoot "config\local.toml"

function Write-Step {
    param([int]$Index, [string]$Text)
    Write-Host ""
    Write-Host ("[{0}/{1}] {2}" -f $Index, $TotalSteps, $Text) -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Text)
    Write-Host ("      OK  {0}" -f $Text) -ForegroundColor Green
}

function Stop-Fail {
    param([string]$Message, [string]$Hint)
    Write-Host ("      FAIL  {0}" -f $Message) -ForegroundColor Red
    if ($Hint) { Write-Host ("      提示  {0}" -f $Hint) -ForegroundColor Yellow }
    exit 1
}

function Get-InterpreterVersion {
    param([string]$Exe)
    $raw = & $Exe -c "import sys; print('.'.join(str(x) for x in sys.version_info[:3]))" 2>&1
    if ($LASTEXITCODE -ne 0) { return $null }
    return ($raw | Out-String).Trim()
}

Write-Host ""
Write-Host "rschange 环境引导" -ForegroundColor White
Write-Host ("仓库根：{0}" -f $RepoRoot) -ForegroundColor DarkGray
Write-Host ("目标解释器：{0}" -f $PythonVersion) -ForegroundColor DarkGray

Set-Location $RepoRoot

# ------------------------------------------------------------------
Write-Step 1 "断言 uv 可用"
# ------------------------------------------------------------------
$UvBin = $env:UV_BIN
if (-not $UvBin) {
    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCmd) { $UvBin = $uvCmd.Source }
}
if (-not $UvBin -or -not (Test-Path $UvBin)) {
    Stop-Fail "未找到 uv" "安装方式：winget install astral-sh.uv 或 pipx install uv。也可用环境变量 UV_BIN 指定绝对路径。"
}
$uvVersion = (& $UvBin --version 2>&1 | Out-String).Trim()
Write-Ok ("uv  {0}" -f $uvVersion)
Write-Ok ("路径 {0}" -f $UvBin)

# ------------------------------------------------------------------
Write-Step 2 "断言解释器可被精确解析（防 conda 陷阱）"
# ------------------------------------------------------------------
if (-not (Test-Path $VersionFile)) {
    Stop-Fail ".python-version 不存在" "该文件必须存在且内容为精确版本号，例如 3.14.6"
}
$pinned = (Get-Content $VersionFile -Raw).Trim()
if ($pinned -ne $PythonVersion) {
    Stop-Fail (".python-version 内容为 [{0}]，与目标 [{1}] 不一致" -f $pinned, $PythonVersion) `
              "两者必须一致。写宽松版本（如 3.14）会让 uv 选中 CIL\conda 的 3.14.7 空环境。"
}
if ($pinned -notmatch '^\d+\.\d+\.\d+$') {
    Stop-Fail (".python-version 必须是三段精确版本号，当前为 [{0}]" -f $pinned) `
              "uv python find 3.14 会返回 CIL\conda\python.exe（空环境），必须写 3.14.6。"
}
Write-Ok (".python-version = {0}" -f $pinned)

if (-not (Test-Path $VenvPython)) {
    $foundRaw = (& $UvBin python find $PythonVersion 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        Stop-Fail ("uv 无法解析 Python {0}" -f $PythonVersion) "确认该解释器已安装。"
    }
    $foundExe = $foundRaw.Trim()
    Write-Ok ("uv 解析到 {0}" -f $foundExe)

    if ($foundExe -match '(?i)conda') {
        Stop-Fail "解析结果落在 conda 环境内，该环境为空壳" `
                  "这正是 A1 缺陷的源头。确认 .python-version 为精确版本号，且 pyproject.toml 中 python-preference = 'only-system'。"
    }
    $foundVer = Get-InterpreterVersion -Exe $foundExe
    if ($foundVer -ne $PythonVersion) {
        Stop-Fail ("解析到的解释器实际版本为 {0}，期望 {1}" -f $foundVer, $PythonVersion) `
                  "版本必须精确一致：_spatial 扩展的 ABI 验证基线是 3.14.6。"
    }
    Write-Ok ("实际版本 {0}（精确匹配）" -f $foundVer)
} else {
    Write-Ok ".venv 已存在，解释器解析检查改由第 4 步执行"
}

# ------------------------------------------------------------------
Write-Step 3 "创建项目级 .venv"
# ------------------------------------------------------------------
if (Test-Path $VenvPython) {
    Write-Ok ".venv 已存在，跳过创建"
} else {
    & $UvBin venv --python $PythonVersion
    if ($LASTEXITCODE -ne 0) { Stop-Fail "uv venv 失败" $null }
    Write-Ok "已创建 .venv"
}

# ------------------------------------------------------------------
Write-Step 4 "断言 .venv 解释器版本"
# ------------------------------------------------------------------
if (-not (Test-Path $VenvPython)) { Stop-Fail ".venv\Scripts\python.exe 不存在" $null }
$venvVer = Get-InterpreterVersion -Exe $VenvPython
if ($venvVer -ne $PythonVersion) {
    Stop-Fail (".venv 解释器版本为 {0}，期望 {1}" -f $venvVer, $PythonVersion) "删除 .venv 后重跑本脚本。"
}
Write-Ok (".venv 解释器版本 {0}" -f $venvVer)

# ------------------------------------------------------------------
Write-Step 5 "按 uv.lock 安装依赖"
# ------------------------------------------------------------------
if ($SkipSync) {
    Write-Ok "已指定 -SkipSync，跳过"
} else {
    & $UvBin sync --all-packages
    if ($LASTEXITCODE -ne 0) {
        Stop-Fail "uv sync 失败" "常见原因：网络不可达、uv.lock 与 pyproject.toml 不同步（试 uv lock）。"
    }
    Write-Ok "uv sync 完成"
}

# ------------------------------------------------------------------
Write-Step 6 "生成 config/local.toml"
# ------------------------------------------------------------------
if (Test-Path $LocalToml) {
    Write-Ok "config/local.toml 已存在，未覆盖"
} else {
    if (-not (Test-Path $ExampleToml)) {
        Stop-Fail "config/local.example.toml 不存在，无法生成模板" "该文件必须入库，作为本机配置的唯一模板。"
    }
    Copy-Item $ExampleToml $LocalToml
    Write-Ok "已从 local.example.toml 生成 config/local.toml（该文件已被 git 忽略）"
}

# ------------------------------------------------------------------
Write-Step 7 "下一步"
# ------------------------------------------------------------------
Write-Host ""
Write-Host "  环境就绪。后续命令一律走 uv，不激活 venv 也能执行：" -ForegroundColor White
Write-Host "    uv run python scripts/verify_baseline.py --phase 1    # 基线锚点校验" -ForegroundColor DarkGray
Write-Host "    uv run pytest                                        # 单元与集成测试" -ForegroundColor DarkGray
Write-Host "    uv run ruff check backend/                           # 静态检查" -ForegroundColor DarkGray
Write-Host "    uv run mypy                                          # 类型检查" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  编译 C++ 引擎（Phase 2 起）：" -ForegroundColor White
Write-Host "    powershell -ExecutionPolicy Bypass -File scripts/build-engine.ps1" -ForegroundColor DarkGray
Write-Host ""

exit 0
