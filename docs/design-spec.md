# Design Spec

> ## ⚠️ Read this first — the buyer values below have been superseded
>
> This document was originally derived by **measuring PNG exports**. The Figma file is now available (`mvrQtmad3nf82ZalpUtFcY`), and several measured values turned out to be **wrong**. The corrected buyer values are in [Figma-derived values](#figma-derived-values-scrum-169), which take precedence over anything in the pixel-derived sections.
>
> **The seller and realtor tickets must measure from Figma directly.** Do not inherit the pixel-derived numbers below.
>
> ### The one thing a raster cannot tell you
>
> SCRUM-163 concluded that cards use **a shadow and no border**, because the card edge is a soft two-pixel ramp (`#f5f5f6` → `#f8f8f9` → `#ffffff`). Figma shows the truth:
>
> ```
> border-[1.06px] border-[rgba(229,231,235,0.5)] border-solid
> ```
>
> A **1px `#e5e7eb` border at 50% opacity**, and no shadow. A half-opacity border composited over white produces exactly that ramp — it is *indistinguishable* from a small shadow in pixel data.
>
> **A luminance ramp does not prove a shadow.** Border-vs-shadow, and any other property involving alpha, must come from Figma. The measurement was sound; the inference was not.

Values below were measured using the tools in [`scripts/design/`](../scripts/design/), each citing its source file and coordinates so it can be re-derived or challenged.

Produced for SCRUM-163, corrected by SCRUM-169. Consumed by SCRUM-164 (tokens), SCRUM-165 (components), SCRUM-166/167 (buyer screens).

---

## Figma-derived values (SCRUM-169)

**These supersede the pixel-derived measurements.** Source: file `mvrQtmad3nf82ZalpUtFcY`, buyer dashboard frame `228:20933`.

### The 1.0597 scale factor

The frame is `1562×4526` — byte-identical to the PNG, which independently confirms the 1× export conclusion. But every value inside it is exactly **1.0597×** a round number:

| Figma | ÷ 1.0597 | |
|---|---|---|
| `1.06px` | **1** | border |
| `21.194px` | **20** | radius |
| `63.582px` | **60** | icon chip |
| `26.493px` | **25** | label line-height |
| `47.687px` | **45** | value line-height |
| `31.797px` | **30** | grid gutter |
| `79.478px` | **75** | stat row height |
| `15.896px` | **15** | chip padding |

The artboard was authored at **1474px** and scaled to 1562. Implement the **intrinsic** (÷1.0597) values — a `21.194px` radius is an artifact of that resize, not a design decision.

### Buyer values

| Property | Figma | Implement | Node |
|---|---|---|---|
| Card border | `rgba(229,231,235,0.5)` 1.06px | **1px `#e5e7eb` @ 50%** | 228:20937 |
| Card shadow | none | **none** | 228:20937 |
| Card radius | 21.194px | **20px** | 228:20937 |
| Card padding | 32.851px | **31px** (`p-8` = 32, within 1px) | 228:20937 |
| Card box | 471.2 × 145.2 | 3-col grid, not fixed | 228:20936 |
| Grid gutter | 31.797px | **30px** (`gap-8` = 32, on grid) | x=0/503/1006 |
| Icon chip | 63.582px, radius 21.194 | **60px**, radius 20px | 228:20944 |
| Chip tint (emerald) | `rgba(15,61,46,0.08)` | **`#0f3d2e` @ 8%** | 228:20944 |
| Chip tint (gold) | `rgba(201,166,70,0.08)` | **`#c9a646` @ 8%** | 228:20966 |
| Stat label | 18.545 / lh 26.493, `#6b7280` | **18px / lh 25px** | 228:20941 |
| Stat value | 39.739 / lh 47.687, `#1a1a1a` | **38px / lh 45px** | 228:20943 |
| Label→value gap | 5.299px | **5px** | 228:20939 |
| Search input | 76px, radius 21.194, bg `#fafafa`, border `#e5e7eb` | **72px**, radius 20px | 228:20973 |
| Placeholder | `rgba(26,26,26,0.5)`, 21.194px | **`#1a1a1a` @ 50%**, 20px | 228:20974 |
| Filters button | 78px | **72px** (+2 = border) | 228:20978 |
| Quick-filter pill | 48px, Inter SemiBold 18.545 | **48px, 18px semibold** | 228:20999 |
| Active pill fill | `#0f3d2e`, fully rounded | ✅ already correct | 228:20999 |

### Typeface

Every Maiplot frame specifies **Inter**. The app uses **Archivo + Fraunces**.

Product decision: **keep Archivo + Fraunces.** The pairing was a deliberate brand choice, and Inter may simply be the designer's default. Type **sizes** are corrected; the **typeface** is not, pending confirmation with the designer.

### Buyer body text is `#1a1a1a`

Figma confirms the buyer surface genuinely uses `#1a1a1a`, not `#101828`. The two-palette finding was real, and SCRUM-164's standardisation moved buyer text off its designed value. **Open decision:** single standardised ramp (consistency) vs per-surface text colours (fidelity).

### What Figma does *not* provide

- **No Variables.** The account is on **Starter**, where they are gated — `get_variable_defs` returns `{}`.
- **No Maiplot interaction states.** The file has a component library at `72:8209`–`72:8610` with `state=hover`, `State=focused`, `State=disabled` — but it is a stock shadcn/ui kit in slate (`#94a3b8`, `#cbd5e1`, `#0f172a`) that the Maiplot screens **never instance**: 315 of 324 instances sit in the `1:*` range (mobile chrome from the unrelated *Ridex* and *Foodio* projects sharing the file), and **zero** in the Maiplot sections. Maiplot screens are static frames.

So **SCRUM-165 remains blocked** — hover, focus-visible and disabled do not exist for Maiplot in any source.

### Working with this file

`get_metadata` on page `0:1` returns **4.7M characters**. Query it with grep/python; do not read it. Node tags are `<frame|text|symbol|instance|section id=`.

Sections: `111:7003` Ridex · `111:7004` Foodio · `125:6328` Onboarding+auth · `142:7930` Buyers Dashboard · `240:314` Seller side · `272:4048` Realtor dashboard · `312:379` Admin Portal.

---

## Method

| Tool | What it establishes |
|---|---|
| `Split-DesignImage.ps1` | Cuts tall exports into native-resolution tiles. A 1562×4526 page viewed whole downscales ~3× and 1px borders vanish. |
| `Get-DesignPalette.ps1` | Tallies every pixel and ranks colours by share. Gives exact hex, not an antialiased blend picked by eye. |
| `Get-DesignScanline.ps1` | Run-length encodes a row or column. Turns "roughly 44px of padding" into an exact pixel index. |

Reproduce any measurement:

```powershell
cd maiplot/scripts/design
./Split-DesignImage.ps1 -Path '../../frontend/web/design/buyer-dashboard/Maiplot Web design.png' -OutputDirectory ./tiles
./Get-DesignScanline.ps1 -Path './tiles/Maiplot Web design__y00000.png' -Row 243 -MinimumRun 8
```

Coordinates below are **tile-local** — relative to the top-left of the named tile, not the full-page export.

---

## Export scale — resolved

The open question was whether the 1562px exports are exactly 1×, because 44px padding and 467px cards looked like odd numbers.

**They are 1×, and the design sits on a 4px grid.** Every independently measured box dimension lands on a multiple of 4:

| Measurement | Value | On 4px grid |
|---|---|---|
| Header height | 72px | ✅ |
| Button / pill height | 48px | ✅ |
| Card corner radius | 16px | ✅ |
| Sidebar width incl. border | 256px | ✅ |
| Container padding | 44px | ✅ |
| Grid gap | 36px | ✅ |
| Card box height | 144px | ✅ (interior 142 + 2 edge) |
| Search input | 72px | ✅ (interior 73 incl. antialiasing) |

Eight measurements taken from four different screens all landing on the grid is not coincidence. Had the export been 1.08× (1562/1440) or 1.25×, none of them would.

**No Figma confirmation needed for geometry.** Type and interaction states still need it.

### Stat cards are a grid, not fixed widths

The measured 468 / 36 / 467 sequence is an artifact of fractional grid widths, not a design token:

```
44 + 467.33 + 36 + 467.33 + 36 + 467.33 + 44 = 1562   ✓ exact
```

Implement as a 3-column grid with `gap: 36px` inside `padding-inline: 44px`. **Do not hardcode 468px** — it is a rounding of 467.33 and will not hold at other viewport widths.

---

## Colour

### ⚠️ The design contains two palettes

Buyer was designed against a different token set than seller and realtor. This is in the design source, not a measurement error — the same semantic role resolves to a different hex per surface.

| Role | Buyer | Seller + Realtor | Notes |
|---|---|---|---|
| Page background | `#fafafa` | `#f9fafb` | gray-50 on seller/realtor |
| Primary text | `#1a1a1a` | `#101828` | |
| Error / danger | `#dc2626`, `#fb2c36` | `#e7000b` | three different reds in total |

SCRUM-164 has to pick one set. Recommendation: **standardise on the seller/realtor values** (`#f9fafb`, `#101828`, `#e7000b`) — they are stock Tailwind, they cover two of three surfaces, and buyer is the surface already scheduled for rework in SCRUM-166/167. Flagging as a decision, not deciding it.

### Core palette — consistent across all surfaces

| Hex | Role | Source |
|---|---|---|
| `#0f3d2e` | **Primary brand green** — buttons, active pills, badges, sidebar active | All surfaces. Buyer 1.86%, seller 1.75%, realtor 1.01% |
| `#144735` | Buyer header bar only | `buyer/Maiplot Web design.png` tile y0, 7.94% |
| `#ffffff` | Card / panel surface | All surfaces, 30–70% |
| `#e5e7eb` | Border — header rule, sidebar rule, dividers | All surfaces. gray-200 |
| `#f3f4f6` | Inactive pill / chip fill | Buyer 0.83%, realtor 0.44%. gray-100 |
| `#6b7280` | Muted / secondary text | `buyer` tile y0 col x=300, y702–713. gray-500 |
| `#d1d5dc` | Input border, disabled edge | `realtor/…(5).png` 0.32% |

`#0f3d2e` appears on every surface at a consistent share. It is the primary, and `tailwind.config.ts` already has it as `emerald.deep`.

### Semantic / status colours

| Hex | Role | Source |
|---|---|---|
| `#00a63e` | Success action — Accept Offer, verified option | `seller/…(13).png` 0.94% |
| `#e7000b` | Danger action — Reject Offer, Not Present | `seller/…(13).png` 0.95% |
| `#dc2626` | Buyer form-validation error text and border | `buyer/Mobile App Onboarding Flow (2).png` 0.40% |
| `#fb2c36` | Discount / urgency badge ("35% Off") | `buyer` tile y0 0.65%. red-500 |
| `#c9a646` | Gold accent — deal-time icon, premium marker | `buyer` tile y0 x1440–1468; `seller/…(13).png` 0.22% |

### Tinted surface fills

| Hex | Role | Source |
|---|---|---|
| `#f0fdf4` | Success panel background | seller 1.77%, realtor 5.53%. green-50 |
| `#fffbeb` | Warning / pending panel | realtor 1.64%, seller 1.06%. amber-50 |
| `#fef2f2` | Error panel | realtor 1.66%. red-50 |
| `#eff6ff` | Info panel | seller 1.06%. blue-50 |
| `#dbeafe` | Info panel, stronger | realtor 0.17%. blue-100 |
| `#f5f1e8` | **Warm cream panel** — insight/tip rails | seller 3.21%, realtor 1.47% |
| `#ebefee` | Muted green tint — icon chips | buyer tile y0 x418–479 |
| `#f6f4ee` | Brand cream background | `realtor/…(12).png` — a gradient swatch, not a screen |

`#f5f1e8` and `#f6f4ee` are close but distinct. `#f6f4ee` already exists in `tailwind.config.ts` as `bone`.

### Stock-Tailwind alignment

`#e5e7eb`, `#6b7280`, `#f3f4f6`, `#f9fafb`, `#d1d5dc`, `#f0fdf4`, `#fffbeb`, `#fef2f2`, `#eff6ff`, `#dbeafe`, `#fb2c36`, `#e7000b`, `#00a63e` are all stock Tailwind values. SCRUM-164 should use the stock scale for these rather than minting duplicate custom tokens — only `#0f3d2e`, `#144735`, `#f5f1e8`, `#f6f4ee` and `#c9a646` genuinely need to be custom.

---

## Geometry

### Layout shell

| Property | Value | Source |
|---|---|---|
| Buyer header height | **72px** | `buyer` tile y0, col x=300: `#144735` y0–71 |
| Buyer header bottom border | **1px `#e5e7eb`** | same scan, y=72 |
| Seller / realtor sidebar width | **255px + 1px border = 256px** | `seller/Maiplot Web design.png` row 600: border at x=255 |
| Sidebar → content gap | **32px** | same scan: `#f9fafb` x256–287 |
| Container padding (inline) | **44px** | `buyer` tile y0 row 243: content starts x=44, ends x=1517 |

Buyer uses a top bar; seller and realtor use a left sidebar. There is no single shell — see `design-index.md` finding 2.

### Cards

> ⚠️ **This table is superseded.** See [Figma-derived values](#figma-derived-values-scrum-169). Radius is 20px not 16px, gap is 30px not 36px, and the card has a **border, not a shadow**. Kept as a record of what the raster method produced and where it went wrong.

| Property | Pixel-derived | Actual (Figma) |
|---|---|---|
| Corner radius | 16px — corner probe y172–188 | **20px** ❌ |
| Box height (stat card) | 144px — interior y172–313 + 2px edge | 145.2 ✅ |
| Grid gap | 36px — card1 ends 511, card2 starts 547 | **30px** ❌ |
| Border | none | **1px `#e5e7eb` @ 50%** ❌ |
| Shadow | ~2px ramp `#f5f5f6`→`#f8f8f9`→`#ffffff` | **none** ❌ |

The radius probe undercounted because it looked for where *pure* `#ffffff` begins, which sits inside the arc. The border/shadow call is explained in the banner at the top — a translucent border and a small shadow are the same pixels.

### Controls

| Property | Value | Source |
|---|---|---|
| Primary button height | **48px** | `buyer` tile y0 col x=300: `#0f3d2e` y512–558 |
| Quick-filter pill height | **48px** | same scan — pill and button share a height |
| Active pill fill | `#0f3d2e`, white label | row 535: `#0f3d2e` from x=203 |
| Inactive pill fill | `#f3f4f6` | row 535 |
| Search input height | **72px** | col x=1000: `#fafafa` y403–475 (73px incl. antialiasing) |
| Search input fill | `#fafafa` on a `#ffffff` card | col x=1000 |

---

## Type

⚠️ **Measured ink heights are facts. Font sizes below are inferred and need Figma confirmation.**

Ink height is the pixel extent of rendered glyphs. Converting it to a font size requires the typeface's cap-height and descender ratios, and **the typeface is not identified** — a PNG cannot report a font family. The estimates assume a typical sans at cap ≈ 0.71em and cap-plus-descender ≈ 0.92em.

| Element | Ink height | Has descender | Inferred size | Source (tile y0) |
|---|---|---|---|---|
| Stat numeral ("7", "98%") | 29px | no | **~40px** | x76–100 / x578–660, y242–270 |
| Section heading ("Urgent Deals") | 38px | yes | **~40px** | x113–360, y652–689 |
| Search placeholder | 20px | yes | **~20px** | x160–670, y432–451 |
| Card label ("Active Listings") | 17px | yes | **~18px** | x78–205, y210–226 |
| Sub-label ("Below market value") | 15px | yes | **~16px** | x113–455, y699–713 |

This is a **large-type design** — the stat numerals and section headings are roughly 40px, and the base body size looks like 16–18px rather than the more common 14px. Worth confirming before it gets normalised downward by habit during implementation.

**Not derivable from PNGs, needs Figma:** font family, weights, line-heights, letter-spacing.

---

## Known drift — spec vs. current code

Work list for SCRUM-164 and SCRUM-166/167.

### Tokens (`frontend/web/tailwind.config.ts`)

| Current | Spec | Action |
|---|---|---|
| `emerald.accent: #1f7a5a` | not present anywhere in 69 exports | **Remove or remap.** Every current usage is wrong. |
| `emerald.deep: #0f3d2e` | `#0f3d2e` primary | ✅ Correct — keep, promote to `primary` |
| `bone: #f6f4ee` | `#f6f4ee` brand cream | ✅ Correct |
| `ink.900 #0d1714` … `ink.300 #9aa8a1` | design text is `#101828` / `#1a1a1a` / `#6b7280` | Ramp does not match. Rebuild. |
| — | `#144735` buyer header | **Missing** |
| — | `#f5f1e8` warm panel | **Missing** — used on seller and realtor |
| — | `#c9a646` gold accent | **Missing** |
| — | status colours (`#00a63e`, `#e7000b`, `#fb2c36`) | **Missing** — no semantic tokens exist |
| no spacing scale | 4px grid | **Missing** |
| no radius scale | 16px cards | **Missing** |
| no shadow scale | card shadow | **Missing** |
| no type scale | ~40 / 20 / 18 / 16px | **Missing** |

`emerald.accent` is the highest-priority fix: it is a colour that exists in the codebase and in no design.

### Components

Counts below are from `grep` over `app/`, `components/` and `lib/` on the SCRUM-163 branch.

#### Every card in the app has its edge treatment inverted

| Pattern | Occurrences |
|---|---|
| `rounded-* border` | **202** |
| `rounded-* shadow` | **0** |
| all `shadow-*` usage, whole app | **14** |

The design gives cards a soft shadow and **no** border. The code gives cards a border and **no** shadow. This is not a handful of screens — it is systematic, and it is the single largest visual gap between design and build.

Because the ramp is only ~2px, this reads as "slightly wrong" rather than obviously broken, which is why it survived four frontend epics.

#### Radius is one step too small nearly everywhere

| Class | Uses | Value |
|---|---|---|
| `rounded-lg` | 140 | 8px |
| `rounded-md` | 83 | 6px |
| `rounded-full` | 82 | — |
| `rounded-xl` | 74 | 12px |
| `rounded-2xl` | **63** | **16px — matches spec** |

Measured card radius is **16px**. The dominant class in the codebase is `rounded-lg` at 8px.

#### Token usage counts

| Token | Uses | Files | Status |
|---|---|---|---|
| `emerald-accent` | **115** | **38** | ❌ Colour appears in **no** design export |
| `emerald-deep` | 276 | — | ✅ Correct (`#0f3d2e`) |
| `ink-300` | 332 | — | ❌ Ramp does not match design |
| `ink-500` | 289 | — | ❌ |
| `ink-900` | 248 | — | ❌ |
| `ink-700` | 91 | — | ❌ |
| `ink-800` | 16 | — | ❌ |
| `bg-bone` | 71 | — | ✅ Correct (`#f6f4ee`) |
| arbitrary `[12px]` / `[#hex]` | 24 | — | ⚠️ Should resolve to tokens |

**`emerald-accent` is 115 usages across 38 files.** SCRUM-164 was scoped as a config change plus cleanup; it is closer to a 38-file sweep. The `ink-*` ramp is another ~976 usages. Worth re-estimating that ticket before it is picked up.

#### Remaining component checks

| Item | Expected | Ticket |
|---|---|---|
| Header bottom border | 1px `#e5e7eb` | SCRUM-165 |
| Button / pill height | 48px | SCRUM-165 |
| Search input height | 72px | SCRUM-166 |
| Stat card row | 3-col grid, gap 36, pad 44 | SCRUM-166 |

---

## Still blocked on Figma

Narrower than first assumed. Indexing found the exports already cover selected, active-tab, error, open-dropdown, toggle and modal-backdrop states — see `design-index.md`.

Genuinely missing:

1. **Hover** — no export shows one.
2. **Focus-visible** — no export shows one. **WCAG AA requirement**, not polish.
3. **Disabled** — no export shows one.
4. **Font family, weights, line-heights** — not derivable from a raster.
5. **Exact shadow parameters** — the 2px ramp constrains but does not determine them.
6. **Transitions / motion** — static exports cannot show them.

Items 1–3 are the substance of SCRUM-165. Item 4 affects the type scale in SCRUM-164 — the spacing and colour work can proceed without it.
