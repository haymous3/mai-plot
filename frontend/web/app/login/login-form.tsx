'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useState } from 'react';

import { PasswordField } from '../_components/password-field';

const MESSAGES: Record<string, string> = {
  INVALID_CREDENTIALS: 'Those sign-in details are incorrect.',
  NOT_ALLOWED: 'Use the admin sign-in for admin accounts.',
  AUTH_SERVICE_UNAVAILABLE: 'Sign-in is temporarily unavailable. Please try again.',
  INVALID_REQUEST: 'Please enter your sign-in details.',
};

/**
 * What each role signs in WITH (SCRUM-207).
 *
 * An approved realtor authenticates with the Maihomme registration number the
 * platform emailed them, not their email address — auth-service refuses the
 * email once a number has been issued. It refuses it with the ordinary
 * "incorrect" error (telling them apart would let a stranger discover which
 * addresses belong to approved realtors), so this label and hint are the only
 * thing standing between a realtor and a mystery. They are load-bearing.
 *
 * A realtor still WAITING on approval has no number and does sign in with their
 * email — the hint says so rather than pretending the field is number-only.
 */
const IDENTIFIER: Record<string, { label: string; placeholder: string; hint?: string }> = {
  buyer: { label: 'Email', placeholder: 'you@example.com' },
  seller: { label: 'Email', placeholder: 'you@example.com' },
  realtor: {
    label: 'Maihomme registration number',
    placeholder: 'MH-R-000123',
    hint: 'The number we emailed you when your account was verified. Not yet verified? Sign in with your email address.',
  },
};

export function LoginForm({ role }: { role: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get('next');
  const [identifier, setIdentifier] = useState('');
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
        body: JSON.stringify({ identifier, password }),
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

  const field = IDENTIFIER[role] ?? IDENTIFIER.buyer;

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      <div className="space-y-1.5">
        <label htmlFor="identifier" className="block text-sm font-medium text-ink-700">
          {field.label}
        </label>
        <input
          id="identifier"
          name="identifier"
          /* Deliberately type="text" for every role, not type="email". A realtor
             types MH-R-000123 here, and an email input would mark that invalid
             and refuse to submit in browsers that enforce it. */
          type="text"
          autoComplete="username"
          required
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          className="w-full rounded-md border border-ink-300/60 bg-white px-3.5 py-2.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
          placeholder={field.placeholder}
        />
        {field.hint && <p className="text-xs leading-5 text-ink-500">{field.hint}</p>}
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <label htmlFor="password" className="block text-sm font-medium text-ink-700">
            Password
          </label>
          {/*
            SCRUM-191. Sits on the label row because that is where it is looked
            for — right next to the field that just failed. The role rides along
            so recovery keeps the same left-panel copy as the screen the user is
            leaving; without it a seller lands on a buyer-flavoured page.
          */}
          <a
            href={`/forgot-password?role=${role}`}
            className="text-sm font-medium text-emerald-deep hover:underline"
          >
            Forgot password?
          </a>
        </div>
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
