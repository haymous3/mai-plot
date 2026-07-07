'use client';

import { useState } from 'react';

/** Save/unsave (favourite) toggle for a listing card (SCRUM-95). Optimistic;
 * reverts on error. Stops the click from following the card's link. */
export function SaveHeart({
  listingId,
  initialSaved,
  className = '',
}: {
  listingId: string;
  initialSaved: boolean;
  className?: string;
}) {
  const [saved, setSaved] = useState(initialSaved);
  const [busy, setBusy] = useState(false);

  async function toggle(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (busy) return;
    const next = !saved;
    setSaved(next);
    setBusy(true);
    try {
      const resp = await fetch(`/api/buyer/listings/${listingId}/save`, {
        method: next ? 'POST' : 'DELETE',
      });
      if (!resp.ok) setSaved(!next); // revert
    } catch {
      setSaved(!next); // revert
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={saved}
      aria-label={saved ? 'Remove from saved' : 'Save property'}
      className={`flex h-8 w-8 items-center justify-center rounded-full bg-white/90 text-base shadow-sm transition hover:bg-white ${className}`}
    >
      <span aria-hidden className={saved ? 'text-red-500' : 'text-ink-400'}>
        {saved ? '♥' : '♡'}
      </span>
    </button>
  );
}
