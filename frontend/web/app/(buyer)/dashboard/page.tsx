import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import type { BuyerLoansResponse } from '@/lib/api';
import { loanServiceUrl } from '@/lib/api';
import { BUYER_LOGIN } from '@/lib/buyer-auth';
import { buyerBackendGet } from '@/lib/buyer-server-api';
import { formatDate, formatNaira, loanStatusLabel } from '@/lib/format';

export const metadata: Metadata = {
  title: 'Dashboard · Maiplot',
};

export default async function BuyerDashboardPage() {
  const result = await buyerBackendGet<BuyerLoansResponse>(`${loanServiceUrl()}/loans/me`);
  if (!result.ok && result.status === 401) redirect(BUYER_LOGIN);

  const loans = result.ok ? result.data.items : [];

  return (
    <main className="mx-auto max-w-4xl px-6 py-12">
      <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Your account</p>
      <h1 className="mt-2 font-display text-3xl text-ink-900">Loan applications</h1>
      <p className="mt-3 max-w-prose text-sm text-ink-500">
        Track the loan applications you&rsquo;ve started. Financing is available from a property
        you have an accepted offer on.
      </p>

      <div className="mt-8">
        {!result.ok ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
            Could not load your applications ({result.code}). Please retry.
          </div>
        ) : loans.length === 0 ? (
          <div className="rounded-lg border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center text-sm text-ink-300">
            You have no loan applications yet.
          </div>
        ) : (
          <ul className="space-y-3">
            {loans.map((loan) => (
              <li key={loan.id}>
                <Link
                  href={`/loans/${loan.id}`}
                  className="flex items-center justify-between rounded-lg border border-ink-300/30 bg-white px-5 py-4 transition hover:border-ink-500/50"
                >
                  <div>
                    <p className="font-medium text-ink-900">
                      {formatNaira(loan.requested_amount_kobo)}
                      {loan.tenure_months ? ` · ${loan.tenure_months} months` : ''}
                    </p>
                    <p className="mt-1 text-xs text-ink-500">
                      Applied {formatDate(loan.created_at)}
                    </p>
                  </div>
                  <span className="rounded-full bg-emerald-deep/10 px-3 py-1 text-xs font-semibold text-emerald-deep">
                    {loanStatusLabel(loan.status)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
