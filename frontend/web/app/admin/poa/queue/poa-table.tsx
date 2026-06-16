'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import type { Pagination, PoaQueueItem } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { slaStatus } from '@/lib/sla';

const REVIEW_ERRORS: Record<string, string> = {
  POA_NOT_PENDING: 'This submission is no longer awaiting review.',
  POA_TARGET_NOT_FOUND: 'This submission no longer exists.',
  POA_REASON_REQUIRED: 'A rejection reason is required.',
  NO_SESSION: 'Your session expired — please sign in again.',
};

export function PoaTable({
  items,
  pagination,
}: {
  items: PoaQueueItem[];
  pagination: Pagination;
}) {
  const router = useRouter();
  const now = new Date();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<PoaQueueItem | null>(null);
  const [viewing, setViewing] = useState<PoaQueueItem | null>(null);

  async function review(userId: string, action: 'approve' | 'reject', reason?: string) {
    setBusyId(userId);
    setError(null);
    try {
      const resp = await fetch(`/api/admin/poa/${userId}/review`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ action, reason }),
      });
      if (!resp.ok) {
        const body = (await resp.json()) as { error?: string };
        setError(REVIEW_ERRORS[body.error ?? ''] ?? 'Could not complete the review.');
        return;
      }
      setRejecting(null);
      router.refresh();
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusyId(null);
    }
  }

  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center text-sm text-ink-300">
        No Power-of-Attorney submissions awaiting review.
      </div>
    );
  }

  return (
    <>
      {error && (
        <p role="alert" className="mb-4 rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
          {error}
        </p>
      )}

      <div className="overflow-hidden rounded-lg border border-ink-300/30 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-ink-300/30 text-left text-xs uppercase tracking-wider text-ink-300">
              <th className="px-5 py-3 font-medium">Document owner</th>
              <th className="px-5 py-3 font-medium">Submitted</th>
              <th className="px-5 py-3 font-medium">SLA</th>
              <th className="px-5 py-3 text-right font-medium">Decision</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const busy = busyId === item.user_id;
              const sla = slaStatus(item.submitted_at, now);
              return (
                <tr key={item.user_id} className="border-b border-ink-300/20 last:border-0">
                  <td className="px-5 py-4 font-medium text-ink-900">{item.owner_name ?? '—'}</td>
                  <td className="px-5 py-4 text-ink-500">{formatDate(item.submitted_at)}</td>
                  <td className="px-5 py-4">
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        sla.overdue
                          ? 'bg-red-100 text-red-700'
                          : sla.hoursRemaining < 12
                            ? 'bg-amber-100 text-amber-800'
                            : 'bg-emerald-deep/10 text-emerald-deep'
                      }`}
                    >
                      {sla.label}
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => setViewing(item)}
                        className="rounded-md border border-ink-300/60 px-3 py-1.5 text-xs font-medium text-ink-700 transition hover:border-ink-500"
                      >
                        View document
                      </button>
                      <button
                        onClick={() => review(item.user_id, 'approve')}
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

      {pagination.total_pages > 1 && (
        <div className="mt-5 flex items-center justify-between text-sm text-ink-500">
          <span>
            Page {pagination.page} of {pagination.total_pages}
          </span>
          <div className="flex gap-2">
            <PageLink href={`/admin/poa/queue?page=${pagination.page - 1}`} disabled={pagination.page <= 1}>
              Previous
            </PageLink>
            <PageLink
              href={`/admin/poa/queue?page=${pagination.page + 1}`}
              disabled={pagination.page >= pagination.total_pages}
            >
              Next
            </PageLink>
          </div>
        </div>
      )}

      {viewing && (
        <DocumentModal item={viewing} onClose={() => setViewing(null)} />
      )}

      {rejecting && (
        <RejectModal
          item={rejecting}
          busy={busyId === rejecting.user_id}
          onCancel={() => setRejecting(null)}
          onConfirm={(reason) => review(rejecting.user_id, 'reject', reason)}
        />
      )}
    </>
  );
}

function PageLink({
  href,
  disabled,
  children,
}: {
  href: string;
  disabled: boolean;
  children: React.ReactNode;
}) {
  if (disabled) {
    return (
      <span className="cursor-not-allowed rounded-md border border-ink-300/40 px-3 py-1.5 text-ink-300">
        {children}
      </span>
    );
  }
  return (
    <Link
      href={href}
      className="rounded-md border border-ink-300/60 px-3 py-1.5 text-ink-700 transition hover:border-ink-500"
    >
      {children}
    </Link>
  );
}

function DocumentModal({ item, onClose }: { item: PoaQueueItem; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-ink-900/50 p-4" onClick={onClose}>
      <div
        className="flex h-[85vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-ink-300/30 px-5 py-3">
          <h2 className="font-display text-lg text-ink-900">
            PoA document — {item.owner_name ?? 'Unknown owner'}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md px-3 py-1.5 text-sm text-ink-500 transition hover:text-ink-900"
          >
            Close
          </button>
        </div>
        <iframe
          title="PoA document"
          src={`/api/admin/poa/${item.user_id}/document`}
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
  item: PoaQueueItem;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (reason: string) => void;
}) {
  const [reason, setReason] = useState('');
  const trimmed = reason.trim();

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-ink-900/40 px-4">
      <div className="w-full max-w-md animate-rise rounded-xl bg-white p-6 shadow-xl">
        <h2 className="font-display text-xl text-ink-900">Reject PoA</h2>
        <p className="mt-1 text-sm text-ink-500">
          {item.owner_name ?? 'This seller'} is notified of the reason. A reason is required.
        </p>
        <textarea
          autoFocus
          rows={4}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Why is this Power-of-Attorney being rejected?"
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
            {busy ? 'Rejecting…' : 'Reject PoA'}
          </button>
        </div>
      </div>
    </div>
  );
}
