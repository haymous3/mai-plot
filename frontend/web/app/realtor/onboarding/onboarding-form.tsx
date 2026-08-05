'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

// Realtor credential submission (SCRUM-156). Post-verification home for what the
// old register funnel collected inline (removed in SCRUM-155): ESVARBON number,
// coverage area, and a credentials document. POSTs to /api/realtor/onboarding
// (→ realtor-service POST /realtors) and lands the realtor on their portal,
// where a "pending approval" banner takes over until the team approves them.

const ERRORS: Record<string, string> = {
  REALTOR_ALREADY_REGISTERED: 'A realtor application already exists for this account.',
  STORAGE_UNAVAILABLE: 'Document upload is temporarily unavailable. Please retry.',
  INVALID_CREDENTIAL: 'That document must be a PDF, PNG, or JPG under 5MB.',
  REALTOR_SERVICE_UNAVAILABLE: 'Onboarding is temporarily unavailable. Please retry.',
  NO_SESSION: 'Your session has expired. Please sign in again.',
};

export function RealtorOnboardingForm() {
  const router = useRouter();
  const [esvarbon, setEsvarbon] = useState('');
  const [coverage, setCoverage] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canSubmit = esvarbon.trim().length > 0 && coverage.trim().length > 0 && file !== null;

  async function submit() {
    if (!file) return;
    setError(null);
    setBusy(true);
    try {
      const form = new FormData();
      form.append('esvarbon_number', esvarbon.trim());
      coverage
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .forEach((state) => form.append('coverage_states', state));
      form.append('file', file);

      const resp = await fetch('/api/realtor/onboarding', { method: 'POST', body: form });
      if (resp.ok) {
        router.replace('/realtor');
        router.refresh();
        return;
      }
      const body = (await resp.json().catch(() => ({}))) as { error_code?: string };
      const code = body.error_code ?? '';
      // Any CREDENTIAL_* validation code maps to the same document-format hint.
      const message = code.startsWith('CREDENTIAL')
        ? ERRORS.INVALID_CREDENTIAL
        : (ERRORS[code] ?? 'Could not submit your credentials. Please retry.');
      setError(message);
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-6 max-w-xl rounded-card-sm border border-line bg-surface-card p-6 sm:p-8">
      <label className="block text-sm font-medium text-ink-700">
        ESVARBON License Number <span className="text-red-500">*</span>
      </label>
      <input
        value={esvarbon}
        onChange={(e) => setEsvarbon(e.target.value)}
        placeholder="ESV/2024/123456"
        className="mt-2 w-full rounded-xl border border-line-strong bg-surface-card px-4 py-3 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
      />
      <p className="mt-1.5 text-xs text-ink-500">
        Your Estate Surveyors and Valuers Registration Board licence number.
      </p>

      <label className="mt-5 block text-sm font-medium text-ink-700">
        Professional Credentials <span className="text-red-500">*</span>
      </label>
      <label className="mt-1.5 flex cursor-pointer flex-col items-center gap-1 rounded-xl border border-dashed border-ink-300/70 px-4 py-8 text-center transition hover:border-emerald-accent">
        <span aria-hidden className="text-2xl text-ink-500">
          ⬆
        </span>
        <span className="text-sm font-medium text-ink-900">
          {file ? file.name : 'Upload credentials'}
        </span>
        <span className="text-xs text-ink-500">
          Licence, certification, or registration (PDF/PNG/JPG, max 5MB)
        </span>
        <input
          type="file"
          accept="application/pdf,image/png,image/jpeg"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </label>

      <label className="mt-5 block text-sm font-medium text-ink-700">
        Coverage Area <span className="text-red-500">*</span>
      </label>
      <input
        value={coverage}
        onChange={(e) => setCoverage(e.target.value)}
        placeholder="e.g., Lagos, Lekki, Victoria Island"
        className="mt-2 w-full rounded-xl border border-line-strong bg-surface-card px-4 py-3 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
      />
      <p className="mt-1.5 text-xs text-ink-500">Comma-separated areas where you provide services.</p>

      {error && (
        <p role="alert" className="mt-4 rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
          {error}
        </p>
      )}
      <button
        type="button"
        disabled={busy || !canSubmit}
        onClick={submit}
        className="mt-6 w-full rounded-lg bg-emerald-deep px-4 py-3 text-sm font-semibold text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto sm:px-8"
      >
        {busy ? 'Submitting…' : 'Submit for review'}
      </button>
    </div>
  );
}
