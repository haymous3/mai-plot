'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import type { LoanDetail } from '@/lib/api';
import { formatDate, formatNaira } from '@/lib/format';
import { bpsToPercent, monthlyPaymentKobo, totalRepaymentKobo } from '@/lib/loan-math';

const POLL_MS = 30_000; // AC: poll status every 30 seconds after submission.
const PENDING = new Set(['submitted', 'under_review', 'info_required']);

function isPending(status: string): boolean {
  return PENDING.has(status);
}

export function LoanStatus({ initial }: { initial: LoanDetail }) {
  const [loan, setLoan] = useState(initial);

  // Poll while the decision is pending; stop once it's terminal.
  useEffect(() => {
    if (!isPending(loan.status)) return;
    let active = true;
    const timer = setInterval(async () => {
      try {
        const resp = await fetch(`/api/buyer/loans/${loan.loan_id}`, { cache: 'no-store' });
        if (!resp.ok) return;
        const next = (await resp.json()) as LoanDetail;
        if (active && next.loan_id) setLoan(next);
      } catch {
        // transient — try again on the next tick
      }
    }, POLL_MS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [loan.status, loan.loan_id]);

  return (
    <div>
      <header className="flex items-center justify-between border-b border-line bg-surface-card px-11 py-4">
        <Link href="/dashboard" className="text-sm text-ink-500 transition hover:text-ink-buyer">
          ⌂ Dashboard
        </Link>
        <h1 className="font-display text-lg text-ink-buyer">Loan Application</h1>
        <span className="w-16" />
      </header>

      <main className="mx-auto max-w-3xl space-y-5 px-11 py-8">
        {isPending(loan.status) ? (
          <PendingView loan={loan} />
        ) : loan.status === 'rejected' ? (
          <RejectedView />
        ) : (
          <ApprovedView loan={loan} />
        )}
      </main>
    </div>
  );
}

function appId(loanId: string): string {
  return `APP-${loanId.replace(/-/g, '').slice(0, 8).toUpperCase()}`;
}

function PendingView({ loan }: { loan: LoanDetail }) {
  const steps: [string, string, 'completed' | 'in_progress' | 'pending'][] = [
    ['Application Received', 'Your application has been successfully submitted', 'completed'],
    ['Document Verification', "We're verifying your uploaded documents", 'in_progress'],
    ['Credit Assessment', 'Credit score and eligibility check', 'pending'],
    ['Bank Approval', `Final review by ${loan.bank_name}`, 'pending'],
  ];
  return (
    <>
      <section className="rounded-card border border-line/50 bg-surface-card px-6 py-10 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-ink-300 text-ink-500" aria-hidden>
          ⏱
        </div>
        <h2 className="mt-4 font-display text-xl text-ink-buyer">Application Under Review</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-ink-500">
          Your loan application has been submitted successfully. We&rsquo;re currently reviewing
          your documents and verifying your information.
        </p>
        <p className="mt-4 text-xs text-ink-500">⏱ Estimated time: 3-5 days</p>
      </section>

      <section className="rounded-card border border-line/50 bg-surface-card p-8">
        <h3 className="font-medium text-ink-buyer">Application Details</h3>
        <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
          <Detail label="Application ID" value={appId(loan.loan_id)} />
          <Detail label="Submitted Date" value={formatDate(loan.created_at)} />
          <Detail label="Loan Amount" value={formatNaira(loan.requested_amount_kobo)} />
          <Detail label="Bank" value={loan.bank_name} />
        </dl>
      </section>

      <section className="rounded-card border border-line/50 bg-surface-card p-8">
        <h3 className="font-medium text-ink-buyer">Review Progress</h3>
        <ul className="mt-4 space-y-4">
          {steps.map(([title, desc, state]) => (
            <li key={title} className="flex items-start justify-between">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 text-ink-500" aria-hidden>
                  {state === 'completed' ? '✓' : state === 'in_progress' ? '↻' : '•'}
                </span>
                <div>
                  <p className="text-sm font-medium text-ink-buyer">{title}</p>
                  <p className="text-xs text-ink-500">{desc}</p>
                </div>
              </div>
              <span className="text-xs text-ink-500">
                {state === 'completed' ? 'Completed' : state === 'in_progress' ? 'In Progress' : 'Pending'}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-xl bg-emerald-deep p-6 text-bone">
        <h3 className="font-medium">What to Expect</h3>
        <ul className="mt-4 space-y-2 text-sm text-bone/80">
          {[
            "You'll receive an email notification when your application status changes",
            'Our team may contact you if additional information is needed',
            'You can check your application status anytime from your dashboard',
            "Once approved, you'll receive details about the next steps",
          ].map((i) => (
            <li key={i} className="flex gap-2">
              <span aria-hidden>✓</span>
              {i}
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}

function ApprovedView({ loan }: { loan: LoanDetail }) {
  const principal = loan.approved_amount_kobo ?? loan.requested_amount_kobo;
  const rate = loan.interest_rate_bps ?? 0;
  const tenure = loan.tenure_months ?? 0;
  const monthly =
    loan.monthly_instalment_kobo ?? (tenure ? monthlyPaymentKobo(principal, rate, tenure) : 0);
  const total = tenure ? monthly * tenure : totalRepaymentKobo(principal, rate, tenure);

  const decisionDate = loan.bank_decision_at ?? loan.created_at;
  const firstPayment = new Date(decisionDate);
  firstPayment.setMonth(firstPayment.getMonth() + 1);

  const steps: [string, string][] = [];
  if (loan.requires_account_opening && !loan.bank_account_opened) {
    steps.push([
      `Open Account with ${loan.bank_name}`,
      "You'll need to open a savings account for loan disbursement",
    ]);
  }
  steps.push(['Sign Loan Agreement', 'Review and sign the loan agreement documents']);
  steps.push(['Fund Disbursement', 'Funds will be transferred directly to the property seller']);

  return (
    <>
      <section className="rounded-card border border-line/50 bg-surface-card px-6 py-10 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full text-2xl text-emerald-deep" aria-hidden>
          ✓
        </div>
        <h2 className="mt-3 font-display text-xl text-ink-buyer">Loan Approved!</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-ink-500">
          Congratulations! Your loan application has been approved by {loan.bank_name}. You can now
          proceed to the next steps.
        </p>
        {loan.bank_decision_at && (
          <p className="mt-4 text-xs text-ink-500">✓ Approved on {formatDate(loan.bank_decision_at)}</p>
        )}
      </section>

      <section className="rounded-card border border-line/50 bg-surface-card p-8">
        <h3 className="font-medium text-ink-buyer">Loan Details</h3>
        <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
          <Detail label="Approved Amount" value={formatNaira(principal)} strong />
          <Detail label="Interest Rate" value={`${bpsToPercent(rate)} per annum`} />
          <Detail label="Monthly Payment" value={formatNaira(monthly)} />
          <Detail label="Loan Tenure" value={`${tenure} months`} />
          <Detail label="Total Repayment" value={formatNaira(total)} />
          <Detail label="First Payment Date" value={formatDate(firstPayment.toISOString())} />
        </dl>
      </section>

      <section className="rounded-card border border-line/50 bg-surface-card p-8">
        <h3 className="font-medium text-ink-buyer">Next Steps</h3>
        <ol className="mt-4 space-y-4">
          {steps.map(([title, desc], i) => (
            <li key={title} className="flex gap-3">
              <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-bone text-xs font-semibold text-ink-700">
                {i + 1}
              </span>
              <div>
                <p className="text-sm font-medium text-ink-buyer">{title}</p>
                <p className="text-xs text-ink-500">{desc}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}

function RejectedView() {
  return (
    <section className="rounded-card border border-line/50 bg-surface-card px-6 py-10 text-center">
      <h2 className="font-display text-xl text-ink-buyer">Application Not Approved</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-ink-500">
        Unfortunately your loan application was not approved this time. Our team will reach out with
        next steps, or you can contact support for more information.
      </p>
      <Link
        href="/dashboard"
        className="mt-6 inline-flex rounded-md border border-ink-300/60 px-5 py-2.5 text-sm font-medium text-ink-700 transition hover:border-ink-500"
      >
        Back to dashboard
      </Link>
    </section>
  );
}

function Detail({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div>
      <dt className="text-xs text-ink-500">{label}</dt>
      <dd className={`mt-0.5 text-ink-buyer ${strong ? 'font-display text-lg' : 'font-medium'}`}>
        {value}
      </dd>
    </div>
  );
}
