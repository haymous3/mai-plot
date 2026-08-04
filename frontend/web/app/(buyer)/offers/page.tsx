import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import { BuyerOffersList } from './buyer-offers-list';
import type { BuyerOffersResponse } from '@/lib/api';
import { transactionServiceUrl } from '@/lib/api';
import { BUYER_LOGIN } from '@/lib/buyer-auth';
import { buyerBackendGet } from '@/lib/buyer-server-api';

export const metadata: Metadata = { title: 'My Offers · Maiplot' };

export default async function BuyerOffersPage() {
  const result = await buyerBackendGet<BuyerOffersResponse>(
    `${transactionServiceUrl()}/offers/placed`,
  );
  if (!result.ok && result.status === 401) redirect(BUYER_LOGIN);
  const offers = result.ok ? result.data.data : [];

  return (
    <main className="mx-auto max-w-3xl px-11 py-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl text-emerald-deep">My Offers</h1>
          <p className="mt-1 text-sm text-ink-500">Track the bids you&rsquo;ve placed and respond to counters</p>
        </div>
        <Link href="/dashboard" className="text-sm font-medium text-emerald-deep hover:underline">
          Browse properties →
        </Link>
      </div>

      <div className="mt-6">
        {!result.ok ? (
          <div className="rounded-xl border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
            Could not load your offers. Please retry.
          </div>
        ) : (
          <BuyerOffersList offers={offers} />
        )}
      </div>
    </main>
  );
}
