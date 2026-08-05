'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

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
      onClick={signOut}
      disabled={busy}
      className="rounded-md border border-ink-300/50 px-3 py-1.5 text-xs font-medium text-ink-700 transition hover:border-ink-500 hover:text-ink-buyer disabled:opacity-60"
    >
      {busy ? 'Signing out…' : 'Sign out'}
    </button>
  );
}
