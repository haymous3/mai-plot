'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import type { AssignableRealtor, UnassignedInspection } from '@/lib/api';
import { formatDate, formatDateTime } from '@/lib/format';

const ASSIGN_ERRORS: Record<string, string> = {
  INSPECTION_NOT_FOUND: 'This request no longer exists.',
  // The normal case when two admins work the queue at once — say "refresh",
  // not "failed": the work got done, just not by this click.
  INSPECTION_NOT_UNASSIGNED:
    'Someone else already assigned this one — refresh to see who has it.',
  REALTOR_NOT_ASSIGNABLE: 'That realtor is no longer approved.',
  NO_SESSION: 'Your session expired — please sign in again.',
  BACKEND_UNAVAILABLE: 'The realtor service is unreachable.',
};

function realtorLabel(realtor: AssignableRealtor): string {
  const name = realtor.full_name?.trim() || `Realtor ${realtor.id.slice(0, 8)}`;
  const coverage = realtor.coverage_states.join(', ');
  return coverage ? `${name} — ${coverage}` : name;
}

function location(item: UnassignedInspection): string {
  return [item.lga, item.state].filter(Boolean).join(', ') || '—';
}

/**
 * The waiting-requests queue with its realtor picker (SCRUM-208).
 *
 * One `<select>` per row rather than a modal: the whole interaction is "who
 * takes this one", and a dialog would add a step to a decision that is already
 * a single choice. The chosen realtor is kept per row so two rows can be worked
 * without one overwriting the other's selection.
 */
export function RequestsTable({
  items,
  realtors,
  realtorsLoaded,
}: {
  items: UnassignedInspection[];
  realtors: AssignableRealtor[];
  realtorsLoaded: boolean;
}) {
  const router = useRouter();
  const [choice, setChoice] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function assign(item: UnassignedInspection) {
    const realtorId = choice[item.id];
    if (!realtorId) return;
    setBusyId(item.id);
    setError(null);
    try {
      const resp = await fetch(`/api/admin/inspections/${item.id}/assign`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ realtor_id: realtorId }),
      });
      if (!resp.ok) {
        const body = (await resp.json().catch(() => ({}))) as { error?: string };
        setError(ASSIGN_ERRORS[body.error ?? ''] ?? 'Could not assign this request.');
        return;
      }
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

      {!realtorsLoaded && (
        <p className="mb-4 rounded-md bg-amber-50 px-3.5 py-2.5 text-sm text-amber-900">
          Could not load the list of realtors, so nothing can be assigned right now. The requests
          below are unaffected — refresh to try again.
        </p>
      )}

      {realtorsLoaded && realtors.length === 0 && (
        <p className="mb-4 rounded-md bg-amber-50 px-3.5 py-2.5 text-sm text-amber-900">
          No approved realtors yet, so there is nobody to assign these to. Approve an application
          in the Realtors queue first.
        </p>
      )}

      <div className="overflow-hidden rounded-lg border border-ink-300/30 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-ink-300/30 text-left text-xs uppercase tracking-wider text-ink-300">
              <th className="px-5 py-3 font-medium">Property</th>
              <th className="px-5 py-3 font-medium">Requested for</th>
              <th className="px-5 py-3 font-medium">Waiting since</th>
              <th className="px-5 py-3 font-medium">Parties</th>
              <th className="px-5 py-3 text-right font-medium">Assign to</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const busy = busyId === item.id;
              const selected = choice[item.id] ?? '';
              return (
                <tr key={item.id} className="border-b border-ink-300/20 last:border-0 align-top">
                  <td className="px-5 py-4">
                    <p className="font-medium text-ink-900">{item.property_title ?? 'Property'}</p>
                    <p className="mt-0.5 text-xs text-ink-500">{location(item)}</p>
                    {!item.property_located && (
                      // Worth saying out loud: without a listing point the sweep
                      // can never place this, however many realtors exist.
                      <p className="mt-1 text-xs text-amber-700">
                        Listing has no location — only manual assignment can place it.
                      </p>
                    )}
                  </td>
                  <td className="px-5 py-4 text-ink-500">{formatDateTime(item.proposed_date)}</td>
                  <td className="px-5 py-4 text-ink-500">{formatDate(item.created_at)}</td>
                  <td className="px-5 py-4 text-xs text-ink-500">
                    {/* Identity is masked until a deal is accepted (§10), so the
                        queue shows references rather than names. */}
                    <span className="font-mono">{item.buyer_ref}</span> ·{' '}
                    <span className="font-mono">{item.seller_ref}</span>
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex items-center justify-end gap-2">
                      <label className="sr-only" htmlFor={`realtor-${item.id}`}>
                        Realtor for {item.property_title ?? 'this request'}
                      </label>
                      <select
                        id={`realtor-${item.id}`}
                        value={selected}
                        disabled={busy || realtors.length === 0}
                        onChange={(e) =>
                          setChoice((prev) => ({ ...prev, [item.id]: e.target.value }))
                        }
                        className="max-w-[16rem] truncate rounded-md border border-ink-300/60 bg-white px-2.5 py-1.5 text-xs text-ink-900 outline-none focus:border-emerald-accent disabled:opacity-50"
                      >
                        <option value="">Choose a realtor…</option>
                        {realtors.map((realtor) => (
                          <option key={realtor.id} value={realtor.id}>
                            {realtorLabel(realtor)}
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={() => void assign(item)}
                        disabled={busy || !selected}
                        className="rounded-md bg-emerald-deep px-3 py-1.5 text-xs font-medium text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {busy ? 'Assigning…' : 'Assign'}
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
