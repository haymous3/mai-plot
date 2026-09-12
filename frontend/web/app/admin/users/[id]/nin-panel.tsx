'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import type { AdminNinStatus } from '@/lib/api';
import { formatDateTime } from '@/lib/format';

const REASON_MIN = 10;
/** How long a revealed number stays on screen before re-masking. */
const REVEAL_SECONDS = 60;

const ERRORS: Record<string, string> = {
  USER_NOT_FOUND: 'This account no longer exists.',
  USER_DELETED: 'This account is deleted — its NIN can be revealed but not changed.',
  NIN_NOT_ON_FILE: 'There is no NIN on this account.',
  NIN_NOT_RECOVERABLE:
    'This NIN was verified before recoverable storage existed, so it cannot be shown. Replace it to store a recoverable copy.',
  NIN_BELONGS_TO_ANOTHER_ACCOUNT: 'Another account already holds this NIN.',
  NIN_FORMAT_INVALID: 'A NIN is exactly 11 digits.',
  NIN_NOT_VERIFIED: 'The registry did not confirm this NIN for this person.',
  NIN_VERIFICATION_UNAVAILABLE:
    'The identity registry is unreachable right now. Nothing was changed — try again in a moment.',
  REASON_REQUIRED: `A reason of at least ${REASON_MIN} characters is required.`,
  NO_SESSION: 'Your session expired — please sign in again.',
  BACKEND_UNAVAILABLE: 'The auth service is unreachable.',
};

function message(code: string | undefined): string {
  return ERRORS[code ?? ''] ?? 'That did not work. Please try again.';
}

type Mode = 'idle' | 'reveal' | 'set' | 'clear';

/**
 * The NIN console for one account (SCRUM-224).
 *
 * The number is masked until an admin asks for it WITH A REASON — the reveal is
 * a POST that writes an audit row, and the reason is what a regulator reads
 * later. Once shown it re-masks after a minute; it is never written to browser
 * storage. Set/Replace re-verifies with the registry before anything is stored,
 * and Clear walks the account's verified status back.
 *
 * On a deleted account only Reveal is offered: a regulator request does not stop
 * at deletion, but nothing about a deleted account should change.
 */
