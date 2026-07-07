'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

/** Per-listing actions on My Listings (SCRUM-98): Edit, View, Pause/Resume.
 * Delete is deferred (no soft-delete endpoint yet). */
export function ListingActions({ id, status }: { id: string; status: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const canPause = status === 'active';
  const canResume = status === 'paused';

  async function toggle(method: 'POST' | 'DELETE') {
    setBusy(true);
    try {
      const resp = await fetch(`/api/seller/listings/${id}/pause`, { method });
      if (resp.ok) router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      <Link
        href={`/seller/listings/${id}/edit`}
        className="rounded-lg bg-emerald-deep px-3.5 py-1.5 text-xs font-semibold text-bone transition hover:bg-emerald-accent"
      >
        ✎ Edit
      </Link>
      <Link
        href={`/listings/${id}`}
        className="rounded-lg border border-ink-300/50 px-3.5 py-1.5 text-xs font-medium text-ink-700 transition hover:border-ink-500"
      >
        👁 View
      </Link>
      {canPause && (
        <button
          type="button"
          disabled={busy}
          onClick={() => toggle('POST')}
          className="rounded-lg bg-amber-100 px-3.5 py-1.5 text-xs font-medium text-amber-700 transition hover:bg-amber-200 disabled:opacity-60"
        >
          ⏸ Pause
        </button>
      )}
      {canResume && (
        <button
          type="button"
          disabled={busy}
          onClick={() => toggle('DELETE')}
          className="rounded-lg bg-emerald-deep/10 px-3.5 py-1.5 text-xs font-medium text-emerald-deep transition hover:bg-emerald-deep/20 disabled:opacity-60"
        >
          ▶ Resume
        </button>
      )}
    </div>
  );
}
