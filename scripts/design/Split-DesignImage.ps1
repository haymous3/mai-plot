<#
.SYNOPSIS
    Slices a tall design export into native-resolution tiles.

.DESCRIPTION
    The buyer exports run up to 1562x4526. Viewed whole they get downscaled
    roughly 3x, which erases 1px borders and makes padding unmeasurable. Slicing
    into short tiles preserves every pixel, so borders, radii and shadow ramps
    stay readable.

    Tiles overlap by -Overlap pixels so a component sitting on a slice boundary
    still appears intact in one of them.

.PARAMETER Path
    Source PNG.

.PARAMETER OutputDirectory
    Where tiles are written. Created if absent. Existing tiles are overwritten.

.PARAMETER SliceHeight
    Tile height in pixels. Default 900 — tall enough to hold a full section,
    short enough to avoid downscaling on read.

.PARAMETER Overlap
    Pixels of vertical overlap between consecutive tiles. Default 100.

.EXAMPLE
    .\Split-DesignImage.ps1 -Path '..\..\frontend\web\design\buyer-dashboard\Maiplot Web design.png' -OutputDirectory .\out

.NOTES
    Windows-only (System.Drawing). Developer tooling — not part of the build or CI.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Path,

    [Parameter(Mandatory)]
    [string]$OutputDirectory,

    [ValidateRange(100, 4000)]
    [int]$SliceHeight = 900,

    [ValidateRange(0, 500)]
    [int]$Overlap = 100
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

if ($Overlap -ge $SliceHeight) {
    throw "Overlap ($Overlap) must be smaller than SliceHeight ($SliceHeight)."
}

$resolved = (Resolve-Path -LiteralPath $Path).ProviderPath
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$outDir = (Resolve-Path -LiteralPath $OutputDirectory).ProviderPath

$img = [System.Drawing.Image]::FromFile($resolved)
try {
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($resolved)
    $step = $SliceHeight - $Overlap
    $index = 0
    $y = 0

    while ($y -lt $img.Height) {
        $h = [math]::Min($SliceHeight, $img.Height - $y)

        # A trailing sliver shorter than the overlap adds nothing the previous
        # tile did not already contain.
        if ($h -le $Overlap -and $index -gt 0) { break }

        $bmp = New-Object System.Drawing.Bitmap($img.Width, $h)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        try {
            $g.DrawImage(
                $img,
                (New-Object System.Drawing.Rectangle(0, 0, $img.Width, $h)),
                (New-Object System.Drawing.Rectangle(0, $y, $img.Width, $h)),
                [System.Drawing.GraphicsUnit]::Pixel
            )

            $outPath = Join-Path $outDir ("{0}__y{1:d5}.png" -f $baseName, $y)
            $bmp.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)

            [PSCustomObject]@{
                Tile    = Split-Path $outPath -Leaf
                OriginY = $y
                Width   = $img.Width
                Height  = $h
                Path    = $outPath
            }
        }
        finally {
            $g.Dispose()
            $bmp.Dispose()
        }

        $index++
        $y += $step
    }
}
finally {
    $img.Dispose()
}
