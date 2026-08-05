import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import { TransactionHistory } from './transaction-history';
import type { WalletPaymentsResponse, WalletSummary } from '@/lib/api';
import { transactionServiceUrl } from '@/lib/api';
import { BUYER_LOGIN } from '@/lib/buyer-auth';
import { buyerBackendGet } from '@/lib/buyer-server-api';
import { dealStageLabel } from '@/lib/deal-stage';
import { formatNaira } from '@/lib/format';

export const metadata: Metadata = { title: 'My Wallet · Maiplot' };

function Tile({
  label,
  value,
  sub,
  icon,
  emphasis = false,
}: {
  label: string;
  value: string;
  sub?: string;
  icon: string;
  emphasis?: boolean;
}) {
  return (
    <div
      className={`rounded-2xl border p-5 ${
        emphasis ? 'border-transparent bg-emerald-deep text-bone' : 'border-ink-300/25 bg-white'
      }`}
    >
      <span
        className={`flex h-9 w-9 items-center justify-center rounded-lg ${
          emphasis ? 'bg-white/10' : 'bg-bone text-emerald-deep'
        }`}
      >
        {icon}
      </span>
      <p className={`mt-3 text-xs ${emphasis ? 'text-bone/70' : 'text-ink-500'}`}>{label}</p>
      <p className={`mt-1 font-display text-2xl ${emphasis ? 'text-bone' : 'text-ink-buyer'}`}>{value}</p>
      {sub && <p className={`mt-1 text-xs ${emphasis ? 'text-bone/70' : 'text-ink-400'}`}>{sub}</p>}
    </div>
  );
}

export default async function WalletPage() {
  const [summaryRes, paymentsRes] = await Promise.all([
    buyerBackendGet<WalletSummary>(`${transactionServiceUrl()}/wallet/summary`),
    buyerBackendGet<WalletPaymentsResponse>(`${transactionServiceUrl()}/wallet/payments`),
  ]);
  if (!summaryRes.ok && summaryRes.status === 401) redirect(BUYER_LOGIN);

  const summary = summaryRes.ok ? summaryRes.data : null;
  const payments = paymentsRes.ok ? paymentsRes.data.data : [];

  return (
    <main className="mx-auto max-w-5xl px-11 py-8">
      <h1 className="font-display text-3xl text-ink-buyer">My Wallet</h1>
      <p className="mt-1 text-sm text-ink-500">Track your escrow, payments, and property investments</p>

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Tile
          label="In Escrow"
          value={formatNaira(summary?.in_escrow_kobo ?? 0)}
          sub={`Locked in ${summary?.escrow_deal_count ?? 0} ${
            (summary?.escrow_deal_count ?? 0) === 1 ? 'transaction' : 'transactions'
          }`}
          icon="🏦"
          emphasis
        />
        <Tile label="Total Invested" value={formatNaira(summary?.total_invested_kobo ?? 0)} icon="📈" />
        <Tile
          label="Active Properties"
          value={String(summary?.active_property_count ?? 0)}
          sub="deals in progress"
          icon="🏠"
        />
      </div>

      <section className="mt-8 rounded-card border border-line/50 bg-surface-card p-8">
        <h2 className="font-display text-xl text-ink-buyer">Active Property Payments</h2>
        <div className="mt-4 space-y-4">
          {!summary || summary.active_payments.length === 0 ? (
            <p className="py-6 text-center text-sm text-ink-400">No active property payments.</p>
          ) : (
            summary.active_payments.map((p) => {
              const pct =
                p.total_kobo > 0 ? Math.min(100, Math.round((p.paid_kobo / p.total_kobo) * 100)) : 0;
              return (
                <div key={p.transaction_id} className="rounded-xl border border-ink-300/25 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-ink-buyer">{p.property_title ?? 'Property'}</p>
                      <p className="mt-0.5 text-xs text-ink-500">
                        {formatNaira(p.paid_kobo)} of {formatNaira(p.total_kobo)} paid
                      </p>
                    </div>
                    <span className="flex-none rounded-full bg-bone px-2.5 py-0.5 text-xs font-medium text-ink-600">
                      {dealStageLabel(p.stage)}
                    </span>
                  </div>
                  <div className="mt-3 h-2 rounded-full bg-ink-300/25">
                    <div
                      className="h-2 rounded-full bg-emerald-deep"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <p className="mt-1 text-xs text-ink-400">{pct}% completed</p>
                  <div className="mt-3 flex gap-2">
                    <Link
                      href={`/listings/${p.listing_id}`}
                      className="flex-1 rounded-lg bg-emerald-deep px-4 py-2 text-center text-sm font-semibold text-bone transition hover:bg-emerald-accent"
                    >
                      Make Payment
                    </Link>
                    <Link
                      href={`/deals/${p.transaction_id}`}
                      className="flex-1 rounded-lg border border-ink-300/50 px-4 py-2 text-center text-sm font-medium text-ink-700 transition hover:border-ink-500"
                    >
                      View Details
                    </Link>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </section>

      <div className="mt-8">
        <TransactionHistory payments={payments} />
      </div>
    </main>
  );
}
