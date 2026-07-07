import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, redirect } from 'next/navigation';

import { SaleProgress } from '../sale-progress';
import type { ListingDetail, SellerDealsResponse } from '@/lib/api';
import { listingServiceUrl, transactionServiceUrl } from '@/lib/api';
import { formatNaira } from '@/lib/format';
import { SESSION_LOGIN } from '@/lib/session';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Transaction · Maiplot Seller' };

export default async function SellerTransactionDetailPage({ params }: { params: { id: string } }) {
  const sales = await sessionBackendGet<SellerDealsResponse>(`${transactionServiceUrl()}/sales`);
  if (!sales.ok) {
    if (sales.status === 401) redirect(`${SESSION_LOGIN}?role=seller`);
    notFound();
  }
  const deal = sales.data.data.find((d) => d.transaction_id === params.id);
  if (!deal) notFound();

  // Hero image + address come from the listing (best-effort — the card still
  // renders if the listing read fails).
  const listing = await sessionBackendGet<ListingDetail>(
    `${listingServiceUrl()}/listings/${encodeURIComponent(deal.listing_id)}`,
  );
  const hero = listing.ok ? (listing.data.media.find((m) => m.type === 'photo')?.url ?? null) : null;
  const address = listing.ok ? listing.data.address_text : null;

  return (
    <main className="mx-auto max-w-3xl px-8 py-8">
      <Link href="/seller/transactions" className="text-sm text-ink-500 hover:text-ink-800">
        ← Back to Transactions
      </Link>

      <div className="mt-4 overflow-hidden rounded-2xl border border-ink-300/25 bg-white">
        <div className="relative h-52 bg-ink-300/20">
          {hero ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={hero} alt="" className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-ink-500">
              No image
            </div>
          )}
          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/60 to-transparent p-4">
            <p className="text-xs text-white/70">Transaction {deal.transaction_id.slice(0, 8)}</p>
            <p className="font-display text-xl text-white">{deal.property_title ?? 'Property'}</p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 border-b border-ink-300/20 p-5 sm:grid-cols-3">
          <Fact label="Address" value={address ?? '—'} />
          <Fact label="Buyer" value={deal.buyer_ref} />
          <Fact label="Sale Price" value={formatNaira(deal.agreed_price_kobo)} />
        </div>

        <div className="p-5">
          <h2 className="font-display text-lg text-ink-900">Transaction Progress</h2>
          <div className="mt-4">
            <SaleProgress stage={deal.stage} />
          </div>
        </div>
      </div>
    </main>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-ink-500">{label}</p>
      <p className="mt-0.5 font-medium text-ink-900">{value}</p>
    </div>
  );
}
