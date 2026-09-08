import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import { AdminNav } from '../admin-nav';
import type { AdminListingsResponse } from '@/lib/api';
import { listingServiceUrl } from '@/lib/api';
import { ADMIN_LOGIN } from '@/lib/auth';
import { formatDate, formatNaira } from '@/lib/format';
import { backendGet } from '@/lib/server-api';

export const metadata: Metadata = {
  title: 'Listings · Maihomme admin',
  robots: { index: false, follow: false },
};

type SearchParams = { status?: string; authority?: string; search?: string; page?: string };

// Every status the listing table allows. "All" is the absence of a filter, which
// is the default here on purpose — pinning this page to one status is exactly
// what made the review queue unable to answer "show me this property".
const STATUS_TABS = [
  { key: '', label: 'All' },
  { key: 'pending_review', label: 'Pending review' },
  { key: 'active', label: 'Active' },
  { key: 'under_offer', label: 'Under offer' },
  { key: 'paused', label: 'Paused' },
  { key: 'sold', label: 'Sold' },
  { key: 'expired', label: 'Expired' },
  { key: 'rejected', label: 'Rejected' },
] as const;

// Widened to Set<string> deliberately: the values come off a URL, so the check
// is what narrows them — a Set of the literal union cannot be asked about an
// arbitrary string.
const STATUSES = new Set<string>(STATUS_TABS.map((t) => t.key).filter(Boolean));

const PAGE_SIZE = 25;

function href(params: SearchParams): string {
  const q = new URLSearchParams();
  if (params.status) q.set('status', params.status);
  if (params.authority) q.set('authority', params.authority);
  if (params.search) q.set('search', params.search);
  if (params.page && params.page !== '1') q.set('page', params.page);
  const qs = q.toString();
  return qs ? `/admin/listings?${qs}` : '/admin/listings';
}

/**
 * The admin listing console (SCRUM-215).
 *
 * Before this, the only admin listing surface was the review queue, pinned to
 * `status=pending_review`. The moment an admin approved a listing it left the
 * only screen that ever showed it — on staging, 13 of 14 listings were
 * unreachable from the admin side entirely.
 *
 * Filters and search are server-rendered LINKS, not client state, matching the
 * user console and every queue: changing a filter is a navigation, so a support
 * conversation can be resumed from a URL.
 */
