'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { formatNaira } from '@/lib/format';
import { getRecentlyViewed, type RecentListing } from '@/lib/recently-viewed';

/** "Recently Viewed" sidebar card, hydrated from the localStorage cache
 * (SCRUM-136). Renders nothing until mounted (the cache is client-only) and
 * nothing when empty, so it's invisible for a first-time buyer but provides a
 * last-viewed fallback when the live feed can't load. */
export function RecentlyViewedCard() {
  const [items, setItems] = useState<RecentListing[] | null>(null);

  useEffect(() => {
    setItems(getRecentlyViewed());
  }, []);

  if (!items || items.length === 0) return null;

  return (
    <div className="rounded-card border border-line/50 bg-surface-card p-8">
      <p className="font-semibold text-ink-buyer">Recently Viewed</p>
      <ul className="mt-3 space-y-3">
        {items.slice(0, 5).map((item) => (
          <li key={item.id}>
            <Link href={`/listings/${item.id}`} className="group flex items-center gap-3">
              <span className="h-10 w-12 flex-none overflow-hidden rounded-lg bg-bone">
                {item.thumbnail_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={item.thumbnail_url} alt="" className="h-full w-full object-cover" />
                ) : (
                  <span className="flex h-full w-full items-center justify-center text-ink-300">
                    🏠
                  </span>
                )}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-ink-buyer group-hover:underline">
                  {item.title}
                </span>
                <span className="block truncate text-xs text-ink-500">
                  {item.location} · {formatNaira(item.asking_price_kobo)}
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
