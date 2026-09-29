'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

import { AccountSwitch } from '@/app/_components/account-switch';

/**
 * Header avatar menu (SCRUM-95): My Offers / My Wallet / Settings / Sign Out.
 *
 * SCRUM-237: CLICK ONLY, behind a hamburger beside "Account". SCRUM-232 had
 * it open on hover with the click toggle kept for touch — so on desktop the
 * hover opened it and the click that followed CLOSED it again. Hover is gone;
 * one click (anywhere on the trigger) opens, a second click, a click outside
 * or Escape closes.
 */
export function AvatarMenu() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
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
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={open ? 'Close account menu' : 'Open account menu'}
        className={`flex items-center gap-2 rounded-full py-1 pl-1 pr-2 text-bone/90 transition hover:bg-white/10 ${
          open ? 'bg-white/10' : ''
        }`}
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-deep text-sm font-semibold text-white">
          👤
        </span>
        <span className="text-left text-xs leading-tight">
          <span className="block font-medium">Account</span>
          <span className="block text-bone/60">Buyer</span>
        </span>
        {/* The hamburger says "this opens a menu" now that hover no longer
            does it for you; it turns into a close mark while open. */}
        <span className="ml-1 flex h-7 w-7 items-center justify-center rounded-full border border-white/20">
          <svg viewBox="0 0 20 20" fill="none" aria-hidden className="h-4 w-4">
            {open ? (
              <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            ) : (
              <path d="M3.5 6h13M3.5 10h13M3.5 14h13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            )}
          </svg>
        </span>
      </button>

      {open && (
        // w-64 rather than w-48 since SCRUM-236: the account switch row carries
        // a one-line description under its label.
        <div role="menu" className="absolute right-0 z-20 mt-2 w-64 overflow-hidden rounded-xl border border-ink-300/30 bg-white py-1 shadow-lg">
          <AccountSwitch current="buyer" variant="menu" onNavigate={() => setOpen(false)} />
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
          {/*
            SCRUM-232: "My Documents" is hidden for now (product decision). The
            /documents route and its page are untouched — only the entry point
            is removed — so restoring it is uncommenting this link.
          <Link
            href="/documents"
            className="block px-4 py-2.5 text-sm text-ink-700 transition hover:bg-bone"
            onClick={() => setOpen(false)}
          >
            My Documents
          </Link>
          */}
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
