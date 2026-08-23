'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  clearVerifyHandoff,
  OTP_TTL_SECONDS,
  VERIFY_EMAIL_KEY,
  VERIFY_EXPIRES_KEY,
  VERIFY_PHONE_KEY,
} from '@/lib/verify-handoff';

const CODE_LENGTH = 6;
/** How long before "Resend code" becomes tappable again. The backend caps at
 *  5/hour per phone; this stops a user burning that allowance in ten seconds. */
const RESEND_COOLDOWN_SECONDS = 60;

type Phase = 'entering' | 'verifying' | 'success' | 'expired' | 'locked' | 'missing';

function mmss(totalSeconds: number): string {
  const s = Math.max(0, totalSeconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/**
 * Mask the middle of an E.164 Nigerian number for display: +234 801 ••• 5678.
 * The user's own number, shown back for confirmation — enough to recognise,
 * not enough to be useful over someone's shoulder.
 */
function maskPhone(e164: string): string {
  const digits = e164.replace(/\D/g, '');
  if (digits.length < 8) return e164;
  return `+${digits.slice(0, 3)} ${digits.slice(3, 6)} ••• ${digits.slice(-4)}`;
}

export function VerifyOtpClient() {
  const router = useRouter();

  const [phone, setPhone] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [expiresAt, setExpiresAt] = useState<number | null>(null);

  const [phase, setPhase] = useState<Phase>('entering');
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [attemptsLeft, setAttemptsLeft] = useState<number | null>(null);
  const [redirect, setRedirect] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [cooldownUntil, setCooldownUntil] = useState<number>(() => 0);
  const [resendState, setResendState] = useState<'idle' | 'sending' | 'sent'>('idle');
  const [emailState, setEmailState] = useState<'idle' | 'sending' | 'sent'>('idle');

  const inputRef = useRef<HTMLInputElement>(null);
  // Guards the auto-submit against firing twice for one filled code (React 18
  // strict mode double-invokes effects, and the OTP is single-use).
  const submittingRef = useRef(false);

  // Read the handoff the register funnel left behind. sessionStorage rather
  // than a query param: an MSISDN in the URL would land in browser history and
  // server access logs.
  useEffect(() => {
    const storedPhone = sessionStorage.getItem(VERIFY_PHONE_KEY);
    if (!storedPhone) {
      setPhase('missing');
      return;
    }
    setPhone(storedPhone);
    setEmail(sessionStorage.getItem(VERIFY_EMAIL_KEY));
    const storedExpiry = Number(sessionStorage.getItem(VERIFY_EXPIRES_KEY));
    setExpiresAt(
      Number.isFinite(storedExpiry) && storedExpiry > 0
        ? storedExpiry
        : Date.now() + OTP_TTL_SECONDS * 1000,
    );
    setCooldownUntil(Date.now() + RESEND_COOLDOWN_SECONDS * 1000);
  }, []);

  // One ticker drives both countdowns.
  useEffect(() => {
    if (phase === 'success' || phase === 'missing') return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [phase]);

  const secondsLeft = useMemo(
    () => (expiresAt ? Math.ceil((expiresAt - now) / 1000) : null),
    [expiresAt, now],
  );
  const cooldownLeft = Math.ceil((cooldownUntil - now) / 1000);

  // Let the countdown itself flip the screen, so a user who walks away comes
  // back to the recovery options rather than a dead field.
  useEffect(() => {
    if (phase === 'entering' && secondsLeft !== null && secondsLeft <= 0) {
      setPhase('expired');
    }
  }, [phase, secondsLeft]);

  const verify = useCallback(
    async (value: string) => {
      if (!phone || submittingRef.current) return;
      submittingRef.current = true;
      setPhase('verifying');
      setError(null);
      try {
        const resp = await fetch('/api/auth/verify-otp', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ phone, otp: value }),
        });
        const body = (await resp.json().catch(() => ({}))) as {
          ok?: boolean;
          redirect?: string;
          error_code?: string;
          details?: { attempts_remaining?: number };
        };

        if (resp.ok && body.ok && body.redirect) {
          clearVerifyHandoff();
          setRedirect(body.redirect);
          setPhase('success');
          return;
        }

        switch (body.error_code) {
          case 'OTP_EXPIRED':
            setPhase('expired');
            return;
          case 'OTP_TOO_MANY_ATTEMPTS':
            setPhase('locked');
            return;
          case 'OTP_INVALID': {
            const left = body.details?.attempts_remaining;
            setAttemptsLeft(typeof left === 'number' ? left : null);
            setError(
              typeof left === 'number'
                ? `That code isn’t right. Check the text and try again — you have ${left} ${
                    left === 1 ? 'attempt' : 'attempts'
                  } left.`
                : 'That code isn’t right. Check the text and try again.',
            );
            setPhase('entering');
            setCode('');
            inputRef.current?.focus();
            return;
          }
          default:
            setError('We couldn’t check that code just now. Please try again.');
            setPhase('entering');
            return;
        }
      } catch {
        setError('Could not reach the server. Please try again.');
        setPhase('entering');
      } finally {
        submittingRef.current = false;
      }
    },
    [phone],
  );

  // Submit as soon as the sixth digit lands — the design has no separate tap
  // for the common case; the button is there for retries and assistive tech.
  useEffect(() => {
    if (phase === 'entering' && code.length === CODE_LENGTH) {
      void verify(code);
    }
  }, [code, phase, verify]);

  useEffect(() => {
    if (phase !== 'success' || !redirect) return;
    const t = setTimeout(() => {
      router.replace(redirect);
      router.refresh();
    }, 1400);
    return () => clearTimeout(t);
  }, [phase, redirect, router]);

  async function resendCode() {
    if (!phone || resendState === 'sending' || cooldownLeft > 0) return;
    setResendState('sending');
    setError(null);
    try {
      const resp = await fetch('/api/auth/otp/resend', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ phone }),
      });
      if (resp.status === 202) {
        const freshExpiry = Date.now() + OTP_TTL_SECONDS * 1000;
        sessionStorage.setItem(VERIFY_EXPIRES_KEY, String(freshExpiry));
        setExpiresAt(freshExpiry);
        setCooldownUntil(Date.now() + RESEND_COOLDOWN_SECONDS * 1000);
        setCode('');
        setAttemptsLeft(null);
        setPhase('entering');
        setResendState('sent');
        inputRef.current?.focus();
        return;
      }
      const body = (await resp.json().catch(() => ({}))) as { error?: string };
      setResendState('idle');
      setError(
        body.error === 'VERIFICATION_RATE_LIMITED'
          ? 'Too many codes requested for this number. Please wait a little and try again.'
          : 'Could not send a new code just now. Please try again.',
      );
    } catch {
      setResendState('idle');
      setError('Could not reach the server. Please try again.');
    }
  }

  async function emailLinkInstead() {
    if (!email || emailState === 'sending') return;
    setEmailState('sending');
    setError(null);
    try {
      const resp = await fetch('/api/auth/verify-email/resend', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      if (resp.status === 202) {
        setEmailState('sent');
        return;
      }
      const body = (await resp.json().catch(() => ({}))) as { error?: string };
      setEmailState('idle');
      setError(
        body.error === 'VERIFICATION_RATE_LIMITED'
          ? 'Too many requests. Please wait a little and try again.'
          : 'Could not send the link just now. Please try again.',
      );
    } catch {
      setEmailState('idle');
      setError('Could not reach the server. Please try again.');
    }
  }

  if (phase === 'missing') return <Missing />;
  if (phase === 'success') return <Success redirect={redirect} />;

  const locked = phase === 'locked';
  const expired = phase === 'expired';
  const showField = !locked && !expired;

  return (
    <div className="w-full max-w-sm animate-rise text-center">
      <div className="mb-9">
        <span className="font-display text-2xl tracking-tight text-emerald-deep">Maiplot</span>
      </div>

      <Icon tone={expired || locked ? 'warn' : 'neutral'}>
        {expired || locked ? <ClockIcon /> : <PhoneIcon />}
      </Icon>

      <h1 className="mt-6 font-display text-2xl text-ink-900">
        {expired ? 'That code has expired' : locked ? 'Too many attempts' : 'Enter your code'}
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-ink-500">
        {expired ? (
          <>Codes are only valid for 5 minutes. Send a fresh one, or switch to email.</>
        ) : locked ? (
          <>For your security this code has been retired. Send a new one to continue.</>
        ) : (
          <>
            We sent a 6-digit code to{' '}
            <span className="whitespace-nowrap font-medium text-ink-700">
              {phone ? maskPhone(phone) : 'your phone'}
            </span>
          </>
        )}
      </p>

      {showField && (
        <>
          <CodeField
            inputRef={inputRef}
            value={code}
            onChange={setCode}
            invalid={attemptsLeft !== null && error !== null}
            disabled={phase === 'verifying'}
          />
          {secondsLeft !== null && secondsLeft > 0 && !error && (
            <p className="mt-3.5 text-sm text-ink-500">
              Code expires in{' '}
              <span className="font-medium tabular-nums text-ink-700">{mmss(secondsLeft)}</span>
            </p>
          )}
        </>
      )}

      {error && (
        <p
          role="alert"
          className="mt-3.5 flex items-start gap-2.5 rounded-md bg-red-50 px-3.5 py-2.5 text-left text-sm leading-relaxed text-red-700"
        >
          <WarnIcon />
          <span>{error}</span>
        </p>
      )}

      {showField ? (
        <button
          type="button"
          disabled={code.length !== CODE_LENGTH || phase === 'verifying'}
          onClick={() => void verify(code)}
          className="mt-5 inline-flex h-11 w-full items-center justify-center rounded-md bg-emerald-deep text-sm font-medium text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:opacity-55"
        >
          {phase === 'verifying' ? 'Verifying…' : 'Verify and continue'}
        </button>
      ) : (
        <button
          type="button"
          onClick={() => void resendCode()}
          disabled={resendState === 'sending'}
          className="mt-7 inline-flex h-11 w-full items-center justify-center rounded-md bg-emerald-deep text-sm font-medium text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:opacity-55"
        >
          {resendState === 'sending' ? 'Sending…' : 'Send a new code'}
        </button>
      )}

      {email && (
        <EmailFallback state={emailState} expired={expired || locked} onSend={emailLinkInstead} />
      )}

      {showField && (
        <div className="mt-6 flex flex-col items-center gap-2.5 border-t border-line pt-6">
          <p className="text-sm text-ink-500">
            Didn&rsquo;t get the text?{' '}
            {cooldownLeft > 0 ? (
              <span className="tabular-nums text-ink-400">Resend in {mmss(cooldownLeft)}</span>
            ) : (
              <button
                type="button"
                onClick={() => void resendCode()}
                disabled={resendState === 'sending'}
                className="font-medium text-emerald-deep hover:underline disabled:opacity-60"
              >
                {resendState === 'sending' ? 'Sending…' : 'Resend code'}
              </button>
            )}
          </p>
          {email && emailState !== 'sent' && (
            <button
              type="button"
              onClick={() => void emailLinkInstead()}
              disabled={emailState === 'sending'}
              className="text-sm font-medium text-emerald-deep hover:underline disabled:opacity-60"
            >
              {emailState === 'sending' ? 'Sending…' : 'Email me a link instead'}
            </button>
          )}
        </div>
      )}

      <p className="mt-6 text-sm text-ink-500">
        Wrong number?{' '}
        <Link href="/register" className="font-medium text-emerald-deep hover:underline">
          Go back
        </Link>
      </p>
    </div>
  );
}

