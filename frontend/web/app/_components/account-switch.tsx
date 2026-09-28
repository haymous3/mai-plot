'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

/**
 * Buyer ↔ seller account switch — SCRUM-236.
 *
 * One person, one sign-in: the buyer and seller accounts share an email and a
 * password, and this is the only place a person moves between them. Rendered
 * in the buyer header's account menu and in the seller rail.
 *
 * Reads `available_roles` from /auth/me on mount. Until that answers, nothing
 * renders — a "Create a seller account" that flips to "Switch to seller" a
 * moment later would invite the wrong click. A failed read also renders
 * nothing: the rest of the menu still works, and switching is not a thing
 * anyone needs to do urgently.
 *
 * The OTHER role is either
 *   - held      → a button that swaps the session and goes to that home, or
 *   - not held  → a link to /add-account, which explains what carries over
 *                 (and, without a verified NIN, why it cannot happen yet)
 *                 before anything is created. Creating an account is never a
 *                 single stray click from a hover menu.
 */

type Current = 'buyer' | 'seller';

const LABEL: Record<Current, string> = { buyer: 'buyer', seller: 'seller' };
const BLURB: Record<Current, string> = {
  buyer: 'Browse, make offers, apply for financing',
  seller: 'List property and manage your offers',
};

export function AccountSwitch({
  current,
  variant,
  onNavigate,
}: {
  current: Current;
  variant: 'menu' | 'rail';
  /** Lets the host menu close itself when a link is followed. */
  onNavigate?: () => void;
}) {
  const router = useRouter();
  const other: Current = current === 'buyer' ? 'seller' : 'buyer';
  const [held, setHeld] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    fetch('/api/auth/me', { cache: 'no-store' })
      .then(async (resp) => {
        if (!resp.ok) return;
        const body = (await resp.json()) as { available_roles?: unknown };
        const roles = Array.isArray(body.available_roles) ? body.available_roles : [];
        if (live) setHeld(roles.includes(other));
      })
      .catch(() => {
        // Degrade to no switch at all; see the component note.
      });
    return () => {
      live = false;
    };
  }, [other]);

  async function switchAccount() {
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch('/api/auth/switch-role', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ role: other }),
      });
      const body = (await resp.json().catch(() => ({}))) as { redirect?: string };
      if (resp.ok && body.redirect) {
        onNavigate?.();
        router.replace(body.redirect);
        router.refresh();
        return;
      }
      setError('Could not switch accounts. Please try again.');
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  if (held === null) return null;

  const title = held ? `Switch to ${LABEL[other]} account` : `Create a ${LABEL[other]} account`;

  if (variant === 'rail') {
    const cls =
      'flex h-11 w-full items-center gap-3 rounded-xl border border-emerald-deep/25 px-4 text-left text-sm font-semibold text-emerald-deep transition hover:bg-emerald-deep/5 disabled:opacity-60';
    return (
      <div>
        {held ? (
          <button type="button" onClick={switchAccount} disabled={busy} className={cls}>
            <SwapGlyph />
            {busy ? 'Switching…' : title}
          </button>
        ) : (
          <Link href={`/add-account?role=${other}`} className={cls} onClick={onNavigate}>
            <PlusGlyph />
            {title}
          </Link>
        )}
        {error && (
          <p role="alert" className="mt-1.5 px-1 text-xs text-status-danger">
            {error}
          </p>
        )}
      </div>
    );
  }

  const rowCls =
    'flex w-full items-start gap-3 px-4 py-3 text-left transition hover:bg-bone disabled:opacity-60';
  const body = (
    <>
      <span className="mt-0.5 flex h-7 w-7 flex-none items-center justify-center rounded-full bg-emerald-deep/10 text-emerald-deep">
        {held ? <SwapGlyph /> : <PlusGlyph />}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-ink-buyer">
          {busy ? 'Switching…' : title}
        </span>
        <span className="mt-0.5 block text-xs leading-4 text-ink-500">{BLURB[other]}</span>
      </span>
    </>
  );
  return (
    <div className="border-b border-line">
      {held ? (
        <button type="button" onClick={switchAccount} disabled={busy} className={rowCls}>
          {body}
        </button>
      ) : (
        <Link href={`/add-account?role=${other}`} className={rowCls} onClick={onNavigate}>
          {body}
        </Link>
      )}
      {error && (
        <p role="alert" className="px-4 pb-2.5 text-xs text-status-danger">
          {error}
        </p>
      )}
    </div>
  );
}

function SwapGlyph() {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden className="h-4 w-4 flex-none">
      <path
        d="M4 7h11m0 0-3-3m3 3-3 3M16 13H5m0 0 3-3m-3 3 3 3"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function PlusGlyph() {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden className="h-4 w-4 flex-none">
      <path d="M10 4v12M4 10h12" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}
