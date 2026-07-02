import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { ApplicationWizard } from './application-wizard';
import type { BankPartnersResponse, FinancingSummary } from '@/lib/api';
import { loanServiceUrl, transactionServiceUrl } from '@/lib/api';
import { BUYER_LOGIN } from '@/lib/buyer-auth';
import { buyerBackendGet } from '@/lib/buyer-server-api';

export const metadata: Metadata = {
  title: 'Loan application · Maiplot',
};

type SearchParams = { bank?: string; amount?: string; tenure?: string };

export default async function LoanApplyPage({
  params,
  searchParams,
}: {
  params: { transactionId: string };
  searchParams: SearchParams;
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
  if (!summaryRes.ok || !partnersRes.ok) {
    redirect(`/financing/${params.transactionId}`);
  }

  const summary = summaryRes.data;
  if (summary.existing_loan) redirect(`/loans/${summary.existing_loan.loan_id}`);

  const partners = partnersRes.data.items;
  const bank = partners.find((p) => p.id === searchParams.bank);
  const amount = Number(searchParams.amount);
  const tenure = Number(searchParams.tenure);

  // Missing/invalid selection — send them back to the calculator to choose.
  if (!bank || !Number.isFinite(amount) || amount <= 0 || !Number.isFinite(tenure) || tenure <= 0) {
    redirect(`/financing/${params.transactionId}`);
  }

  return (
    <ApplicationWizard
      transactionId={params.transactionId}
      summary={summary}
      bank={bank}
      amountKobo={amount}
      tenureMonths={tenure}
    />
  );
}
