import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { PayoutAccountForm } from '@/app/_components/payout-account-form';
import { readPayoutAccount } from '@/lib/payout-account-server';
import { SESSION_LOGIN } from '@/lib/session';
import { sessionAccessToken } from '@/lib/session-server';

export const metadata: Metadata = { title: 'Payout Account · Maihomme Seller' };

const HOW_IT_WORKS = [
  'When a sale completes and the title transfer is confirmed, your proceeds are released from escrow within 48 hours.',
  'The platform fee is deducted first; you receive the net amount.',
  'Payouts only ever go to the account shown here.',
];

const PROTECTIONS = [
  'We check the account with your bank and show you the name on it before saving.',
  'Adding or changing it needs your password.',
  'We email you every time it changes.',
];

/** Seller payout bank account (SCRUM-223). The layout already gates on a seller
 * session; the redirect here only covers a session that expired mid-render. */
export default async function SellerPayoutsPage() {
  if (!sessionAccessToken()) redirect(`${SESSION_LOGIN}?role=seller`);
  const payout = await readPayoutAccount();

  return (
    <main className="mx-auto max-w-6xl px-8 py-8">
      <div>
        <h1 className="font-display text-3xl text-emerald-deep">Payout Account</h1>
        <p className="mt-1 text-sm text-ink-500">Where your sale proceeds are paid</p>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_300px]">
        <div>
          {payout.status === 'unknown' ? (
            <div className="rounded-xl border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
              We couldn&rsquo;t load your payout account. Please refresh to try again.
            </div>
          ) : (
            <PayoutAccountForm initial={payout.status === 'set' ? payout.account : null} />
          )}
        </div>

        <aside className="space-y-4">
          <RailCard title="How payouts work" items={HOW_IT_WORKS} />
          <RailCard title="How we protect it" items={PROTECTIONS} />
        </aside>
      </div>
    </main>
  );
}

function RailCard({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-2xl border border-line bg-surface-card p-5">
      <h2 className="text-sm font-semibold text-ink-900">{title}</h2>
      <ul className="mt-3 space-y-2.5">
        {items.map((item) => (
          <li key={item} className="flex gap-2.5 text-sm leading-5 text-ink-600">
            <span aria-hidden className="mt-2 h-1.5 w-1.5 flex-none rounded-full bg-emerald-deep" />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
