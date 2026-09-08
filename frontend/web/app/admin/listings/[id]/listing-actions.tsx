'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import type { AdminListingAction, AdminListingDetail } from '@/lib/api';

const ERRORS: Record<string, string> = {
  LISTING_NOT_FOUND: 'This listing no longer exists.',
  REASON_REQUIRED: 'A reason is required — the seller is shown it.',
  // Not a failure to retry: there is a live deal behind this listing, and the
  // admin has to go and resolve it.
  LISTING_UNDER_OFFER:
    'A buyer’s accepted offer is holding this listing. Resolve the transaction before changing it.',
  // Somebody else moved it. Refresh is the whole fix.
  LISTING_STATUS_CONFLICT:
    'This listing has already changed — refresh to see its current status.',
  NO_SESSION: 'Your session expired — please sign in again.',
  BACKEND_UNAVAILABLE: 'The listing service is unreachable.',
};

/** Which actions the listing's current status actually allows. Mirrors the
 * service's own table: offering a button that can only 409 is worse than
 * offering none. */
function availableActions(status: string): AdminListingAction[] {
  if (status === 'active') return ['pause', 'expire', 'take_down'];
  if (status === 'paused') return ['unpause', 'take_down'];
  return [];
}

const LABELS: Record<AdminListingAction, string> = {
  pause: 'Pause',
  unpause: 'Return to the feed',
  take_down: 'Take down',
  expire: 'Expire now',
};

const BUSY_LABELS: Record<AdminListingAction, string> = {
  pause: 'Pausing…',
  unpause: 'Restoring…',
  take_down: 'Taking down…',
  expire: 'Expiring…',
};

/**
 * Admin actions on a live listing (SCRUM-215).
 *
 * Client-side because each is a mutation with its own error state, and take-down
 * needs a reason plus a confirmation step. The page around it stays a Server
 * Component read.
 */
export function ListingActions({ listing }: { listing: AdminListingDetail }) {
  const router = useRouter();
  const [busy, setBusy] = useState<AdminListingAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState('');

  const actions = availableActions(listing.status);

  async function apply(action: AdminListingAction, withReason?: string) {
    setBusy(action);
    setError(null);
    try {
      const resp = await fetch(`/api/admin/listings/${listing.id}/status`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ action, reason: withReason }),
      });
      if (!resp.ok) {
        const body = (await resp.json().catch(() => ({}))) as { error?: string };
        setError(ERRORS[body.error ?? ''] ?? 'That did not work. Please try again.');
        return;
      }
      setConfirming(false);
      setReason('');
      router.refresh();
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="mt-6 rounded-lg border border-ink-300/30 bg-white p-6">
      <h2 className="font-display text-lg text-ink-900">Actions</h2>

      {error && (
        <p role="alert" className="mt-4 rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
          {error}
        </p>
      )}

      {listing.status === 'under_offer' ? (
        <p className="mt-3 max-w-prose text-sm text-ink-500">
          A buyer’s offer has been accepted, so this listing is locked to that deal for 72 hours and
          there may be money in escrow behind it. Changing it is a decision about the transaction,
          not the listing — resolve the deal first.
        </p>
      ) : actions.length === 0 ? (
        <p className="mt-3 max-w-prose text-sm text-ink-500">
          Nothing to do here: a listing that is {listing.status.replace(/_/g, ' ')} has no admin
          actions.{' '}
          {listing.status === 'pending_review' &&
            'It is waiting on a first decision in the review queue.'}
        </p>
      ) : (
        <>
          <p className="mt-3 max-w-prose text-sm text-ink-500">
            Pausing hides the listing from the feed and search, and is reversible. Taking it down
            marks it rejected and shows the seller your reason. Neither touches the property’s
            content — price, description and photos belong to the seller.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            {actions.map((action) => (
              <button
                key={action}
                onClick={() => (action === 'take_down' ? setConfirming(true) : void apply(action))}
                disabled={busy !== null}
                className={
                  action === 'take_down'
                    ? 'rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-700 transition hover:bg-red-50 disabled:opacity-50'
                    : 'rounded-md border border-ink-300/60 px-4 py-2 text-sm font-medium text-ink-700 transition hover:bg-bone disabled:opacity-50'
                }
              >
                {busy === action ? BUSY_LABELS[action] : LABELS[action]}
              </button>
            ))}
          </div>
        </>
      )}

      {confirming && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 px-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="takedown-title"
        >
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <h3 id="takedown-title" className="font-display text-xl text-ink-900">
              Take down “{listing.title}”?
            </h3>

            <ul className="mt-4 space-y-2 text-sm text-ink-700">
              <li>· It leaves the feed and the search index immediately.</li>
              <li>· The seller sees it as rejected, with the reason you write below.</li>
              <li>· Buyers who saved it keep the saved entry but cannot open the listing.</li>
              <li>· Pausing is the reversible option if you only need it out of sight.</li>
            </ul>

            <label className="mt-5 block text-sm font-medium text-ink-900" htmlFor="takedown-reason">
              Reason (the seller reads this)
            </label>
            <textarea
              id="takedown-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              maxLength={2000}
              placeholder="e.g. Duplicate of an existing listing."
              className="mt-1.5 w-full rounded-md border border-ink-300/60 bg-white px-3 py-2 text-sm text-ink-900 outline-none focus:border-emerald-accent"
            />

            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setConfirming(false)}
                disabled={busy !== null}
                className="rounded-md border border-ink-300/60 px-4 py-2 text-sm font-medium text-ink-700 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={() => void apply('take_down', reason)}
                disabled={busy !== null || reason.trim().length === 0}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy === 'take_down' ? 'Taking down…' : 'Take down listing'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
