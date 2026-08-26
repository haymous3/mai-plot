import type { Metadata } from 'next';

import { RealtorHeader } from '../realtor-header';
import type { CommissionHistoryItem, CommissionHistoryResponse, CommissionSummary } from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { formatDate, formatNaira } from '@/lib/format';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Earnings · Maihomme Realtor' };

const STATUS_META: Record<string, { label: string; pill: string }> = {
  pending: { label: 'Pending', pill: 'bg-amber-100 text-amber-700' },
  available: { label: 'Available', pill: 'bg-blue-100 text-blue-700' },
  withdrawn: { label: 'Paid', pill: 'bg-emerald-deep/10 text-emerald-deep' },
};

/** Realtor Earnings (SCRUM-140, PR5). Balance tiles from the commission summary
 * + a transaction history table from the per-commission list. Commission is 2%
 * of the deal value, accrued on completed deals (SCRUM-74); no money moves here
 * — this is read-only. */
export default async function RealtorEarningsPage() {
  const [summaryRes, historyRes] = await Promise.all([
    sessionBackendGet<CommissionSummary>(`${realtorServiceUrl()}/realtors/me/commission`),
    sessionBackendGet<CommissionHistoryResponse>(`${realtorServiceUrl()}/realtors/me/commissions`),
  ]);

  const summary = summaryRes.ok ? summaryRes.data : null;
  const history = historyRes.ok ? historyRes.data.data : [];
  const total = summary
    ? summary.pending_kobo + summary.available_kobo + summary.withdrawn_kobo
    : 0;

  return (
    <main className="mx-auto max-w-4xl px-8 py-8">
      <RealtorHeader title="Earnings" subtitle="Your commission balance and payout history" />

      {!summaryRes.ok ? (
        <div className="mt-8 rounded-xl border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
          Could not load your earnings. Please retry.
        </div>
      ) : (
        <>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Tile icon="💰" value={formatNaira(total)} label="Total Earned" />
            <Tile
              icon="✅"
              value={formatNaira(summary?.available_kobo ?? 0)}
              label="Available"
              accent
            />
            <Tile icon="⏳" value={formatNaira(summary?.pending_kobo ?? 0)} label="Pending" />
            <Tile icon="🏦" value={formatNaira(summary?.withdrawn_kobo ?? 0)} label="Paid Out" />
          </div>

          <div className="mt-4 rounded-xl border border-emerald-deep/15 bg-emerald-deep/5 px-4 py-3 text-xs text-ink-700">
            Commission is 2% of each completed deal&apos;s value, held for 3 business days before it
            becomes available. Payouts are made by our team once available.
          </div>

          <section className="mt-6 rounded-card-sm border border-line bg-surface-card p-6">
            <h2 className="font-display text-lg text-ink-900">Transaction History</h2>
            {history.length === 0 ? (
              <p className="py-8 text-center text-sm text-ink-500">
                No commissions yet. You earn 2% once a deal you inspected completes.
              </p>
            ) : (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[560px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-line text-xs text-ink-500">
                      <th className="pb-2 pr-4 font-medium">Property</th>
                      <th className="pb-2 pr-4 font-medium">Date</th>
                      <th className="pb-2 pr-4 font-medium">Rate</th>
                      <th className="pb-2 pr-4 font-medium">Amount</th>
                      <th className="pb-2 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {history.map((c) => (
                      <Row key={c.commission_id} c={c} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </main>
  );
}

function Row({ c }: { c: CommissionHistoryItem }) {
  const meta = STATUS_META[c.status] ?? { label: c.status, pill: 'bg-ink-300/20 text-ink-500' };
  return (
    <tr>
      <td className="py-3 pr-4 text-ink-900">{c.property_title ?? 'Property deal'}</td>
      <td className="py-3 pr-4 text-ink-600">{formatDate(c.created_at)}</td>
      <td className="py-3 pr-4 text-ink-600">{(c.rate_bps / 100).toFixed(0)}%</td>
      <td className="py-3 pr-4 font-medium text-ink-900">{formatNaira(c.amount_kobo)}</td>
      <td className="py-3">
        <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${meta.pill}`}>
          {meta.label}
        </span>
      </td>
    </tr>
  );
}

function Tile({
  icon,
  value,
  label,
  accent = false,
}: {
  icon: string;
  value: string;
  label: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`rounded-2xl border p-5 ${
        accent ? 'border-emerald-deep/30 bg-emerald-deep/5' : 'border-ink-300/25 bg-white'
      }`}
    >
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-bone text-lg">
        {icon}
      </span>
      <p className="mt-3 font-display text-2xl text-ink-900">{value}</p>
      <p className="text-sm text-ink-600">{label}</p>
    </div>
  );
}
