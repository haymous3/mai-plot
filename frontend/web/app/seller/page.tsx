import type { Metadata } from 'next';
import Link from 'next/link';

import { buildActivity, timeAgo } from './activity';
import { SellerHeader } from './seller-header';
import type {
  SellerDealsResponse,
  SellerDocumentsResponse,
  SellerListingsResponse,
  SellerOffersResponse,
} from '@/lib/api';
import { documentServiceUrl, listingServiceUrl, transactionServiceUrl } from '@/lib/api';
import { formatNaira } from '@/lib/format';
import { isSaleActive } from '@/lib/seller-deal-stage';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Dashboard · Maiplot Seller' };

const ACTIVE_LISTING_STATUSES = new Set(['active', 'under_offer', 'paused', 'pending_review']);

/** Seller Dashboard Overview (SCRUM-98). Stats + recent activity are derived from
 * the listings/offers/sales/documents endpoints — there is no dedicated stats or
 * activity source. */
export default async function SellerOverviewPage() {
  const [listingsR, offersR, salesR, docsR] = await Promise.all([
    sessionBackendGet<SellerListingsResponse>(`${listingServiceUrl()}/listings/mine`),
    sessionBackendGet<SellerOffersResponse>(`${transactionServiceUrl()}/offers`),
    sessionBackendGet<SellerDealsResponse>(`${transactionServiceUrl()}/sales`),
    sessionBackendGet<SellerDocumentsResponse>(`${documentServiceUrl()}/documents/mine`),
  ]);

  const listings = listingsR.ok ? listingsR.data.data : [];
  const offers = offersR.ok ? offersR.data.data : [];
  const sales = salesR.ok ? salesR.data.data : [];
  const docs = docsR.ok ? docsR.data.data : [];

  const activeListings = listings.filter((l) => ACTIVE_LISTING_STATUSES.has(l.status)).length;
  const totalViews = listings.reduce((n, l) => n + l.view_count, 0);
  const totalSaves = listings.reduce((n, l) => n + l.saves_count, 0);
  const pendingOffers = offers.filter((o) => o.status === 'pending').length;
  const dealsInProgress = sales.filter((s) => isSaleActive(s.stage)).length;
  const completed = sales.filter((s) => s.stage === 'completed');
  const completedTotal = completed.reduce((n, s) => n + s.agreed_price_kobo, 0);
  const conversion = totalViews > 0 ? (offers.length / totalViews) * 100 : 0;

  const activity = buildActivity(offers, sales, docs);

  return (
    <main className="mx-auto max-w-6xl px-8 py-8">
      <SellerHeader title="Dashboard Overview" subtitle="Welcome back" />

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_300px]">
        <div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Stat icon="🏠" value={String(activeListings)} label="Active Listings" />
            <Stat icon="🤝" value={String(offers.length)} label="Offers Received" hint={`${pendingOffers} pending`} />
            <Stat icon="📈" value={String(dealsInProgress)} label="Deals in Progress" />
            <Stat
              icon="✓"
              value={String(completed.length)}
              label="Completed Sales"
              hint={completedTotal > 0 ? `${formatNaira(completedTotal)} total` : undefined}
            />
          </div>

          <section className="mt-6 rounded-2xl border border-ink-300/25 bg-white p-6">
            <h2 className="font-display text-lg text-ink-900">Recent Activity</h2>
            <ul className="mt-3 divide-y divide-ink-300/15">
              {activity.length === 0 ? (
                <li className="py-8 text-center text-sm text-ink-500">No recent activity yet.</li>
              ) : (
                activity.map((a, i) => (
                  <li key={i} className="flex items-start gap-3 py-3">
                    <span className="mt-0.5 flex h-8 w-8 flex-none items-center justify-center rounded-lg bg-bone text-sm">
                      {a.icon}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-ink-900">{a.title}</p>
                      <p className="truncate text-sm text-ink-500">{a.detail}</p>
                      <p className="text-xs text-ink-300">{timeAgo(a.ts)}</p>
                    </div>
                  </li>
                ))
              )}
            </ul>
          </section>
        </div>

        <aside className="space-y-4">
          <div className="space-y-2">
            <Link
              href="/seller/listings/new"
              className="block rounded-xl bg-emerald-deep px-4 py-3 text-center text-sm font-semibold text-bone transition hover:bg-emerald-accent"
            >
              + New Listing
            </Link>
            <Link
              href="/seller/offers"
              className="block rounded-xl border border-emerald-deep/40 px-4 py-3 text-center text-sm font-semibold text-emerald-deep transition hover:bg-emerald-deep/5"
            >
              View Pending Offers ({pendingOffers})
            </Link>
          </div>

          <div className="rounded-2xl bg-bone/70 p-5">
            <p className="text-sm font-medium text-ink-800">Performance Insights</p>
            <Insight label="Total Views" value={totalViews.toLocaleString()} />
            <Insight label="Saves / Bookmarks" value={String(totalSaves)} />
            <Insight label="Offer Conversion" value={`${conversion.toFixed(1)}%`} />
          </div>

          <div className="rounded-2xl border border-emerald-deep/15 bg-emerald-deep/5 p-5">
            <p className="text-sm font-medium text-emerald-deep">Pro Tip</p>
            <p className="mt-1 text-xs text-ink-700">
              Verified listings with complete documentation perform 3× better. Upload all documents to
              increase buyer trust.
            </p>
          </div>
        </aside>
      </div>
    </main>
  );
}

function Stat({ icon, value, label, hint }: { icon: string; value: string; label: string; hint?: string }) {
  return (
    <div className="rounded-2xl border border-ink-300/25 bg-white p-5">
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-bone text-lg">{icon}</span>
      <p className="mt-3 font-display text-3xl text-ink-900">{value}</p>
      <p className="text-sm text-ink-600">{label}</p>
      {hint && <p className="mt-0.5 text-xs text-emerald-deep">↗ {hint}</p>}
    </div>
  );
}

function Insight({ label, value }: { label: string; value: string }) {
  return (
    <div className="mt-3 flex items-center justify-between border-t border-ink-300/15 pt-2 first:border-0 first:pt-0">
      <span className="text-xs text-ink-600">{label}</span>
      <span className="text-sm font-semibold text-ink-900">{value}</span>
    </div>
  );
}
