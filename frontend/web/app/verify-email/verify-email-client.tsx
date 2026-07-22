'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';

type Phase = 'verifying' | 'success' | 'expired' | 'invalid' | 'missing' | 'error';

// How the BFF's error codes map to a terminal phase. Anything unrecognised is
// treated as a transient error (retryable) rather than a dead link.
function phaseForError(code: string | undefined): Phase {
  switch (code) {
    case 'EMAIL_TOKEN_EXPIRED':
      return 'expired';
    case 'EMAIL_TOKEN_INVALID':
      return 'invalid';
    case 'AUTH_SERVICE_UNAVAILABLE':
    case 'INVALID_REQUEST':
      return 'error';
    default:
      return 'error';
  }
}

export function VerifyEmailClient() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get('token');

  const [phase, setPhase] = useState<Phase>(token ? 'verifying' : 'missing');
  const [redirect, setRedirect] = useState<string | null>(null);
  // Guard against the effect firing twice (React 18 strict mode) burning the
  // single-use token on the first, throwaway render.
  const startedRef = useRef(false);

  const verify = useCallback(async () => {
    if (!token) {
      setPhase('missing');
      return;
    }
    setPhase('verifying');
    try {
      const resp = await fetch('/api/auth/verify-email', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ token }),
      });
      const body = (await resp.json().catch(() => ({}))) as {
        ok?: boolean;
        redirect?: string;
        error?: string;
      };
      if (resp.ok && body.ok && body.redirect) {
        setRedirect(body.redirect);
        setPhase('success');
        return;
      }
      setPhase(phaseForError(body.error));
    } catch {
      setPhase('error');
    }
  }, [token]);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    void verify();
  }, [verify]);

  // On success, hand the now-signed-in user to their dashboard shortly after
  // the confirmation shows.
  useEffect(() => {
    if (phase !== 'success' || !redirect) return;
    const t = setTimeout(() => {
      router.replace(redirect);
      router.refresh();
    }, 1400);
    return () => clearTimeout(t);
  }, [phase, redirect, router]);

  return (
    <div className="w-full max-w-sm animate-rise text-center">
      <div className="mb-9">
        <span className="font-display text-2xl tracking-tight text-emerald-deep">Maiplot</span>
      </div>

      {phase === 'verifying' && <Verifying />}
      {phase === 'success' && <Success redirect={redirect} />}
      {phase === 'expired' && <Expired />}
      {phase === 'invalid' && <Invalid />}
      {phase === 'missing' && <Missing />}
      {phase === 'error' && <ErrorState onRetry={verify} />}
    </div>
  );
}

function Icon({ tone, children }: { tone: 'neutral' | 'success' | 'warn' | 'error'; children: React.ReactNode }) {
  const toneClass = {
    neutral: 'bg-ink-300/20 text-ink-500',
    success: 'bg-emerald-accent/12 text-emerald-deep',
    warn: 'bg-amber-100 text-amber-700',
    error: 'bg-red-50 text-red-700',
  }[tone];
  return (
    <div className={`mx-auto flex h-14 w-14 items-center justify-center rounded-full ${toneClass}`}>
      {children}
    </div>
  );
}

function Verifying() {
  return (
    <>
      <Icon tone="neutral">
        <span
          aria-hidden
          className="h-6 w-6 animate-spin rounded-full border-2 border-ink-300/50 border-t-emerald-deep"
        />
      </Icon>
      <h1 className="mt-6 font-display text-2xl text-ink-900">Confirming your email…</h1>
      <p className="mt-2 text-sm text-ink-500">This only takes a moment.</p>
    </>
  );
}

function Success({ redirect }: { redirect: string | null }) {
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
      <h1 className="mt-6 font-display text-2xl text-ink-900">You&rsquo;re verified</h1>
      <p className="mt-2 text-sm text-ink-500">Your email is confirmed. Taking you to your dashboard…</p>
      {redirect && (
        <a
          href={redirect}
          className="mt-6 inline-flex w-full items-center justify-center rounded-md bg-emerald-deep px-4 py-2.5 text-sm font-medium text-bone transition hover:bg-emerald-accent"
        >
          Continue
        </a>
      )}
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
        Verification links are valid for a short time. Request a fresh one to finish setting up your
        account.
      </p>
      {/* Resend is not built yet (needs POST /auth/verify/email/resend, tracked
          in its own backend ticket). Shown but disabled so the action isn't a
          dead click; sign-in remains the working path. */}
      <button
        type="button"
        disabled
        title="Resend will be available soon"
        className="mt-6 inline-flex w-full cursor-not-allowed items-center justify-center rounded-md bg-emerald-deep/40 px-4 py-2.5 text-sm font-medium text-bone"
      >
        Resend email
      </button>
      <p className="mt-1.5 text-xs text-ink-300">Resend is coming soon.</p>
      <NavLinks />
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
        It may have already been used or the link is incomplete. If you&rsquo;ve already verified,
        just sign in.
      </p>
      <NavLinks />
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
      <h1 className="mt-6 font-display text-2xl text-ink-900">Missing verification link</h1>
      <p className="mt-2 text-sm text-ink-500">
        Open the link from the verification email we sent you — it carries the code that confirms
        your account.
      </p>
      <NavLinks />
    </>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
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
      <h1 className="mt-6 font-display text-2xl text-ink-900">Something went wrong</h1>
      <p className="mt-2 text-sm text-ink-500">We couldn&rsquo;t confirm your email just now. Please try again.</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-6 inline-flex w-full items-center justify-center rounded-md bg-emerald-deep px-4 py-2.5 text-sm font-medium text-bone transition hover:bg-emerald-accent"
      >
        Try again
      </button>
      <NavLinks />
    </>
  );
}

function NavLinks() {
  return (
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
  );
}
