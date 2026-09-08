import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, redirect } from 'next/navigation';

import { ListingActions } from './listing-actions';
import { AdminNav } from '../../admin-nav';
import type { AdminListingDetail } from '@/lib/api';
import { listingServiceUrl } from '@/lib/api';
import { ADMIN_LOGIN } from '@/lib/auth';
import { formatDate, formatDateTime, formatNaira } from '@/lib/format';
import { backendGet } from '@/lib/server-api';

export const metadata: Metadata = {
  title: 'Listing · Maihomme admin',
  robots: { index: false, follow: false },
};

/** Audit actions rendered as sentences. An unmapped action still shows its raw
 * key rather than vanishing — a missing history row is worse than an ugly one. */
const ACTION_LABELS: Record<string, string> = {
  'listing.active': 'Approved and published',
  'listing.rejected': 'Rejected at review',
  'listing.paused_by_admin': 'Paused by an admin',
  'listing.unpaused_by_admin': 'Returned to the feed by an admin',
  'listing.taken_down_by_admin': 'Taken down by an admin',
  'listing.expired_by_admin': 'Expired early by an admin',
};

/**
 * One listing, in full, for an admin (SCRUM-215).
 *
 * This page did not exist. The approve/reject decision was made from a queue row
 * carrying the title, the LGA and the price — no photo, no description, no
 * address, no documents. An admin was publishing property listings to the
 * marketplace sight-unseen.
 */
export default async function AdminListingDetailPage({ params }: { params: { id: string } }) {
  const result = await backendGet<AdminListingDetail>(
    `${listingServiceUrl()}/admin/listings/${params.id}`,
  );
  if (!result.ok && result.status === 401) redirect(ADMIN_LOGIN);
  if (!result.ok && result.status === 404) notFound();

  if (!result.ok) {
    return (
      <div className="flex min-h-screen bg-bone">
        <AdminNav active="listings" count={null} />
        <main className="mx-auto min-w-0 flex-1 max-w-4xl px-6 py-12">
          <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
            {result.status === 403
              ? 'This console is restricted to admin reviewers.'
              : `Could not load this listing (${result.code}). Please retry.`}
          </div>
        </main>
      </div>
    );
  }

  const listing = result.data;
  const photos = listing.media.filter((m) => m.type === 'photo');

  return (
    <div className="flex min-h-screen bg-bone">
      <AdminNav active="listings" count={null} />

      <main className="mx-auto min-w-0 flex-1 max-w-4xl px-6 py-12">
        <Link href="/admin/listings" className="text-sm text-ink-500 underline">
          ← All listings
        </Link>

        <h1 className="mt-4 font-display text-3xl text-ink-900">{listing.title}</h1>
        <p className="mt-2 text-sm text-ink-500">
          {listing.address_text} · {listing.lga}, {listing.state}
        </p>
        <p className="mt-1 text-xs text-ink-300">
          {listing.location.lat.toFixed(5)}, {listing.location.lng.toFixed(5)}
        </p>

        {photos.length > 0 ? (
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {photos.map((photo) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={photo.url}
                src={photo.url}
                alt=""
                className="aspect-[4/3] w-full rounded-lg object-cover"
              />
            ))}
          </div>
        ) : (
          <p className="mt-6 rounded-lg border border-dashed border-ink-300/50 bg-white/60 px-6 py-10 text-center text-sm text-ink-300">
            This listing has no photos. Worth knowing before approving it.
          </p>
        )}

        <section className="mt-8 rounded-lg border border-ink-300/30 bg-white p-6">
          <h2 className="font-display text-lg text-ink-900">Property</h2>
          <dl className="mt-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
            <Field label="Asking price" value={formatNaira(listing.asking_price_kobo)} />
            <Field label="Type" value={listing.property_type} />
            <Field label="Sale" value={listing.sale_type} />
            <Field
              label="Size"
              value={listing.size_sqm ? `${listing.size_sqm} sqm` : 'Not given'}
            />
            <Field label="Status" value={listing.status.replace(/_/g, ' ')} />
            <Field
              label="Documents"
              value={listing.doc_verification_status.replace(/_/g, ' ')}
            />
            <Field
              label="Urgency"
              value={listing.urgency_tag ? listing.urgency_tag.replace('_', ' ') : '—'}
            />
            <Field
              label="Expires"
              value={listing.expires_at ? formatDate(listing.expires_at) : '—'}
            />
            <Field
              label="Interest"
              value={`${listing.view_count} views · ${listing.interest_count} interested`}
            />
          </dl>

          {listing.description ? (
            <p className="mt-6 whitespace-pre-line text-sm text-ink-700">{listing.description}</p>
          ) : (
            <p className="mt-6 text-sm text-ink-300">No description was provided.</p>
          )}

          {listing.rejection_reason && (
            <p className="mt-6 rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
              <span className="font-medium">Reason shown to the seller:</span>{' '}
              {listing.rejection_reason}
            </p>
          )}
        </section>

        <section className="mt-6 rounded-lg border border-ink-300/30 bg-white p-6">
          <h2 className="font-display text-lg text-ink-900">Seller</h2>
          <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
            <Field
              label="Authority"
              value={
                listing.seller.authority_type
                  ? listing.seller.authority_type.replace(/_/g, ' ')
                  : 'Unknown — the account may be deleted'
              }
            />
            {listing.seller.poa_owner_name && (
              <Field label="Acting for" value={listing.seller.poa_owner_name} />
            )}
          </dl>
          {/* Contact details live in the user console rather than being copied
              here: one place owns a person, and it already carries the whole
              account (SCRUM-209). */}
          <Link
            href={`/admin/users/${listing.seller.id}`}
            className="mt-4 inline-block text-sm text-ink-700 underline"
          >
            Open this seller&rsquo;s account
          </Link>
        </section>

        <ListingActions listing={listing} />

        <section className="mt-6 rounded-lg border border-ink-300/30 bg-white p-6">
          <h2 className="font-display text-lg text-ink-900">History</h2>
          {listing.history.length === 0 ? (
            <p className="mt-3 text-sm text-ink-300">
              Nothing has been recorded against this listing yet.
            </p>
          ) : (
            <ul className="mt-4 space-y-3 text-sm">
              {listing.history.map((entry) => (
                <li key={entry.id} className="border-l-2 border-ink-300/30 pl-3">
                  <p className="text-ink-900">
                    {ACTION_LABELS[entry.action] ?? entry.action}
                  </p>
                  <p className="text-xs text-ink-500">
                    {formatDateTime(entry.created_at)}
                    {entry.actor_role ? ` · ${entry.actor_role}` : ''}
                  </p>
                  {typeof entry.new_value?.reason === 'string' && (
                    <p className="mt-1 text-xs text-ink-500">“{entry.new_value.reason}”</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <p className="mt-6 text-xs text-ink-300">
          Listed {formatDate(listing.created_at)} · last changed {formatDateTime(listing.updated_at)}
        </p>
      </main>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-ink-300">{label}</dt>
      <dd className="mt-1 text-ink-900">{value}</dd>
    </div>
  );
}
