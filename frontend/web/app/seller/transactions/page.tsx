import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import { SaleProgress } from './sale-progress';
import type { SellerDeal, SellerDealsResponse } from '@/lib/api';
import { transactionServiceUrl } from '@/lib/api';
import { formatNaira } from '@/lib/format';
import { SESSION_LOGIN } from '@/lib/session';
import { sessionBackendGet } from '@/lib/session-api';
import { isSaleActive, sellerStageLabel } from '@/lib/seller-deal-stage';

export const metadata: Metadata = { title: 'Transactions · Maiplot Seller' };

const RESPONSIBILITIES = [
  'Ensure all documents are verified',
  'Coordinate with the title transfer agent',
  'Facilitate property inspection',
];

function SaleCard({ deal }: { deal: SellerDeal }) {
  return (
    <div className="rounded-2xl border border-ink-300/25 bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium text-ink-900">{deal.property_title ?? 'Property'}</p>
          <p className="text-xs text-ink-500">Buyer: {deal.buyer_ref}</p>
          <span
            className={`mt-1 inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${
              isSaleActive(deal.stage)
                ? 'bg-amber-100 text-amber-700'
                : 'bg-emerald-deep/10 text-emerald-deep'
            }`}
          >
            {sellerStageLabel(deal.stage)}
          </span>
        </div>
        <div className="text-right">
          <p className="text-xs text-ink-500">Sale Price</p>
          <p className="font-display text-lg text-emerald-deep">{formatNaira(deal.agreed_price_kobo)}</p>
        </div>
      </div>

      <div className="mt-4">
        <SaleProgress stage={deal.stage} />
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-ink-300/20 pt-3">
        <p className="text-xs text-ink-500">
          Transaction {deal.transaction_id.slice(0, 8)}
        </p>
        <Link
          href={`/seller/transactions/${deal.transaction_id}`}
          className="text-sm font-medium text-amber-600 hover:underline"
        >
          View Full Details →
        </Link>
      </div>
    </div>
  );
}

export default async function SellerTransactionsPage() {
  const result = await sessionBackendGet<SellerDealsResponse>(`${transactionServiceUrl()}/sales`);
  if (!result.ok && result.status === 401) redirect(`${SESSION_LOGIN}?role=seller`);
  const deals = result.ok ? result.data.data : [];

  return (
    <main className="mx-auto max-w-6xl px-8 py-8">
      <div>
        <h1 className="font-display text-3xl text-emerald-deep">Transactions</h1>
        <p className="mt-1 text-sm text-ink-500">Track your active deals and sales</p>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_300px]">
        <div className="space-y-4">
          {!result.ok ? (
            <div className="rounded-xl border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
              Could not load your transactions. Please retry.
            </div>
          ) : deals.length === 0 ? (
            <div className="rounded-xl border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center text-sm text-ink-500">
              No transactions yet. They&rsquo;ll appear here once you accept an offer.
            </div>
          ) : (
            deals.map((d) => <SaleCard key={d.transaction_id} deal={d} />)
          )}
        </div>

        <aside className="space-y-4">
          <div className="rounded-2xl bg-bone/70 p-5">
            <p className="text-sm font-medium text-ink-800">Payment &amp; Escrow</p>
            <p className="mt-2 text-xs text-ink-600">
              Funds are released to you upon successful title verification and transfer completion.
              The exact buyer / loan split appears once financing is confirmed.
            </p>
          </div>
          <div className="rounded-2xl border border-emerald-deep/15 bg-emerald-deep/5 p-5">
            <p className="text-sm font-medium text-emerald-deep">Seller Responsibilities</p>
            <ul className="mt-2 space-y-1.5 text-xs text-ink-700">
              {RESPONSIBILITIES.map((r) => (
                <li key={r} className="flex gap-2">
                  <span className="text-emerald-accent">✓</span> {r}
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </div>
    </main>
  );
}
