'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useId, useState } from 'react';
import { MoneyInput } from '@/app/_components/money-input';
import { nairaToKobo } from '@/lib/money-input';

type Quick = 'all' | 'verified' | 'distress';

const PROPERTY_TYPES = [
  { value: '', label: 'Any type' },
  { value: 'land', label: 'Land' },
  { value: 'residential', label: 'Residential' },
  { value: 'commercial', label: 'Commercial' },
];

/** The URL params the expandable panel owns — counted for the Filters badge. */
const PANEL_PARAMS = ['state', 'property_type', 'price_min', 'price_max'] as const;

/**
 * One treatment for every control in the expanded panel (SCRUM-245). They were
 * 38px `rounded-md` boxes with 12px labels beside a 72px search field and 48px
 * pills — a second, smaller design system inside the same card. Now they share
 * the search field's fill, border and focus ring at a 48px height.
 */
const PANEL_CONTROL =
  'mt-1.5 h-12 w-full rounded-xl border border-line bg-surface-page px-4 text-sm font-normal text-ink-buyer outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20';

const PANEL_LABEL = 'block text-sm font-medium text-ink-700';

/** Search + quick filters + expandable filter row for the buyer feed
 * (SCRUM-95). Writes the filter state into the URL search params; the server
 * component re-fetches the feed from them. */
export function SearchFilterBar() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const panelId = useId();
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

  // With the panel closed nothing else shows that a price or type filter is
  // narrowing the feed, so the button carries the count.
  const activeCount = PANEL_PARAMS.filter((k) => params.get(k)).length;

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
      aria-pressed={quick === v}
      // 48px tall, fully rounded, 18px semibold from `sm` — Figma node
      // 228:20999 gives Inter Semi Bold 18.545px at the frame's 1.0597 scale,
      // i.e. 17.5px. Phones get 40px / 14px so the three pills fit two rows
      // of a 375px screen instead of running off its edge (SCRUM-245).
      // Active fill is the #0f3d2e primary; inactive is `surface-muted`.
      className={`h-10 whitespace-nowrap rounded-full px-4 text-sm font-semibold transition sm:h-12 sm:px-5 sm:text-label-lg ${
        quick === v ? 'bg-emerald-deep text-white' : 'bg-surface-muted text-ink-700 hover:bg-ink-300/40'
      }`}
    >
      {label}
    </button>
  );

  return (
    // Search card is p-10 (40px) with a 36px gap to the quick-filter row on
    // desktop — measured from the card bounds y360-600 on the dashboard export.
    // Scaled down below `lg`: 40px a side left a 375px phone a 230px search box.
    <div className="rounded-card border border-line/50 bg-surface-card p-5 sm:p-8 lg:p-10">
      <div className="flex gap-3 sm:gap-4">
        <div className="relative min-w-0 flex-1">
          <SearchIcon className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-300 sm:left-5" />
          {/* 72px tall from `sm`, #fafafa fill, 1px #e5e7eb border, 20px
              radius — Figma 228:20973 (76px / rounded-[21.194px] at 1.0597
              scale). 56px on phones. */}
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && apply({ q: q.trim() || null })}
            placeholder="Search by location, property type, or price range…"
            aria-label="Search properties"
            enterKeyHint="search"
            className="h-14 w-full text-ellipsis rounded-card border border-line bg-surface-page pl-11 pr-4 text-base text-ink-buyer outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20 sm:h-18 sm:pl-14 sm:pr-5 sm:text-field"
          />
        </div>
        <button
          type="button"
          onClick={() => setShowFilters((s) => !s)}
          aria-expanded={showFilters}
          aria-controls={panelId}
          // Icon-only on phones (a square beside the search field); the word
          // comes back from `sm`. The accessible name is the same either way.
          className={`relative flex h-14 w-14 flex-none items-center justify-center gap-2 rounded-card text-sm font-semibold transition sm:h-18 sm:w-auto sm:px-6 ${
            showFilters ? 'bg-emerald-deep text-white' : 'border border-line text-ink-700 hover:border-ink-500'
          }`}
        >
          <SlidersIcon className="h-5 w-5" />
          <span className="sr-only sm:not-sr-only">Filters</span>
          {activeCount > 0 && (
            <span
              // Phones: a corner badge OVER the card edge, so it is always the
              // accent colour with a card-coloured ring — white-on-open would
              // vanish into the card. From `sm` it sits inside the button and
              // inverts with it.
              className={`absolute -right-1.5 -top-1.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-emerald-accent px-1 text-xs font-semibold text-white ring-2 ring-surface-card sm:static sm:ml-0.5 sm:ring-0 ${
                showFilters ? 'sm:bg-white sm:text-emerald-deep' : 'sm:bg-emerald-deep sm:text-white'
              }`}
            >
              {activeCount}
              <span className="sr-only"> active</span>
            </span>
          )}
        </button>
      </div>

      {/* Label above the pills on phones, inline from `sm`; pills wrap rather
          than push the page sideways. */}
      <div className="mt-5 flex flex-wrap items-center gap-2 sm:mt-9 sm:gap-3">
        <span className="w-full text-sm text-ink-500 sm:w-auto">Quick filters:</span>
        {quickBtn('all', 'All Properties')}
        {quickBtn('verified', 'Verified Only')}
        {quickBtn('distress', 'Distress Sales')}
      </div>

      {showFilters && (
        <div
          id={panelId}
          className="mt-5 grid grid-cols-1 gap-4 border-t border-line pt-5 sm:mt-6 sm:grid-cols-2 sm:pt-6 lg:grid-cols-4"
        >
          <label className={PANEL_LABEL}>
            Location (state)
            <input
              defaultValue={params.get('state') ?? ''}
              onBlur={(e) => apply({ state: e.target.value.trim() || null })}
              placeholder="e.g. Lagos"
              className={PANEL_CONTROL}
            />
          </label>
          <label className={PANEL_LABEL}>
            Property Type
            <select
              defaultValue={params.get('property_type') ?? ''}
              onChange={(e) => apply({ property_type: e.target.value || null })}
              className={PANEL_CONTROL}
            >
              {PROPERTY_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <label className={PANEL_LABEL}>
            Min Price (₦)
            <MoneyInput
              value={priceMin}
              onChange={setPriceMin}
              onBlur={() => apply({ price_min: priceMin ? String(nairaToKobo(priceMin)) : null })}
              placeholder="₦0"
              ariaLabel="Minimum price in naira"
              className={PANEL_CONTROL}
            />
          </label>
          <label className={PANEL_LABEL}>
            Max Price (₦)
            <MoneyInput
              value={priceMax}
              onChange={setPriceMax}
              onBlur={() => apply({ price_max: priceMax ? String(nairaToKobo(priceMax)) : null })}
              placeholder="No limit"
              ariaLabel="Maximum price in naira"
              className={PANEL_CONTROL}
            />
          </label>
        </div>
      )}
    </div>
  );
}

// Inline SVGs, not the 🔍 / ⚙ emoji they replace: emoji render in each
// platform's own colour font (a blue-and-purple magnifier on Windows) and at
// a size the surrounding text does not control.
function SearchIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" className={className} aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

function SlidersIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" className={className} aria-hidden>
      <path d="M4 7h10M18 7h2M4 17h4M12 17h8" />
      <circle cx="16" cy="7" r="2" />
      <circle cx="10" cy="17" r="2" />
    </svg>
  );
}
