'use client';

import { useEffect, useState } from 'react';

import {
  getExistingSubscription,
  isPushSupported,
  registerServiceWorker,
  subscribeToPush,
  unsubscribeFromPush,
} from '@/lib/push';

type Status = 'loading' | 'unsupported' | 'denied' | 'on' | 'off' | 'busy';

/**
 * In-browser notification opt-in (SCRUM-121). Registers the Service Worker on
 * mount (first load), then lets the admin enable/disable Web Push. Permission is
 * requested only when they click Enable — the meaningful action, never on load.
 */
export function PushToggle() {
  const [status, setStatus] = useState<Status>('loading');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!isPushSupported()) {
      setStatus('unsupported');
      return;
    }
    (async () => {
      try {
        await registerServiceWorker();
        if (Notification.permission === 'denied') {
          if (!cancelled) setStatus('denied');
          return;
        }
        const existing = await getExistingSubscription();
        if (!cancelled) setStatus(existing ? 'on' : 'off');
      } catch {
        if (!cancelled) setStatus('unsupported');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function enable() {
    setStatus('busy');
    setError(null);
    try {
      const outcome = await subscribeToPush();
      setStatus(outcome === 'subscribed' ? 'on' : outcome === 'denied' ? 'denied' : 'unsupported');
    } catch {
      setError('Could not enable notifications.');
      setStatus('off');
    }
  }

  async function disable() {
    setStatus('busy');
    setError(null);
    try {
      await unsubscribeFromPush();
      setStatus('off');
    } catch {
      setError('Could not disable notifications.');
      setStatus('on');
    }
  }

  // Nothing to show on browsers without push (or while we check).
  if (status === 'loading' || status === 'unsupported') return null;

  if (status === 'denied') {
    return (
      <span
        title="Notifications are blocked in your browser settings."
        className="px-4 text-xs text-ink-300"
      >
        Notifications blocked
      </span>
    );
  }

  const on = status === 'on';
  const busy = status === 'busy';
  return (
    // Full-width rail row rather than the bordered pill it was in the old top
    // bar (SCRUM-217); the label sits on one line at 256px.
    <div className="flex flex-col gap-1">
      {error && <span className="px-4 text-xs text-red-600">{error}</span>}
      <button
        type="button"
        onClick={on ? disable : enable}
        disabled={busy}
        aria-pressed={on}
        className={`flex h-11 w-full items-center gap-3 rounded-xl px-4 text-sm font-semibold transition disabled:opacity-50 ${
          on
            ? 'text-ink-500 hover:bg-surface-muted'
            : 'text-emerald-deep hover:bg-emerald-deep/5'
        }`}
      >
        <span aria-hidden className="flex h-5 w-5 flex-none items-center justify-center">
          {on ? '🔕' : '🔔'}
        </span>
        {busy ? '…' : on ? 'Mute browser alerts' : 'Enable browser alerts'}
      </button>
    </div>
  );
}
