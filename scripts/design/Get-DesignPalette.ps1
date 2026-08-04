<#
.SYNOPSIS
    Extracts the exact colour palette from a design export, ranked by pixel share.

.DESCRIPTION
    Tallies every sampled pixel and reports the most frequent colours with their
    share of the sampled area. This gives exact hex values rather than eyeballed
    approximations, which is the whole point: a colour picked by eye off a
    downscaled screenshot is an antialiased blend, not the real token.

    Photographic regions (property images) produce thousands of near-unique
    colours that dilute the ranking. -MinimumShare filters them out; UI surfaces
    are large flat areas and always rank well above the threshold.

.PARAMETER Path
    Source PNG, or a directory to scan.

.PARAMETER Top
    How many colours to report. Default 25.

.PARAMETER Stride
    Sample every Nth pixel in both axes. Default 2 (samples 25% of pixels).
    Stride 1 is exact but ~4x slower; flat UI colours rank identically either way.

.PARAMETER MinimumShare
    Drop colours below this percentage of sampled pixels. Default 0.1.

.EXAMPLE
    .\Get-DesignPalette.ps1 -Path '..\..\frontend\web\design\buyer-dashboard\Maiplot Web design.png'

.EXAMPLE
    .\Get-DesignPalette.ps1 -Path '..\..\frontend\web\design\realtor-dashboard' -Top 15

.NOTES
    Windows-only (System.Drawing). Developer tooling — not part of the build or CI.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Path,

    [ValidateRange(1, 200)]
    [int]$Top = 25,

    [ValidateRange(1, 8)]
    [int]$Stride = 2,

    [ValidateRange(0, 100)]
    [double]$MinimumShare = 0.1
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'DesignImage.psm1') -Force

$resolved = (Resolve-Path -LiteralPath $Path).ProviderPath
$targets = if (Test-Path -LiteralPath $resolved -PathType Container) {
    Get-ChildItem -LiteralPath $resolved -Filter *.png -Recurse | Select-Object -ExpandProperty FullName
} else {
    @($resolved)
}

foreach ($target in $targets) {
    $img = Import-DesignBitmap -Path $target
    $tally = @{}

    for ($y = 0; $y -lt $img.Height; $y += $Stride) {
        $row = $y * $img.Stride
        for ($x = 0; $x -lt $img.Width; $x += $Stride) {
            $o = $row + $x * 4
            $key = '{0:x2}{1:x2}{2:x2}' -f $img.Bytes[$o + 2], $img.Bytes[$o + 1], $img.Bytes[$o]
            if ($tally.ContainsKey($key)) { $tally[$key]++ } else { $tally[$key] = 1 }
        }
    }

    $sampled = ($tally.Values | Measure-Object -Sum).Sum

    Write-Verbose "$($img.Name): $($tally.Count) distinct colours across $sampled sampled pixels"

    $tally.GetEnumerator() |
        Sort-Object Value -Descending |
        ForEach-Object {
            $share = 100 * $_.Value / $sampled
            if ($share -ge $MinimumShare) {
                [PSCustomObject]@{
                    Source   = $img.Name
                    Hex      = "#$($_.Key)"
                    Pixels   = $_.Value
                    Share    = [math]::Round($share, 2)
                    Distinct = $tally.Count
                }
            }
        } |
        Select-Object -First $Top
}
