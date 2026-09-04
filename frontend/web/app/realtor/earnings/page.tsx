import type { Metadata } from 'next';
import Link from 'next/link';

import { TransactionHistory } from './transaction-history';
import {
  ArrowLeftIcon,
  CheckCircleIcon,
  ClockIcon,
  TrendingUpIcon,
  WalletIcon,
} from '../_icons';
import type {
  CommissionHistoryResponse,
  CommissionSummary,
  RealtorInspectionsResponse,
} from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { formatNaira } from '@/lib/format';
import { commissionRateLabel, earningsBalances } from '@/lib/realtor-earnings';
import { countInspections } from '@/lib/realtor-inspection';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Earnings · Maihomme Realtor' };

const PAYMENT_INFORMATION = [
  'Commission accrues when a deal you inspected completes',
  'It is held for 3 business days, then becomes available for payout',
  'Payouts are made by bank transfer to your registered account',
];

/** Realtor Earnings (SCRUM-140, redesigned in SCRUM-204 from Figma 287:2).
 * Read-only — no money moves here.
 *
 * ⚠️ The design is drawn against a fixed ₦50,000-per-inspection fee. The
 * shipped model is 2% of each completed deal held for 3 business days
 * (CLAUDE.md §8 rule 7). Product owner's call: keep the real model, take the
 * design's visual treatment. The copy therefore describes what happens, not
 * what the artboard says. */
export default async function RealtorEarningsPage() {
  const [summaryRes, historyRes, inspRes] = await Promise.all([
    sessionBackendGet<CommissionSummary>(`${realtorServiceUrl()}/realtors/me/commission`),
    sessionBackendGet<CommissionHistoryResponse>(`${realtorServiceUrl()}/realtors/me/commissions`),
    sessionBackendGet<RealtorInspectionsResponse>(`${realtorServiceUrl()}/inspections/mine`),
  ]);

  const summary = summaryRes.ok ? summaryRes.data : null;
  const history = historyRes.ok ? historyRes.data.data : [];
  const completed = inspRes.ok ? countInspections(inspRes.data.data).completed : 0;
  const balances = earningsBalances(summary, history);

  return (
    <main className="mx-auto max-w-[1088px] px-8 py-8">
      <Link
        href="/realtor"
        className="inline-flex items-center gap-2 text-sm font-medium text-ink-600 transition hover:text-ink-900"
      >
        <ArrowLeftIcon className="h-4 w-4" />
        Back to Dashboard
      </Link>
      <h1 className="mt-3 text-3xl font-bold leading-9 text-ink-900">Earnings</h1>
      <p className="mt-2 text-base leading-6 text-ink-600">
        Track your commission payments and transaction history
      </p>

      {!summaryRes.ok ? (
        <div className="mt-8 rounded-card-sm border border-status-danger/30 bg-distress-50 px-6 py-10 text-center text-sm text-distress-700">
          Could not load your earnings. Please retry.
        </div>
      ) : (
        <>
          <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_260px_260px]">
            <div
              className="rounded-card-sm p-6"
              style={{ backgroundImage: 'linear-gradient(165deg, #0f3d2e 0%, #0a2d21 100%)' }}
            >
              <p className="flex items-center gap-2 text-sm leading-5 text-white/90">
                <WalletIcon className="h-6 w-6 flex-none" />
                Total Earnings
              </p>
              <p className="mt-2 text-4xl font-bold leading-10 text-white">
                {formatNaira(balances.totalKobo)}
              </p>
              <p className="mt-3 flex items-center gap-2 text-sm leading-5 text-white/90">
                <TrendingUpIcon className="h-4 w-4 flex-none" />
                {completed} inspection{completed === 1 ? '' : 's'} completed
              </p>
            </div>

            <BalanceCard
              tone="done"
              label="Paid"
              value={formatNaira(balances.paidKobo)}
              sub={`${balances.paidCount} payment${balances.paidCount === 1 ? '' : 's'}`}
            />
            <BalanceCard
              tone="pending"
              label="Pending"
              value={formatNaira(balances.outstandingKobo)}
              sub={
                balances.availableKobo > 0
                  ? `${formatNaira(balances.availableKobo)} ready for payout`
                  : `${balances.outstandingCount} awaiting payout`
              }
            />
          </div>

          <section className="mt-6 flex gap-4 rounded-card-sm border border-status-gold/20 bg-surface-warm p-6">
            <span className="flex h-12 w-12 flex-none items-center justify-center rounded-[10px] bg-status-gold/20">
              <WalletIcon className="h-6 w-6 text-status-gold" />
            </span>
            <div>
              <h2 className="text-lg font-bold text-ink-900">Commission Per Deal</h2>
              <p className="mt-2 text-3xl font-bold leading-9 text-emerald-deep">
                {commissionRateLabel(history)}
              </p>
              <p className="mt-2 text-sm leading-5 text-ink-600">
                You earn a percentage of each completed deal you inspected. Commission is held for
                3 business days after the deal closes, then becomes available for payout.
              </p>
            </div>
          </section>

          <TransactionHistory items={history} />

          <section className="mt-6 rounded-card-sm border border-scheduled-200 bg-scheduled-50 p-6">
            <h2 className="text-sm font-semibold text-scheduled-900">Payment Information</h2>
            <ul className="mt-3 space-y-2">
              {PAYMENT_INFORMATION.map((line) => (
                <li key={line} className="flex items-start gap-2 text-sm text-scheduled-800">
                  <CheckCircleIcon className="mt-0.5 h-4 w-4 flex-none" strokeWidth={2} />
                  {line}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </main>
  );
}

/** Balance card beside the hero (Figma 287:26 / 287:37): 144px tall, 14px
 * radius, a tinted 20px glyph beside the label. */
function BalanceCard({
  tone,
  label,
  value,
  sub,
}: {
  tone: 'done' | 'pending';
  label: string;
  value: string;
  sub: string;
}) {
  const Icon = tone === 'done' ? CheckCircleIcon : ClockIcon;
  return (
    <div className="rounded-card-sm border border-line bg-surface-card p-6">
      <p className="flex items-center gap-2 text-sm leading-5 text-ink-600">
        <Icon className={`h-5 w-5 flex-none ${tone === 'done' ? 'text-done-700' : 'text-pending-700'}`} />
        {label}
      </p>
      <p className="mt-2 text-2xl font-bold leading-8 text-ink-900">{value}</p>
      <p className="mt-2 text-xs leading-4 text-ink-500">{sub}</p>
    </div>
  );
}
