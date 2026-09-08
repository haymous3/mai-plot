'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import type { AdminDeal, AssignableRealtor } from '@/lib/api';
import { formatDate, formatNaira } from '@/lib/format';

const SCHEDULE_ERRORS: Record<string, string> = {
  TRANSACTION_NOT_FOUND: 'That deal no longer exists.',
  // The common collision: somebody already booked one, by hand or automatically.
  // "Already has one" is the useful sentence, not "failed".
  INSPECTION_ALREADY_ACTIVE:
    'This deal already has a live inspection — refresh to see who has it.',
  PROPOSED_DATE_INVALID: 'Pick a date and time in the future.',
  REALTOR_NOT_ASSIGNABLE: 'That realtor is no longer approved.',
  NO_REALTOR_IN_RANGE: 'No realtor could be found automatically — choose one.',
  NO_SESSION: 'Your session expired — please sign in again.',
  BACKEND_UNAVAILABLE: 'The realtor service is unreachable.',
};

function realtorLabel(realtor: AssignableRealtor): string {
  const name = realtor.full_name?.trim() || `Realtor ${realtor.id.slice(0, 8)}`;
  const coverage = realtor.coverage_states.join(', ');
  return coverage ? `${name} — ${coverage}` : name;
}

function location(deal: AdminDeal): string {
  return [deal.lga, deal.state].filter(Boolean).join(', ') || '—';
}

/** A `datetime-local` value is wall-clock with no zone. Sending it as-is would
 * hand the backend a naive datetime, which it cannot compare against "now".
 * Interpreting it in the admin's own browser zone and sending UTC is both
 * correct and what the admin meant when they typed a time. */
function toUtcIso(localValue: string): string | null {
  const parsed = new Date(localValue);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

/**
 * Live deals with a per-row "who and when" (SCRUM-213).
 *
 * Inline controls rather than a modal, matching the sibling requests queue: the
 * whole interaction is two fields and a button, and state is kept per deal so
 * two rows can be filled in without one clobbering the other.
 */
export function ScheduleTable({
  items,
  realtors,
  realtorsLoaded,
}: {
  items: AdminDeal[];
  realtors: AssignableRealtor[];
  realtorsLoaded: boolean;
}) {
  const router = useRouter();
  const [realtorChoice, setRealtorChoice] = useState<Record<string, string>>({});
  const [dateChoice, setDateChoice] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function schedule(deal: AdminDeal) {
    const realtorId = realtorChoice[deal.id];
    const localDate = dateChoice[deal.id];
    if (!realtorId || !localDate) return;
    const proposedDate = toUtcIso(localDate);
    if (!proposedDate) {
      setError('That date could not be read. Please pick it again.');
      return;
    }

    setBusyId(deal.id);
    setError(null);
    setDone(null);
    try {
      const resp = await fetch('/api/admin/inspections', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          transaction_id: deal.id,
          proposed_date: proposedDate,
          realtor_id: realtorId,
        }),
      });
      if (!resp.ok) {
        const body = (await resp.json().catch(() => ({}))) as { error?: string };
        setError(SCHEDULE_ERRORS[body.error ?? ''] ?? 'Could not schedule this inspection.');
        return;
      }
      setDone(deal.property_title ?? 'the deal');
      router.refresh();
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      {error && (
        <p role="alert" className="mb-4 rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
          {error}
        </p>
      )}

      {done && (
        <p
          role="status"
          className="mb-4 rounded-md bg-emerald-50 px-3.5 py-2.5 text-sm text-emerald-900"
        >
          Inspection scheduled for {done}. The realtor has been notified and has 2 hours to accept.
        </p>
      )}

      {!realtorsLoaded && (
        <p className="mb-4 rounded-md bg-amber-50 px-3.5 py-2.5 text-sm text-amber-900">
          Could not load the list of realtors, so nothing can be scheduled right now. The deals
          below are unaffected — refresh to try again.
        </p>
      )}

      {realtorsLoaded && realtors.length === 0 && (
        <p className="mb-4 rounded-md bg-amber-50 px-3.5 py-2.5 text-sm text-amber-900">
          No approved realtors yet, so there is nobody to send. Approve an application in the
          Realtors queue first.
        </p>
      )}

      <div className="overflow-x-auto rounded-lg border border-ink-300/30 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-ink-300/30 text-left text-xs uppercase tracking-wider text-ink-300">
              <th className="px-5 py-3 font-medium">Property</th>
              <th className="px-5 py-3 font-medium">Stage</th>
              <th className="px-5 py-3 font-medium">Price</th>
              <th className="px-5 py-3 font-medium">Parties</th>
              <th className="px-5 py-3 text-right font-medium">Send a realtor</th>
            </tr>
          </thead>
          <tbody>
            {items.map((deal) => {
              const busy = busyId === deal.id;
              const realtorId = realtorChoice[deal.id] ?? '';
              const date = dateChoice[deal.id] ?? '';
              return (
                <tr key={deal.id} className="border-b border-ink-300/20 align-top last:border-0">
                  <td className="px-5 py-4">
                    <p className="font-medium text-ink-900">{deal.property_title ?? 'Property'}</p>
                    <p className="mt-0.5 text-xs text-ink-500">{location(deal)}</p>
                    <p className="mt-0.5 text-xs text-ink-300">
                      Deal opened {formatDate(deal.created_at)}
                    </p>
                  </td>
                  <td className="px-5 py-4 text-ink-500">{deal.stage.replace(/_/g, ' ')}</td>
                  <td className="px-5 py-4 text-ink-500">{formatNaira(deal.agreed_price_kobo)}</td>
                  <td className="px-5 py-4 text-xs text-ink-500">
                    {/* Identity is masked from everyone but the counterparties
                        (§10), so the list shows references rather than names. */}
                    <span className="font-mono">{deal.buyer_ref}</span> ·{' '}
                    <span className="font-mono">{deal.seller_ref}</span>
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex flex-col items-end gap-2">
                      <label className="sr-only" htmlFor={`date-${deal.id}`}>
                        Inspection date and time for {deal.property_title ?? 'this deal'}
                      </label>
                      <input
                        id={`date-${deal.id}`}
                        type="datetime-local"
                        value={date}
                        disabled={busy}
                        onChange={(e) =>
                          setDateChoice((prev) => ({ ...prev, [deal.id]: e.target.value }))
                        }
                        className="w-full max-w-[16rem] rounded-md border border-ink-300/60 bg-white px-2.5 py-1.5 text-xs text-ink-900 outline-none focus:border-emerald-accent disabled:opacity-50"
                      />
                      <label className="sr-only" htmlFor={`realtor-${deal.id}`}>
                        Realtor for {deal.property_title ?? 'this deal'}
                      </label>
                      <select
                        id={`realtor-${deal.id}`}
                        value={realtorId}
                        disabled={busy || realtors.length === 0}
                        onChange={(e) =>
                          setRealtorChoice((prev) => ({ ...prev, [deal.id]: e.target.value }))
                        }
                        className="w-full max-w-[16rem] truncate rounded-md border border-ink-300/60 bg-white px-2.5 py-1.5 text-xs text-ink-900 outline-none focus:border-emerald-accent disabled:opacity-50"
                      >
                        <option value="">Choose a realtor…</option>
                        {realtors.map((realtor) => (
                          <option key={realtor.id} value={realtor.id}>
                            {realtorLabel(realtor)}
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={() => void schedule(deal)}
                        disabled={busy || !realtorId || !date}
                        className="rounded-md bg-emerald-deep px-3 py-1.5 text-xs font-medium text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {busy ? 'Scheduling…' : 'Schedule'}
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
