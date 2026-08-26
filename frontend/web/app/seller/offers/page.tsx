import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { OffersList } from './offers-list';
import type { SellerOffersResponse } from '@/lib/api';
import { transactionServiceUrl } from '@/lib/api';
import { SESSION_LOGIN } from '@/lib/session';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Offers · Maihomme Seller' };

const TIPS = [
  'Respond to offers within 24–48 hours for best results.',
  'Counter offers can help you meet in the middle.',
  'Cash buyers often close faster.',
];

export default async function SellerOffersPage() {
  const result = await sessionBackendGet<SellerOffersResponse>(`${transactionServiceUrl()}/offers`);
  if (!result.ok && result.status === 401) redirect(`${SESSION_LOGIN}?role=seller`);
  const offers = result.ok ? result.data.data : [];

  const count = (s: string) => offers.filter((o) => o.status === s).length;

  return (
    <main className="mx-auto max-w-6xl px-8 py-8">
      <div>
        <h1 className="font-display text-3xl text-emerald-deep">Offers</h1>
        <p className="mt-1 text-sm text-ink-500">Review and respond to buyer offers</p>
      </div>

      <div className="mt-2 grid gap-6 lg:grid-cols-[1fr_300px]">
        <div>
          {!result.ok ? (
            <div className="mt-6 rounded-xl border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
              Could not load your offers. Please retry.
            </div>
          ) : (
            <OffersList offers={offers} />
          )}
        </div>

        <aside className="space-y-4 lg:mt-6">
          <h2 className="font-display text-lg text-ink-900">Offer Summary</h2>
          <SummaryTile n={count('pending')} label="Pending Offers" cls="bg-amber-50 text-amber-700" />
          <SummaryTile n={count('accepted')} label="Accepted Offers" cls="bg-emerald-deep/5 text-emerald-deep" />
          <SummaryTile n={count('countered')} label="Counter Offers" cls="bg-blue-50 text-blue-700" />
          <div className="rounded-2xl bg-bone/70 p-4">
            <p className="text-sm font-medium text-ink-800">Negotiation Tips</p>
            <ul className="mt-2 space-y-1.5 text-xs text-ink-600">
              {TIPS.map((t) => (
                <li key={t} className="flex gap-2">
                  <span className="text-amber-500">•</span> {t}
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </div>
    </main>
  );
}

function SummaryTile({ n, label, cls }: { n: number; label: string; cls: string }) {
  return (
    <div className={`rounded-2xl px-4 py-4 ${cls}`}>
      <p className="text-2xl font-semibold">{n}</p>
      <p className="text-sm">{label}</p>
    </div>
  );
}
