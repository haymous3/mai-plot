'use client';

import { useRouter } from 'next/navigation';
import { useMemo, useRef, useState } from 'react';

import { DOCUMENT_TYPE_LABELS, type SellerDocument } from '@/lib/api';

type Tab = 'all' | 'verified' | 'pending' | 'rejected';
const TABS: { key: Tab; label: string }[] = [
  { key: 'all', label: 'All Documents' },
  { key: 'verified', label: 'Verified' },
  { key: 'pending', label: 'Pending' },
  { key: 'rejected', label: 'Rejected' },
];

// The backend has 4 statuses; the design groups under_review with pending and
// surfaces failed as "Rejected".
function bucket(status: string): Exclude<Tab, 'all'> {
  if (status === 'verified') return 'verified';
  if (status === 'failed') return 'rejected';
  return 'pending';
}

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  verified: { label: '✓ Verified', cls: 'bg-emerald-deep/10 text-emerald-deep' },
  pending: { label: '◷ Pending Review', cls: 'bg-amber-50 text-amber-700' },
  under_review: { label: '◷ Under Review', cls: 'bg-amber-50 text-amber-700' },
  failed: { label: '✕ Rejected', cls: 'bg-red-50 text-red-700' },
};

export function DocumentsList({ documents }: { documents: SellerDocument[] }) {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>('all');
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const visible = useMemo(
    () => (tab === 'all' ? documents : documents.filter((d) => bucket(d.verification_status) === tab)),
    [documents, tab],
  );

  return (
    <div>
      <div className="mt-6 flex flex-wrap gap-1 rounded-xl border border-line bg-surface-card p-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
              tab === t.key ? 'bg-emerald-deep text-bone' : 'text-ink-600 hover:bg-bone'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}

      <div className="mt-4 space-y-3">
        {visible.length === 0 ? (
          <div className="rounded-xl border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center text-sm text-ink-500">
            No documents in this view.
          </div>
        ) : (
          visible.map((d) => (
            <DocumentCard
              key={d.id}
              doc={d}
              busy={busyId === d.id}
              onReupload={async (file) => {
                setBusyId(d.id);
                setError(null);
                try {
                  const form = new FormData();
                  form.set('document_type', d.document_type);
                  form.set('file', file);
                  const resp = await fetch(`/api/seller/listings/${d.listing_id}/documents`, {
                    method: 'POST',
                    body: form,
                  });
                  if (!resp.ok) {
                    const body = (await resp.json().catch(() => ({}))) as { message?: string };
                    setError(body.message ?? 'Re-upload failed. Please retry.');
                    return;
                  }
                  router.refresh();
                } finally {
                  setBusyId(null);
                }
              }}
            />
          ))
        )}
      </div>
    </div>
  );
}

function DocumentCard({
  doc,
  busy,
  onReupload,
}: {
  doc: SellerDocument;
  busy: boolean;
  onReupload: (file: File) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const badge = STATUS_BADGE[doc.verification_status] ?? {
    label: doc.verification_status,
    cls: 'bg-ink-300/20 text-ink-600',
  };
  const rejected = doc.verification_status === 'failed';
  const verified = doc.verification_status === 'verified';

  return (
    <div className="rounded-2xl border border-line bg-surface-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium text-ink-900">
            {DOCUMENT_TYPE_LABELS[doc.document_type] ?? doc.document_type}
          </p>
          <p className="text-xs text-ink-500">
            {doc.property_title ?? 'Property'} · uploaded {new Date(doc.created_at).toLocaleDateString()}
          </p>
        </div>
        <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${badge.cls}`}>
          {badge.label}
        </span>
      </div>

      {rejected && doc.verification_notes && (
        <div className="mt-3 rounded-lg bg-red-50 px-3 py-2">
          <p className="text-xs font-medium text-red-700">Admin Feedback</p>
          <p className="text-sm text-red-700">{doc.verification_notes}</p>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {verified && (
          <a
            href={`/api/seller/documents/${doc.id}/view`}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg border border-ink-300/50 px-3.5 py-1.5 text-xs font-medium text-ink-700 transition hover:border-ink-500"
          >
            👁 View
          </a>
        )}
        {rejected && (
          <button
            type="button"
            disabled={busy}
            onClick={() => fileRef.current?.click()}
            className="rounded-lg bg-emerald-deep px-3.5 py-1.5 text-xs font-semibold text-bone transition hover:bg-emerald-accent disabled:opacity-60"
          >
            ⭱ {busy ? 'Uploading…' : 'Re-upload'}
          </button>
        )}
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf,image/jpeg,image/png"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onReupload(f);
            e.target.value = '';
          }}
        />
      </div>
    </div>
  );
}
