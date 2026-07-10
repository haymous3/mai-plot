'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

/** Realtor logout (SCRUM-140) — clears the shared session via /api/auth/logout.
 * Mirrors the seller sign-out. */
export function RealtorSignOut() {
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
    <button
      type="button"
      onClick={signOut}
      disabled={busy}
      className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-red-600 transition hover:bg-red-50 disabled:opacity-60"
    >
      <span aria-hidden>⎋</span> {busy ? 'Logging out…' : 'Logout'}
    </button>
  );
}
