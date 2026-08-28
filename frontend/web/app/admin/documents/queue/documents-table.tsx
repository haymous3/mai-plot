'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import type { DocQueueItem, DocReviewableStatus, DocSource, Pagination } from '@/lib/api';
import { CATEGORY_LABELS, describeDocument, describeOwner, formatFileSize } from '@/lib/document-review';
import { formatDate } from '@/lib/format';

const REVIEW_ERRORS: Record<string, string> = {
  DOCUMENT_NOT_FOUND: 'This document no longer exists.',
  DOCUMENT_NOT_PENDING: 'This document has already been decided.',
  NOTES_REQUIRED_FOR_REJECTION: 'A rejection reason is required.',
  DOCUMENT_STORAGE_UNAVAILABLE: 'The file store is temporarily unavailable.',
  NO_SESSION: 'Your session expired — please sign in again.',
};

export function DocumentsTable({
  items,
  pagination,
  source,
  status,
}: {
  items: DocQueueItem[];
  pagination: Pagination;
  source: DocSource;
  status: DocReviewableStatus;
}) {
  const router = useRouter();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<DocQueueItem | null>(null);
  const [viewing, setViewing] = useState<DocQueueItem | null>(null);

  async function review(item: DocQueueItem, action: 'verify' | 'reject', notes?: string) {
    setBusyId(item.id);
    setError(null);
    try {
      const resp = await fetch(`/api/admin/documents/${item.id}/review`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ action, source: item.source, notes }),
      });
      if (!resp.ok) {
        const body = (await resp.json()) as { error?: string };
        setError(REVIEW_ERRORS[body.error ?? ''] ?? 'Could not complete the review.');
        return;
      }
      setRejecting(null);
      setViewing(null);
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
        {status === 'under_review'
          ? 'No documents have been flagged for manual checking.'
          : source === 'personal'
            ? 'No personal documents awaiting review.'
            : 'No property documents awaiting review.'}
      </div>
    );
  }

  const pageHref = (page: number) =>
    `/admin/documents/queue?source=${source}&status=${status}&page=${page}`;

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
              <th className="px-5 py-3 font-medium">Document</th>
              <th className="px-5 py-3 font-medium">
                {source === 'personal' ? 'Owner' : 'Listing'}
              </th>
              <th className="px-5 py-3 font-medium">Uploaded</th>
              <th className="px-5 py-3 text-right font-medium">Decision</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const busy = busyId === item.id;
              const size = formatFileSize(item.size_bytes);
              return (
                <tr key={item.id} className="border-b border-ink-300/20 last:border-0">
                  <td className="px-5 py-4">
                    <span className="font-medium text-ink-900">{describeDocument(item)}</span>
                    {item.category && (
                      <span className="ml-2 rounded-full bg-ink-900/5 px-2 py-0.5 text-xs text-ink-500">
                        {CATEGORY_LABELS[item.category] ?? item.category}
                      </span>
                    )}
                    {size && <span className="ml-2 text-xs text-ink-300">{size}</span>}
                  </td>
                  <td className="px-5 py-4 text-ink-500">
                    {describeOwner(item)}
                  </td>
                  <td className="px-5 py-4 text-ink-500">{formatDate(item.created_at)}</td>
                  <td className="px-5 py-4">
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => setViewing(item)}
                        className="rounded-md border border-ink-300/60 px-3 py-1.5 text-xs font-medium text-ink-700 transition hover:border-ink-500"
                      >
                        View
                      </button>
                      <button
                        onClick={() => review(item, 'verify')}
                        disabled={busy}
                        className="rounded-md bg-emerald-deep px-3 py-1.5 text-xs font-medium text-bone transition hover:bg-emerald-accent disabled:opacity-50"
                      >
                        {busy ? '…' : 'Verify'}
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
            <PageLink href={pageHref(pagination.page - 1)} disabled={pagination.page <= 1}>
              Previous
            </PageLink>
            <PageLink
              href={pageHref(pagination.page + 1)}
              disabled={pagination.page >= pagination.total_pages}
            >
              Next
            </PageLink>
          </div>
        </div>
      )}

      {viewing && <DocumentModal item={viewing} onClose={() => setViewing(null)} />}

      {rejecting && (
        <RejectModal
          item={rejecting}
          busy={busyId === rejecting.id}
          onCancel={() => setRejecting(null)}
          onConfirm={(notes) => review(rejecting, 'reject', notes)}
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

function DocumentModal({ item, onClose }: { item: DocQueueItem; onClose: () => void }) {
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
          <h2 className="font-display text-lg text-ink-900">{describeDocument(item)}</h2>
          <button
            onClick={onClose}
            className="rounded-md px-3 py-1.5 text-sm text-ink-500 transition hover:text-ink-900"
          >
            Close
          </button>
        </div>
        <iframe
          title={describeDocument(item)}
          src={`/api/admin/documents/${item.id}/file?source=${item.source}`}
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
  item: DocQueueItem;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (notes: string) => void;
}) {
  const [notes, setNotes] = useState('');
  const trimmed = notes.trim();

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-ink-900/40 px-4">
      <div className="w-full max-w-md animate-rise rounded-xl bg-white p-6 shadow-xl">
        <h2 className="font-display text-xl text-ink-900">Reject document</h2>
        <p className="mt-1 text-sm text-ink-500">
          The reason is stored against {describeDocument(item)} and is required.
        </p>
        <textarea
          autoFocus
          rows={4}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Why is this document being rejected?"
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
            {busy ? 'Rejecting…' : 'Reject document'}
          </button>
        </div>
      </div>
    </div>
  );
}
