[CmdletBinding()]
param([string] $Python, [switch] $AllowUnverified)

. (Join-Path $PSScriptRoot 'windows_common.ps1')
Assert-Windows
$BuildPython = Get-BuildPython $Python
$null = Assert-GeneratedPath 'release'
$null = Assert-GeneratedPath 'dist'
$null = Assert-GeneratedPath 'build\.work'
Push-Location $ProjectRoot
try {
    $arguments = @('scripts/windows_support.py', 'package')
    if ($AllowUnverified) { $arguments += '--allow-unverified' }
    Invoke-BuildPython -Arguments $arguments
} finally {
    Pop-Location
}
