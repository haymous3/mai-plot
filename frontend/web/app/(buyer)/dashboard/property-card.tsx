import Link from 'next/link';

import { SaveHeart } from './save-heart';
import type { FeedItem } from '@/lib/api';
import { formatNaira } from '@/lib/format';

function daysLeft(iso: string | null): number | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  return ms <= 0 ? 0 : Math.ceil(ms / 86_400_000);
}

function saleLabel(saleType: string): string {
  return saleType === 'distress' ? 'Distress' : 'Normal Sale';
}

function Thumb({ item, className }: { item: FeedItem; className: string }) {
  return item.thumbnail_url ? (
    // eslint-disable-next-line @next/next/no-img-element -- listing media is an external CDN URL
    <img src={item.thumbnail_url} alt={item.title} className={`${className} object-cover`} />
  ) : (
    <div className={`${className} flex items-center justify-center bg-bone text-ink-300`}>
      <span aria-hidden className="text-2xl">
        🏠
      </span>
    </div>
  );
}

function Specs({ item }: { item: FeedItem }) {
  return (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-500">
      {item.size_sqm && <span>⤢ {Number(item.size_sqm).toLocaleString()} sqm</span>}
      <span className="rounded bg-bone px-1.5 py-0.5 capitalize">{item.property_type}</span>
    </p>
  );
}

/** A listing card in the buyer feed. `grid` for the Urgent Deals grid, `row` for
 * the All Properties list. `saved` seeds the favourite heart. */
export function PropertyCard({
  item,
  variant,
  saved = false,
}: {
  item: FeedItem;
  variant: 'grid' | 'row';
  saved?: boolean;
}) {
  const left = daysLeft(item.urgency_expires_at);
  const verified = item.doc_verification_status === 'verified';
  const href = `/listings/${item.id}`;

  if (variant === 'grid') {
    return (
      <Link
        href={href}
        className="group block overflow-hidden rounded-xl border border-ink-300/25 bg-white transition hover:border-ink-500/40 hover:shadow-sm"
      >
        <div className="relative">
          <Thumb item={item} className="h-40 w-full" />
          <div className="absolute left-2 top-2 flex flex-col gap-1">
            {item.sale_type === 'distress' && (
              <span className="rounded-full bg-red-500 px-2 py-0.5 text-[11px] font-semibold text-white">
                🔥 {saleLabel(item.sale_type)}
              </span>
            )}
            {verified && (
              <span className="rounded-full bg-emerald-deep px-2 py-0.5 text-[11px] font-semibold text-bone">
                ✓ Verified
              </span>
            )}
          </div>
          {left !== null && (
            <span className="absolute bottom-2 left-2 rounded-full bg-white/90 px-2 py-0.5 text-[11px] font-medium text-red-600">
              ⏱ {left}d left
            </span>
          )}
          <SaveHeart listingId={item.id} initialSaved={saved} className="absolute right-2 top-2" />
        </div>
        <div className="p-3">
          <p className="truncate font-medium text-ink-900">{item.title}</p>
          <p className="mt-0.5 truncate text-xs text-ink-500">
            📍 {item.lga}, {item.state}
          </p>
          <div className="mt-2">
            <Specs item={item} />
          </div>
          <p className="mt-2 text-[11px] uppercase tracking-wide text-ink-400">Asking</p>
          <p className="font-display text-lg text-emerald-deep">
            {formatNaira(item.asking_price_kobo)}
          </p>
        </div>
      </Link>
    );
  }

  return (
    <Link
      href={href}
      className="flex gap-4 rounded-xl border border-ink-300/25 bg-white p-3 transition hover:border-ink-500/40 hover:shadow-sm"
    >
      <div className="relative flex-none">
        <Thumb item={item} className="h-24 w-32 rounded-lg" />
        <span
          className={`absolute left-1.5 top-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
            item.sale_type === 'distress' ? 'bg-red-500 text-white' : 'bg-ink-900/80 text-white'
          }`}
        >
          {saleLabel(item.sale_type)}
        </span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <p className="truncate font-medium text-ink-900">{item.title}</p>
          {verified && (
            <span aria-label="Verified" className="text-emerald-accent">
              ✓
            </span>
          )}
          <span className="ml-auto flex-none">
            <SaveHeart
              listingId={item.id}
              initialSaved={saved}
              className="!bg-transparent !shadow-none"
            />
          </span>
        </div>
        <p className="mt-0.5 truncate text-xs text-ink-500">
          📍 {item.lga}, {item.state}
        </p>
        <div className="mt-1.5">
          <Specs item={item} />
        </div>
        <div className="mt-2 flex items-end justify-between">
          <p className="font-display text-base text-emerald-deep">
            {formatNaira(item.asking_price_kobo)}
          </p>
          {left !== null && <span className="text-xs font-medium text-red-600">{left} days left</span>}
        </div>
      </div>
    </Link>
  );
}