/**
 * Six cells, one input. The cells are presentation only (aria-hidden) so a
 * screen reader hears a single labelled field rather than six; the real input
 * carries autocomplete="one-time-code", which is what lets iOS and Android
 * drop the whole code in from the SMS.
 */
const CodeField = ({
  inputRef,
  value,
  onChange,
  invalid,
  disabled,
}: {
  inputRef: React.RefObject<HTMLInputElement>;
  value: string;
  onChange: (v: string) => void;
  invalid: boolean;
  disabled: boolean;
}) => {
  const cells = Array.from({ length: CODE_LENGTH }, (_, i) => value[i] ?? '');
  const activeIndex = Math.min(value.length, CODE_LENGTH - 1);

  return (
    <div
      className="relative mt-7"
      onClick={() => inputRef.current?.focus()}
      role="presentation"
    >
      <input
        ref={inputRef}
        type="text"
        inputMode="numeric"
        autoComplete="one-time-code"
        aria-label="6-digit verification code"
        aria-invalid={invalid || undefined}
        maxLength={CODE_LENGTH}
        disabled={disabled}
        value={value}
        autoFocus
        onChange={(e) => onChange(e.target.value.replace(/\D/g, '').slice(0, CODE_LENGTH))}
        className="absolute inset-0 h-full w-full cursor-default opacity-0"
      />
      <div className="pointer-events-none flex justify-center gap-1.5 sm:gap-2" aria-hidden>
        {cells.map((digit, i) => {
          const isActive = !disabled && !invalid && i === activeIndex && value.length < CODE_LENGTH;
          const border = invalid
            ? 'border border-status-danger'
            : isActive
              ? 'border-2 border-emerald-accent ring-[3px] ring-emerald-accent/20'
              : 'border border-ink-300/60';
          return (
            <div
              key={i}
              className={`flex h-14 w-[48px] items-center justify-center rounded-md bg-white text-xl font-medium text-ink-900 transition sm:w-[52px] ${border} ${
                disabled ? 'opacity-55' : ''
              }`}
            >
              {digit}
            </div>
          );
        })}
      </div>
    </div>
  );
};

