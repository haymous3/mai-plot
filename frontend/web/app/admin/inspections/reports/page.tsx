import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { ReportsTable } from './reports-table';
import { AdminNav } from '../../admin-nav';
import type { ReportReviewFilter, ReportReviewQueueResponse } from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { ADMIN_LOGIN } from '@/lib/auth';
import { backendGet } from '@/lib/server-api';

export const metadata: Metadata = {
  title: 'Inspection report review · Maihomme',
  robots: { index: false, follow: false },
};

const FILTERS: { value: ReportReviewFilter; label: string }[] = [
  { value: 'pending', label: 'Awaiting review' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'all', label: 'All' },
];

function parseFilter(raw: string | undefined): ReportReviewFilter {
  return raw === 'approved' || raw === 'rejected' || raw === 'all' ? raw : 'pending';
}

/** Admin inspection-report review queue (SCRUM-205). Greenfield — /admin had no
 * inspections page at all. Mirrors the document queue (SCRUM-192): the filter
 * is server-rendered links rather than client state, because the queue is a
 * Server Component read and changing a filter is a navigation. */
export default async function ReportQueuePage({
  searchParams,
}: {
  searchParams: { status?: string };
}) {
  const status = parseFilter(searchParams.status);

  const url = new URL(`${realtorServiceUrl()}/admin/inspections/reports/queue`);
  url.searchParams.set('review_status', status);

  const result = await backendGet<ReportReviewQueueResponse>(url.toString());
  if (!result.ok && result.status === 401) redirect(ADMIN_LOGIN);
  const forbidden = !result.ok && result.status === 403;

  return (
    <div className="min-h-screen bg-bone">
      <AdminNav
        active="reports"
        count={result.ok && status === 'pending' ? result.data.data.length : null}
      />

      <main className="mx-auto max-w-6xl px-6 py-12">
        <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Admin</p>
        <h1 className="mt-2 font-display text-3xl text-ink-900">Inspection report review</h1>
        <p className="mt-3 max-w-prose text-sm text-ink-500">
          Approve or reject the reports realtors file after an inspection. A rejection needs a
          reason — it is what the realtor sees, and the only thing telling them what to fix. A
          rejected report can be resubmitted; an approved one is final.
        </p>

        <div className="mt-8">
          <Filter
            label="Status"
            options={FILTERS}
            active={status}
            hrefFor={(value) => `/admin/inspections/reports?status=${value}`}
          />
        </div>

        <div className="mt-6">
          {forbidden ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-6 py-10 text-center text-sm text-amber-800">
              This queue is restricted to administrators.
            </div>
          ) : !result.ok ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
              Could not load the queue ({result.code}). Please retry.
            </div>
          ) : (
            <ReportsTable items={result.data.data} status={status} />
          )}
        </div>
      </main>
    </div>
  );
}

/** Server-rendered filter as links, not client state — same reasoning as the
 * document queue. */
function Filter({
  label,
  options,
  active,
  hrefFor,
}: {
  label: string;
  options: { value: string; label: string }[];
  active: string;
  hrefFor: (value: string) => string;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="text-xs uppercase tracking-wider text-ink-300">{label}</span>
      <div className="flex gap-1 rounded-md bg-ink-900/5 p-0.5">
        {options.map((o) => (
          <a
            key={o.value}
            href={hrefFor(o.value)}
            aria-current={o.value === active ? 'true' : undefined}
            className={`rounded px-3 py-1.5 text-sm transition ${
              o.value === active
                ? 'bg-white font-medium text-ink-900 shadow-sm'
                : 'text-ink-500 hover:text-ink-900'
            }`}
          >
            {o.label}
          </a>
        ))}
      </div>
    </div>
  );
}
