'use client';

import { useEffect, useState } from 'react';

import type { ActiveLoan, LoanRepayments, RepaymentMilestone } from '@/lib/api';
import { formatDate, formatNaira } from '@/lib/format';

/** Admin active-loans table (SCRUM-77). Each row expands to fetch and show that
 * loan's milestone schedule from the same-origin proxy. The rollup (paid /
 * overdue / totals) comes pre-computed on each row, so the table is useful
 * without expanding. */
export function LoansTable({ items }: { items: ActiveLoan[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-ink-300/30 bg-white">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-ink-300/30 text-left text-xs uppercase tracking-wider text-ink-300">
            <th className="px-5 py-3 font-medium">Loan</th>
            <th className="px-5 py-3 font-medium">Status</th>
            <th className="px-5 py-3 font-medium">Amount</th>
            <th className="px-5 py-3 font-medium">Repaid</th>
            <th className="px-5 py-3 font-medium">Overdue</th>
            <th className="px-5 py-3 font-medium">Next due</th>
            <th className="px-5 py-3 font-medium">Title</th>
          </tr>
        </thead>
        <tbody>
          {items.map((loan) => (
            <LoanRow key={loan.loan_id} loan={loan} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LoanRow({ loan }: { loan: ActiveLoan }) {
  const [open, setOpen] = useState(false);
  const { progress: p } = loan;

  return (
    <>
      <tr
        onClick={() => setOpen((o) => !o)}
        className="cursor-pointer border-b border-ink-300/20 align-top last:border-0 hover:bg-ink-900/[0.02]"
      >
        <td className="px-5 py-4">
          <span className="font-mono text-xs text-ink-900">{loan.loan_id.slice(0, 8)}</span>
          <span className="ml-1 text-ink-300">{open ? '▾' : '▸'}</span>
        </td>
        <td className="px-5 py-4">
          <StatusBadge status={loan.status} />
        </td>
        <td className="whitespace-nowrap px-5 py-4 text-ink-900">
          {formatNaira(loan.requested_amount_kobo)}
        </td>
        <td className="px-5 py-4 text-ink-500">
          {p.paid_count}/{p.milestone_count}
          <span className="ml-1 text-xs text-ink-300">({formatNaira(p.total_paid_kobo)})</span>
        </td>
        <td className="px-5 py-4">
          {p.overdue_count > 0 ? (
            <span className="rounded-full bg-red-50 px-2 py-0.5 text-xs font-semibold text-red-700">
              {p.overdue_count}
            </span>
          ) : (
            <span className="text-ink-300">—</span>
          )}
        </td>
        <td className="whitespace-nowrap px-5 py-4 text-ink-500">
          {p.next_due_date ? formatDate(p.next_due_date) : '—'}
        </td>
        <td className="px-5 py-4">
          {loan.title_released ? (
            <span className="rounded-full bg-emerald-deep/10 px-2 py-0.5 text-xs font-semibold text-emerald-deep">
              Released
            </span>
          ) : (
            <span className="text-ink-300">Held</span>
          )}
        </td>
      </tr>
      {open && (
        <tr className="border-b border-ink-300/20 last:border-0">
          <td colSpan={7} className="bg-ink-900/[0.015] px-5 py-4">
            <MilestoneDetail loanId={loan.loan_id} />
          </td>
        </tr>
      )}
    </>
  );
}

type DetailState =
  | { phase: 'loading' }
  | { phase: 'error'; code: string }
  | { phase: 'ready'; data: LoanRepayments };

function MilestoneDetail({ loanId }: { loanId: string }) {
  const [state, setState] = useState<DetailState>({ phase: 'loading' });

  // Fetch the schedule lazily — this component only mounts when the row opens.
  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const resp = await fetch(`/api/admin/loans/${loanId}/repayments`, { cache: 'no-store' });
        if (!active) return;
        if (!resp.ok) {
          const body = (await resp.json().catch(() => ({}))) as { error?: string };
          if (active) setState({ phase: 'error', code: body.error ?? 'REPAYMENTS_FAILED' });
          return;
        }
        const data = (await resp.json()) as LoanRepayments;
        if (active) setState({ phase: 'ready', data });
      } catch {
        if (active) setState({ phase: 'error', code: 'NETWORK_ERROR' });
      }
    })();
    return () => {
      active = false;
    };
  }, [loanId]);

  if (state.phase === 'loading') {
    return <p className="text-xs text-ink-300">Loading schedule…</p>;
  }
  if (state.phase === 'error') {
    return <p className="text-xs text-red-700">Could not load schedule ({state.code}).</p>;
  }
  if (state.data.milestones.length === 0) {
    return <p className="text-xs text-ink-300">No repayment milestones recorded yet.</p>;
  }

  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-left uppercase tracking-wider text-ink-300">
          <th className="py-2 pr-4 font-medium">Due</th>
          <th className="py-2 pr-4 font-medium">Amount due</th>
          <th className="py-2 pr-4 font-medium">Paid</th>
          <th className="py-2 pr-4 font-medium">Status</th>
          <th className="py-2 pr-4 font-medium">Paid at</th>
        </tr>
      </thead>
      <tbody>
        {state.data.milestones.map((m, i) => (
          <MilestoneRow key={`${m.due_date}-${i}`} milestone={m} />
        ))}
      </tbody>
    </table>
  );
}

function MilestoneRow({ milestone: m }: { milestone: RepaymentMilestone }) {
  return (
    <tr className="border-t border-ink-300/15">
      <td className="py-2 pr-4 text-ink-700">{formatDate(m.due_date)}</td>
      <td className="py-2 pr-4 text-ink-700">{formatNaira(m.amount_due_kobo)}</td>
      <td className="py-2 pr-4 text-ink-700">{formatNaira(m.amount_paid_kobo)}</td>
      <td className="py-2 pr-4">
        {m.is_overdue ? (
          <span className="font-semibold text-red-700">overdue</span>
        ) : (
          <StatusBadge status={m.status} />
        )}
      </td>
      <td className="py-2 pr-4 text-ink-500">{m.paid_at ? formatDate(m.paid_at) : '—'}</td>
    </tr>
  );
}

const STATUS_STYLES: Record<string, string> = {
  approved: 'bg-emerald-deep/10 text-emerald-deep',
  disbursed: 'bg-emerald-deep/10 text-emerald-deep',
  repaying: 'bg-blue-50 text-blue-700',
  fully_repaid: 'bg-emerald-deep/10 text-emerald-deep',
  defaulted: 'bg-red-50 text-red-700',
  paid: 'bg-emerald-deep/10 text-emerald-deep',
  pending: 'bg-ink-900/5 text-ink-500',
};

function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? 'bg-ink-900/5 text-ink-500';
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${style}`}>
      {status.replace(/_/g, ' ')}
    </span>
  );
}