function EmailFallback({
  state,
  expired,
  onSend,
}: {
  state: 'idle' | 'sending' | 'sent';
  expired: boolean;
  onSend: () => void;
}) {
  // Generic copy, matching the backend's no-enumeration 202.
  if (state === 'sent') {
    return (
      <p className="mt-4 rounded-md bg-emerald-deep/10 px-3.5 py-3 text-sm leading-relaxed text-emerald-deep">
        If that email needs verification, we&rsquo;ve sent a link. Check your inbox &mdash; and your
        spam or promotions folder.
      </p>
    );
  }
  if (!expired) return null;
  return (
    <>
      <button
        type="button"
        onClick={onSend}
        disabled={state === 'sending'}
        className="mt-2.5 inline-flex h-11 w-full items-center justify-center rounded-md border border-ink-300/60 bg-white text-sm font-medium text-ink-700 transition hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-60"
      >
        {state === 'sending' ? 'Sending…' : 'Email me a link instead'}
      </button>
      <p className="mt-6 flex items-start gap-2.5 rounded-md bg-surface-warm px-3.5 py-3 text-left text-sm leading-relaxed text-ink-500">
        <InfoIcon />
        <span>
          Texts to some Nigerian networks can be slow or blocked. The email link works the same way.
        </span>
      </p>
    </>
  );
}

