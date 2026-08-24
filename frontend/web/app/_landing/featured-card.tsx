import Link from 'next/link';

import { AreaIcon, CheckCircleIcon, ChevronRightIcon, MapPinIcon } from './icons';
import type { FeedItem } from '@/lib/api';
import { formatNaira } from '@/lib/format';

/**
 * Featured-listing card on the public landing page — Figma node 627:67.
 * That artboard is 1:1, so the values below are literal.
 *
 * NOTE: this is a FOURTH card treatment. The landing card has a border AND a
 * shadow — `rgba(0,0,0,0.06)` plus Tailwind's default `shadow` — where the app
 * surfaces have one or the other:
 *   buyer    20px radius, #e5e7eb @50%, no shadow
 *   seller   16px radius, #e5e7eb solid, no shadow
 *   realtor  14px radius, #e5e7eb solid, no shadow
 *   landing  16px radius, rgba(0,0,0,0.06) + shadow   <- here
 *
 * Titles use #1a1a1a (`ink-buyer`), matching the buyer surface rather than the
 * #101828 of seller and realtor.
 *
 * TWO DESIGN ELEMENTS HAVE NO DATA BEHIND THEM and are deliberately omitted
 * (re-confirmed with the product owner in SCRUM-178):
 *   - "5 Beds / 6 Baths" — the listing feed exposes property_type and size_sqm
 *     only; there are no bedroom or bathroom fields on FeedItem.
 *   - the gold "Premium" tag — no corresponding field exists.
 * Inventing either would mean showing buyers numbers we do not have.
 *
 * The design's OTHER two overlays do have data behind them and are built:
 * the red "Distress" tag is `sale_type`, and the white "Verified" pill is
 * `doc_verification_status`. Badge colours measured off the export —
 * #fef2f2 fill (stock `red-50`) with #e7000b text (`status-danger`).
 */
export function FeaturedCard({ item }: { item: FeedItem }) {
  const verified = item.doc_verification_status === 'verified';

  return (
    <Link
      href={`/listings/${item.id}`}
      className="group flex flex-col overflow-hidden rounded-2xl border border-black/[0.06] bg-surface-card shadow transition hover:shadow-md"
    >
      {/* 208px media band on an emerald 10% fallback, with a top-down scrim so
          the location text stays legible over any photo (node 627:68/627:70). */}
      <div className="relative h-52 w-full overflow-hidden bg-emerald-deep/10">
        {item.thumbnail_url && (
          // eslint-disable-next-line @next/next/no-img-element -- listing media is an external CDN URL
          <img
            src={item.thumbnail_url}
            alt={item.title}
            className="h-full w-full object-cover"
          />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-transparent" />

        {item.sale_type === 'distress' && (
          <span className="absolute left-3 top-3 rounded-full bg-red-50 px-2.5 py-1 text-xs font-bold leading-none text-status-danger">
            Distress
          </span>
        )}

        {verified && (
          <span className="absolute right-3 top-3 flex items-center gap-1 rounded-full bg-white/95 px-2.5 py-1 text-[10px] font-semibold leading-none text-emerald-deep">
            <CheckCircleIcon className="h-3.5 w-3.5" strokeWidth={2.2} />
            Verified
          </span>
        )}

        <span className="absolute bottom-3 left-3 flex items-center gap-1 text-xs leading-4 text-white">
          <MapPinIcon className="h-4 w-4" />
          {item.lga}, {item.state}
        </span>
      </div>

      <div className="flex flex-col p-5">
        <p className="text-xs font-medium capitalize leading-4 text-ink-500">{item.property_type}</p>
        <h3 className="pt-0.5 text-base font-semibold leading-[22px] text-ink-buyer">{item.title}</h3>

        {item.size_sqm && (
          <p className="flex items-center gap-1.5 pt-3 text-sm leading-5 text-ink-500">
            <AreaIcon className="h-4 w-4" strokeWidth={1.6} />
            {Number(item.size_sqm).toLocaleString()}sqm
          </p>
        )}

        <div className="mt-4 flex items-center justify-between border-t border-black/[0.06] pt-4">
          <p className="text-xl font-bold leading-7 text-emerald-deep">
            {formatNaira(item.asking_price_kobo)}
          </p>
          <span className="flex items-center gap-1 text-sm font-semibold leading-5 text-emerald-deep">
            View
            <ChevronRightIcon className="h-4 w-4" />
          </span>
        </div>
      </div>
    </Link>
  );
}
