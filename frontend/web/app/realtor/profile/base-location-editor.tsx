'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { BaseLocationPicker } from '@/app/_components/base-location-picker';
import type { BaseLocation } from '@/app/_components/base-location-picker';
import { describeBase } from '@/lib/nigeria-areas';

const CONTROL =
  'block h-11 w-full rounded-lg border border-line bg-white px-3 text-sm text-ink-900 outline-none transition focus:border-emerald-deep focus:ring-2 focus:ring-emerald-deep/20 disabled:cursor-not-allowed disabled:bg-surface-muted';

/**
 * Realtor Profile → Base location (SCRUM-214). Shows where assignments are
 * searched from, and lets the realtor set or move it. Saving refreshes the
 * page so the dashboard nudge (a server read) disappears at once.
 */
export function BaseLocationEditor({ initial }: { initial: BaseLocation | null }) {
  const router = useRouter();
  const [saved, setSaved] = useState<BaseLocation | null>(initial);
  const [editing, setEditing] = useState(initial === null);
  const [draft, setDraft] = useState<BaseLocation | null>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function save() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch('/api/realtor/base-location', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(draft),
      });
      const body = (await resp.json().catch(() => ({}))) as { error_code?: string };
      if (!resp.ok) {
        setError(
          body.error_code === 'LOCATION_OUTSIDE_NIGERIA'
            ? 'Your base location must be in Nigeria.'
            : 'We couldn’t save your base location. Please try again.',
        );
        return;
      }
      setSaved(draft);
      setEditing(false);
      setNote('Base location saved. You’ll be offered inspections within 50 km of it.');
      router.refresh();
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  if (saved && !editing) {
    return (
      <div>
        {note && (
          <p role="status" className="mb-4 rounded-lg bg-emerald-deep/10 px-4 py-3 text-sm text-emerald-deep">
            {note}
          </p>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm font-medium text-ink-900">📍 {describeBase(saved.lat, saved.lng)}</p>
          <button
            type="button"
            onClick={() => {
              setDraft(saved);
              setEditing(true);
              setNote(null);
            }}
            className="rounded-lg border border-line px-4 py-2 text-sm font-semibold text-ink-700 transition hover:border-emerald-deep hover:text-emerald-deep"
          >
            Change
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <BaseLocationPicker
        idPrefix="profile-base"
        value={draft}
        onChange={setDraft}
        controlClassName={CONTROL}
        disabled={busy}
      />
      {error && (
        <p role="alert" className="mt-3 text-sm text-status-danger">
          {error}
        </p>
      )}
      <div className="mt-4 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => void save()}
          disabled={!draft || busy}
          className="rounded-lg bg-emerald-deep px-4 py-2 text-sm font-semibold text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:bg-line disabled:text-ink-400"
        >
          {busy ? 'Saving…' : 'Save base location'}
        </button>
        {saved && (
          <button
            type="button"
            onClick={() => {
              setEditing(false);
              setError(null);
            }}
            disabled={busy}
            className="rounded-lg px-4 py-2 text-sm font-semibold text-ink-500 transition hover:text-ink-700"
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}