function Success({ redirect }: { redirect: string | null }) {
  return (
    <div className="w-full max-w-sm animate-rise text-center">
      <div className="mb-9">
        <span className="font-display text-2xl tracking-tight text-emerald-deep">Maiplot</span>
      </div>
      <Icon tone="success">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-[26px] w-[26px]"
          aria-hidden
        >
          <path d="M5 12.5l4.5 4.5L19 7.5" />
        </svg>
      </Icon>
      <h1 className="mt-6 font-display text-2xl text-ink-900">You&rsquo;re verified</h1>
      <p className="mt-2 text-sm text-ink-500">
        Your number is confirmed. Taking you to your dashboard&hellip;
      </p>
      {redirect && (
        <a
          href={redirect}
          className="mt-6 inline-flex h-11 w-full items-center justify-center rounded-md bg-emerald-deep text-sm font-medium text-bone transition hover:bg-emerald-accent"
        >
          Continue
        </a>
      )}
    </div>
  );
}

/** Reached by opening /verify-otp directly, or in a tab that never registered.
 *  Mirrors the equivalent state on /verify-email rather than dead-ending. */
function Missing() {
  return (
    <div className="w-full max-w-sm animate-rise text-center">
      <div className="mb-9">
        <span className="font-display text-2xl tracking-tight text-emerald-deep">Maiplot</span>
      </div>
      <Icon tone="error">
        <WarnGlyph />
      </Icon>
      <h1 className="mt-6 font-display text-2xl text-ink-900">Nothing to verify yet</h1>
      <p className="mt-2 text-sm leading-relaxed text-ink-500">
        We don&rsquo;t have a number to check a code against. Start your sign-up and we&rsquo;ll
        text you one.
      </p>
      <div className="mt-6 flex items-center justify-center gap-4 text-sm">
        <Link href="/register" className="font-medium text-emerald-deep hover:underline">
          Create an account
        </Link>
        <span className="text-ink-300" aria-hidden>
          &middot;
        </span>
        <Link href="/login" className="font-medium text-emerald-deep hover:underline">
          Go to sign in
        </Link>
      </div>
    </div>
  );
}

function Icon({
  tone,
  children,
}: {
  tone: 'neutral' | 'success' | 'warn' | 'error';
  children: React.ReactNode;
}) {
  const toneClass = {
    neutral: 'bg-emerald-deep/12 text-emerald-deep',
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

function PhoneIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-[26px] w-[26px]"
      aria-hidden
    >
      <rect x="6" y="2.5" width="12" height="19" rx="2.5" />
      <path d="M10.5 18.5h3" />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-[26px] w-[26px]"
      aria-hidden
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5V12l2.75 1.6" />
    </svg>
  );
}

function WarnIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="mt-0.5 h-[18px] w-[18px] shrink-0" aria-hidden>
      <path
        fillRule="evenodd"
        d="M10 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16Zm0 4a1 1 0 0 1 1 1v3a1 1 0 1 1-2 0V7a1 1 0 0 1 1-1Zm0 7.5a1 1 0 1 0 0 2 1 1 0 0 0 0-2Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function InfoIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="mt-0.5 h-[18px] w-[18px] shrink-0" aria-hidden>
      <path
        fillRule="evenodd"
        d="M10 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16Zm.75 4.25a.75.75 0 0 0-1.5 0v.5a.75.75 0 0 0 1.5 0v-.5ZM10 9a.75.75 0 0 1 .75.75v4a.75.75 0 0 1-1.5 0v-4A.75.75 0 0 1 10 9Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function WarnGlyph() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="h-7 w-7" aria-hidden>
      <path
        fillRule="evenodd"
        d="M10 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16Zm0 4a1 1 0 0 1 1 1v3a1 1 0 1 1-2 0V7a1 1 0 0 1 1-1Zm0 7.5a1 1 0 1 0 0 2 1 1 0 0 0 0-2Z"
        clipRule="evenodd"
      />
    </svg>
  );
}
