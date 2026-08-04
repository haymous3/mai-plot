import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import { LoanStatusCard } from './loan-status-card';
import { PropertyCard } from './property-card';
import { RecentlyViewedCard } from './recently-viewed-card';
import { SearchFilterBar } from './search-filter-bar';
import type { BuyerLoansResponse, DealsResponse, FeedResponse } from '@/lib/api';
import { listingServiceUrl, loanServiceUrl, transactionServiceUrl } from '@/lib/api';
import { BUYER_LOGIN } from '@/lib/buyer-auth';
import { buyerBackendGet } from '@/lib/buyer-server-api';
import { dealCompletedSteps, dealStageLabel, DEAL_TOTAL_STEPS, isDealActive } from '@/lib/deal-stage';
import { formatNaira } from '@/lib/format';

export const metadata: Metadata = { title: 'Dashboard · Maiplot' };

// Verified % and avg deal time are platform aggregates owned by analytics-service
// (not built yet — SCRUM-126 is audit-log only). Shown as placeholders until that
// endpoint exists; Active Listings below is live from the feed total.
const PLACEHOLDER_STATS = { verifiedPct: '98%', avgDealDays: '14 days' };

const FEED_KEYS = [
  'q',
  'state',
  'sale_type',
  'property_type',
  'price_min',
  'price_max',
  'doc_status',
] as const;

function buildFeedUrl(params: Record<string, string | undefined>): string {
  const sp = new URLSearchParams();
  for (const k of FEED_KEYS) {
    const v = params[k];
    if (v) sp.set(k, v);
  }
  sp.set('page_size', '18');
  // Search uses the ES endpoint; the plain feed otherwise.
  const path = params.q ? '/listings/search' : '/listings';
  return `${listingServiceUrl()}${path}?${sp.toString()}`;
}

async function fetchFeed(url: string): Promise<FeedResponse | null> {
  const result = await buyerBackendGet<FeedResponse>(url);
  if (!result.ok && result.status === 401) redirect(BUYER_LOGIN);
  return result.ok ? result.data : null;
}

/**
 * Values from Figma node 228:20937, divided by the frame's 1.0597 scale factor.
 *
 * The card edge is a 1px `#e5e7eb` border at 50% opacity and NO shadow.
 * SCRUM-163 read the resulting soft two-pixel ramp as a shadow — a translucent
 * border and a small shadow are indistinguishable in a raster. Corrected in
 * SCRUM-169.
 *
 * 20px radius, 31px padding (p-8 = 32, within 1px), 60px chip centred
 * vertically against the card rather than aligned to the padding box.
 *
 * Chip tint is the stat's own accent at 8% opacity — emerald for listings and
 * verification, gold for deal time (`rgba(201,166,70,0.08)` at node 228:20966).
 */
function StatCard({
  label,
  value,
  icon,
  accent = 'emerald',
}: {
  label: string;
  value: string;
  icon: string;
  accent?: 'emerald' | 'gold';
}) {
  return (
    <div className="flex items-center justify-between rounded-card border border-line/50 bg-surface-card p-8">
      <div>
        <p className="text-label-lg text-ink-500">{label}</p>
        <p className="mt-1.5 font-display text-stat text-ink-900">{value}</p>
      </div>
      <span
        aria-hidden
        className={`flex h-15 w-15 flex-none items-center justify-center rounded-card ${
          accent === 'gold' ? 'bg-status-gold/[0.08] text-status-gold' : 'bg-emerald-deep/[0.08] text-emerald-deep'
        }`}
      >
        {icon}
      </span>
    </div>
  );
}

function SidebarCard({ children }: { children: React.ReactNode }) {
  return <div className="rounded-card border border-line/50 bg-surface-card p-8">{children}</div>;
}

