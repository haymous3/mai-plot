import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import { AdminNav } from '../admin-nav';
import { AuditFilters } from './audit-filters';
import type { AuditLogEntry, AuditLogListResponse } from '@/lib/api';
import { analyticsServiceUrl } from '@/lib/api';
import { ADMIN_LOGIN } from '@/lib/auth';
import { formatDateTime } from '@/lib/format';
import { backendGet } from '@/lib/server-api';

export const metadata: Metadata = {
  title: 'Audit log · Maihomme',
  robots: { index: false, follow: false },
};

const PAGE_SIZE = 50;

type SearchParams = {
  entity_type?: string;
  action?: string;
  actor_id?: string;
  date_from?: string;
  date_to?: string;
  page?: string;
};

export default async function AuditLogPage({ searchParams }: { searchParams: SearchParams }) {
  const page = Math.max(1, Number(searchParams.page) || 1);

  const url = new URL(`${analyticsServiceUrl()}/admin/analytics/audit-log`);
  url.searchParams.set('page', String(page));
  url.searchParams.set('page_size', String(PAGE_SIZE));
  if (searchParams.entity_type) url.searchParams.set('entity_type', searchParams.entity_type);
  if (searchParams.action) url.searchParams.set('action', searchParams.action);
  if (searchParams.actor_id) url.searchParams.set('actor_id', searchParams.actor_id);
  if (searchParams.date_from) url.searchParams.set('date_from', searchParams.date_from);
  // Make the "to" day inclusive (end-of-day) rather than midnight.
  if (searchParams.date_to) url.searchParams.set('date_to', `${searchParams.date_to}T23:59:59`);

  const result = await backendGet<AuditLogListResponse>(url.toString());
  if (!result.ok && result.status === 401) {
    redirect(ADMIN_LOGIN);
  }

  const current = {
    entity_type: searchParams.entity_type ?? '',
    action: searchParams.action ?? '',
    actor_id: searchParams.actor_id ?? '',
    date_from: searchParams.date_from ?? '',
    date_to: searchParams.date_to ?? '',
  };

  return (
    <div className="min-h-screen bg-bone">
      <AdminNav active="audit" count={null} />

      <main className="mx-auto max-w-6xl px-6 py-12">
        <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Analytics</p>
        <h1 className="mt-2 font-display text-3xl text-ink-900">Audit log</h1>
        <p className="mt-3 max-w-prose text-sm text-ink-500">
          Every state change on transactions, listings, documents, and realtors — newest first.
          Filter by entity, action, actor, or date.
        </p>

        <div className="mt-8">
          <AuditFilters current={current} />

          {!result.ok ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
              Could not load the audit log ({result.code}). Please retry.
            </div>
          ) : result.data.items.length === 0 ? (
            <div className="rounded-lg border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center text-sm text-ink-300">
              No audit entries match these filters.
            </div>
          ) : (
            <>
              <AuditTable items={result.data.items} />
              <Pagination
                page={result.data.pagination.page}
                totalPages={result.data.pagination.total_pages}
                total={result.data.pagination.total}
                params={searchParams}
              />
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function short(id: string | null): string {
  return id ? id.slice(0, 8) : '—';
}

function AuditTable({ items }: { items: AuditLogEntry[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-ink-300/30 bg-white">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-ink-300/30 text-left text-xs uppercase tracking-wider text-ink-300">
            <th className="px-5 py-3 font-medium">Time (UTC)</th>
            <th className="px-5 py-3 font-medium">Actor</th>
            <th className="px-5 py-3 font-medium">Action</th>
            <th className="px-5 py-3 font-medium">Entity</th>
            <th className="px-5 py-3 font-medium">IP</th>
            <th className="px-5 py-3 font-medium">Changes</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className="border-b border-ink-300/20 align-top last:border-0">
              <td className="whitespace-nowrap px-5 py-4 text-ink-500">
                {formatDateTime(item.created_at)}
              </td>
              <td className="px-5 py-4">
                <span className="text-ink-900">{item.actor_role ?? '—'}</span>
                {item.actor_id && (
                  <span className="ml-1 font-mono text-xs text-ink-300">{short(item.actor_id)}</span>
                )}
              </td>
              <td className="px-5 py-4">
                <span className="rounded bg-ink-900/5 px-1.5 py-0.5 font-mono text-xs text-ink-900">
                  {item.action}
                </span>
              </td>
              <td className="px-5 py-4 text-ink-500">
                {item.entity_type}
                <span className="ml-1 font-mono text-xs text-ink-300">{short(item.entity_id)}</span>
              </td>
              <td className="px-5 py-4 font-mono text-xs text-ink-500">{item.ip_address ?? '—'}</td>
              <td className="px-5 py-4">
                {item.old_value || item.new_value ? (
                  <details className="text-xs">
                    <summary className="cursor-pointer text-emerald-deep">view</summary>
                    <pre className="mt-2 max-w-md overflow-x-auto whitespace-pre-wrap rounded bg-ink-900/[0.03] p-2 text-ink-700">
                      {JSON.stringify({ old: item.old_value, new: item.new_value }, null, 2)}
                    </pre>
                  </details>
                ) : (
                  <span className="text-ink-300">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Pagination({
  page,
  totalPages,
  total,
  params,
}: {
  page: number;
  totalPages: number;
  total: number;
  params: SearchParams;
}) {
  function hrefFor(target: number): string {
    const qs = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (key !== 'page' && value) qs.set(key, value);
    }
    qs.set('page', String(target));
    return `/admin/audit?${qs.toString()}`;
  }

  return (
    <div className="mt-5 flex items-center justify-between text-sm text-ink-500">
      <span>
        {total} {total === 1 ? 'entry' : 'entries'}
        {totalPages > 1 ? ` · page ${page} of ${totalPages}` : ''}
      </span>
      {totalPages > 1 && (
        <div className="flex gap-2">
          <PageLink href={hrefFor(page - 1)} disabled={page <= 1}>
            Previous
          </PageLink>
          <PageLink href={hrefFor(page + 1)} disabled={page >= totalPages}>
            Next
          </PageLink>
        </div>
      )}
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
    <Link
      href={href}
      className="rounded-md border border-ink-300/60 px-3 py-1.5 text-ink-700 transition hover:border-ink-500"
    >
      {children}
    </Link>
  );
}
