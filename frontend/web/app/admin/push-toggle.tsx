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
        className="text-xs text-ink-300"
      >
        Notifications blocked
      </span>
    );
  }

  const on = status === 'on';
  const busy = status === 'busy';
  return (
    <div className="flex items-center gap-2">
      {error && <span className="text-xs text-red-600">{error}</span>}
      <button
        onClick={on ? disable : enable}
        disabled={busy}
        aria-pressed={on}
        className={`rounded-md border px-3 py-1.5 text-xs font-medium transition disabled:opacity-50 ${
          on
            ? 'border-ink-300/60 text-ink-500 hover:border-ink-500 hover:text-ink-900'
            : 'border-emerald-deep/40 text-emerald-deep hover:border-emerald-deep'
        }`}
      >
        {busy ? '…' : on ? 'Disable notifications' : 'Enable notifications'}
      </button>
    </div>
  );
}