export default async function AdminListingsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const status =
    searchParams.status && STATUSES.has(searchParams.status) ? searchParams.status : undefined;
  const authority =
    searchParams.authority === 'owner' || searchParams.authority === 'power_of_attorney'
      ? searchParams.authority
      : undefined;
  // The API rejects a 1-character search, so the page drops it rather than
  // rendering a 422 at somebody who is still typing.
  const rawSearch = (searchParams.search ?? '').trim();
  const search = rawSearch.length >= 2 ? rawSearch : undefined;
  const page = Math.max(1, Number(searchParams.page ?? '1') || 1);

  const url = new URL(`${listingServiceUrl()}/admin/listings`);
  if (status) url.searchParams.set('status', status);
  if (authority) url.searchParams.set('authority_type', authority);
  if (search) url.searchParams.set('search', search);
  url.searchParams.set('page', String(page));
  url.searchParams.set('page_size', String(PAGE_SIZE));

  const result = await backendGet<AdminListingsResponse>(url.toString());
  if (!result.ok && result.status === 401) redirect(ADMIN_LOGIN);
  const forbidden = !result.ok && result.status === 403;

  const items = result.ok ? result.data.data : [];
  const pagination = result.ok ? result.data.pagination : null;

  return (
    <div className="min-h-screen bg-bone">
      <AdminNav active="listings" count={pagination ? pagination.total : null} />

      <main className="mx-auto max-w-6xl px-6 py-12">
        <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Admin</p>
        <h1 className="mt-2 font-display text-3xl text-ink-900">Listings</h1>
        <p className="mt-3 max-w-prose text-sm text-ink-500">
          Every property on the platform, in any status. Listings still waiting on a first decision
          are handled in the{' '}
          <Link href="/admin/listings/queue" className="underline">
            review queue
          </Link>
          .
        </p>

        <form method="get" className="mt-8 flex max-w-md gap-2">
          {status && <input type="hidden" name="status" value={status} />}
          {authority && <input type="hidden" name="authority" value={authority} />}
          <label className="sr-only" htmlFor="search">
            Search listings by title or address
          </label>
          <input
            id="search"
            name="search"
            defaultValue={rawSearch}
            placeholder="Title or address"
            className="flex-1 rounded-md border border-ink-300/60 bg-white px-3 py-2 text-sm text-ink-900 outline-none focus:border-emerald-accent"
          />
          <button
            type="submit"
            className="rounded-md border border-ink-300/60 px-4 py-2 text-sm font-medium text-ink-900 transition hover:bg-white"
          >
            Search
          </button>
        </form>

        <nav className="mt-6 flex flex-wrap gap-1.5" aria-label="Filter by status">
          {STATUS_TABS.map((tab) => {
            const isActive = (status ?? '') === tab.key;
            return (
              <Link
                key={tab.key || 'all'}
                href={href({ status: tab.key, authority, search: rawSearch })}
                aria-current={isActive ? 'page' : undefined}
                className={
                  isActive
                    ? 'rounded-full bg-emerald-deep px-3.5 py-1.5 text-xs font-medium text-bone'
                    : 'rounded-full border border-ink-300/60 px-3.5 py-1.5 text-xs font-medium text-ink-700 transition hover:bg-white'
                }
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>

        <nav className="mt-2 flex flex-wrap gap-1.5" aria-label="Filter by seller authority">
          {[
            { key: '', label: 'Any seller' },
            { key: 'owner', label: 'Owner' },
            { key: 'power_of_attorney', label: 'Power of Attorney' },
          ].map((tab) => {
            const isActive = (authority ?? '') === tab.key;
            return (
              <Link
                key={tab.key || 'any'}
                href={href({ status, authority: tab.key, search: rawSearch })}
                aria-current={isActive ? 'page' : undefined}
                className={
                  isActive
                    ? 'rounded-full bg-ink-700 px-3.5 py-1.5 text-xs font-medium text-bone'
                    : 'rounded-full border border-ink-300/60 px-3.5 py-1.5 text-xs font-medium text-ink-700 transition hover:bg-white'
                }
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-8">
          {forbidden ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-6 py-10 text-center text-sm text-amber-800">
              This console is restricted to admin reviewers.
            </div>
          ) : !result.ok ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
              Could not load listings ({result.code}). Please retry.
            </div>
          ) : items.length === 0 ? (
            <div className="rounded-lg border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center text-sm text-ink-300">
              {search ? `No listings match “${search}”.` : 'No listings match these filters.'}
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-ink-300/30 bg-white">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-ink-300/30 text-left text-xs uppercase tracking-wider text-ink-300">
                    <th className="px-5 py-3 font-medium">Property</th>
                    <th className="px-5 py-3 font-medium">Status</th>
                    <th className="px-5 py-3 font-medium">Price</th>
                    <th className="px-5 py-3 font-medium">Documents</th>
                    <th className="px-5 py-3 font-medium">Listed</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.id} className="border-b border-ink-300/20 align-top last:border-0">
                      <td className="px-5 py-4">
                        <div className="flex gap-3">
                          {/* A plain <img>: these are CDN URLs from a service that
                              can point anywhere, and next/image needs each host
                              configured up front. */}
                          {item.cover_photo_url ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              src={item.cover_photo_url}
                              alt=""
                              className="h-12 w-16 shrink-0 rounded object-cover"
                            />
                          ) : (
                            <div className="flex h-12 w-16 shrink-0 items-center justify-center rounded bg-bone text-[10px] text-ink-300">
                              No photo
                            </div>
                          )}
                          <div>
                            <Link
                              href={`/admin/listings/${item.id}`}
                              className="font-medium text-ink-900 underline-offset-2 hover:underline"
                            >
                              {item.title}
                            </Link>
                            <p className="mt-0.5 text-xs text-ink-500">
                              {[item.lga, item.state].filter(Boolean).join(', ')} ·{' '}
                              {item.property_type}
                            </p>
                            {item.seller_authority_type === 'power_of_attorney' && (
                              <p className="mt-0.5 text-xs text-amber-700">Power of Attorney</p>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <StatusPill status={item.status} />
                        {item.sale_type === 'distress' && (
                          <p className="mt-1 text-xs text-ink-500">
                            Distress{item.urgency_tag ? ` · ${item.urgency_tag.replace('_', ' ')}` : ''}
                          </p>
                        )}
                      </td>
                      <td className="px-5 py-4 text-ink-500">
                        {formatNaira(item.asking_price_kobo)}
                      </td>
                      <td className="px-5 py-4 text-xs text-ink-500">
                        {item.doc_verification_status.replace(/_/g, ' ')}
                      </td>
                      <td className="px-5 py-4 text-xs text-ink-500">
                        {formatDate(item.created_at)}
                        <p className="mt-0.5 text-ink-300">
                          {item.view_count} views · {item.interest_count} interested
                        </p>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {pagination && pagination.total_pages > 1 && (
          <div className="mt-6 flex items-center justify-between text-sm text-ink-500">
            <span>
              Page {pagination.page} of {pagination.total_pages} · {pagination.total} listings
            </span>
            <div className="flex gap-2">
              {pagination.page > 1 && (
                <Link
                  href={href({
                    status,
                    authority,
                    search: rawSearch,
                    page: String(pagination.page - 1),
                  })}
                  className="rounded-md border border-ink-300/60 px-3 py-1.5 transition hover:bg-white"
                >
                  Previous
                </Link>
              )}
              {pagination.page < pagination.total_pages && (
                <Link
                  href={href({
                    status,
                    authority,
                    search: rawSearch,
                    page: String(pagination.page + 1),
                  })}
                  className="rounded-md border border-ink-300/60 px-3 py-1.5 transition hover:bg-white"
                >
                  Next
                </Link>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

/** Status treatments follow the realtor portal's measured scales (SCRUM-204):
 * `under_offer` reads as in-progress, terminal states read as neutral. */
const PILLS: Record<string, string> = {
  pending_review: 'bg-pending-100 text-pending-700',
  active: 'bg-done-100 text-done-700',
  under_offer: 'bg-scheduled-100 text-scheduled-700',
  paused: 'bg-bone text-ink-700',
  sold: 'bg-bone text-ink-700',
  expired: 'bg-bone text-ink-500',
  rejected: 'bg-red-50 text-red-700',
};

function StatusPill({ status }: { status: string }) {
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-1 text-xs font-medium ${
        PILLS[status] ?? 'bg-bone text-ink-700'
      }`}
    >
      {status.replace(/_/g, ' ')}
    </span>
  );
}
