<#
.SYNOPSIS
    Measures exact geometry by run-length encoding a row or column of pixels.

.DESCRIPTION
    Walks a single row (-Row) or column (-Column) and reports each run of
    identical colour with its start, end and width. This is how spacing gets
    measured precisely rather than estimated: the boundary between a #fafafa
    page background and a #ffffff card is an exact pixel index, so container
    padding, card width and gutter all fall out as arithmetic.

    Reading the output:
      - A 1px run of a distinct colour is a border.
      - A short ramp (#f5f5f6 -> #f8f8f9 -> #ffffff) is a shadow, not a border.
        This distinction is invisible by eye and matters for implementation.
      - Runs under -MinimumRun are antialiasing on text and icon edges; raise
        the threshold to see structure, lower it to inspect a specific element.

.PARAMETER Path
    Source PNG.

.PARAMETER Row
    Y coordinate for a horizontal scan. Mutually exclusive with -Column.

.PARAMETER Column
    X coordinate for a vertical scan. Mutually exclusive with -Row.

.PARAMETER MinimumRun
    Suppress runs shorter than this. Default 1 (show everything).

.EXAMPLE
    # Horizontal cut through the stat-card row: card edges, widths and gutters.
    .\Get-DesignScanline.ps1 -Path '.\slice.png' -Row 243 -MinimumRun 3

.EXAMPLE
    # Vertical cut down an empty card column: header height, card top and bottom.
    .\Get-DesignScanline.ps1 -Path '.\slice.png' -Column 300 -MinimumRun 5

.NOTES
    Windows-only (System.Drawing). Developer tooling — not part of the build or CI.
#>
[CmdletBinding(DefaultParameterSetName = 'Row')]
param(
    [Parameter(Mandatory)]
    [string]$Path,

    [Parameter(Mandatory, ParameterSetName = 'Row')]
    [int]$Row,

    [Parameter(Mandatory, ParameterSetName = 'Column')]
    [int]$Column,

    [ValidateRange(1, 500)]
    [int]$MinimumRun = 1
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'DesignImage.psm1') -Force

$img = Import-DesignBitmap -Path $Path

if ($PSCmdlet.ParameterSetName -eq 'Row') {
    $axis = 'x'
    $length = $img.Width
    if ($Row -lt 0 -or $Row -ge $img.Height) {
        throw "Row $Row outside image height $($img.Height)."
    }
} else {
    $axis = 'y'
    $length = $img.Height
    if ($Column -lt 0 -or $Column -ge $img.Width) {
        throw "Column $Column outside image width $($img.Width)."
    }
}

$previous = $null
$runStart = 0

function Write-Run {
    param($Start, $End, $Hex)
    $width = $End - $Start + 1
    if ($width -ge $MinimumRun) {
        [PSCustomObject]@{
            Axis  = $axis
            Start = $Start
            End   = $End
            Width = $width
            Hex   = "#$Hex"
        }
    }
}

for ($i = 0; $i -lt $length; $i++) {
    $hex = if ($PSCmdlet.ParameterSetName -eq 'Row') {
        Get-DesignPixel -Image $img -X $i -Y $Row
    } else {
        Get-DesignPixel -Image $img -X $Column -Y $i
    }

    if ($hex -ne $previous) {
        if ($null -ne $previous) { Write-Run -Start $runStart -End ($i - 1) -Hex $previous }
        $previous = $hex
        $runStart = $i
    }
}

Write-Run -Start $runStart -End ($length - 1) -Hex $previous
