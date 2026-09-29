import Link from 'next/link';

import type { PayoutAccountStatus } from '@/lib/payout-account-server';

/**
 * "Add your payout bank account" banner (SCRUM-223) — seller Overview and
 * Transactions, realtor Earnings. Only on a CONFIRMED missing account; an
 * unreadable one renders nothing (see readPayoutAccount), because telling
 * someone to add details they already gave sends them to re-enter them.
 *
 * `consequence` is the role's own sentence about what cannot happen without it
 * — sale proceeds for a seller, commission for a realtor — so the banner says
 * plainly why it matters rather than "complete your profile".
 */
export function PayoutNudge({
  payout,
  href,
  consequence,
}: {
  payout: PayoutAccountStatus;
  href: string;
  consequence: string;
}) {
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
            {consequence} It takes a minute, and we check the account with your bank.
          </p>
        </div>
      </div>
      <Link
        href={href}
        className="rounded-lg bg-emerald-deep px-4 py-2 text-sm font-semibold text-bone transition hover:bg-emerald-accent"
      >
        Add payout account
      </Link>
    </div>
  );
}
