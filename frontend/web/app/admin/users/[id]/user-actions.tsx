'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import type { AdminUserDetail } from '@/lib/api';

const ERRORS: Record<string, string> = {
  USER_NOT_FOUND: 'This account no longer exists.',
  USER_DELETED: 'This account is deleted — it cannot be changed.',
  USER_ALREADY_DELETED: 'This account was already deleted. Refresh to see it.',
  NOTHING_TO_UPDATE: 'Change something before saving.',
  CANNOT_DELETE_STAFF: 'Admin and legal-team accounts are managed outside this console.',
  CANNOT_DELETE_SELF: 'You cannot delete your own account here.',
  // Temporary and actionable — say what has to happen, not just "no".
  USER_HAS_ACTIVE_DEALS:
    'This user still has a deal in progress. It has to be completed or cancelled before the account can be deleted.',
  // Nothing was deleted. The distinction matters: a retry is the whole fix.
  DELETE_CHECK_UNAVAILABLE:
    'We could not confirm this user has no deals in progress, so nothing was deleted. Try again in a moment.',
  REASON_REQUIRED: 'A reason is required to suspend an account.',
  NO_SESSION: 'Your session expired — please sign in again.',
  BACKEND_UNAVAILABLE: 'The auth service is unreachable.',
};

function message(code: string | undefined): string {
  return ERRORS[code ?? ''] ?? 'That did not work. Please try again.';
}

/**
 * Edit / suspend / delete for one account (SCRUM-209).
 *
 * Client-side because all three are mutations with their own error states, and
 * the delete needs a confirmation step. The page around it stays a Server
 * Component read.
 */
export function UserActions({ user }: { user: AdminUserDetail }) {
  const router = useRouter();
  const [fullName, setFullName] = useState(user.full_name ?? '');
  const [location, setLocation] = useState(user.location ?? '');
  const [address, setAddress] = useState(user.address ?? '');
  const [busy, setBusy] = useState<null | 'save' | 'active' | 'delete'>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [suspendReason, setSuspendReason] = useState('');
  const [askingSuspend, setAskingSuspend] = useState(false);

  // A deleted account is read-only: every write endpoint refuses it, so offering
  // the controls would only produce errors.
  if (user.deleted_at) {
    return (
      <section className="mt-6 rounded-lg border border-ink-300/30 bg-white p-6">
        <h2 className="font-display text-lg text-ink-900">Deleted account</h2>
        <p className="mt-2 text-sm text-ink-500">
          This account was deleted, so it can no longer be edited or suspended. Its transactions,
          escrow movements and audit history are retained — deleting an account never removes the
          financial record. The email and phone have been released, so this person can sign up
          again as a new account.
        </p>
      </section>
    );
  }

  async function send(
    url: string,
    init: RequestInit,
    which: 'save' | 'active' | 'delete',
  ): Promise<boolean> {
    setBusy(which);
    setError(null);
    setSaved(false);
    try {
      const resp = await fetch(url, init);
      if (!resp.ok) {
        const body = (await resp.json().catch(() => ({}))) as { error?: string };
        setError(message(body.error));
        return false;
      }
      return true;
    } catch {
      setError('Could not reach the server. Please try again.');
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function save() {
    const ok = await send(
      `/api/admin/users/${user.id}`,
      {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        // Empty strings are sent as null so a field can be CLEARED — the API
        // treats a present null as "clear this" and an absent key as "leave it".
        body: JSON.stringify({
          full_name: fullName.trim() || null,
          location: location.trim() || null,
          address: address.trim() || null,
        }),
      },
      'save',
    );
    if (ok) {
      setSaved(true);
      router.refresh();
    }
  }

  async function setActive(active: boolean) {
    const ok = await send(
      `/api/admin/users/${user.id}/${active ? 'reactivate' : 'suspend'}`,
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(active ? {} : { reason: suspendReason.trim() }),
      },
      'active',
    );
    if (ok) {
      setAskingSuspend(false);
      setSuspendReason('');
      router.refresh();
    }
  }

  async function remove() {
    const ok = await send(
      `/api/admin/users/${user.id}`,
      {
        method: 'DELETE',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ reason: 'Deleted from the admin console' }),
      },
      'delete',
    );
    if (ok) {
      setConfirming(false);
      // Back to the list: the account is gone, so staying on its page would show
      // a read-only shell of what was just deleted.
      router.push('/admin/users');
      router.refresh();
    }
  }

  return (
    <>
      {error && (
        <p role="alert" className="mt-6 rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
          {error}
        </p>
      )}

      <section className="mt-6 rounded-lg border border-ink-300/30 bg-white p-6">
        <h2 className="font-display text-lg text-ink-900">Edit profile</h2>
        <p className="mt-1 text-sm text-ink-500">
          Corrections only — a misspelled name, a stale address. Clearing a field leaves it empty.
        </p>

        <div className="mt-5 space-y-4">
          <Labelled id="full_name" label="Full name">
            <input
              id="full_name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              disabled={busy !== null}
              className={inputClass}
            />
          </Labelled>
          <Labelled id="location" label="Location">
            <input
              id="location"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              disabled={busy !== null}
              placeholder="e.g. Lagos"
              className={inputClass}
            />
          </Labelled>
          <Labelled id="address" label="Address">
            <textarea
              id="address"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              disabled={busy !== null}
              rows={2}
              className={inputClass}
            />
          </Labelled>
        </div>

        <div className="mt-5 flex items-center gap-3">
          <button
            onClick={() => void save()}
            disabled={busy !== null}
            className="rounded-md bg-emerald-deep px-4 py-2 text-sm font-medium text-bone transition hover:bg-emerald-accent disabled:opacity-50"
          >
            {busy === 'save' ? 'Saving…' : 'Save changes'}
          </button>
          {saved && <span className="text-sm text-emerald-deep">Saved.</span>}
        </div>
      </section>

      <section className="mt-6 rounded-lg border border-ink-300/30 bg-white p-6">
        <h2 className="font-display text-lg text-ink-900">Access</h2>
        {user.is_active ? (
          <>
            <p className="mt-1 text-sm text-ink-500">
              Suspending signs this user out everywhere and blocks new sign-ins. Nothing is
              deleted, and you can lift it at any time.
            </p>
            {askingSuspend ? (
              <div className="mt-4">
                <Labelled id="suspend_reason" label="Reason (recorded in the audit log)">
                  <input
                    id="suspend_reason"
                    value={suspendReason}
                    onChange={(e) => setSuspendReason(e.target.value)}
                    disabled={busy !== null}
                    placeholder="e.g. chargeback under investigation"
                    className={inputClass}
                  />
                </Labelled>
                <div className="mt-3 flex gap-2">
                  <button
                    onClick={() => void setActive(false)}
                    disabled={busy !== null || suspendReason.trim() === ''}
                    className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-700 disabled:opacity-50"
                  >
                    {busy === 'active' ? 'Suspending…' : 'Confirm suspension'}
                  </button>
                  <button
                    onClick={() => setAskingSuspend(false)}
                    disabled={busy !== null}
                    className="rounded-md border border-ink-300/60 px-4 py-2 text-sm font-medium text-ink-700"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setAskingSuspend(true)}
                className="mt-4 rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-700 transition hover:bg-red-50"
              >
                Suspend account
              </button>
            )}
          </>
        ) : (
          <>
            <p className="mt-1 text-sm text-ink-500">
              This account is suspended: the user cannot sign in. Reactivating restores access
              immediately.
            </p>
            <button
              onClick={() => void setActive(true)}
              disabled={busy !== null}
              className="mt-4 rounded-md bg-emerald-deep px-4 py-2 text-sm font-medium text-bone transition hover:bg-emerald-accent disabled:opacity-50"
            >
              {busy === 'active' ? 'Reactivating…' : 'Reactivate account'}
            </button>
          </>
        )}
      </section>

      <section className="mt-6 rounded-lg border border-red-200 bg-red-50/40 p-6">
        <h2 className="font-display text-lg text-ink-900">Delete account</h2>
        <p className="mt-1 text-sm text-ink-500">
          Removes this person&rsquo;s access to Maihomme. Their financial history is kept.
        </p>
        <button
          onClick={() => setConfirming(true)}
          className="mt-4 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-700"
        >
          Delete account…
        </button>
      </section>

      {confirming && (
        <DeleteModal
          name={user.full_name?.trim() || user.email || 'this account'}
          busy={busy === 'delete'}
          onCancel={() => setConfirming(false)}
          onConfirm={() => void remove()}
        />
      )}
    </>
  );
}

