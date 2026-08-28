'use client';

import { useState } from 'react';

const MESSAGES: Record<string, string> = {
  PASSWORD_RESET_RATE_LIMITED: 'Too many requests. Please wait a little and try again.',
  VALIDATION_ERROR: 'Please enter a valid email address.',
  AUTH_SERVICE_UNAVAILABLE: 'Password reset is temporarily unavailable. Please try again.',
  INVALID_REQUEST: 'Please enter your email address.',
};

export function ForgotPasswordForm({ role }: { role: string }) {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = email.trim();
    if (!trimmed) return;
    setError(null);
    setSubmitting(true);
    try {
      const resp = await fetch('/api/auth/password/forgot', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email: trimmed }),
      });
      if (resp.ok) {
        setSent(true);
        return;
      }
      const body = (await resp.json().catch(() => ({}))) as { error?: string };
      setError(MESSAGES[body.error ?? ''] ?? 'Could not send the link just now. Please try again.');
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  if (sent) {
    return (
      <>
        <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Account recovery</p>
        <h2 className="mt-2 font-display text-3xl text-ink-900">Check your email</h2>

        {/*
          Deliberately generic, and it must stay that way. The backend answers a
          byte-identical 202 for a known and an unknown address so the endpoint
          cannot be used to enumerate accounts — copy that said "we've sent you
          a link" would leak through the UI exactly what the API refuses to.
        */}
        <p className="mt-6 rounded-md bg-emerald-deep/10 px-3.5 py-3 text-sm text-emerald-deep">
          If that email has an account, we&rsquo;ve sent a reset link. Check your inbox — and your
          spam or promotions folder.
        </p>

        <p className="mt-6 text-sm text-ink-500">
          The link is valid for 15 minutes. Didn&rsquo;t get it?{' '}
          {/*
            Since the confirmation above cannot tell the user they mistyped,
            a way back to the form is the only remedy for a typo.
          */}
          <button
            type="button"
            onClick={() => {
              setSent(false);
              setError(null);
            }}
            className="font-medium text-emerald-deep hover:underline"
          >
            Use a different email
          </button>
          .
        </p>

        <p className="mt-8 text-sm text-ink-500">
          Remembered it?{' '}
          <a
            href={`/login?role=${role}`}
            className="font-medium text-emerald-deep hover:underline"
          >
            Back to sign in
          </a>
        </p>
      </>
    );
  }

  return (
    <>
      <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Account recovery</p>
      <h2 className="mt-2 font-display text-3xl text-ink-900">Forgot your password?</h2>
      <p className="mt-2 text-sm text-ink-500">
        Enter the email on your account and we&rsquo;ll send you a link to set a new password.
      </p>

      <form onSubmit={onSubmit} className="mt-8 space-y-5" noValidate>
        <div className="space-y-1.5">
          <label htmlFor="email" className="block text-sm font-medium text-ink-700">
            Email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="w-full rounded-md border border-ink-300/60 bg-white px-3.5 py-2.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
          />
        </div>

        {error && (
          <p role="alert" className="rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting || email.trim().length === 0}
          className="flex w-full items-center justify-center rounded-md bg-emerald-deep px-4 py-2.5 text-sm font-medium text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? 'Sending…' : 'Send reset link'}
        </button>
      </form>

      <p className="mt-8 text-sm text-ink-500">
        Remembered it?{' '}
        <a href={`/login?role=${role}`} className="font-medium text-emerald-deep hover:underline">
          Back to sign in
        </a>
      </p>
    </>
  );
}
