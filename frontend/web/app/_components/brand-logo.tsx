import Image from 'next/image';

import logo from '@/public/brand/logo.png';
import logoOnDark from '@/public/brand/logo-on-dark.png';
import mark from '@/public/brand/mark.png';
import markOnDark from '@/public/brand/mark-on-dark.png';

/**
 * The Maihomme logo — SCRUM-230.
 *
 * Until this ticket every surface drew its own placeholder lockup: an "M" tile
 * plus the word "Maihomme" set in the display face. The designer's logo landed
 * as a single JPG on an opaque off-white canvas (`public/brand/
 * maihomme_logo.source.jpg`, kept verbatim as the source of record), which
 * cannot sit on the emerald header or the auth panels without a cream box
 * around it. The four PNGs next to it are derived from that JPG: the flat
 * background keyed to alpha, colour un-premultiplied so the antialiased edges
 * do not fringe, and cropped to the ink.
 *
 *   logo.png          navy wordmark + gold house, for white / bone surfaces
 *   logo-on-dark.png  the same with the navy recoloured to `bone`; the gold is
 *                     untouched, for `emerald-deep` / `brand-header` surfaces
 *   mark.png          the "H"-with-roof glyph alone, the recognisable unit
 *   mark-on-dark.png  its on-dark twin
 *
 * `app/icon.png`, `apple-icon.png` and `opengraph-image.png` are built from the
 * same crop (Next picks them up by filename); regenerate all seven together if
 * the source ever changes — one drifting is worse than none.
 *
 * ⚠️ `unoptimized`: the files are already small (16–90 KB) and render at
 * 28–40px, and it keeps the self-hosted standalone image free of a runtime
 * `sharp` dependency. Static imports still supply the intrinsic size, so
 * there is no layout shift.
 *
 * ⚠️ PALETTE. The logo is navy + gold; the app is emerald green, measured off
 * the Figma exports. This component only places the mark — reconciling the two
 * is a design decision, not something to bury in a branding sweep.
 */
export function BrandLogo({
  tone = 'light',
  variant = 'wordmark',
  height = 28,
  priority = false,
  className,
}: {
  /** The surface the logo sits on — `dark` swaps the navy for bone. */
  tone?: 'light' | 'dark';
  /** Full wordmark, or the house glyph alone. */
  variant?: 'wordmark' | 'mark';
  /** Rendered height in CSS px; width follows the asset's aspect ratio. */
  height?: number;
  /** Above-the-fold placements (navs, auth panels) should not lazy-load. */
  priority?: boolean;
  className?: string;
}) {
  const src =
    variant === 'mark'
      ? tone === 'dark'
        ? markOnDark
        : mark
      : tone === 'dark'
        ? logoOnDark
        : logo;
  const width = Math.round((height * src.width) / src.height);
  return (
    <Image
      src={src}
      alt="Maihomme"
      height={height}
      width={width}
      priority={priority}
      unoptimized
      className={className}
    />
  );
}
