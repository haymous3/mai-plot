import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { ListingActions } from './listing-actions';
import { SellerHeader } from '../seller-header';
import type { SellerListingItem, SellerListingsResponse } from '@/lib/api';
import { listingServiceUrl } from '@/lib/api';
import { SESSION_LOGIN } from '@/lib/session';
import { sessionBackendGet } from '@/lib/session-api';
import { formatNaira } from '@/lib/format';

export const metadata: Metadata = { title: 'My Listings · Maiplot Seller' };

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  active: { label: 'live', cls: 'bg-emerald-deep/10 text-emerald-deep' },
  paused: { label: 'paused', cls: 'bg-amber-100 text-amber-700' },
  pending_review: { label: 'under review', cls: 'bg-amber-100 text-amber-700' },
  under_offer: { label: 'under offer', cls: 'bg-blue-100 text-blue-700' },
  sold: { label: 'sold', cls: 'bg-ink-300/20 text-ink-600' },
  expired: { label: 'expired', cls: 'bg-ink-300/20 text-ink-500' },
  rejected: { label: 'rejected', cls: 'bg-red-100 text-red-700' },
};

const DOC_BADGE: Record<string, { label: string; cls: string }> = {
  verified: { label: '✓ approved', cls: 'text-emerald-deep' },
  pending: { label: '◷ pending', cls: 'text-amber-600' },
  not_submitted: { label: '○ no docs', cls: 'text-ink-500' },
  failed: { label: '✕ rejected', cls: 'text-red-600' },
};

function ListingCard({ item }: { item: SellerListingItem }) {
  const badge = STATUS_BADGE[item.status] ?? { label: item.status, cls: 'bg-ink-300/20 text-ink-600' };
  const doc = DOC_BADGE[item.doc_verification_status];
  return (
    <div className="rounded-2xl border border-ink-300/25 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <p className="font-medium text-ink-900">{item.title}</p>
            {item.sale_type === 'distress' && (
              <span className="rounded-full bg-red-100 px-2 py-0.5 text-[11px] font-medium text-red-600">
                Distress
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs text-ink-500">
            📍 {item.lga}, {item.state}
          </p>
        </div>
        <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${badge.cls}`}>
          {badge.label}
        </span>
      </div>

      <div className="mt-2 flex items-center gap-2">
        <p className="font-display text-lg text-emerald-deep">{formatNaira(item.asking_price_kobo)}</p>
        {doc && <span className={`text-xs font-medium ${doc.cls}`}>{doc.label}</span>}
      </div>

      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-500">
        <span>👁 {item.view_count} views</span>
        <span>🤝 {item.offers_count} offers</span>
        <span>♥ {item.saves_count} saves</span>
      </p>

      <ListingActions id={item.id} status={item.status} />
    </div>
  );
}

export default async function SellerListingsPage() {
  const result = await sessionBackendGet<SellerListingsResponse>(
    `${listingServiceUrl()}/listings/mine`,
  );
  if (!result.ok && result.status === 401) redirect(`${SESSION_LOGIN}?role=seller`);
  const listings = result.ok ? result.data.data : [];

  return (
    <main className="mx-auto max-w-6xl px-8 py-8">
      <SellerHeader title="My Listings" subtitle="Manage your property listings" />

      <div className="mt-6 space-y-3">
        {!result.ok ? (
          <div className="rounded-xl border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
            Could not load your listings. Please retry.
          </div>
        ) : listings.length === 0 ? (
          <div className="rounded-xl border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center text-sm text-ink-500">
            You haven&rsquo;t created any listings yet.
          </div>
        ) : (
          listings.map((item) => <ListingCard key={item.id} item={item} />)
        )}
      </div>
    </main>
  );
}
