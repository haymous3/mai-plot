'use client';

import { useState } from 'react';

import type { WalletPayment } from '@/lib/api';
import { formatNaira } from '@/lib/format';

type Tab = 'all' | 'payment' | 'refund';

const TYPE_LABEL: Record<string, string> = {
  buyer_deposit: 'Property deposit',
  refund: 'Refund',
};

function statusColor(status: string): string {
  if (status === 'completed') return 'text-emerald-deep';
  if (status === 'failed') return 'text-red-600';
  return 'text-amber-600'; // initiated / processing
}

/** "Transaction History" list with All / Payments / Refunds tabs (SCRUM-95).
 * Read-only. buyer_deposit is money out (−), a refund is money in (+). */
export function TransactionHistory({ payments }: { payments: WalletPayment[] }) {
  const [tab, setTab] = useState<Tab>('all');

  const filtered = payments.filter((p) =>
    tab === 'all'
      ? true
      : tab === 'refund'
        ? p.payment_type === 'refund'
        : p.payment_type === 'buyer_deposit',
  );

  const tabBtn = (v: Tab, label: string) => (
    <button
      type="button"
      onClick={() => setTab(v)}
      className={`rounded-full px-3.5 py-1.5 text-xs font-medium transition ${
        tab === v ? 'bg-emerald-deep text-bone' : 'bg-bone text-ink-700 hover:bg-ink-300/20'
      }`}
    >
      {label}
    </button>
  );

  return (
    <section className="rounded-card bg-surface-card p-8 shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-xl text-ink-900">Transaction History</h2>
        <div className="flex gap-2">
          {tabBtn('all', 'All')}
          {tabBtn('payment', 'Payments')}
          {tabBtn('refund', 'Refunds')}
        </div>
      </div>

      <ul className="mt-4 divide-y divide-ink-300/15">
        {filtered.length === 0 ? (
          <li className="py-10 text-center text-sm text-ink-400">No transactions yet.</li>
        ) : (
          filtered.map((p) => {
            const incoming = p.payment_type === 'refund';
            return (
              <li key={p.id} className="flex items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-ink-900">
                    {TYPE_LABEL[p.payment_type] ?? p.payment_type.replace(/_/g, ' ')}
                    {p.property_title ? ` · ${p.property_title}` : ''}
                  </p>
                  <p className="mt-0.5 text-xs text-ink-400">
                    {new Date(p.created_at).toLocaleDateString()}
                    {p.provider_reference ? ` · Ref: ${p.provider_reference}` : ''}
                  </p>
                </div>
                <div className="flex-none text-right">
                  <p className={`text-sm font-semibold ${incoming ? 'text-emerald-deep' : 'text-ink-900'}`}>
                    {incoming ? '+' : '−'}
                    {formatNaira(p.amount_kobo)}
                  </p>
                  <p className={`text-xs capitalize ${statusColor(p.status)}`}>{p.status}</p>
                </div>
              </li>
            );
          })
        )}
      </ul>
    </section>
  );
}
