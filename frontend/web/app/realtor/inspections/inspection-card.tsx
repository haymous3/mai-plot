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

  return (
    <div className="rounded-2xl border border-ink-300/25 bg-white p-5">
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

      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-ink-300/15 pt-3 text-sm">
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
            <button
              type="button"
              onClick={accept}
              disabled={busy}
              className="mt-3 w-full rounded-lg bg-emerald-deep px-4 py-2.5 text-sm font-semibold text-bone transition hover:bg-emerald-accent disabled:opacity-60"
            >
              {busy ? 'Accepting…' : 'Accept assignment'}
            </button>
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
