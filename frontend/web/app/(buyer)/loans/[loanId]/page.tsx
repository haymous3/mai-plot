import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { LoanStatus } from './loan-status';
import type { LoanDetail } from '@/lib/api';
import { loanServiceUrl } from '@/lib/api';
import { BUYER_LOGIN } from '@/lib/buyer-auth';
import { buyerBackendGet } from '@/lib/buyer-server-api';

export const metadata: Metadata = {
  title: 'Loan status · Maihomme',
};

export default async function LoanStatusPage({ params }: { params: { loanId: string } }) {
  const result = await buyerBackendGet<LoanDetail>(`${loanServiceUrl()}/loans/${params.loanId}`);
  if (!result.ok && result.status === 401) redirect(BUYER_LOGIN);

  if (!result.ok) {
    return (
      <main className="mx-auto max-w-2xl px-11 py-16">
        <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
          {result.status === 404
            ? 'We could not find this loan application.'
            : result.status === 403
              ? 'You can only view your own loan applications.'
              : `Could not load this application (${result.code}).`}
        </div>
      </main>
    );
  }

  return <LoanStatus initial={result.data} />;
}
