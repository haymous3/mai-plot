'use client';

import { useState } from 'react';

import type { NotificationPreferences } from '@/lib/api';

type Channel = keyof NotificationPreferences;

const CHANNELS: { key: Channel; label: string; description: string }[] = [
  {
    key: 'email_enabled',
    label: 'Email',
    description: 'Transaction milestones and document updates by email.',
  },
  {
    key: 'sms_enabled',
    label: 'SMS',
    description: 'Critical alerts (deal accepted, loan approved) by text message.',
  },
  {
    key: 'push_enabled',
    label: 'Push',
    description: 'In-browser push notifications when Maihomme is closed.',
  },
];

/**
 * Notification channel toggles (SCRUM-125). Each switch optimistically PATCHes the
 * one channel it controls and reverts if the backend rejects it. in_app is not
 * shown — it's always delivered and has no backend flag.
 */
export function PreferencesForm({ initial }: { initial: NotificationPreferences }) {
  const [prefs, setPrefs] = useState<NotificationPreferences>(initial);
  const [busy, setBusy] = useState<Channel | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle(channel: Channel) {
    const next = !prefs[channel];
    setPrefs((p) => ({ ...p, [channel]: next }));
    setBusy(channel);
    setError(null);
    try {
      const resp = await fetch('/api/admin/notifications/preferences', {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ [channel]: next }),
      });
      if (!resp.ok) {
        setPrefs((p) => ({ ...p, [channel]: !next })); // revert
        setError('Could not save your preference. Please try again.');
        return;
      }
      // Trust the backend's full new state.
      const data = (await resp.json()) as NotificationPreferences;
      setPrefs(data);
    } catch {
      setPrefs((p) => ({ ...p, [channel]: !next }));
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="rounded-lg border border-ink-300/30 bg-white">
      {error && (
        <p role="alert" className="border-b border-red-100 bg-red-50 px-5 py-3 text-sm text-red-700">
          {error}
        </p>
      )}
      <ul>
        {CHANNELS.map((channel) => {
          const on = prefs[channel.key];
          return (
            <li
              key={channel.key}
              className="flex items-center justify-between gap-4 border-b border-ink-300/15 px-5 py-4 last:border-0"
            >
              <div>
                <p className="text-sm font-medium text-ink-900">{channel.label}</p>
                <p className="mt-0.5 text-sm text-ink-500">{channel.description}</p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={on}
                aria-label={`${channel.label} notifications`}
                disabled={busy === channel.key}
                onClick={() => toggle(channel.key)}
                className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition disabled:opacity-50 ${
                  on ? 'bg-emerald-deep' : 'bg-ink-300/50'
                }`}
              >
                <span
                  className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition ${
                    on ? 'translate-x-5' : 'translate-x-0.5'
                  }`}
                />
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
