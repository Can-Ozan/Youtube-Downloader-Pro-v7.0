Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))

function Assert-Windows {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'This build pipeline requires Windows 10/11 x64.'
    }
}

function Get-BuildPython([string] $Requested) {
    if ($Requested) { return (Get-Command $Requested -ErrorAction Stop).Source }
    $localPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $localPython -PathType Leaf) { return $localPython }
    return (Get-Command python -ErrorAction Stop).Source
}

function Invoke-BuildPython([string[]] $Arguments) {
    & $BuildPython @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python command failed ($LASTEXITCODE): $($Arguments -join ' ')" }
}

function Assert-GeneratedPath([string] $RelativePath) {
    $allowed = @('build\.work', 'build\.cache', 'dist', 'release')
    if ($RelativePath -notin $allowed) { throw "Not an allowed generated directory: $RelativePath" }
    $target = [IO.Path]::GetFullPath((Join-Path $ProjectRoot $RelativePath))
    $prefix = $ProjectRoot.TrimEnd('\') + '\'
    if (-not $target.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Generated path is outside the repository: $target"
    }
    # Refuse junctions/symlinks at any ancestor or inside a recursively removed tree.
    $ancestor = $target
    while ($ancestor) {
        if (Test-Path -LiteralPath $ancestor) {
            $item = Get-Item -LiteralPath $ancestor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Refusing a generated path through a junction/symlink: $ancestor"
            }
        }
        $ancestor = Split-Path -Parent $ancestor
    }
    if (Test-Path -LiteralPath $target) {
        $links = Get-ChildItem -LiteralPath $target -Force -Recurse |
            Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }
        if ($links) { throw "Refusing cleanup of a tree containing junctions/symlinks: $target" }
    }
    return $target
}