export default async function BuyerDashboardPage({
  searchParams,
}: {
  searchParams: Record<string, string | string[] | undefined>;
}) {
  const flat: Record<string, string | undefined> = {};
  for (const k of FEED_KEYS) {
    const v = searchParams[k];
    flat[k] = Array.isArray(v) ? v[0] : v;
  }

  const [urgent, all, saved, dealsRes, loansRes] = await Promise.all([
    fetchFeed(`${listingServiceUrl()}/listings?sale_type=distress&sort=urgency&page_size=4`),
    fetchFeed(buildFeedUrl(flat)),
    fetchFeed(`${listingServiceUrl()}/listings/saved`),
    buyerBackendGet<DealsResponse>(`${transactionServiceUrl()}/transactions`),
    buyerBackendGet<BuyerLoansResponse>(`${loanServiceUrl()}/loans/me`),
  ]);

  // Most recent loan, if any — surfaced as a status card (SCRUM-135).
  const latestLoan = loansRes.ok ? (loansRes.data.items[0] ?? null) : null;

  const activeListings = all?.pagination.total ?? 0;
  const savedIds = new Set((saved?.data ?? []).map((i) => i.id));
  const activeDeals = (dealsRes.ok ? dealsRes.data.data : []).filter((d) => isDealActive(d.stage));

  return (
    /*
     * Full-bleed with 44px inline padding, not width-constrained — the design's
     * content spans 1477 of a 1562px frame. `max-w-6xl` (1152px) was ~320px
     * narrower than intended. Capped at the frame width so it matches at 1562
     * and does not stretch indefinitely on ultrawide displays.
     *
     * A 3-column grid, NOT fixed widths: Figma places the cards at x=0/503/1006
     * at 471.2 wide, i.e. a 31.8px gutter — 30px once the frame's 1.0597 scale
     * is removed, so `gap-8` (32px) on the 4px grid. Hardcoding 471 would not
     * hold at any other viewport.
     */
    <main className="mx-auto max-w-[1562px] px-11 py-8">
      <div className="grid grid-cols-1 gap-8 sm:grid-cols-3">
        <StatCard label="Active Listings" value={String(activeListings)} icon="📈" />
        <StatCard label="Verified This Week" value={PLACEHOLDER_STATS.verifiedPct} icon="🛡" />
        <StatCard label="Avg. Deal Time" value={PLACEHOLDER_STATS.avgDealDays} icon="⏱" accent="gold" />
      </div>

      <div className="mt-9">
        <SearchFilterBar />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        <div>
          {urgent && urgent.data.length > 0 && (
            <section>
              <div className="flex items-end justify-between">
                <div>
                  <h2 className="font-display text-2xl text-ink-900">🔥 Urgent Deals</h2>
                  <p className="text-xs text-ink-500">Below market value · Limited time</p>
                </div>
                <Link
                  href="/dashboard?sale_type=distress"
                  className="text-sm text-emerald-deep hover:underline"
                >
                  View All →
                </Link>
              </div>
              <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                {urgent.data.map((item) => (
                  <PropertyCard
                    key={item.id}
                    item={item}
                    variant="grid"
                    saved={savedIds.has(item.id)}
                  />
                ))}
              </div>
            </section>
          )}

          <section className="mt-8">
            <h2 className="font-display text-2xl text-ink-900">All Properties</h2>
            <p className="text-xs text-ink-500">{activeListings} listings available</p>
            <div className="mt-4 space-y-3">
              {!all ? (
                <div className="rounded-xl border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
                  Could not load listings. Please retry.
                </div>
              ) : all.data.length === 0 ? (
                <div className="rounded-xl border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center text-sm text-ink-400">
                  No properties match your filters.
                </div>
              ) : (
                all.data.map((item) => (
                  <PropertyCard
                    key={item.id}
                    item={item}
                    variant="row"
                    saved={savedIds.has(item.id)}
                  />
                ))
              )}
            </div>
          </section>
        </div>

        <aside className="space-y-4">
          <div className="rounded-2xl bg-emerald-deep p-5 text-bone">
            <p className="flex items-center gap-2 font-semibold">🛡 Trust Verified</p>
            <p className="mt-2 text-sm text-bone/80">
              80% of new listings verified with complete legal documentation.
            </p>
            <p className="mt-3 rounded-lg bg-white/10 px-3 py-2 text-xs">
              ✓ Verified properties close 3x faster
            </p>
          </div>

          {latestLoan && <LoanStatusCard loan={latestLoan} />}

          <SidebarCard>
            <p className="flex items-center gap-2 font-semibold text-ink-900">💳 Get Financing</p>
            <p className="mt-1 text-xs text-ink-500">Pre-approval for up to 50% of property value.</p>
            <Link
              href="/dashboard"
              className="mt-4 block rounded-lg bg-emerald-deep px-4 py-2.5 text-center text-sm font-semibold text-bone transition hover:bg-emerald-accent"
            >
              Apply for Pre-Approval
            </Link>
          </SidebarCard>

          <SidebarCard>
            <div className="flex items-center justify-between">
              <p className="flex items-center gap-2 font-semibold text-ink-900">💼 Your Active Deals</p>
              {activeDeals.length > 0 && (
                <span className="rounded-full bg-emerald-deep/10 px-2 py-0.5 text-xs font-medium text-emerald-deep">
                  {activeDeals.length} active
                </span>
              )}
            </div>
            {activeDeals.length === 0 ? (
              <div className="mt-4 flex flex-col items-center py-4 text-center">
                <span aria-hidden className="text-2xl text-ink-300">
                  ⓘ
                </span>
                <p className="mt-2 text-sm text-ink-500">No active deals yet</p>
                <p className="mt-1 text-xs font-medium text-emerald-deep">
                  Start exploring properties
                </p>
              </div>
            ) : (
              <ul className="mt-3 space-y-3">
                {activeDeals.slice(0, 3).map((d) => (
                  <li key={d.transaction_id}>
                    <Link
                      href={`/deals/${d.transaction_id}`}
                      className="block rounded-xl border border-ink-300/25 p-3 transition hover:border-ink-500/40"
                    >
                      <p className="truncate text-sm font-medium text-ink-900">
                        {d.property_title ?? 'Property deal'}
                      </p>
                      <p className="mt-0.5 text-xs text-ink-500">
                        Bid {formatNaira(d.agreed_price_kobo)}
                      </p>
                      <div className="mt-2 flex items-center justify-between text-xs">
                        <span className="text-ink-500">{dealStageLabel(d.stage)}</span>
                        <span className="text-ink-400">
                          Step {dealCompletedSteps(d.stage)} of {DEAL_TOTAL_STEPS}
                        </span>
                      </div>
                      <div className="mt-1.5 h-1 rounded-full bg-ink-300/30">
                        <div
                          className="h-1 rounded-full bg-emerald-deep"
                          style={{
                            width: `${(dealCompletedSteps(d.stage) / DEAL_TOTAL_STEPS) * 100}%`,
                          }}
                        />
                      </div>
                      <p className="mt-2 text-xs font-medium text-emerald-deep">Track progress →</p>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </SidebarCard>

          <SidebarCard>
            <p className="font-semibold text-ink-900">Saved Properties</p>
            {!saved || saved.data.length === 0 ? (
              <p className="mt-4 text-center text-sm text-ink-400">No saved properties yet.</p>
            ) : (
              <ul className="mt-3 space-y-3">
                {saved.data.slice(0, 4).map((item) => (
                  <li key={item.id}>
                    <Link href={`/listings/${item.id}`} className="flex items-center gap-3 group">
                      <span className="flex h-10 w-12 flex-none items-center justify-center rounded-lg bg-bone text-ink-300">
                        🏠
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium text-ink-900 group-hover:underline">
                          {item.title}
                        </span>
                        <span className="block truncate text-xs text-ink-500">
                          {item.lga} · {formatNaira(item.asking_price_kobo)}
                        </span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </SidebarCard>

          <RecentlyViewedCard />
        </aside>
      </div>
    </main>
  );
}
