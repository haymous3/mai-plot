'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

/**
 * Header avatar menu (SCRUM-95): My Offers / My Wallet / Settings / Sign Out.
 *
 * SCRUM-232: opens on HOVER. The wrapper (button + dropdown) owns the
 * mouseenter/mouseleave pair so the pointer can travel from the trigger down
 * into the menu. Two details keep that travel from closing it:
 *   - the dropdown's visual gap is PADDING on the panel wrapper, not a margin,
 *     so the 8px between button and panel is still inside the hover area;
 *   - leaving starts a short grace timer (CLOSE_DELAY_MS) instead of closing
 *     at once, and re-entering cancels it — a pointer that overshoots the
 *     edge by a few pixels does not lose the menu.
 * The click toggle is kept: touch screens have no hover, so without it the
 * menu would be unreachable on a phone. Desktop users never notice the click
 * path — hover has already opened it by the time they press.
 */
const CLOSE_DELAY_MS = 250;

export function AvatarMenu() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function cancelClose() {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }
  function hoverIn() {
    cancelClose();
    setOpen(true);
  }
  function hoverOut() {
    cancelClose();
    closeTimer.current = setTimeout(() => setOpen(false), CLOSE_DELAY_MS);
  }

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => {
      document.removeEventListener('mousedown', onClick);
      cancelClose();
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
    <div
      ref={ref}
      className="relative"
      onMouseEnter={hoverIn}
      onMouseLeave={hoverOut}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-full py-1 pl-1 pr-2 text-bone/90 transition hover:bg-white/10"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-deep text-sm font-semibold text-white">
          👤
        </span>
        <span className="text-left text-xs leading-tight">
          <span className="block font-medium">Account</span>
          <span className="block text-bone/60">Buyer</span>
        </span>
      </button>

      {open && (
        <div className="absolute right-0 z-20 pt-2">
          <div className="w-48 overflow-hidden rounded-xl border border-ink-300/30 bg-white py-1 shadow-lg">
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
        </div>
      )}
    </div>
  );
}
