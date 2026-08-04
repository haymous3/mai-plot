import Link from 'next/link';

import type { BuyerLoan } from '@/lib/api';
import { formatNaira } from '@/lib/format';

const STATUS: Record<string, { label: string; cls: string }> = {
  submitted: { label: 'Submitted', cls: 'bg-amber-100 text-amber-700' },
  under_review: { label: 'Under Review', cls: 'bg-amber-100 text-amber-700' },
  info_required: { label: 'Info Required', cls: 'bg-amber-100 text-amber-700' },
  approved: { label: 'Approved', cls: 'bg-emerald-deep/10 text-emerald-deep' },
  disbursed: { label: 'Disbursed', cls: 'bg-emerald-deep/10 text-emerald-deep' },
  repaying: { label: 'Repaying', cls: 'bg-blue-100 text-blue-700' },
  fully_repaid: { label: 'Fully Repaid', cls: 'bg-emerald-deep/10 text-emerald-deep' },
  rejected: { label: 'Rejected', cls: 'bg-red-100 text-red-700' },
  defaulted: { label: 'Defaulted', cls: 'bg-red-100 text-red-700' },
};

/** Loan-status summary for the buyer dashboard sidebar (SCRUM-135). Shows the
 * caller's most recent loan application with a link to its full status page. */
export function LoanStatusCard({ loan }: { loan: BuyerLoan }) {
  const badge = STATUS[loan.status] ?? { label: loan.status, cls: 'bg-ink-300/20 text-ink-600' };
  return (
    <div className="rounded-card border border-line/50 bg-surface-card p-8">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-2 font-semibold text-ink-900">💳 Loan Status</p>
        <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${badge.cls}`}>
          {badge.label}
        </span>
      </div>
      <p className="mt-3 font-display text-xl text-emerald-deep">
        {formatNaira(loan.requested_amount_kobo)}
      </p>
      <p className="text-xs text-ink-500">
        Requested{loan.tenure_months ? ` · ${loan.tenure_months} months` : ''}
      </p>
      <Link
        href={`/loans/${loan.id}`}
        className="mt-4 block rounded-lg border border-emerald-deep/40 px-4 py-2.5 text-center text-sm font-semibold text-emerald-deep transition hover:bg-emerald-deep/5"
      >
        View loan details
      </Link>
    </div>
  );
}
