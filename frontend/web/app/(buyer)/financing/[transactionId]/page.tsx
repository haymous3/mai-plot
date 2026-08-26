import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import { FinancingCalculator } from './financing-calculator';
import type { BankPartnersResponse, FinancingSummary } from '@/lib/api';
import { loanServiceUrl, transactionServiceUrl } from '@/lib/api';
import { BUYER_LOGIN } from '@/lib/buyer-auth';
import { buyerBackendGet } from '@/lib/buyer-server-api';

export const metadata: Metadata = {
  title: 'Property financing · Maihomme',
};

export default async function FinancingPage({
  params,
}: {
  params: { transactionId: string };
}) {
  const [summaryRes, partnersRes] = await Promise.all([
    buyerBackendGet<FinancingSummary>(
      `${transactionServiceUrl()}/transactions/${params.transactionId}/financing-summary`,
    ),
    buyerBackendGet<BankPartnersResponse>(`${loanServiceUrl()}/loans/bank-partners`),
  ]);

  if (
    (!summaryRes.ok && summaryRes.status === 401) ||
    (!partnersRes.ok && partnersRes.status === 401)
  ) {
    redirect(BUYER_LOGIN);
  }

  if (!summaryRes.ok) {
    return (
      <ErrorCard>
        {summaryRes.status === 403
          ? 'This financing is only available to the buyer on the deal.'
          : summaryRes.status === 404
            ? 'We could not find this deal.'
            : `Could not load financing (${summaryRes.code}).`}
      </ErrorCard>
    );
  }

  const summary = summaryRes.data;
  const partners = partnersRes.ok ? partnersRes.data.items : [];

  // Already applied — send them to their application status instead.
  if (summary.existing_loan) {
    return (
      <main className="mx-auto max-w-2xl px-11 py-16 text-center">
        <h1 className="font-display text-2xl text-ink-buyer">You&rsquo;ve already applied</h1>
        <p className="mt-3 text-sm text-ink-500">
          You have a loan application in progress for this property.
        </p>
        <Link
          href={`/loans/${summary.existing_loan.loan_id}`}
          className="mt-6 inline-flex rounded-md bg-emerald-deep px-5 py-2.5 text-sm font-medium text-bone transition hover:bg-emerald-accent"
        >
          View application status
        </Link>
      </main>
    );
  }

  return <FinancingCalculator summary={summary} partners={partners} />;
}

function ErrorCard({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-2xl px-11 py-16">
      <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
        {children}
      </div>
    </main>
  );
}