const inputClass =
  'w-full rounded-md border border-ink-300/60 bg-white px-3 py-2 text-sm text-ink-900 outline-none focus:border-emerald-accent disabled:opacity-60';

function Labelled({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-ink-700">
        {label}
      </label>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

/**
 * The delete confirmation.
 *
 * It states what actually happens rather than asking "are you sure?": what is
 * removed, what is KEPT, and the one consequence nobody expects — the email and
 * phone are released, so the person can sign up again and this account will not
 * be reachable by searching for them.
 *
 * `dialog` semantics by hand (role, aria-modal, labelled title) rather than a
 * library, matching the reject modals already in the admin surface.
 */
function DeleteModal({
  name,
  busy,
  onCancel,
  onConfirm,
}: {
  name: string;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-title"
    >
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h3 id="delete-title" className="font-display text-xl text-ink-900">
          Delete {name}?
        </h3>

        <ul className="mt-4 space-y-2 text-sm text-ink-700">
          <li>· They are signed out everywhere and can no longer sign in.</li>
          <li>· Their email and phone are released, so they could sign up again as a new account.</li>
          <li>· Transactions, escrow movements and audit history are kept — deleting an account never removes the financial record.</li>
          <li>· This cannot be undone from the admin console.</li>
        </ul>

        <p className="mt-4 rounded-md bg-bone px-3 py-2 text-xs text-ink-500">
          If the account has a deal in progress, the delete will be refused — finish or cancel the
          deal first. Suspending is the reversible option.
        </p>

        <div className="mt-6 flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={busy}
            className="rounded-md border border-ink-300/60 px-4 py-2 text-sm font-medium text-ink-700 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={busy}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-700 disabled:opacity-50"
          >
            {busy ? 'Deleting…' : 'Delete account'}
          </button>
        </div>
      </div>
    </div>
  );
}
