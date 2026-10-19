'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

/** Buyer sign-out — the bottom row of the buyer rail (SCRUM-248). Styled as the
 * seller rail's Logout row; posts to the buyer BFF logout. */
export function BuyerSignOut() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function signOut() {
    setBusy(true);
    try {
      const resp = await fetch('/api/buyer/logout', { method: 'POST' });
      const body = (await resp.json()) as { redirect?: string };
      router.replace(body.redirect ?? '/login');
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={signOut}
      disabled={busy}
      className="flex h-11 w-full items-center gap-3 rounded-xl px-4 text-sm font-semibold text-status-danger transition hover:bg-status-danger/5 disabled:opacity-60"
    >
      <span aria-hidden className="flex h-5 w-5 flex-none items-center justify-center">
        ⎋
      </span>
      {busy ? 'Signing out…' : 'Sign Out'}
    </button>
  );
}
