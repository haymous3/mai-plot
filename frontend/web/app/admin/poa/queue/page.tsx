import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { AdminNav } from '../../admin-nav';
import { PoaTable } from './poa-table';
import type { PoaQueueResponse } from '@/lib/api';
import { authServiceUrl } from '@/lib/api';
import { ADMIN_LOGIN } from '@/lib/auth';
import { backendGet } from '@/lib/server-api';

export const metadata: Metadata = {
  title: 'PoA review queue · Maiplot',
  robots: { index: false, follow: false },
};

const PAGE_SIZE = 20;

export default async function PoaQueuePage({
  searchParams,
}: {
  searchParams: { page?: string };
}) {
  const page = Math.max(1, Number(searchParams.page) || 1);

  const url = new URL(`${authServiceUrl()}/admin/poa/queue`);
  url.searchParams.set('page', String(page));
  url.searchParams.set('page_size', String(PAGE_SIZE));

  const result = await backendGet<PoaQueueResponse>(url.toString());
  if (!result.ok && result.status === 401) {
    redirect(ADMIN_LOGIN);
  }
  const forbidden = !result.ok && result.status === 403;

  return (
    <div className="min-h-screen bg-bone">
      <AdminNav active="poa" count={result.ok ? result.data.pagination.total : null} />

      <main className="mx-auto max-w-6xl px-6 py-12">
        <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Legal team</p>
        <h1 className="mt-2 font-display text-3xl text-ink-900">
          Power-of-Attorney review
        </h1>
        <p className="mt-3 max-w-prose text-sm text-ink-500">
          Verify each Power-of-Attorney document before the seller can publish. Submissions carry a
          48-hour review SLA.
        </p>

        <div className="mt-8">
          {forbidden ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-6 py-10 text-center text-sm text-amber-800">
              This queue is restricted to the legal team.
            </div>
          ) : !result.ok ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
              Could not load the queue ({result.code}). Please retry.
            </div>
          ) : (
            <PoaTable items={result.data.items} pagination={result.data.pagination} />
          )}
        </div>
      </main>
    </div>
  );
}
