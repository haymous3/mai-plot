<#
.SYNOPSIS
    Builds labelled contact sheets from a directory of design exports.

.DESCRIPTION
    The exports are named opaquely ("Maiplot Web design (7).png") and several
    files named "Mobile App Onboarding Flow" are in fact desktop-width screens.
    Identifying 60+ of them one at a time is slow; a contact sheet puts a grid
    of numbered thumbnails on one page so screens can be matched to routes in
    a handful of passes.

    Thumbnails are cropped to the top -CropHeight pixels rather than squeezed
    whole. A full 1562x4526 page scaled into a thumbnail cell is unreadable,
    while its top region still shows the header and page title — which is what
    identifies the screen.

    Each cell is stamped with an index that matches the manifest emitted to the
    pipeline, so a sheet can be read back to real filenames.

.PARAMETER Path
    Directory of PNGs to sheet.

.PARAMETER OutputDirectory
    Where sheets are written.

.PARAMETER Columns
    Thumbnails per row. Default 3.

.PARAMETER Rows
    Thumbnail rows per sheet. Default 3.

.PARAMETER CellWidth
    Thumbnail cell width in pixels. Default 500.

.PARAMETER CropHeight
    How much of the top of each source image to use. Default 1000.

.EXAMPLE
    .\New-DesignContactSheet.ps1 -Path '..\..\frontend\web\design\buyer-dashboard' -OutputDirectory .\sheets

.NOTES
    Windows-only (System.Drawing). Developer tooling — not part of the build or CI.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Path,

    [Parameter(Mandatory)]
    [string]$OutputDirectory,

    [ValidateRange(1, 6)]
    [int]$Columns = 3,

    [ValidateRange(1, 6)]
    [int]$Rows = 3,

    [ValidateRange(200, 1200)]
    [int]$CellWidth = 500,

    [ValidateRange(200, 6000)]
    [int]$CropHeight = 1000
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$resolved = (Resolve-Path -LiteralPath $Path).ProviderPath
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$outDir = (Resolve-Path -LiteralPath $OutputDirectory).ProviderPath

$files = Get-ChildItem -LiteralPath $resolved -Filter *.png | Sort-Object Name
if ($files.Count -eq 0) { throw "No PNGs found in $resolved" }

$labelHeight = 26
$cellHeight = [int]($CellWidth * 0.72)
$pad = 10
$sheetWidth = $Columns * ($CellWidth + $pad) + $pad
$sheetHeight = $Rows * ($cellHeight + $labelHeight + $pad) + $pad
$perSheet = $Columns * $Rows
$sheetCount = [math]::Ceiling($files.Count / $perSheet)

$font = New-Object System.Drawing.Font('Consolas', 11, [System.Drawing.FontStyle]::Bold)
$labelBrush = [System.Drawing.Brushes]::Black
$borderPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(160, 160, 160), 1)

try {
    for ($s = 0; $s -lt $sheetCount; $s++) {
        $sheet = New-Object System.Drawing.Bitmap($sheetWidth, $sheetHeight)
        $g = [System.Drawing.Graphics]::FromImage($sheet)

        try {
            $g.Clear([System.Drawing.Color]::White)
            $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic

            for ($i = 0; $i -lt $perSheet; $i++) {
                $fileIndex = $s * $perSheet + $i
                if ($fileIndex -ge $files.Count) { break }

                $file = $files[$fileIndex]
                $col = $i % $Columns
                $row = [math]::Floor($i / $Columns)
                $x = $pad + $col * ($CellWidth + $pad)
                $y = $pad + $row * ($cellHeight + $labelHeight + $pad)

                $src = [System.Drawing.Image]::FromFile($file.FullName)
                try {
                    $srcH = [math]::Min($CropHeight, $src.Height)
                    $srcRect = New-Object System.Drawing.Rectangle(0, 0, $src.Width, $srcH)

                    # Preserve aspect ratio of the cropped region inside the cell.
                    $scale = [math]::Min($CellWidth / $src.Width, $cellHeight / $srcH)
                    $drawW = [int]($src.Width * $scale)
                    $drawH = [int]($srcH * $scale)
                    $dstRect = New-Object System.Drawing.Rectangle($x, ($y + $labelHeight), $drawW, $drawH)

                    $g.DrawImage($src, $dstRect, $srcRect, [System.Drawing.GraphicsUnit]::Pixel)
                    $g.DrawRectangle($borderPen, $dstRect)

                    $truncated = if ($file.Name.Length -gt 52) { $file.Name.Substring(0, 49) + '...' } else { $file.Name }
                    $g.DrawString(("[{0}] {1}" -f $fileIndex, $truncated), $font, $labelBrush, $x, ($y + 4))

                    [PSCustomObject]@{
                        Index  = $fileIndex
                        Sheet  = $s
                        Name   = $file.Name
                        Width  = $src.Width
                        Height = $src.Height
                    }
                }
                finally {
                    $src.Dispose()
                }
            }

            $sheetName = "{0}__sheet{1:d2}.png" -f (Split-Path $resolved -Leaf), $s
            $sheet.Save((Join-Path $outDir $sheetName), [System.Drawing.Imaging.ImageFormat]::Png)
        }
        finally {
            $g.Dispose()
            $sheet.Dispose()
        }
    }
}
finally {
    $font.Dispose()
    $borderPen.Dispose()
}
