import Link from 'next/link';

import type { PayoutAccountStatus } from '@/lib/payout-account-server';

/**
 * "Add your payout account" banner (SCRUM-223) for the seller Overview and
 * Transactions pages. Only on a CONFIRMED missing account — an unreadable one
 * renders nothing (see readPayoutAccount). Sale proceeds are released within
 * 48h of title transfer (§8.8) and have nowhere to go without one, so the
 * copy says that plainly rather than as a generic "complete your profile".
 */
export function PayoutNudge({ payout }: { payout: PayoutAccountStatus }) {
  if (payout.status !== 'missing') return null;
  return (
    <div className="mt-6 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4">
      <div className="flex items-start gap-3">
        <span aria-hidden className="text-xl leading-6">
          🏦
        </span>
        <div>
          <p className="text-sm font-semibold text-ink-900">Add your payout bank account</p>
          <p className="mt-0.5 text-sm text-ink-600">
            We can&rsquo;t send your sale proceeds until you do. It takes a minute, and we check the
            account with your bank.
          </p>
        </div>
      </div>
      <Link
        href="/seller/payouts"
        className="rounded-lg bg-emerald-deep px-4 py-2 text-sm font-semibold text-bone transition hover:bg-emerald-accent"
      >
        Add payout account
      </Link>
    </div>
  );
}
