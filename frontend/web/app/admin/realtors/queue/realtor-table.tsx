'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import type { RealtorQueueItem } from '@/lib/api';
import { formatDate } from '@/lib/format';

const REVIEW_ERRORS: Record<string, string> = {
  REALTOR_NOT_ACTIONABLE: 'This applicant is no longer awaiting review.',
  REALTOR_NOT_FOUND: 'This applicant no longer exists.',
  REASON_REQUIRED: 'A rejection reason is required.',
  NO_SESSION: 'Your session expired — please sign in again.',
  // The approval was NOT applied — issuing the registration number failed and
  // realtor-service refuses to approve without one (SCRUM-207). Say "try again"
  // rather than anything final: the applicant is still pending and a retry is
  // the whole remedy.
  REGISTRATION_NUMBER_UNAVAILABLE:
    'Could not issue a registration number just now, so the applicant was not approved. Please try again.',
};

export function RealtorTable({ items }: { items: RealtorQueueItem[] }) {
  const router = useRouter();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<RealtorQueueItem | null>(null);
  const [viewing, setViewing] = useState<RealtorQueueItem | null>(null);
  // The number just issued, kept on screen after the row disappears from the
  // queue. The realtor is emailed it, but if that never arrives the reviewer is
  // the only one who can pass it on — and nothing else in the admin surface can
  // show it (SCRUM-207).
  const [issued, setIssued] = useState<{ name: string; number: string } | null>(null);

  async function review(id: string, action: 'approve' | 'reject', reason?: string) {
    setBusyId(id);
    setError(null);
    try {
      const resp = await fetch(`/api/admin/realtors/${id}/review`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ action, reason }),
      });
      const body = (await resp.json().catch(() => ({}))) as {
        error?: string;
        registration_number?: string | null;
      };
      if (!resp.ok) {
        setError(REVIEW_ERRORS[body.error ?? ''] ?? 'Could not complete the review.');
        return;
      }
      if (action === 'approve' && body.registration_number) {
        const applicant = items.find((i) => i.id === id);
        setIssued({
          name: applicant?.full_name ?? 'This applicant',
          number: body.registration_number,
        });
      }
      setRejecting(null);
      router.refresh();
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusyId(null);
    }
  }

  const issuedNotice = issued && (
    <div className="mb-4 rounded-md border border-emerald-accent/30 bg-emerald-accent/5 px-3.5 py-2.5 text-sm text-ink-700">
      <span className="font-medium">{issued.name}</span> approved. Registration number{' '}
      <span className="font-mono font-medium text-ink-900">{issued.number}</span> — emailed to them,
      and what they sign in with. Pass it on if they say the email never arrived.
    </div>
  );

  if (items.length === 0) {
    return (
      <>
        {issuedNotice}
        <div className="rounded-lg border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center text-sm text-ink-300">
          No realtor applications awaiting review.
        </div>
      </>
    );
  }

  return (
    <>
      {issuedNotice}
      {error && (
        <p role="alert" className="mb-4 rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
          {error}
        </p>
      )}

      <div className="overflow-hidden rounded-lg border border-ink-300/30 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-ink-300/30 text-left text-xs uppercase tracking-wider text-ink-300">
              {/* Was "ESVARBON licence" — the only identifying column, until
                  SCRUM-207 stopped collecting it. Approving an anonymous row is
                  not a review. */}
              <th className="px-5 py-3 font-medium">Applicant</th>
              <th className="px-5 py-3 font-medium">Experience</th>
              <th className="px-5 py-3 font-medium">Coverage</th>
              <th className="px-5 py-3 font-medium">Applied</th>
              <th className="px-5 py-3 text-right font-medium">Decision</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const busy = busyId === item.id;
              return (
                <tr key={item.id} className="border-b border-ink-300/20 last:border-0">
                  <td className="px-5 py-4 font-medium text-ink-900">
                    {item.full_name ?? 'Name not provided'}
                  </td>
                  <td className="px-5 py-4 text-ink-500">
                    {item.years_of_experience === null
                      ? '—'
                      : `${item.years_of_experience} yr${item.years_of_experience === 1 ? '' : 's'}`}
                  </td>
                  <td className="px-5 py-4 text-ink-500">
                    {item.coverage_states.length > 0 ? item.coverage_states.join(', ') : '—'}
                  </td>
                  <td className="px-5 py-4 text-ink-500">{formatDate(item.created_at)}</td>
                  <td className="px-5 py-4">
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => setViewing(item)}
                        className="rounded-md border border-ink-300/60 px-3 py-1.5 text-xs font-medium text-ink-700 transition hover:border-ink-500"
                      >
                        View ID
                      </button>
                      <button
                        onClick={() => review(item.id, 'approve')}
                        disabled={busy}
                        className="rounded-md bg-emerald-deep px-3 py-1.5 text-xs font-medium text-bone transition hover:bg-emerald-accent disabled:opacity-50"
                      >
                        {busy ? '…' : 'Approve'}
                      </button>
                      <button
                        onClick={() => {
                          setError(null);
                          setRejecting(item);
                        }}
                        disabled={busy}
                        className="rounded-md border border-ink-300/60 px-3 py-1.5 text-xs font-medium text-ink-700 transition hover:border-red-300 hover:text-red-700 disabled:opacity-50"
                      >
                        Reject
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {viewing && <DocumentModal item={viewing} onClose={() => setViewing(null)} />}

      {rejecting && (
        <RejectModal
          item={rejecting}
          busy={busyId === rejecting.id}
          onCancel={() => setRejecting(null)}
          onConfirm={(reason) => review(rejecting.id, 'reject', reason)}
        />
      )}
    </>
  );
}

function DocumentModal({ item, onClose }: { item: RealtorQueueItem; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-20 flex items-center justify-center bg-ink-900/50 p-4"
      onClick={onClose}
    >
      <div
        className="flex h-[85vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-ink-300/30 px-5 py-3">
          <h2 className="font-display text-lg text-ink-900">
            Government ID — {item.full_name ?? 'applicant'}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md px-3 py-1.5 text-sm text-ink-500 transition hover:text-ink-900"
          >
            Close
          </button>
        </div>
        <iframe
          title="Government ID document"
          src={`/api/admin/realtors/${item.id}/government-id`}
          className="h-full w-full flex-1 bg-ink-300/10"
        />
      </div>
    </div>
  );
}

function RejectModal({
  item,
  busy,
  onCancel,
  onConfirm,
}: {
  item: RealtorQueueItem;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (reason: string) => void;
}) {
  const [reason, setReason] = useState('');
  const trimmed = reason.trim();

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-ink-900/40 px-4">
      <div className="w-full max-w-md animate-rise rounded-xl bg-white p-6 shadow-xl">
        <h2 className="font-display text-xl text-ink-900">Reject application</h2>
        <p className="mt-1 text-sm text-ink-500">
          The applicant is notified of the reason and can re-apply. A reason is required — use it to
          request anything missing (e.g. a clearer ID).
        </p>
        <textarea
          autoFocus
          rows={4}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Why is this application being rejected, or what's needed to re-apply?"
          className="mt-4 w-full resize-none rounded-md border border-ink-300/60 px-3.5 py-2.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-red-400 focus:ring-2 focus:ring-red-200"
        />
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={busy}
            className="rounded-md px-4 py-2 text-sm font-medium text-ink-500 transition hover:text-ink-900 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(trimmed)}
            disabled={busy || trimmed.length === 0}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? 'Rejecting…' : 'Reject application'}
          </button>
        </div>
      </div>
    </div>
  );
}
