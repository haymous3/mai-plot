import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import { AdminNav } from '../../admin-nav';
import { QueueTable } from './queue-table';
import type { AdminQueueResponse, AuthorityFilter } from '@/lib/api';
import { listingServiceUrl } from '@/lib/api';
import { ADMIN_LOGIN } from '@/lib/auth';
import { backendGet } from '@/lib/server-api';

export const metadata: Metadata = {
  title: 'Listing review queue · Maiplot',
  robots: { index: false, follow: false },
};

const PAGE_SIZE = 20;

const FILTERS: { label: string; value: AuthorityFilter | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Owner', value: 'owner' },
  { label: 'Power of Attorney', value: 'power_of_attorney' },
];

function parseAuthority(value: string | undefined): AuthorityFilter | null {
  return value === 'owner' || value === 'power_of_attorney' ? value : null;
}

export default async function ListingQueuePage({
  searchParams,
}: {
  searchParams: { authority?: string; page?: string };
}) {
  const authority = parseAuthority(searchParams.authority);
  const page = Math.max(1, Number(searchParams.page) || 1);

  const url = new URL(`${listingServiceUrl()}/admin/listings/queue`);
  url.searchParams.set('status', 'pending_review');
  url.searchParams.set('page', String(page));
  url.searchParams.set('page_size', String(PAGE_SIZE));
  if (authority) url.searchParams.set('authority_type', authority);

  const result = await backendGet<AdminQueueResponse>(url.toString());
  if (!result.ok && result.status === 401) {
    redirect(ADMIN_LOGIN);
  }

  return (
    <div className="min-h-screen bg-bone">
      <AdminNav active="listings" count={result.ok ? result.data.pagination.total : null} />

      <main className="mx-auto max-w-6xl px-6 py-12">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Review</p>
            <h1 className="mt-2 font-display text-3xl text-ink-900">Listing review queue</h1>
          </div>
          {result.ok && (
            <span className="inline-flex items-center gap-2 rounded-full bg-emerald-deep/5 px-3.5 py-1.5 text-sm font-medium text-emerald-deep ring-1 ring-emerald-deep/15">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-accent" />
              {result.data.pagination.total} awaiting review
            </span>
          )}
        </div>

        {/* Authority filter */}
        <nav className="mt-7 flex gap-1.5" aria-label="Filter by seller authority">
          {FILTERS.map((f) => {
            const active = (authority ?? 'all') === f.value;
            const href = f.value === 'all' ? '/admin/listings/queue' : `/admin/listings/queue?authority=${f.value}`;
            return (
              <Link
                key={f.value}
                href={href}
                className={`rounded-md px-3.5 py-1.5 text-sm transition ${
                  active
                    ? 'bg-ink-900 text-bone'
                    : 'text-ink-500 hover:bg-ink-900/5 hover:text-ink-900'
                }`}
              >
                {f.label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-6">
          {!result.ok ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
              Could not load the queue ({result.code}). Please retry.
            </div>
          ) : (
            <QueueTable
              items={result.data.data}
              pagination={result.data.pagination}
              authority={authority}
            />
          )}
        </div>
      </main>
    </div>
  );
}
