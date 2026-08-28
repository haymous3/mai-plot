'use client';

import { useSearchParams } from 'next/navigation';
import { useState } from 'react';

import { PasswordField } from '../_components/password-field';
import {
  canSubmitReset,
  PASSWORD_RULES,
  ResetPhase,
  resetPhaseForError,
} from '@/lib/password-reset';

const INLINE_MESSAGES: Record<string, string> = {
  PASSWORD_TOO_WEAK: 'Use at least 8 characters, including an uppercase letter and a number.',
  AUTH_SERVICE_UNAVAILABLE: 'Password reset is temporarily unavailable. Please try again.',
  INVALID_REQUEST: 'Please enter your new password.',
};

export function ResetPasswordClient() {
  const params = useSearchParams();
  const token = params.get('token');

  const [phase, setPhase] = useState<ResetPhase>(token ? 'form' : 'missing');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mismatch = confirm.length > 0 && password !== confirm;
  const canSubmit = canSubmitReset(password, confirm, submitting);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !canSubmit) return;
    setError(null);
    setSubmitting(true);
    try {
      const resp = await fetch('/api/auth/password/reset', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ token, new_password: password }),
      });
      if (resp.ok) {
        setPhase('success');
        return;
      }
      const body = (await resp.json().catch(() => ({}))) as { error?: string };
      const terminal = resetPhaseForError(body.error);
      if (terminal) {
        setPhase(terminal);
        return;
      }
      setError(
        INLINE_MESSAGES[body.error ?? ''] ?? 'Could not reset your password. Please try again.',
      );
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="w-full max-w-sm animate-rise">
      <div className="mb-9 lg:hidden">
        <span className="font-display text-2xl tracking-tight text-emerald-deep">Maihomme</span>
      </div>

      {phase === 'form' && (
        <>
          <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Account recovery</p>
          <h1 className="mt-2 font-display text-3xl text-ink-900">Set a new password</h1>
          <p className="mt-2 text-sm text-ink-500">
            Choose a password you haven&rsquo;t used before. You&rsquo;ll sign in with it straight
            after.
          </p>

          <form onSubmit={onSubmit} className="mt-8 space-y-5" noValidate>
            <div className="space-y-1.5">
              <label htmlFor="new-password" className="block text-sm font-medium text-ink-700">
                New password
              </label>
              <PasswordField
                id="new-password"
                name="new-password"
                autoComplete="new-password"
                required
                value={password}
                onChange={setPassword}
                placeholder="••••••••"
                disabled={submitting}
              />
              <ul className="space-y-1 pt-1">
                {PASSWORD_RULES.map((rule) => {
                  const met = rule.test(password);
                  return (
                    <li
                      key={rule.label}
                      className={`flex items-center gap-2 text-xs ${
                        met ? 'text-emerald-deep' : 'text-ink-500'
                      }`}
                    >
                      <CheckDot met={met} />
                      {rule.label}
                    </li>
                  );
                })}
              </ul>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="confirm-password" className="block text-sm font-medium text-ink-700">
                Confirm new password
              </label>
              <PasswordField
                id="confirm-password"
                name="confirm-password"
                autoComplete="new-password"
                required
                value={confirm}
                onChange={setConfirm}
                placeholder="••••••••"
                disabled={submitting}
              />
              {mismatch && (
                <p className="text-xs text-red-700">Both passwords must match.</p>
              )}
            </div>

            {error && (
              <p role="alert" className="rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={!canSubmit}
              className="flex w-full items-center justify-center rounded-md bg-emerald-deep px-4 py-2.5 text-sm font-medium text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? 'Saving…' : 'Reset password'}
            </button>
          </form>
        </>
      )}

      {phase !== 'form' && (
        <div className="text-center">
          {phase === 'success' && <Success />}
          {phase === 'expired' && <Expired />}
          {phase === 'invalid' && <Invalid />}
          {phase === 'missing' && <Missing />}
        </div>
      )}
    </div>
  );
}

function CheckDot({ met }: { met: boolean }) {
  return met ? (
    <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5 shrink-0" aria-hidden>
      <path
        fillRule="evenodd"
        d="M16.7 5.3a1 1 0 0 1 0 1.4l-7 7a1 1 0 0 1-1.4 0l-3.5-3.5a1 1 0 1 1 1.4-1.4l2.8 2.8 6.3-6.3a1 1 0 0 1 1.4 0Z"
        clipRule="evenodd"
      />
    </svg>
  ) : (
    <span
      aria-hidden
      className="h-3.5 w-3.5 shrink-0 rounded-full border border-ink-300/60"
    />
  );
}

