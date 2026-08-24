import Link from 'next/link';

import { CheckCircleIcon, HouseIcon, SearchIcon } from './icons';
import { Nav } from './nav';
import { Shell } from './sections';
import type { FeedItem } from '@/lib/api';
import { formatNaira } from '@/lib/format';

/**
 * Landing hero — SCRUM-178.
 *
 * SCRUM-174 shipped a deliberate placeholder here because Figma node 627:8 was
 * an empty 1577×944 frame. This export fills it, so the placeholder is gone.
 *
 * Measured off the 1577×7215 export (artboard is 1:1 — container 1216px,
 * photo 576×520, buttons 235×56, chip 140×96 all land on round numbers, which
 * is the reliable 1:1 test):
 *
 *   nav row        y0..72
 *   badge pill     x180..504, y153..191   → 40px tall, fully rounded
 *   H1             cap height 44px, line pitch 70px → 60px/70px
 *   body           cap 14.5px, pitch 29px → 20px/29px
 *   buttons        235×56 at a 16px gap, 12px radius
 *   photo card     x820..1396, y228..747  → 576×520, right-aligned
 *   financing chip x1280..1420, y214..311 → overhangs the photo up and right
 *   price card     x788..994,  y659..770  → overhangs the photo down and left
 *
 * Left column and photo are vertically centred on each other (both centre on
 * y≈487), hence `items-center`.
 *
 * THE PHOTO IS LIVE DATA, NOT A STOCK ASSET. The design's price card carries a
 * location, a price and a verified tick — which is exactly a `FeedItem`. So the
 * hero renders the top featured listing rather than a hardcoded image we would
 * have to ship and keep in sync. With no feed (service down, empty result, no
 * thumbnail) the photo falls back to a flat tint and the price card drops out;
 * the financing chip stays because 50% is a business rule (CLAUDE.md §8.5), not
 * a property of any one listing.
 */
