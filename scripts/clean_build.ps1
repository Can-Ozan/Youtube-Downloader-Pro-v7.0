[CmdletBinding(SupportsShouldProcess)]
param([switch] $IncludeRelease)

. (Join-Path $PSScriptRoot 'windows_common.ps1')
Assert-Windows
$directories = @('build\.work', 'build\.cache', 'dist')
if ($IncludeRelease) { $directories += 'release' }
# Validate every target before deleting any output. build/ itself is source.
$targets = @($directories | ForEach-Object { Assert-GeneratedPath $_ })
foreach ($target in $targets) {
    if ((Test-Path -LiteralPath $target) -and $PSCmdlet.ShouldProcess($target, 'Remove generated output')) {
        Remove-Item -LiteralPath $target -Recurse -Force
        Write-Host "Removed generated output: $target"
    }
}