function Icon({
  tone,
  children,
}: {
  tone: 'success' | 'warn' | 'error';
  children: React.ReactNode;
}) {
  const toneClass = {
    success: 'bg-emerald-deep/12 text-emerald-deep',
    warn: 'bg-amber-100 text-amber-700',
    error: 'bg-red-50 text-red-700',
  }[tone];
  return (
    <div className={`mx-auto flex h-14 w-14 items-center justify-center rounded-full ${toneClass}`}>
      {children}
    </div>
  );
}

function Success() {
  return (
    <>
      <Icon tone="success">
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-7 w-7" aria-hidden>
          <path
            fillRule="evenodd"
            d="M16.7 5.3a1 1 0 0 1 0 1.4l-7 7a1 1 0 0 1-1.4 0l-3.5-3.5a1 1 0 1 1 1.4-1.4l2.8 2.8 6.3-6.3a1 1 0 0 1 1.4 0Z"
            clipRule="evenodd"
          />
        </svg>
      </Icon>
      <h1 className="mt-6 font-display text-2xl text-ink-900">Password reset</h1>
      {/*
        No auto-redirect, unlike /verify-email. Reset issues no session by
        design, so the user has to sign in with a password they only just
        invented — being hurried off the confirmation is the wrong moment.
      */}
      <p className="mt-2 text-sm text-ink-500">
        You&rsquo;ve been signed out everywhere else. Sign in with your new password to continue.
      </p>
      <a
        href="/login"
        className="mt-6 inline-flex w-full items-center justify-center rounded-md bg-emerald-deep px-4 py-2.5 text-sm font-medium text-bone transition hover:bg-emerald-accent"
      >
        Go to sign in
      </a>
    </>
  );
}

function Expired() {
  return (
    <>
      <Icon tone="warn">
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-7 w-7" aria-hidden>
          <path
            fillRule="evenodd"
            d="M10 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16Zm.75 4a.75.75 0 0 0-1.5 0v4c0 .3.18.57.46.69l3 1.5a.75.75 0 1 0 .67-1.34l-2.63-1.32V6Z"
            clipRule="evenodd"
          />
        </svg>
      </Icon>
      <h1 className="mt-6 font-display text-2xl text-ink-900">This link has expired</h1>
      <p className="mt-2 text-sm text-ink-500">
        Reset links are valid for 15 minutes. Request a fresh one and we&rsquo;ll email it straight
        away.
      </p>
      <RequestNewLink />
    </>
  );
}

function Invalid() {
  return (
    <>
      <Icon tone="error">
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-7 w-7" aria-hidden>
          <path
            fillRule="evenodd"
            d="M10 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16ZM7.3 7.3a1 1 0 0 1 1.4 0L10 8.6l1.3-1.3a1 1 0 1 1 1.4 1.4L11.4 10l1.3 1.3a1 1 0 0 1-1.4 1.4L10 11.4l-1.3 1.3a1 1 0 0 1-1.4-1.4L8.6 10 7.3 8.7a1 1 0 0 1 0-1.4Z"
            clipRule="evenodd"
          />
        </svg>
      </Icon>
      <h1 className="mt-6 font-display text-2xl text-ink-900">This link isn&rsquo;t valid</h1>
      <p className="mt-2 text-sm text-ink-500">
        It may already have been used, or replaced by a newer one. Only the most recent reset link
        works — request another to continue.
      </p>
      <RequestNewLink />
    </>
  );
}

function Missing() {
  return (
    <>
      <Icon tone="error">
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-7 w-7" aria-hidden>
          <path
            fillRule="evenodd"
            d="M10 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16Zm0 4a1 1 0 0 1 1 1v3a1 1 0 1 1-2 0V7a1 1 0 0 1 1-1Zm0 7.5a1 1 0 1 0 0 2 1 1 0 0 0 0-2Z"
            clipRule="evenodd"
          />
        </svg>
      </Icon>
      <h1 className="mt-6 font-display text-2xl text-ink-900">Missing reset link</h1>
      <p className="mt-2 text-sm text-ink-500">
        Open the link from the reset email we sent you — it carries the code that lets you set a new
        password.
      </p>
      <RequestNewLink />
    </>
  );
}

function RequestNewLink() {
  return (
    <>
      <a
        href="/forgot-password"
        className="mt-6 inline-flex w-full items-center justify-center rounded-md bg-emerald-deep px-4 py-2.5 text-sm font-medium text-bone transition hover:bg-emerald-accent"
      >
        Request a new link
      </a>
      <div className="mt-6 flex items-center justify-center gap-4 text-sm">
        <a href="/login" className="font-medium text-emerald-deep hover:underline">
          Go to sign in
        </a>
        <span className="text-ink-300" aria-hidden>
          ·
        </span>
        <a href="/register" className="font-medium text-emerald-deep hover:underline">
          Create an account
        </a>
      </div>
    </>
  );
}
