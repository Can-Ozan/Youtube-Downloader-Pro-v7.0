[CmdletBinding()]
param(
    [string] $Python,
    [switch] $InstallDependencies,
    [string] $FFmpegDirectory,
    [switch] $DebugConsole,
    [switch] $AllowBlockedSmokeTest
)

. (Join-Path $PSScriptRoot 'windows_common.ps1')
Assert-Windows
$BuildPython = Get-BuildPython $Python
if ($FFmpegDirectory) { $FFmpegDirectory = (Resolve-Path -LiteralPath $FFmpegDirectory).Path }
$savedEnvironment = @{}
foreach ($key in @('PYINSTALLER_CONFIG_DIR', 'YDP_BUNDLE_FFMPEG', 'YDP_DEBUG_CONSOLE', 'QT_QPA_PLATFORM')) {
    $savedEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
}
Push-Location $ProjectRoot
try {
    if ($InstallDependencies) {
        # Dependency installation is an explicit developer action, isolated to a venv.
        Invoke-BuildPython -Arguments @('-c', 'import sys; assert sys.prefix != sys.base_prefix, "Create a virtual environment first"')
        Invoke-BuildPython -Arguments @('-m', 'pip', 'install', '-e', '.[dev]')
    }
    Invoke-BuildPython -Arguments @('scripts/windows_support.py', 'environment')
    Invoke-BuildPython -Arguments @('-m', 'pip', 'check')
    & (Join-Path $PSScriptRoot 'clean_build.ps1')
    $env:PYINSTALLER_CONFIG_DIR = Assert-GeneratedPath 'build\.cache'
    $env:QT_QPA_PLATFORM = 'offscreen'
    [Environment]::SetEnvironmentVariable('YDP_BUNDLE_FFMPEG', $null, 'Process')
    [Environment]::SetEnvironmentVariable('YDP_DEBUG_CONSOLE', $null, 'Process')
    if ($FFmpegDirectory) { $env:YDP_BUNDLE_FFMPEG = (Resolve-Path -LiteralPath $FFmpegDirectory).Path }
    if ($DebugConsole) { $env:YDP_DEBUG_CONSOLE = '1' }
    Invoke-BuildPython -Arguments @('-m', 'pytest')
    Invoke-BuildPython -Arguments @('-m', 'ruff', 'check', '.')
    Invoke-BuildPython -Arguments @('-m', 'compileall', 'youtube_downloader_pro')
    Invoke-BuildPython -Arguments @('-m', 'youtube_downloader_pro', '--smoke-test', '--data-dir', '.test-artifacts/source-startup', '--smoke-report', '.test-artifacts/source-startup.json')
    Invoke-BuildPython -Arguments @('-m', 'PyInstaller', '--noconfirm', '--workpath', 'build/.work', '--distpath', 'dist', 'build/windows.spec')
    Invoke-BuildPython -Arguments @('scripts/windows_support.py', 'audit')
    $smokeArguments = @('scripts/windows_support.py', 'smoke')
    if ($AllowBlockedSmokeTest) { $smokeArguments += '--allow-blocked' }
    Invoke-BuildPython -Arguments $smokeArguments
    Write-Host "EXE: $(Join-Path $ProjectRoot 'dist\YouTube Downloader Pro\YouTube Downloader Pro.exe')"
    Write-Host 'Startup status: build/.work/packaged-smoke.json. Distribute the entire ONEDIR folder.'
} finally {
    foreach ($key in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($key, $savedEnvironment[$key], 'Process')
    }
    Pop-Location
}