export function Hero({ featured }: { featured?: FeedItem }) {
  const photo = featured?.thumbnail_url ?? null;

  return (
    <section className="relative overflow-hidden bg-gradient-to-b from-emerald-deep from-85% to-[#124031] text-white">
      <Nav />

      <Shell className="grid items-center gap-y-16 pb-[124px] pt-20 lg:grid-cols-[1fr_576px] lg:gap-x-[120px]">
        <div>
          <p className="inline-flex min-h-10 items-center gap-2 rounded-full bg-white/10 px-5 py-2 text-[15px] leading-5 text-white/90">
            <span aria-hidden className="h-2 w-2 flex-none rounded-full bg-status-gold" />
            Nigeria&apos;s Most Trusted Property Platform
          </p>

          {/*
            Arbitrary font sizes, not `text-5xl`/`text-6xl`. Tailwind's named
            scale steps set font-size AND line-height, and the `sm:` variant is
            emitted after the base utilities — so `sm:text-6xl` would silently
            override `leading-[1.16]` back to 1. Arbitrary sizes carry no
            line-height, so the measured 70px pitch survives.
          */}
          <h1 className="mt-8 max-w-[520px] font-display text-[40px] font-bold leading-[1.16] sm:text-[52px] lg:text-[60px]">
            Own Your Dream Property,{' '}
            {/*
              Block-level so the gold clause always starts its own line, as the
              design draws it. The exact wrap inside each half is left to the
              browser — the design is set in Inter and the app renders Fraunces
              (a deliberate brand divergence recorded in tailwind.config.ts), so
              hard-coded line breaks would not reproduce the drawing anyway.
            */}
            <span className="block text-status-gold">Safely &amp; Effortlessly.</span>
          </h1>

          <p className="mt-6 max-w-[520px] text-xl leading-[29px] text-white/75">
            Maihomme connects buyers, sellers, and agents on a verified, escrow-secured platform —
            with financing up to 50% through partner banks.
          </p>

          <div className="mt-10 flex flex-wrap gap-4">
            <Link
              href="/dashboard"
              className="inline-flex h-14 items-center gap-2.5 rounded-xl bg-status-gold px-7 text-base font-semibold text-white transition hover:brightness-105"
            >
              <SearchIcon className="h-5 w-5" />
              Explore Properties
            </Link>
            <Link
              href="/register"
              className="inline-flex h-14 items-center gap-2.5 rounded-xl border border-white/20 bg-white/10 px-7 text-base font-semibold text-white transition hover:bg-white/15"
            >
              <HouseIcon className="h-5 w-5" />
              List Your Property
            </Link>
          </div>

          <dl className="mt-14 flex flex-wrap gap-9">
            {[
              { value: '12K+', label: 'Listings' },
              { value: '9.6K+', label: 'Homeowners' },
              { value: '14', label: 'Partner Banks' },
            ].map((s) => (
              <div key={s.label}>
                <dd className="text-2xl font-bold leading-8">{s.value}</dd>
                <dt className="mt-0.5 text-sm leading-5 text-white/70">{s.label}</dt>
              </div>
            ))}
          </dl>
        </div>

        <div className="relative">
          <div className="h-[520px] w-full overflow-hidden rounded-2xl bg-white/10">
            {photo && (
              // eslint-disable-next-line @next/next/no-img-element -- listing media is an external CDN URL
              <img
                src={photo}
                alt={featured?.title ?? ''}
                className="h-full w-full object-cover"
              />
            )}
          </div>

          <div className="absolute right-4 top-4 w-[140px] rounded-2xl bg-emerald-deep px-4 py-3.5 shadow-xl lg:-right-6 lg:-top-3">
            <p className="text-xs leading-4 text-white/70">Financing Available</p>
            <p className="mt-1 text-2xl font-bold leading-8">50%</p>
            <p className="text-xs font-semibold leading-4 text-status-gold">via Partner Banks</p>
          </div>

          {featured && (
            <div className="absolute bottom-4 left-4 rounded-2xl bg-white px-5 py-5 shadow-xl lg:-bottom-6 lg:-left-8">
              <p className="text-sm leading-5 text-ink-500">
                {featured.lga}, {featured.state}
              </p>
              <p className="mt-1 text-2xl font-bold leading-8 text-emerald-deep">
                {formatNaira(featured.asking_price_kobo)}
              </p>
              {featured.doc_verification_status === 'verified' && (
                <p className="mt-1.5 flex items-center gap-1.5 text-sm font-semibold leading-5 text-emerald-deep">
                  <CheckCircleIcon className="h-4 w-4" strokeWidth={2} />
                  Verified &amp; Escrow-Ready
                </p>
              )}
            </div>
          )}
        </div>
      </Shell>

      <HeroWave />
    </section>
  );
}

/**
 * The curved bottom edge of the hero.
 *
 * Traced at 21 columns of the export by walking each column down until the
 * pixel turns white. The boundary is a shallow double curve, not an arc:
 *
 *   x     0   160   320   480   640   800   960  1120  1280  1440  1576
 *   y   944   924   909   904   908   914   917   916   910   901   892
 *
 * Normalised to the 52px band between the highest (892) and lowest (944) point
 * and fitted with three cubics. `preserveAspectRatio="none"` lets it stretch to
 * any viewport width, which is what a full-bleed divider needs — the vertical
 * scale stays fixed at 52px so the curve flattens rather than deepens on wide
 * screens.
 */
function HeroWave() {
  return (
    <svg
      viewBox="0 0 1577 52"
      preserveAspectRatio="none"
      className="absolute inset-x-0 bottom-0 h-[52px] w-full"
      aria-hidden
    >
      <path
        d="M0 52 C160 33 340 13 480 12 C650 15 850 25 1000 25 C1180 24 1400 12 1577 0 L1577 52 Z"
        fill="#ffffff"
      />
    </svg>
  );
}
