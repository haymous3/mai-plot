# Design extraction tooling

Measures exact colour and geometry out of the Figma PNG exports so the design spec is derived from pixels rather than estimated by eye.

Built for SCRUM-163. Output lives in [`docs/design-spec.md`](../../docs/design-spec.md) and [`docs/design-index.md`](../../docs/design-index.md).

> **Developer tooling only.** Windows PowerShell + `System.Drawing`. Not part of the Next.js build, not run in CI, not imported by application code.

## Why this exists

Two problems make the exports hard to use directly:

1. **They are too tall to read.** The buyer pages run to 1562×4526. Viewed whole they downscale roughly 3×, and a 1px border becomes a third of a pixel — invisible. Slicing preserves every pixel.

2. **Eyeballing colour is unreliable.** A colour sampled off a downscaled screenshot is an antialiased blend of neighbours, not the token. Tallying actual pixel values gives the real hex.

The exports are gitignored (`.gitignore:68`) — 39MB of PNGs would sit in git history forever. These scripts plus the two docs are what remains reviewable.

## Scripts

| Script | Purpose |
|---|---|
| `DesignImage.psm1` | Shared bitmap loader. Reads a PNG into a flat BGRA array via `LockBits` so callers avoid per-pixel `GetPixel` cost. |
| `Split-DesignImage.ps1` | Slices a tall export into native-resolution tiles with configurable overlap. |
| `Get-DesignPalette.ps1` | Ranks colours by pixel share. Exact hex values. |
| `Get-DesignScanline.ps1` | Run-length encodes a row or column. Turns spacing into exact pixel indices. |
| `New-DesignContactSheet.ps1` | Numbered thumbnail grids for identifying screens in bulk. |

## Usage

```powershell
cd maiplot/scripts/design
$design = '../../frontend/web/design'

# 1. Slice a tall page into readable tiles
./Split-DesignImage.ps1 -Path "$design/buyer-dashboard/Maiplot Web design.png" -OutputDirectory ./tiles

# 2. Exact palette, ranked by share
./Get-DesignPalette.ps1 -Path './tiles/Maiplot Web design__y00000.png' -Top 20

# 3. Horizontal cut: card edges, widths, gutters
./Get-DesignScanline.ps1 -Path './tiles/Maiplot Web design__y00000.png' -Row 243 -MinimumRun 8

# 4. Vertical cut: header height, card top and bottom
./Get-DesignScanline.ps1 -Path './tiles/Maiplot Web design__y00000.png' -Column 300 -MinimumRun 5

# 5. Identify a whole directory at once
./New-DesignContactSheet.ps1 -Path "$design/seller-dashboard" -OutputDirectory ./sheets
```

## Reading scanline output

```
Start  End Width Hex
   42   42     1 #f5f5f6     <- shadow ramp
   43   43     1 #f8f8f9     <- shadow ramp
   44  511   468 #ffffff     <- card interior
```

- A **1px run of a distinct colour** is a border.
- A **short luminance ramp** into the surface is a shadow, not a border. This distinction is invisible by eye and is the thing most often implemented wrong.
- Runs of 1–2px inside text are antialiasing. Raise `-MinimumRun` to see structure.

## Gotchas

- **Tile coordinates are tile-local.** A measurement at row 243 of `…__y00800.png` is row 1043 of the source. `design-spec.md` cites tile plus coordinate for this reason.
- **Photographic regions swamp the palette.** Property images produce thousands of near-unique colours. `-MinimumShare` filters them; flat UI colours always rank well above the threshold.
- **Exports are not one uniform scale.** Widths range 545–2343px. The 1562px group is the reference; do not mix measurements across groups. See the scale section of `design-spec.md`.
- `Get-DesignPalette.ps1` defaults to `-Stride 2` (25% of pixels). Flat UI colours rank identically at stride 1; only fine gradients differ.
