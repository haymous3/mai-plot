'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

/** Header avatar menu (SCRUM-95): Settings / My Documents / Sign Out. */
export function AvatarMenu() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

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
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-full py-1 pl-1 pr-2 text-bone/90 transition hover:bg-white/10"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-accent text-sm font-semibold text-white">
          👤
        </span>
        <span className="text-left text-xs leading-tight">
          <span className="block font-medium">Account</span>
          <span className="block text-bone/60">Buyer</span>
        </span>
      </button>

      {open && (
        <div className="absolute right-0 z-20 mt-2 w-48 overflow-hidden rounded-xl border border-ink-300/30 bg-white py-1 shadow-lg">
          <Link
            href="/offers"
            className="block px-4 py-2.5 text-sm text-ink-700 transition hover:bg-bone"
            onClick={() => setOpen(false)}
          >
            My Offers
          </Link>
          <Link
            href="/wallet"
            className="block px-4 py-2.5 text-sm text-ink-700 transition hover:bg-bone"
            onClick={() => setOpen(false)}
          >
            My Wallet
          </Link>
          <Link
            href="/settings"
            className="block px-4 py-2.5 text-sm text-ink-700 transition hover:bg-bone"
            onClick={() => setOpen(false)}
          >
            Settings
          </Link>
          <Link
            href="/documents"
            className="block px-4 py-2.5 text-sm text-ink-700 transition hover:bg-bone"
            onClick={() => setOpen(false)}
          >
            My Documents
          </Link>
          <button
            type="button"
            onClick={signOut}
            disabled={busy}
            className="block w-full px-4 py-2.5 text-left text-sm text-red-600 transition hover:bg-bone disabled:opacity-60"
          >
            {busy ? 'Signing out…' : 'Sign Out'}
          </button>
        </div>
      )}
    </div>
  );
}
