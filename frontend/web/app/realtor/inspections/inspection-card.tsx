'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import type { RealtorInspection } from '@/lib/api';
import { formatDate, formatDateTime } from '@/lib/format';
import {
  acceptanceWindow,
  inspectionLocation,
  inspectionStatusMeta,
} from '@/lib/realtor-inspection';

const ACCEPT_ERRORS: Record<string, string> = {
  ASSIGNMENT_EXPIRED: 'The 2-hour window has elapsed — this assignment is being reassigned.',
  INSPECTION_NOT_PENDING: 'This assignment is no longer awaiting your response.',
  NOT_ASSIGNED_REALTOR: 'This assignment is not yours.',
  INSPECTION_NOT_FOUND: 'This assignment no longer exists.',
  INVALID_PROPOSED_TIME: 'Choose a date and time in the future.',
};

/** One assigned-inspection card (SCRUM-140). Pending assignments show a live
 * acceptance countdown + Accept; scheduled/completed show their state. */
export function InspectionCard({ insp }: { insp: RealtorInspection }) {
  const router = useRouter();
  const meta = inspectionStatusMeta(insp.status);
  const isPending = insp.status === 'pending';

  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposing, setProposing] = useState(false);
  const [proposedAt, setProposedAt] = useState('');

  useEffect(() => {
    if (!isPending) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [isPending]);

  const win = isPending ? acceptanceWindow(insp.assignment_expires_at, now) : null;

  async function accept() {
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch(`/api/realtor/inspections/${insp.inspection_id}/accept`, {
        method: 'POST',
      });
      if (resp.ok) {
        router.refresh();
        return;
      }
      const body = (await resp.json().catch(() => ({}))) as { error_code?: string };
      setError(ACCEPT_ERRORS[body.error_code ?? ''] ?? 'Could not accept the assignment. Please retry.');
      setBusy(false);
    } catch {
      setError('Network error. Please retry.');
      setBusy(false);
    }
  }

  async function propose() {
    if (!proposedAt) {
      setError('Pick a date and time first.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // datetime-local has no timezone; convert to an absolute ISO instant.
      const iso = new Date(proposedAt).toISOString();
      const resp = await fetch(`/api/realtor/inspections/${insp.inspection_id}/propose-time`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ proposed_date: iso }),
      });
      if (resp.ok) {
        router.refresh();
        return;
      }
      const body = (await resp.json().catch(() => ({}))) as { error_code?: string };
      setError(ACCEPT_ERRORS[body.error_code ?? ''] ?? 'Could not propose a time. Please retry.');
      setBusy(false);
    } catch {
      setError('Network error. Please retry.');
      setBusy(false);
    }
  }

  return (
    <div className="rounded-card-sm border border-line bg-surface-card p-6">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium text-ink-900">
            {insp.property_title ?? 'Property inspection'}
          </p>
          <p className="mt-0.5 truncate text-sm text-ink-500">📍 {inspectionLocation(insp)}</p>
        </div>
        <span className={`flex-none rounded-full px-2.5 py-1 text-xs font-medium ${meta.pill}`}>
          {meta.label}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-3 text-sm">
        <div>
          <p className="text-xs text-ink-500">Proposed date</p>
          <p className="mt-0.5 text-ink-900">🗓 {formatDate(insp.proposed_date)}</p>
        </div>
        {insp.confirmed_date && (
          <div>
            <p className="text-xs text-ink-500">Confirmed date</p>
            <p className="mt-0.5 text-ink-900">✓ {formatDate(insp.confirmed_date)}</p>
          </div>
        )}
        {insp.report_submitted_at && (
          <div>
            <p className="text-xs text-ink-500">Report submitted</p>
            <p className="mt-0.5 text-ink-900">📝 {formatDate(insp.report_submitted_at)}</p>
          </div>
        )}
      </div>

      {isPending && win && (
        <div className="mt-4 rounded-xl bg-bone px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-ink-600">Acceptance window</span>
            <span
              className={`text-xs font-semibold ${
                win.expired ? 'text-ink-500' : win.urgent ? 'text-red-600' : 'text-amber-700'
              }`}
            >
              ⏳ {win.label}
            </span>
          </div>
          <p className="mt-1 text-xs text-ink-500">
            Respond by {formatDateTime(insp.assignment_expires_at)}
          </p>

          {win.expired ? (
            <p className="mt-3 rounded-lg bg-ink-300/15 px-3 py-2 text-xs text-ink-600">
              This window has elapsed and the assignment is being reassigned to another realtor in
              range.
            </p>
          ) : (
            <>
              <button
                type="button"
                onClick={accept}
                disabled={busy}
                className="mt-3 w-full rounded-lg bg-emerald-deep px-4 py-2.5 text-sm font-semibold text-bone transition hover:bg-emerald-accent disabled:opacity-60"
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
                <div className="mt-3 space-y-2">
                  <label className="block text-xs text-ink-600">Propose a new date &amp; time</label>
                  <input
                    type="datetime-local"
                    value={proposedAt}
                    onChange={(e) => setProposedAt(e.target.value)}
                    className="w-full rounded-xl border border-line-strong bg-surface-card px-3 py-2 text-sm text-ink-900 outline-none transition focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
                  />
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setProposing(false);
                        setError(null);
                      }}
                      disabled={busy}
                      className="flex-1 rounded-lg border border-ink-300/60 px-3 py-2 text-xs font-medium text-ink-700 transition hover:border-ink-500 disabled:opacity-60"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={propose}
                      disabled={busy || !proposedAt}
                      className="flex-1 rounded-lg bg-emerald-deep px-3 py-2 text-xs font-semibold text-bone transition hover:bg-emerald-accent disabled:opacity-60"
                    >
                      {busy ? 'Sending…' : 'Send proposal'}
                    </button>
                  </div>
                </div>
              )}
            </>
          )}

          {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
        </div>
      )}

      {insp.status === 'accepted' || insp.status === 'rescheduled' ? (
        <div className="mt-4 rounded-xl bg-emerald-deep/5 px-4 py-3">
          <p className="text-xs text-ink-700">
            You&apos;ve accepted this inspection. Submit your GPS-stamped report on inspection day.
          </p>
          <Link
            href={`/realtor/inspections/${insp.inspection_id}/report`}
            className="mt-3 block rounded-lg bg-emerald-deep px-4 py-2.5 text-center text-sm font-semibold text-bone transition hover:bg-emerald-accent"
          >
            Submit Report
          </Link>
        </div>
      ) : null}
    </div>
  );
}