export function NinPanel({
  userId,
  status,
  deleted,
}: {
  userId: string;
  status: AdminNinStatus;
  deleted: boolean;
}) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>('idle');
  const [reason, setReason] = useState('');
  const [nin, setNin] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mismatches, setMismatches] = useState<string[]>([]);
  const [revealed, setRevealed] = useState<string | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [copied, setCopied] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  // Re-mask on a timer. Cleared on unmount and whenever the value changes.
  useEffect(() => {
    if (revealed === null) return;
    setSecondsLeft(REVEAL_SECONDS);
    const tick = setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          clearInterval(tick);
          setRevealed(null);
          setCopied(false);
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(tick);
  }, [revealed]);

  const reasonOk = reason.trim().length >= REASON_MIN;
  const ninOk = /^\d{11}$/.test(nin);

  function open(next: Mode) {
    setMode(next);
    setReason('');
    setNin('');
    setError(null);
    setMismatches([]);
    setDone(null);
  }

  async function submit() {
    setBusy(true);
    setError(null);
    setMismatches([]);
    try {
      const base = `/api/admin/users/${userId}/nin`;
      const headers = { 'content-type': 'application/json' };
      const trimmed = reason.trim();
      const resp =
        mode === 'reveal'
          ? await fetch(`${base}/reveal`, {
              method: 'POST',
              headers,
              body: JSON.stringify({ reason: trimmed }),
            })
          : mode === 'set'
            ? await fetch(base, {
                method: 'PUT',
                headers,
                body: JSON.stringify({ nin, reason: trimmed }),
              })
            : await fetch(base, {
                method: 'DELETE',
                headers,
                body: JSON.stringify({ reason: trimmed }),
              });

      if (!resp.ok) {
        const body = (await resp.json().catch(() => ({}))) as {
          error?: string;
          details?: { mismatches?: string[] };
        };
        setError(message(body.error));
        if (body.error === 'NIN_NOT_VERIFIED' && body.details?.mismatches?.length) {
          setMismatches(body.details.mismatches);
        }
        return;
      }

      if (mode === 'reveal') {
        const body = (await resp.json()) as { nin: string };
        setRevealed(body.nin);
        setMode('idle');
        return;
      }
      setDone(mode === 'set' ? 'NIN verified and saved.' : 'NIN cleared.');
      setMode('idle');
      // The page owns the status (a Server Component read); refresh it.
      router.refresh();
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (revealed === null) return;
    try {
      await navigator.clipboard.writeText(revealed);
      setCopied(true);
    } catch {
      // Clipboard can be blocked; the number is on screen regardless.
    }
  }

  const masked = status.nin_last4 ? `••••••• ${status.nin_last4}` : '—';

  return (
    <section className="mt-6 rounded-lg border border-ink-300/30 bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-lg text-ink-900">National identity number</h2>
          <p className="mt-1 text-sm text-ink-500">
            Every reveal and every change is recorded in the audit log with your name and the
            reason you give.
          </p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-sm font-medium ${
            status.nin_verified
              ? 'bg-emerald-100 text-emerald-800'
              : 'bg-ink-300/25 text-ink-600'
          }`}
        >
          {status.nin_verified ? 'verified' : 'not on file'}
        </span>
      </div>

      <dl className="mt-5 grid gap-4 sm:grid-cols-2">
        <div>
          <dt className="text-xs uppercase tracking-wide text-ink-300">NIN</dt>
          <dd className="mt-1 flex flex-wrap items-center gap-3">
            {revealed !== null ? (
              <>
                <span className="font-mono text-lg tracking-[0.15em] text-ink-900">
                  {revealed}
                </span>
                <button
                  onClick={() => void copy()}
                  className="rounded-md border border-ink-300/60 px-2.5 py-1 text-xs font-medium text-ink-700 hover:bg-bone"
                >
                  {copied ? 'Copied' : 'Copy'}
                </button>
                <span className="text-xs text-ink-500">hides in {secondsLeft}s</span>
              </>
            ) : (
              <span className="font-mono text-lg tracking-[0.15em] text-ink-900">{masked}</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-ink-300">Verified</dt>
          <dd className="mt-1 text-sm text-ink-900">
            {status.nin_verified_at ? formatDateTime(status.nin_verified_at) : '—'}
          </dd>
        </div>
      </dl>

      {/* A linked second account (SCRUM-225/229). The status above is the
          ROOT's, and every write or reveal is refused here on purpose: the
          reveal audit belongs on the row that holds the number, and exactly
          one row owns a NIN. So: a pointer, not the controls. */}
      {status.held_by_user_id && (
        <p className="mt-4 rounded-md bg-emerald-deep/10 px-3.5 py-2.5 text-sm text-emerald-deep">
          This is a linked second account. Its identity is verified through another account of
          the same person, which holds the NIN.{' '}
          <Link
            href={`/admin/users/${status.held_by_user_id}`}
            className="font-medium underline underline-offset-2 hover:no-underline"
          >
            Manage the NIN there
          </Link>
          .
        </p>
      )}

      {status.nin_verified && !status.recoverable && !status.held_by_user_id && (
        <p className="mt-4 rounded-md bg-amber-50 px-3.5 py-2.5 text-sm text-amber-800">
          This NIN was verified before recoverable storage existed. It counts as verified, but
          it cannot be shown. Use <strong>Replace</strong> to re-verify the number with the
          registry and store a recoverable copy.
        </p>
      )}

      {error && (
        <div role="alert" className="mt-4 rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
          <p>{error}</p>
          {mismatches.length > 0 && (
            <p className="mt-1 text-xs">
              Did not match on: {mismatches.map((m) => m.replace('_', ' ')).join(', ')}. Check
              the name on the account against the person&rsquo;s identity document.
            </p>
          )}
        </div>
      )}
      {done && <p className="mt-4 text-sm text-emerald-deep">{done}</p>}

      {status.held_by_user_id ? null : mode === 'idle' ? (
        <div className="mt-5 flex flex-wrap gap-2">
          {status.nin_verified && status.recoverable && revealed === null && (
            <button
              onClick={() => open('reveal')}
              className="rounded-md bg-emerald-deep px-4 py-2 text-sm font-medium text-bone transition hover:bg-emerald-accent"
            >
              Reveal…
            </button>
          )}
          {!deleted && (
            <button
              onClick={() => open('set')}
              className="rounded-md border border-ink-300/60 px-4 py-2 text-sm font-medium text-ink-700 transition hover:bg-bone"
            >
              {status.nin_verified ? 'Replace…' : 'Add NIN…'}
            </button>
          )}
          {!deleted && status.nin_verified && (
            <button
              onClick={() => open('clear')}
              className="rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-700 transition hover:bg-red-50"
            >
              Clear…
            </button>
          )}
        </div>
      ) : (
        <div className="mt-5 rounded-md border border-ink-300/30 bg-bone p-4">
          <p className="text-sm font-medium text-ink-900">
            {mode === 'reveal' && 'Reveal this NIN'}
            {mode === 'set' && (status.nin_verified ? 'Replace this NIN' : 'Add a NIN')}
            {mode === 'clear' && 'Clear this NIN'}
          </p>
          <p className="mt-1 text-sm text-ink-500">
            {mode === 'reveal' &&
              'The number will show for one minute. Your name, the time and this reason go in the audit log.'}
            {mode === 'set' &&
              'The number is checked against the identity registry (a paid call) before anything is saved. It must match the name on this account.'}
            {mode === 'clear' &&
              'Removes the NIN from this account. The account stops counting as identity-verified until a NIN or BVN is verified again, and the number becomes free for another account to use.'}
          </p>

          <div className="mt-4 space-y-4">
            {mode === 'set' && (
              <div>
                <label htmlFor="nin" className="block text-sm font-medium text-ink-700">
                  NIN (11 digits)
                </label>
                <input
                  id="nin"
                  inputMode="numeric"
                  autoComplete="off"
                  value={nin}
                  onChange={(e) => setNin(e.target.value.replace(/\D/g, '').slice(0, 11))}
                  disabled={busy}
                  className={`${inputClass} font-mono tracking-[0.15em]`}
                />
              </div>
            )}
            <div>
              <label htmlFor="nin_reason" className="block text-sm font-medium text-ink-700">
                Reason (recorded in the audit log)
              </label>
              <input
                id="nin_reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                disabled={busy}
                placeholder={
                  mode === 'reveal'
                    ? 'e.g. support ticket #4412 — identity check on a call'
                    : 'e.g. user typed the wrong number at registration'
                }
                className={inputClass}
              />
              {!reasonOk && reason.length > 0 && (
                <p className="mt-1 text-xs text-ink-500">
                  At least {REASON_MIN} characters — say what a colleague would need to know.
                </p>
              )}
            </div>
          </div>

          <div className="mt-4 flex gap-2">
            <button
              onClick={() => void submit()}
              disabled={busy || !reasonOk || (mode === 'set' && !ninOk)}
              className={`rounded-md px-4 py-2 text-sm font-medium transition disabled:opacity-50 ${
                mode === 'clear'
                  ? 'bg-red-600 text-white hover:bg-red-700'
                  : 'bg-emerald-deep text-bone hover:bg-emerald-accent'
              }`}
            >
              {busy
                ? mode === 'reveal'
                  ? 'Revealing…'
                  : mode === 'set'
                    ? 'Verifying…'
                    : 'Clearing…'
                : mode === 'reveal'
                  ? 'Reveal'
                  : mode === 'set'
                    ? 'Verify and save'
                    : 'Confirm clear'}
            </button>
            <button
              onClick={() => setMode('idle')}
              disabled={busy}
              className="rounded-md border border-ink-300/60 px-4 py-2 text-sm font-medium text-ink-700"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

const inputClass =
  'w-full rounded-md border border-ink-300/60 bg-white px-3 py-2 text-sm text-ink-900 outline-none focus:border-emerald-accent disabled:opacity-60';
