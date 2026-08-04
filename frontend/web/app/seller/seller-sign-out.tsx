'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

/** Seller logout (SCRUM-98) — clears the shared session via /api/auth/logout. */
export function SellerSignOut() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function signOut() {
    setBusy(true);
    try {
      const resp = await fetch('/api/auth/logout', { method: 'POST' });
      const body = (await resp.json()) as { redirect?: string };
      router.replace(body.redirect ?? '/login');
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    // Matches the sidebar nav item (44px, 12px radius, 16px inset) but in
    // `status-danger` — the design gives Logout #e7000b, node 276:434.
    // `text-red-600` was #dc2626, a different red.
    <button
      type="button"
      onClick={signOut}
      disabled={busy}
      className="flex h-11 w-full items-center gap-3 rounded-xl px-4 text-sm font-semibold text-status-danger transition hover:bg-status-danger/5 disabled:opacity-60"
    >
      <span aria-hidden className="flex h-5 w-5 flex-none items-center justify-center">
        ⎋
      </span>
      {busy ? 'Logging out…' : 'Logout'}
    </button>
  );
}
