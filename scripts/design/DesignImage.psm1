<#
.SYNOPSIS
    Shared bitmap loading for the design-spec extraction tools.

.DESCRIPTION
    Loads a PNG into a flat BGRA byte array once, via LockBits, so callers can
    read pixels without paying the per-call cost of Bitmap.GetPixel(). A full
    1562x900 palette tally is ~700k reads; GetPixel makes that take minutes,
    while an array index makes it take seconds.
#>

Add-Type -AssemblyName System.Drawing

function Import-DesignBitmap {
    <#
    .SYNOPSIS
        Reads a PNG into memory as a raw 32bpp BGRA byte array.

    .OUTPUTS
        PSCustomObject with Path, Width, Height, Stride and Bytes.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    $resolved = (Resolve-Path -LiteralPath $Path).ProviderPath
    $bmp = New-Object System.Drawing.Bitmap($resolved)
    $data = $null

    try {
        $rect = New-Object System.Drawing.Rectangle(0, 0, $bmp.Width, $bmp.Height)
        $data = $bmp.LockBits(
            $rect,
            [System.Drawing.Imaging.ImageLockMode]::ReadOnly,
            [System.Drawing.Imaging.PixelFormat]::Format32bppArgb
        )

        $bytes = New-Object byte[] ($data.Stride * $bmp.Height)
        [System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $bytes, 0, $bytes.Length)

        [PSCustomObject]@{
            Path   = $resolved
            Name   = Split-Path $resolved -Leaf
            Width  = $bmp.Width
            Height = $bmp.Height
            Stride = $data.Stride
            Bytes  = $bytes
        }
    }
    finally {
        if ($null -ne $data) { $bmp.UnlockBits($data) }
        $bmp.Dispose()
    }
}

function Get-DesignPixel {
    <#
    .SYNOPSIS
        Returns the hex colour (rrggbb, no leading #) at a coordinate.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]$Image,
        [Parameter(Mandatory)][int]$X,
        [Parameter(Mandatory)][int]$Y
    )

    if ($X -lt 0 -or $X -ge $Image.Width)  { throw "X=$X outside image width $($Image.Width)" }
    if ($Y -lt 0 -or $Y -ge $Image.Height) { throw "Y=$Y outside image height $($Image.Height)" }

    # BGRA byte order: index+2 is red, +1 green, +0 blue.
    $offset = $Y * $Image.Stride + $X * 4
    '{0:x2}{1:x2}{2:x2}' -f $Image.Bytes[$offset + 2], $Image.Bytes[$offset + 1], $Image.Bytes[$offset]
}

Export-ModuleMember -Function Import-DesignBitmap, Get-DesignPixel
