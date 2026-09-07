import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import { AdminNav } from '../admin-nav';
import type { AdminUserListResponse } from '@/lib/api';
import { authServiceUrl } from '@/lib/api';
import { ADMIN_LOGIN } from '@/lib/auth';
import { formatDate } from '@/lib/format';
import { backendGet } from '@/lib/server-api';

export const metadata: Metadata = {
  title: 'Users · Maihomme admin',
  robots: { index: false, follow: false },
};

type SearchParams = { role?: string; search?: string; include_deleted?: string; page?: string };

const TABS = [
  { key: '', label: 'All' },
  { key: 'buyer', label: 'Buyers' },
  { key: 'seller', label: 'Sellers' },
  { key: 'realtor', label: 'Realtors' },
] as const;

// Staff are shown by their real roles rather than lumped under one tab: an admin
// looking for "who has access" needs to see WHICH kind, and there are only ever a
// handful of them.
const STAFF_TABS = [
  { key: 'admin', label: 'Admins' },
  { key: 'legal_team', label: 'Legal team' },
] as const;

const ROLES = new Set([
  'buyer',
  'seller',
  'realtor',
  'bank_partner',
  'admin',
  'legal_team',
]);

const PAGE_SIZE = 25;

/**
 * The admin user console (SCRUM-209).
 *
 * Before this, no admin surface could show a user: every queue is a queue of
 * things, so an admin could review a seller's power of attorney without being
 * able to look up the seller.
 *
 * Filters and search are server-rendered LINKS, not client state — the same
 * pattern as the document, listing and inspection queues. Changing a filter is a
 * navigation, which means a support conversation can be resumed from a URL.
 */
