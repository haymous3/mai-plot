import type { Metadata } from 'next';
import Link from 'next/link';

import { SellerHeader } from './seller-header';

export const metadata: Metadata = { title: 'Dashboard · Maiplot Seller' };

/** Seller Dashboard Overview (SCRUM-98). Stats + recent activity land in a later
 * PR; for now this is the signed-in landing with quick links to the sections. */
export default function SellerOverviewPage() {
  return (
    <main className="mx-auto max-w-6xl px-8 py-8">
      <SellerHeader title="Dashboard Overview" subtitle="Welcome back" />

      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Link
          href="/seller/listings"
          className="rounded-2xl border border-ink-300/25 bg-white p-6 transition hover:border-ink-500/40"
        >
          <p className="text-2xl">📦</p>
          <p className="mt-3 font-medium text-ink-900">My Listings</p>
          <p className="mt-1 text-sm text-ink-500">Manage your property listings.</p>
        </Link>
        <Link
          href="/seller/listings/new"
          className="rounded-2xl border border-ink-300/25 bg-white p-6 transition hover:border-ink-500/40"
        >
          <p className="text-2xl">➕</p>
          <p className="mt-3 font-medium text-ink-900">Create a Listing</p>
          <p className="mt-1 text-sm text-ink-500">List a new property for sale.</p>
        </Link>
        <Link
          href="/seller/offers"
          className="rounded-2xl border border-ink-300/25 bg-white p-6 transition hover:border-ink-500/40"
        >
          <p className="text-2xl">🤝</p>
          <p className="mt-3 font-medium text-ink-900">Offers</p>
          <p className="mt-1 text-sm text-ink-500">Review and respond to buyer offers.</p>
        </Link>
      </div>

      <p className="mt-8 rounded-xl border border-dashed border-ink-300/40 bg-white/60 px-6 py-10 text-center text-sm text-ink-500">
        Performance insights &amp; recent activity are coming to this overview soon.
      </p>
    </main>
  );
}
