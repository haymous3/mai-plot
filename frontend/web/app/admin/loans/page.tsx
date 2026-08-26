import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { AdminNav } from '../admin-nav';
import { LoansTable } from './loans-table';
import type { ActiveLoansResponse } from '@/lib/api';
import { loanServiceUrl } from '@/lib/api';
import { ADMIN_LOGIN } from '@/lib/auth';
import { backendGet } from '@/lib/server-api';

export const metadata: Metadata = {
  title: 'Active loans · Maihomme',
  robots: { index: false, follow: false },
};

const PAGE_SIZE = 50;

type SearchParams = { page?: string };

export default async function AdminLoansPage({ searchParams }: { searchParams: SearchParams }) {
  const page = Math.max(1, Number(searchParams.page) || 1);
  const offset = (page - 1) * PAGE_SIZE;

  const url = new URL(`${loanServiceUrl()}/admin/loans`);
  url.searchParams.set('limit', String(PAGE_SIZE));
  url.searchParams.set('offset', String(offset));

  const result = await backendGet<ActiveLoansResponse>(url.toString());
  if (!result.ok && result.status === 401) {
    redirect(ADMIN_LOGIN);
  }
  const forbidden = !result.ok && result.status === 403;
  const items = result.ok ? result.data.items : [];

  return (
    <div className="min-h-screen bg-bone">
      <AdminNav active="loans" count={result.ok ? items.length : null} />

      <main className="mx-auto max-w-6xl px-6 py-12">
        <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Loans</p>
        <h1 className="mt-2 font-display text-3xl text-ink-900">Active loans &amp; repayment status</h1>
        <p className="mt-3 max-w-prose text-sm text-ink-500">
          Decided loans and how their repayment is tracking — paid milestones, anything overdue, and
          when the bank releases the title on full repayment. Expand a loan to see its schedule.
        </p>

        <div className="mt-8">
          {forbidden ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-6 py-10 text-center text-sm text-amber-800">
              This view is restricted to admin reviewers.
            </div>
          ) : !result.ok ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
              Could not load loans ({result.code}). Please retry.
            </div>
          ) : items.length === 0 ? (
            <div className="rounded-lg border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center text-sm text-ink-300">
              {page > 1 ? 'No more loans on this page.' : 'No active loans yet.'}
            </div>
          ) : (
            <>
              <LoansTable items={items} />
              <Pagination page={page} count={items.length} pageSize={PAGE_SIZE} />
            </>
          )}
        </div>
      </main>
    </div>
  );
}

/** Offset pager. /admin/loans returns no total, so "Next" is enabled only when a
 * full page came back (there may be more) and "Previous" only past page 1. */
function Pagination({ page, count, pageSize }: { page: number; count: number; pageSize: number }) {
  const hasNext = count === pageSize;
  const hasPrev = page > 1;
  if (!hasNext && !hasPrev) return null;

  return (
    <div className="mt-5 flex items-center justify-between text-sm text-ink-500">
      <span>
        {count} {count === 1 ? 'loan' : 'loans'} · page {page}
      </span>
      <div className="flex gap-2">
        <PageLink href={`/admin/loans?page=${page - 1}`} disabled={!hasPrev}>
          Previous
        </PageLink>
        <PageLink href={`/admin/loans?page=${page + 1}`} disabled={!hasNext}>
          Next
        </PageLink>
      </div>
    </div>
  );
}

function PageLink({
  href,
  disabled,
  children,
}: {
  href: string;
  disabled: boolean;
  children: React.ReactNode;
}) {
  if (disabled) {
    return (
      <span className="cursor-not-allowed rounded-md border border-ink-300/40 px-3 py-1.5 text-ink-300">
        {children}
      </span>
    );
  }
  return (
    <a
      href={href}
      className="rounded-md border border-ink-300/60 px-3 py-1.5 text-ink-700 transition hover:border-ink-500"
    >
      {children}
    </a>
  );
}
