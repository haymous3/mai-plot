'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useState } from 'react';

import { PasswordField } from '../_components/password-field';

const MESSAGES: Record<string, string> = {
  INVALID_CREDENTIALS: 'Email or password is incorrect.',
  NOT_ALLOWED: 'Use the admin sign-in for admin accounts.',
  AUTH_SERVICE_UNAVAILABLE: 'Sign-in is temporarily unavailable. Please try again.',
  INVALID_REQUEST: 'Please enter your email and password.',
};

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get('next');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const resp = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const body = (await resp.json()) as { ok?: boolean; redirect?: string; error?: string };
      if (resp.ok && body.ok && body.redirect) {
        // Only follow a same-origin relative `next` to avoid an open redirect.
        // Reject protocol-relative ("//host") and backslash ("/\\host") forms —
        // browsers treat those as absolute cross-origin URLs.
        const isSafeNext =
          typeof next === 'string' &&
          next.startsWith('/') &&
          !next.startsWith('//') &&
          !next.startsWith('/\\');
        const dest = isSafeNext ? (next as string) : body.redirect;
        router.replace(dest);
        router.refresh();
        return;
      }
      setError(MESSAGES[body.error ?? ''] ?? 'Could not sign in. Please try again.');
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
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
          className="w-full rounded-md border border-ink-300/60 bg-white px-3.5 py-2.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
          placeholder="you@example.com"
        />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="password" className="block text-sm font-medium text-ink-700">
          Password
        </label>
        <PasswordField
          id="password"
          name="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={setPassword}
          placeholder="••••••••"
        />
      </div>

      {error && (
        <p role="alert" className="rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="flex w-full items-center justify-center rounded-md bg-emerald-deep px-4 py-2.5 text-sm font-medium text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:opacity-60"
      >
        {submitting ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  );
}
