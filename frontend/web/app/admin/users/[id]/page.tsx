import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import { UserActions } from './user-actions';
import { AdminNav } from '../../admin-nav';
import type { AdminUserDetail } from '@/lib/api';
import { authServiceUrl } from '@/lib/api';
import { ADMIN_LOGIN } from '@/lib/auth';
import { formatDateTime } from '@/lib/format';
import { backendGet } from '@/lib/server-api';

export const metadata: Metadata = {
  title: 'Account · Maihomme admin',
  robots: { index: false, follow: false },
};

/**
 * One account (SCRUM-209).
 *
 * ⚠️ Opening this page WRITES AN AUDIT ROW (`user.viewed_by_admin`) — this is the
 * platform's PII for one person, and reading about somebody is an act even when
 * nothing changes. Same reasoning as opening a document for review in SCRUM-192.
 */
export default async function AdminUserDetailPage({ params }: { params: { id: string } }) {
  const result = await backendGet<AdminUserDetail>(
    `${authServiceUrl()}/admin/users/${params.id}`,
  );
  if (!result.ok && result.status === 401) redirect(ADMIN_LOGIN);

  if (!result.ok) {
    const message =
      result.status === 404
        ? 'No account with that id.'
        : result.status === 403
          ? 'This console is restricted to admin accounts.'
          : `Could not load this account (${result.code}).`;
    return (
      <div className="flex min-h-screen bg-bone">
        <AdminNav active="users" count={null} />
        <main className="mx-auto min-w-0 flex-1 max-w-3xl px-6 py-12">
          <BackLink />
          <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 px-6 py-10 text-center text-sm text-amber-800">
            {message}
          </div>
        </main>
      </div>
    );
  }

  const user = result.data;
  const name = user.full_name?.trim() || 'Name not provided';

  return (
    <div className="flex min-h-screen bg-bone">
      <AdminNav active="users" count={null} />

      <main className="mx-auto min-w-0 flex-1 max-w-3xl px-6 py-12">
        <BackLink />

        <div className="mt-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-ink-300">{user.role}</p>
            <h1 className="mt-1 font-display text-3xl text-ink-900">{name}</h1>
          </div>
          {user.deleted_at ? (
            <span className="rounded-full bg-ink-300/25 px-3 py-1 text-sm font-medium text-ink-600">
              deleted {formatDateTime(user.deleted_at)}
            </span>
          ) : (
            <span
              className={`rounded-full px-3 py-1 text-sm font-medium ${
                user.is_active
                  ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-red-100 text-red-700'
              }`}
            >
              {user.is_active ? 'active' : 'suspended'}
            </span>
          )}
        </div>

        <section className="mt-8 rounded-lg border border-ink-300/30 bg-white p-6">
          <h2 className="font-display text-lg text-ink-900">Account</h2>
          <dl className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field label="Email" value={user.email} />
            <Field label="Phone" value={user.phone} />
            <Field label="Verified status" value={user.verified_status} />
            <Field label="Joined" value={formatDateTime(user.created_at)} />
            {user.registration_number && (
              <Field label="Maihomme registration number" value={user.registration_number} mono />
            )}
            {user.seller_authority_type && (
              <Field label="Selling authority" value={user.seller_authority_type} />
            )}
            {user.seller_authority_type === 'power_of_attorney' && (
              <Field label="PoA status" value={user.poa_verified_status} />
            )}
            {/* Booleans, never values: both identifiers are stored as bcrypt
                hashes and the hash is as sensitive as the number (§4). */}
            <Field label="NIN verified" value={user.nin_verified ? 'yes' : 'no'} />
            <Field label="BVN verified" value={user.bvn_verified ? 'yes' : 'no'} />
          </dl>
          <p className="mt-5 border-t border-ink-300/30 pt-4 text-xs leading-5 text-ink-500">
            Role, email and phone are not editable here. A role change would be a way to grant
            admin access from the console, and email and phone are the identifiers this account was
            verified with — changing one silently would hand the account to whoever holds the new
            address, and for a realtor it would break the registration number they sign in with.
          </p>
        </section>

        <UserActions user={user} />
      </main>
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/admin/users" className="text-sm text-ink-500 underline hover:text-ink-700">
      ← All users
    </Link>
  );
}

function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string | null;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-ink-300">{label}</dt>
      <dd className={`mt-1 text-sm text-ink-900 ${mono ? 'font-mono' : ''}`}>{value ?? '—'}</dd>
    </div>
  );
}
