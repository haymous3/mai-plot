import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { AdminNav } from '../../admin-nav';
import { DocumentsTable } from './documents-table';
import type { DocQueueResponse, DocReviewableStatus, DocSource } from '@/lib/api';
import { documentServiceUrl } from '@/lib/api';
import { ADMIN_LOGIN } from '@/lib/auth';
import { backendGet } from '@/lib/server-api';

export const metadata: Metadata = {
  title: 'Document review queue · Maihomme',
  robots: { index: false, follow: false },
};

const PAGE_SIZE = 20;

function parseSource(raw: string | undefined): DocSource {
  return raw === 'personal' ? 'personal' : 'listing';
}

function parseStatus(raw: string | undefined): DocReviewableStatus {
  return raw === 'under_review' ? 'under_review' : 'pending';
}

export default async function DocumentQueuePage({
  searchParams,
}: {
  searchParams: { page?: string; source?: string; status?: string };
}) {
  const page = Math.max(1, Number(searchParams.page) || 1);
  const source = parseSource(searchParams.source);
  const status = parseStatus(searchParams.status);

  const url = new URL(`${documentServiceUrl()}/admin/documents/queue`);
  url.searchParams.set('source', source);
  url.searchParams.set('status', status);
  url.searchParams.set('page', String(page));
  url.searchParams.set('page_size', String(PAGE_SIZE));

  const result = await backendGet<DocQueueResponse>(url.toString());
  if (!result.ok && result.status === 401) {
    redirect(ADMIN_LOGIN);
  }
  const forbidden = !result.ok && result.status === 403;

  return (
    <div className="min-h-screen bg-bone">
      <AdminNav active="documents" count={result.ok ? result.data.pagination.total : null} />

      <main className="mx-auto max-w-6xl px-6 py-12">
        <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Legal team</p>
        <h1 className="mt-2 font-display text-3xl text-ink-900">Document review</h1>
        <p className="mt-3 max-w-prose text-sm text-ink-500">
          Verify or reject uploaded documents. Property paperwork comes from sellers; personal
          documents are identity and financial records people upload to their own account.
        </p>

        <div className="mt-8 flex flex-wrap items-center gap-6">
          <Filter
            label="Document type"
            options={[
              { value: 'listing', label: 'Property' },
              { value: 'personal', label: 'Personal' },
            ]}
            active={source}
            hrefFor={(value) => `/admin/documents/queue?source=${value}&status=${status}`}
          />
          <Filter
            label="Status"
            options={[
              { value: 'pending', label: 'Awaiting review' },
              { value: 'under_review', label: 'Flagged by OCR' },
            ]}
            active={status}
            hrefFor={(value) => `/admin/documents/queue?source=${source}&status=${value}`}
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
            <DocumentsTable
              items={result.data.data}
              pagination={result.data.pagination}
              source={source}
              status={status}
            />
          )}
        </div>
      </main>
    </div>
  );
}

/** Server-rendered filter as links, not client state — the queue is a Server
 * Component read, so changing a filter is a navigation. */
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
