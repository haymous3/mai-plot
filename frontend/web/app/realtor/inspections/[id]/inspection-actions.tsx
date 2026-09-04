'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import type { RealtorInspection } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { acceptanceWindow } from '@/lib/realtor-inspection';

const ACCEPT_ERRORS: Record<string, string> = {
  ASSIGNMENT_EXPIRED: 'The 2-hour window has elapsed — this assignment is being reassigned.',
  INSPECTION_NOT_PENDING: 'This assignment is no longer awaiting your response.',
  NOT_ASSIGNED_REALTOR: 'This assignment is not yours.',
  INSPECTION_NOT_FOUND: 'This assignment no longer exists.',
  INVALID_PROPOSED_TIME: 'Choose a date and time in the future.',
};

/** Acceptance actions for a pending assignment (SCRUM-140, moved onto the
 * detail page by SCRUM-204).
 *
 * The designed table carries only "View Details", but the 2-hour acceptance
 * window is enforced server-side and a lapsed assignment is reassigned to
 * another realtor in range — so the countdown and Accept cannot simply
 * disappear from the UI. They live here instead of inline on every row. */
export function InspectionActions({ insp }: { insp: RealtorInspection }) {
  const router = useRouter();

  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposing, setProposing] = useState(false);
  const [proposedAt, setProposedAt] = useState('');

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const win = acceptanceWindow(insp.assignment_expires_at, now);

  async function post(path: string, body?: unknown) {
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch(`/api/realtor/inspections/${insp.inspection_id}/${path}`, {
        method: 'POST',
        ...(body === undefined
          ? {}
          : { headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }),
      });
      if (resp.ok) {
        router.refresh();
        return;
      }
      const payload = (await resp.json().catch(() => ({}))) as { error_code?: string };
      setError(
        ACCEPT_ERRORS[payload.error_code ?? ''] ?? 'Could not complete that. Please retry.',
      );
    } catch {
      setError('Network error. Please retry.');
    }
    setBusy(false);
  }

  function propose() {
    if (!proposedAt) {
      setError('Pick a date and time first.');
      return;
    }
    // datetime-local has no timezone; convert to an absolute ISO instant.
    void post('propose-time', { proposed_date: new Date(proposedAt).toISOString() });
  }

  return (
    <div className="rounded-card-sm border border-pending-200 bg-pending-50 p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium text-ink-900">Acceptance window</span>
        <span
          className={`text-sm font-semibold ${
            win.expired ? 'text-ink-500' : win.urgent ? 'text-status-danger' : 'text-pending-700'
          }`}
        >
          {win.label}
        </span>
      </div>
      <p className="mt-1 text-xs text-ink-600">
        Respond by {formatDateTime(insp.assignment_expires_at)}
      </p>

      {win.expired ? (
        <p className="mt-4 rounded-[10px] bg-surface-muted px-4 py-3 text-sm text-ink-600">
          This window has elapsed and the assignment is being reassigned to another realtor in
          range.
        </p>
      ) : (
        <>
          <button
            type="button"
            onClick={() => void post('accept')}
            disabled={busy}
            className="mt-4 h-11 w-full rounded-[10px] bg-emerald-deep text-sm font-semibold text-white transition hover:bg-emerald-accent disabled:opacity-60"
          >
            {busy && !proposing ? 'Accepting…' : 'Accept assignment'}
          </button>

          {!proposing ? (
            <button
              type="button"
              onClick={() => {
                setProposing(true);
                setError(null);
              }}
              className="mt-2 w-full text-center text-xs font-medium text-emerald-deep hover:underline"
            >
              Propose an alternate time
            </button>
          ) : (
            <div className="mt-4 space-y-2">
              <label htmlFor="proposed-at" className="block text-xs text-ink-600">
                Propose a new date &amp; time
              </label>
              <input
                id="proposed-at"
                type="datetime-local"
                value={proposedAt}
                onChange={(e) => setProposedAt(e.target.value)}
                className="h-11 w-full rounded-[10px] border border-line-strong bg-surface-card px-3 text-sm text-ink-900 outline-none transition focus:border-emerald-deep"
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setProposing(false);
                    setError(null);
                  }}
                  disabled={busy}
                  className="h-10 flex-1 rounded-[10px] border border-line-strong text-xs font-medium text-ink-700 transition hover:border-ink-500 disabled:opacity-60"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={propose}
                  disabled={busy || !proposedAt}
                  className="h-10 flex-1 rounded-[10px] bg-emerald-deep text-xs font-semibold text-white transition hover:bg-emerald-accent disabled:opacity-60"
                >
                  {busy ? 'Sending…' : 'Send proposal'}
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {error && <p className="mt-3 text-xs text-status-danger">{error}</p>}
    </div>
  );
}
