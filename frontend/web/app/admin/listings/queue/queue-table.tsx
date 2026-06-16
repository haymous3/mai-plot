'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import type { AdminQueueItem, AuthorityFilter, Pagination } from '@/lib/api';
import { formatDate, formatNaira, isPowerOfAttorney } from '@/lib/format';

const REVIEW_ERRORS: Record<string, string> = {
  LISTING_NOT_PENDING_REVIEW: 'This listing is no longer awaiting review.',
  LISTING_NOT_FOUND: 'This listing no longer exists.',
  COMMENT_REQUIRED_FOR_REJECTION: 'A rejection comment is required.',
  NO_SESSION: 'Your session expired — please sign in again.',
};

function queueHref(authority: AuthorityFilter | null, page: number): string {
  const params = new URLSearchParams();
  if (authority) params.set('authority', authority);
  if (page > 1) params.set('page', String(page));
  const qs = params.toString();
  return qs ? `/admin/listings/queue?${qs}` : '/admin/listings/queue';
}

export function QueueTable({
  items,
  pagination,
  authority,
}: {
  items: AdminQueueItem[];
  pagination: Pagination;
  authority: AuthorityFilter | null;
}) {
  const router = useRouter();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<AdminQueueItem | null>(null);

  async function review(id: string, action: 'approve' | 'reject', comment?: string) {
    setBusyId(id);
    setError(null);
    try {
      const resp = await fetch(`/api/admin/listings/${id}/review`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ action, comment }),
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
        Nothing awaiting review.
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
              <th className="px-5 py-3 font-medium">Listing</th>
              <th className="px-5 py-3 font-medium">Location</th>
              <th className="px-5 py-3 font-medium">Price</th>
              <th className="px-5 py-3 font-medium">Submitted</th>
              <th className="px-5 py-3 text-right font-medium">Decision</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const poa = isPowerOfAttorney(item.seller_authority_type);
              const busy = busyId === item.id;
              return (
                <tr key={item.id} className="border-b border-ink-300/20 last:border-0">
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-ink-900">{item.title}</span>
                      {poa && (
                        <span className="rounded-sm bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800">
                          PoA
                        </span>
                      )}
                      {item.sale_type === 'distress' && (
                        <span className="rounded-sm bg-emerald-deep/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-deep">
                          Distress
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-5 py-4 text-ink-500">
                    {item.lga}, {item.state}
                  </td>
                  <td className="px-5 py-4 tabular-nums text-ink-900">
                    {formatNaira(item.asking_price_kobo)}
                  </td>
                  <td className="px-5 py-4 text-ink-500">{formatDate(item.created_at)}</td>
                  <td className="px-5 py-4">
                    <div className="flex justify-end gap-2">
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

      {/* Pagination */}
      {pagination.total_pages > 1 && (
        <div className="mt-5 flex items-center justify-between text-sm text-ink-500">
          <span>
            Page {pagination.page} of {pagination.total_pages}
          </span>
          <div className="flex gap-2">
            <PageLink
              href={queueHref(authority, pagination.page - 1)}
              disabled={pagination.page <= 1}
            >
              Previous
            </PageLink>
            <PageLink
              href={queueHref(authority, pagination.page + 1)}
              disabled={pagination.page >= pagination.total_pages}
            >
              Next
            </PageLink>
          </div>
        </div>
      )}

      {rejecting && (
        <RejectModal
          item={rejecting}
          busy={busyId === rejecting.id}
          onCancel={() => setRejecting(null)}
          onConfirm={(comment) => review(rejecting.id, 'reject', comment)}
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

function RejectModal({
  item,
  busy,
  onCancel,
  onConfirm,
}: {
  item: AdminQueueItem;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (comment: string) => void;
}) {
  const [comment, setComment] = useState('');
  const trimmed = comment.trim();

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-ink-900/40 px-4">
      <div className="w-full max-w-md animate-rise rounded-xl bg-white p-6 shadow-xl">
        <h2 className="font-display text-xl text-ink-900">Reject listing</h2>
        <p className="mt-1 text-sm text-ink-500">
          &ldquo;{item.title}&rdquo; — the seller sees this reason. A comment is required.
        </p>
        <textarea
          autoFocus
          rows={4}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Why is this listing being rejected?"
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
            {busy ? 'Rejecting…' : 'Reject listing'}
          </button>
        </div>
      </div>
    </div>
  );
}
