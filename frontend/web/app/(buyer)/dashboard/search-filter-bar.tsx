'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useState } from 'react';

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
      className={`rounded-full px-3.5 py-1.5 text-xs font-medium transition ${
        quick === v ? 'bg-emerald-deep text-bone' : 'bg-bone text-ink-700 hover:bg-ink-300/20'
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="rounded-2xl border border-ink-300/25 bg-white p-4">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <span aria-hidden className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-300">
            🔍
          </span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && apply({ q: q.trim() || null })}
            placeholder="Search by location, property type, or price range…"
            className="w-full rounded-lg border border-ink-300/50 bg-white py-2.5 pl-10 pr-3.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
          />
        </div>
        <button
          type="button"
          onClick={() => setShowFilters((s) => !s)}
          className={`flex items-center gap-1.5 rounded-lg px-4 text-sm font-medium transition ${
            showFilters ? 'bg-emerald-deep text-bone' : 'border border-ink-300/50 text-ink-700 hover:border-ink-500'
          }`}
        >
          ⚙ Filters
        </button>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <span className="text-xs text-ink-400">Quick filters:</span>
        {quickBtn('all', 'All Properties')}
        {quickBtn('verified', 'Verified Only')}
        {quickBtn('distress', 'Distress Sales')}
      </div>

      {showFilters && (
        <div className="mt-4 grid grid-cols-1 gap-3 border-t border-ink-300/20 pt-4 sm:grid-cols-4">
          <label className="text-xs font-medium text-ink-700">
            Location (state)
            <input
              defaultValue={params.get('state') ?? ''}
              onBlur={(e) => apply({ state: e.target.value.trim() || null })}
              placeholder="e.g. Lagos"
              className="mt-1 w-full rounded-md border border-ink-300/50 px-3 py-2 text-sm font-normal text-ink-900 outline-none focus:border-emerald-accent"
            />
          </label>
          <label className="text-xs font-medium text-ink-700">
            Property Type
            <select
              defaultValue={params.get('property_type') ?? ''}
              onChange={(e) => apply({ property_type: e.target.value || null })}
              className="mt-1 w-full rounded-md border border-ink-300/50 px-3 py-2 text-sm font-normal text-ink-900 outline-none focus:border-emerald-accent"
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
            <input
              inputMode="numeric"
              defaultValue={params.get('price_min') ? String(Number(params.get('price_min')) / 100) : ''}
              onBlur={(e) => {
                const naira = e.target.value.replace(/\D/g, '');
                apply({ price_min: naira ? String(Number(naira) * 100) : null });
              }}
              placeholder="₦0"
              className="mt-1 w-full rounded-md border border-ink-300/50 px-3 py-2 text-sm font-normal text-ink-900 outline-none focus:border-emerald-accent"
            />
          </label>
          <label className="text-xs font-medium text-ink-700">
            Max Price (₦)
            <input
              inputMode="numeric"
              defaultValue={params.get('price_max') ? String(Number(params.get('price_max')) / 100) : ''}
              onBlur={(e) => {
                const naira = e.target.value.replace(/\D/g, '');
                apply({ price_max: naira ? String(Number(naira) * 100) : null });
              }}
              placeholder="No limit"
              className="mt-1 w-full rounded-md border border-ink-300/50 px-3 py-2 text-sm font-normal text-ink-900 outline-none focus:border-emerald-accent"
            />
          </label>
        </div>
      )}
    </div>
  );
}
