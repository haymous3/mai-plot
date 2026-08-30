'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useState } from 'react';
import { MoneyInput } from '@/app/_components/money-input';
import { nairaToKobo } from '@/lib/money-input';

type Quick = 'all' | 'verified' | 'distress';

const PROPERTY_TYPES = [
  { value: '', label: 'Any type' },
  { value: 'land', label: 'Land' },
  { value: 'residential', label: 'Residential' },
  { value: 'commercial', label: 'Commercial' },
];

/** Search + quick filters + expandable filter row for the buyer feed
 * (SCRUM-95). Writes the filter state into the URL search params; the server
 * component re-fetches the feed from them. */
export function SearchFilterBar() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [showFilters, setShowFilters] = useState(false);
  const [q, setQ] = useState(params.get('q') ?? '');
  // Price filters became CONTROLLED for SCRUM-202: grouping as you type needs
  // the value in state. They still apply on blur, so a half-typed amount does
  // not fire a search on every keystroke.
  const [priceMin, setPriceMin] = useState(
    params.get('price_min') ? String(Number(params.get('price_min')) / 100) : '',
  );
  const [priceMax, setPriceMax] = useState(
    params.get('price_max') ? String(Number(params.get('price_max')) / 100) : '',
  );

  const quick: Quick =
    params.get('sale_type') === 'distress'
      ? 'distress'
      : params.get('doc_status') === 'verified'
        ? 'verified'
        : 'all';

  function apply(next: Record<string, string | null>) {
    const sp = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(next)) {
      if (v === null || v === '') sp.delete(k);
      else sp.set(k, v);
    }
    router.push(`${pathname}?${sp.toString()}`);
  }

  function setQuick(v: Quick) {
    apply({
      sale_type: v === 'distress' ? 'distress' : null,
      doc_status: v === 'verified' ? 'verified' : null,
    });
  }

  const quickBtn = (v: Quick, label: string) => (
    <button
      type="button"
      onClick={() => setQuick(v)}
      // 48px tall, fully rounded. Label is 18px semibold, not 14px medium —
      // Figma node 228:20999 gives Inter Semi Bold 18.545px at the frame's
      // 1.0597 scale, i.e. 17.5px. Active fill is the #0f3d2e primary;
      // inactive is `surface-muted` (#f3f4f6).
      className={`h-12 rounded-full px-5 text-label-lg font-semibold transition ${
        quick === v ? 'bg-emerald-deep text-white' : 'bg-surface-muted text-ink-700 hover:bg-ink-300/40'
      }`}
    >
      {label}
    </button>
  );

  return (
    // Search card is p-10 (40px) with a 36px gap to the quick-filter row —
    // measured from the card bounds y360-600 on the dashboard export.
    <div className="rounded-card border border-line/50 bg-surface-card p-10">
      <div className="flex gap-4">
        <div className="relative flex-1">
          <span aria-hidden className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 text-ink-300">
            🔍
          </span>
          {/* 72px tall, #fafafa fill, 1px #e5e7eb border, 20px radius —
              Figma 228:20973 (76px / rounded-[21.194px] at 1.0597 scale). */}
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && apply({ q: q.trim() || null })}
            placeholder="Search by location, property type, or price range…"
            className="h-18 w-full rounded-card border border-line bg-surface-page pl-14 pr-5 text-field text-ink-buyer outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
          />
        </div>
        <button
          type="button"
          onClick={() => setShowFilters((s) => !s)}
          className={`flex h-18 items-center gap-1.5 rounded-card px-6 text-sm font-medium transition ${
            showFilters ? 'bg-emerald-deep text-bone' : 'border border-line text-ink-700 hover:border-ink-500'
          }`}
        >
          ⚙ Filters
        </button>
      </div>

      <div className="mt-9 flex items-center gap-3">
        <span className="text-sm text-ink-500">Quick filters:</span>
        {quickBtn('all', 'All Properties')}
        {quickBtn('verified', 'Verified Only')}
        {quickBtn('distress', 'Distress Sales')}
      </div>

      {showFilters && (
        <div className="mt-4 grid grid-cols-1 gap-3 border-t border-line pt-4 sm:grid-cols-4">
          <label className="text-xs font-medium text-ink-700">
            Location (state)
            <input
              defaultValue={params.get('state') ?? ''}
              onBlur={(e) => apply({ state: e.target.value.trim() || null })}
              placeholder="e.g. Lagos"
              className="mt-1 w-full rounded-md border border-ink-300/50 px-3 py-2 text-sm font-normal text-ink-buyer outline-none focus:border-emerald-accent"
            />
          </label>
          <label className="text-xs font-medium text-ink-700">
            Property Type
            <select
              defaultValue={params.get('property_type') ?? ''}
              onChange={(e) => apply({ property_type: e.target.value || null })}
              className="mt-1 w-full rounded-md border border-ink-300/50 px-3 py-2 text-sm font-normal text-ink-buyer outline-none focus:border-emerald-accent"
            >
              {PROPERTY_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-ink-700">
            Min Price (₦)
            <MoneyInput
              value={priceMin}
              onChange={setPriceMin}
              onBlur={() => apply({ price_min: priceMin ? String(nairaToKobo(priceMin)) : null })}
              placeholder="₦0"
              ariaLabel="Minimum price in naira"
              className="mt-1 w-full rounded-md border border-ink-300/50 px-3 py-2 text-sm font-normal text-ink-buyer outline-none focus:border-emerald-accent"
            />
          </label>
          <label className="text-xs font-medium text-ink-700">
            Max Price (₦)
            <MoneyInput
              value={priceMax}
              onChange={setPriceMax}
              onBlur={() => apply({ price_max: priceMax ? String(nairaToKobo(priceMax)) : null })}
              placeholder="No limit"
              ariaLabel="Maximum price in naira"
              className="mt-1 w-full rounded-md border border-ink-300/50 px-3 py-2 text-sm font-normal text-ink-buyer outline-none focus:border-emerald-accent"
            />
          </label>
        </div>
      )}
    </div>
  );
}