export default async function AdminUsersPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const role = searchParams.role && ROLES.has(searchParams.role) ? searchParams.role : undefined;
  // The API rejects a 1-character search (it matches most of the table), so the
  // page drops it rather than rendering a 422.
  const rawSearch = (searchParams.search ?? '').trim();
  const search = rawSearch.length >= 2 ? rawSearch : undefined;
  const includeDeleted = searchParams.include_deleted === 'true';
  const page = Math.max(1, Number(searchParams.page ?? '1') || 1);

  const url = new URL(`${authServiceUrl()}/admin/users`);
  if (role) url.searchParams.set('role', role);
  if (search) url.searchParams.set('search', search);
  if (includeDeleted) url.searchParams.set('include_deleted', 'true');
  url.searchParams.set('page', String(page));
  url.searchParams.set('page_size', String(PAGE_SIZE));

  const result = await backendGet<AdminUserListResponse>(url.toString());
  if (!result.ok && result.status === 401) redirect(ADMIN_LOGIN);
  const forbidden = !result.ok && result.status === 403;

  const items = result.ok ? result.data.items : [];
  const total = result.ok ? result.data.pagination.total : 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function hrefWith(overrides: Partial<SearchParams>): string {
    const qs = new URLSearchParams();
    const merged: SearchParams = { ...searchParams, ...overrides };
    for (const [key, value] of Object.entries(merged)) {
      // A changed filter resets to page 1: staying on page 4 of a different
      // result set shows an empty table and reads as a bug.
      if (value && key !== 'page') qs.set(key, String(value));
    }
    if (merged.page && merged.page !== '1') qs.set('page', String(merged.page));
    const query = qs.toString();
    return query ? `/admin/users?${query}` : '/admin/users';
  }

  return (
    <div className="min-h-screen bg-bone">
      <AdminNav active="users" count={result.ok ? total : null} />

      <main className="mx-auto max-w-6xl px-6 py-12">
        <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Admin</p>
        <h1 className="mt-2 font-display text-3xl text-ink-900">Users</h1>
        <p className="mt-3 max-w-prose text-sm text-ink-500">
          Every account on the platform. Open one to correct a profile, suspend access, or delete
          it. Roles and verified identifiers (email, phone) are deliberately not editable — see the
          note on the account page.
        </p>

        <div className="mt-7 flex flex-wrap items-center gap-2">
          {[...TABS, ...STAFF_TABS].map((tab) => {
            const active = (role ?? '') === tab.key;
            return (
              <Link
                key={tab.key || 'all'}
                href={hrefWith({ role: tab.key || undefined, page: undefined })}
                className={`rounded-full px-3.5 py-1.5 text-sm transition ${
                  active
                    ? 'bg-emerald-deep text-bone'
                    : 'border border-ink-300/60 text-ink-700 hover:border-ink-500'
                }`}
              >
                {tab.label}
              </Link>
            );
          })}

          {/* GET, so a search is a shareable URL — the same reason the filters are
              links. Method and action are explicit rather than relying on the
              default, because this form must never become a POST. */}
          <form method="GET" action="/admin/users" className="ml-auto flex items-center gap-2">
            {role && <input type="hidden" name="role" value={role} />}
            {includeDeleted && <input type="hidden" name="include_deleted" value="true" />}
            <input
              type="search"
              name="search"
              defaultValue={rawSearch}
              placeholder="Name, email or phone"
              minLength={2}
              className="w-56 rounded-md border border-ink-300/60 bg-white px-3 py-1.5 text-sm text-ink-900 outline-none placeholder:text-ink-300 focus:border-emerald-accent"
            />
            <button
              type="submit"
              className="rounded-md border border-ink-300/60 px-3 py-1.5 text-sm font-medium text-ink-700 transition hover:border-ink-500"
            >
              Search
            </button>
          </form>
        </div>

        <div className="mt-4 flex items-center gap-4 text-xs text-ink-500">
          <Link
            href={hrefWith({
              include_deleted: includeDeleted ? undefined : 'true',
              page: undefined,
            })}
            className="underline hover:text-ink-700"
          >
            {includeDeleted ? 'Hide deleted accounts' : 'Show deleted accounts'}
          </Link>
          {(role || search || includeDeleted) && (
            <Link href="/admin/users" className="underline hover:text-ink-700">
              Clear filters
            </Link>
          )}
        </div>

        <div className="mt-6">
          {forbidden ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-6 py-10 text-center text-sm text-amber-800">
              This console is restricted to admin accounts. (Legal-team accounts review powers of
              attorney instead.)
            </div>
          ) : !result.ok ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
              Could not load users ({result.code}). Please retry.
            </div>
          ) : items.length === 0 ? (
            <div className="rounded-lg border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center text-sm text-ink-300">
              {search ? `No account matches “${rawSearch}”.` : 'No accounts to show.'}
            </div>
          ) : (
            <>
              <div className="overflow-hidden rounded-lg border border-ink-300/30 bg-white">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-ink-300/30 text-left text-xs uppercase tracking-wider text-ink-300">
                      <th className="px-5 py-3 font-medium">Name</th>
                      <th className="px-5 py-3 font-medium">Role</th>
                      <th className="px-5 py-3 font-medium">Contact</th>
                      <th className="px-5 py-3 font-medium">Joined</th>
                      <th className="px-5 py-3 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((user) => (
                      <tr key={user.id} className="border-b border-ink-300/20 last:border-0">
                        <td className="px-5 py-4">
                          <Link
                            href={`/admin/users/${user.id}`}
                            className="font-medium text-ink-900 underline decoration-ink-300 underline-offset-2 hover:decoration-ink-500"
                          >
                            {/* An account created before SCRUM-197, or through the
                                API, holds "" rather than null — `??` would not
                                fire and the cell would render blank. */}
                            {user.full_name?.trim() || 'Name not provided'}
                          </Link>
                          {user.registration_number && (
                            <p className="mt-0.5 font-mono text-xs text-ink-500">
                              {user.registration_number}
                            </p>
                          )}
                        </td>
                        <td className="px-5 py-4 text-ink-500">{user.role}</td>
                        <td className="px-5 py-4 text-ink-500">
                          <p>{user.email ?? '—'}</p>
                          <p className="text-xs">{user.phone ?? '—'}</p>
                        </td>
                        <td className="px-5 py-4 text-ink-500">{formatDate(user.created_at)}</td>
                        <td className="px-5 py-4">
                          <StatusPill user={user} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-5 flex items-center justify-between text-sm text-ink-500">
                <span>
                  {total} {total === 1 ? 'account' : 'accounts'}
                  {totalPages > 1 ? ` · page ${page} of ${totalPages}` : ''}
                </span>
                {totalPages > 1 && (
                  <div className="flex gap-2">
                    <PageLink
                      href={hrefWith({ page: String(page - 1) })}
                      disabled={page <= 1}
                    >
                      Previous
                    </PageLink>
                    <PageLink
                      href={hrefWith({ page: String(page + 1) })}
                      disabled={page >= totalPages}
                    >
                      Next
                    </PageLink>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function StatusPill({ user }: { user: { deleted: boolean; is_active: boolean } }) {
  // Deleted outranks suspended: a deleted account is also inactive, and showing
  // "suspended" for one would understate what happened to it.
  const { label, className } = user.deleted
    ? { label: 'deleted', className: 'bg-ink-300/25 text-ink-600' }
    : user.is_active
      ? { label: 'active', className: 'bg-emerald-100 text-emerald-800' }
      : { label: 'suspended', className: 'bg-red-100 text-red-700' };
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${className}`}>
      {label}
    </span>
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
      <span className="rounded-md border border-ink-300/40 px-3 py-1.5 text-xs text-ink-300">
        {children}
      </span>
    );
  }
  return (
    <Link
      href={href}
      className="rounded-md border border-ink-300/60 px-3 py-1.5 text-xs font-medium text-ink-700 transition hover:border-ink-500"
    >
      {children}
    </Link>
  );
}
