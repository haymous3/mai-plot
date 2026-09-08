'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

export function SignOutButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function signOut() {
    setBusy(true);
    try {
      const resp = await fetch('/api/admin/logout', { method: 'POST' });
      const body = (await resp.json()) as { redirect?: string };
      router.replace(body.redirect ?? '/admin/login');
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    // Matches the sidebar nav row (44px, 12px radius, 16px inset) in
    // `status-danger`, the same treatment as the seller and realtor rails
    // (SCRUM-217). It was a small bordered pill while the nav was a top bar.
    <button
      type="button"
      onClick={signOut}
      disabled={busy}
      className="flex h-11 w-full items-center gap-3 rounded-xl px-4 text-sm font-semibold text-status-danger transition hover:bg-status-danger/5 disabled:opacity-60"
    >
      <span aria-hidden className="flex h-5 w-5 flex-none items-center justify-center">
        ⎋
      </span>
      {busy ? 'Signing out…' : 'Sign out'}
    </button>
  );
}
