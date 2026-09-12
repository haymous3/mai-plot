'use client';

import { useCallback, useRef, useState } from 'react';

import type { NinStatus } from '@/lib/nin-verification';
import { isCompleteNin, ninIsSettled, ninOutcome } from '@/lib/nin-verification';

import { CONTROL, FieldLabel, SecureNote } from './fields';

/**
 * A NIN field that verifies as soon as the number is entered — SCRUM-221.
 *
 * Before this, every screen posted the NIN inside `submit()`, after the user had
 * filled in three or four more fields. A wrong digit in the FIRST field failed
 * the WHOLE step, minutes later, with the message nowhere near its cause.
 *
 * ⚠️ VERIFICATION FIRES ON BLUR, NOT ON A KEYSTROKE DEBOUNCE. Two reasons, and
 * both are load-bearing:
 *   · Each call costs the business roughly ₦100 (Ninja, SCRUM-218), so firing
 *     while someone is still typing bills for every intermediate value.
 *   · A debounce fires on a mistyped 11th digit before the user has noticed it,
 *     spending the call and showing a failure they were about to fix anyway.
 * Blur is the only unambiguous "I am done with this field" signal available.
 *
 * ⚠️ The same value is never verified twice (`attempted`), so tabbing back and
 * forth over a settled field cannot spend a second call.
 *
 * ⚠️ NOT FOR THE EXISTING-ACCOUNT STEP. The NIN collected there (SCRUM-226) is
 * a LOOKUP against an account that already exists — it must not be verified,
 * which would both charge for nothing and write the wrong state.
 */

/** Where the caller's session posts NIN verification. All three proxy to the
 * same auth-service endpoint; they differ only in which session cookie they
 * read (see the route files — collapsing them wants its own ticket). */
export type NinEndpoint = '/api/buyer/nin-verify' | '/api/auth/nin' | '/api/auth/seller/nin';

export { ninIsSettled };
export type { NinStatus };

export function useNinVerification(endpoint: NinEndpoint) {
  const [status, setStatus] = useState<NinStatus>('idle');
  const [message, setMessage] = useState<string | null>(null);
  // The last value we actually spent a call on, so a re-blur is free.
  const attempted = useRef<string | null>(null);

  const reset = useCallback(() => {
    attempted.current = null;
    setStatus('idle');
    setMessage(null);
  }, []);

  const verify = useCallback(
    async (raw: string) => {
      const nin = raw.trim();
      if (!isCompleteNin(nin)) return;
      if (attempted.current === nin) return;
      attempted.current = nin;

      setStatus('checking');
      setMessage(null);
      try {
        const resp = await fetch(endpoint, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ nin }),
        });
        const body = (await resp.json().catch(() => ({}))) as {
          error_code?: string;
          status?: string;
        };

        const outcome = ninOutcome(resp.ok, body);
        setStatus(outcome.status);
        setMessage(outcome.message);
        // Clearing the memo is what lets "Try again" actually re-fire on the
        // SAME number. Only retryable outcomes get that: re-sending one the
        // server already stored can never do anything but 409.
        if (outcome.retryable) attempted.current = null;
      } catch {
        setStatus('error');
        setMessage('We could not reach the server. Please try again.');
        attempted.current = null;
      }
    },
    [endpoint],
  );

  return { status, message, verify, reset } as const;
}

/**
 * What stands in for the NIN field when the account is already verified —
 * on this account, or through the one it is linked to (SCRUM-225/228).
 *
 * Shown INSTEAD of the field, never alongside a disabled one: an empty,
 * disabled input reads as broken. A one-line explanation is what makes the gap
 * in the form legible. Same call Settings made (`account.nin_verified ?`).
 */
export function NinAlreadyVerified() {
  return (
    <div>
      <FieldLabel htmlFor="nin-verified" hint="(National Identification Number)">
        NIN
      </FieldLabel>
      <div
        id="nin-verified"
        role="status"
        className="mt-3 flex h-[68px] w-full items-center gap-3 rounded-2xl border border-emerald-deep/40 bg-[#f3f5f4] px-6 text-base text-ink-buyer"
      >
        <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-emerald-deep text-white">
          <svg
            viewBox="0 0 24 24"
            className="h-3.5 w-3.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden
          >
            <path d="M5 12.5l4.5 4.5L19 7.5" />
          </svg>
        </span>
        <span>Identity verified through your existing account</span>
      </div>
    </div>
  );
}

export function NinVerifyField({
  id = 'nin',
  value,
  onChange,
  status,
  message,
  onBlurVerify,
  onRetry,
  disabled,
}: {
  id?: string;
  value: string;
  onChange: (v: string) => void;
  status: NinStatus;
  message: string | null;
  onBlurVerify: () => void;
  onRetry: () => void;
  disabled?: boolean;
}) {
  const settled = ninIsSettled(status);
  const failed = status === 'error';

  return (
    <div>
      <FieldLabel htmlFor={id} hint="(National Identification Number)">
        NIN
      </FieldLabel>

      <div className="relative">
        <input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value.replace(/[^\d]/g, '').slice(0, 11))}
          onBlur={onBlurVerify}
          placeholder="NIN should not be more than 11 digits"
          inputMode="numeric"
          maxLength={11}
          disabled={disabled || status === 'checking'}
          aria-invalid={failed}
          aria-describedby={message ? `${id}-status` : undefined}
          className={`${CONTROL} pr-14 ${
            failed ? 'border-distress-700 focus:border-distress-700' : ''
          } ${settled ? 'border-emerald-deep' : ''}`}
        />

        {/* Fixed footprint so settling does not shift the field's height. */}
        <span
          className="pointer-events-none absolute right-6 top-[calc(50%+6px)] -translate-y-1/2"
          aria-hidden
        >
          {status === 'checking' && (
            <svg viewBox="0 0 24 24" className="h-6 w-6 animate-spin text-ink-400" fill="none">
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.4" opacity="0.25" />
              <path
                d="M21 12a9 9 0 0 0-9-9"
                stroke="currentColor"
                strokeWidth="2.4"
                strokeLinecap="round"
              />
            </svg>
          )}
          {settled && (
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-deep text-white">
              <svg
                viewBox="0 0 24 24"
                className="h-3.5 w-3.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M5 12.5l4.5 4.5L19 7.5" />
              </svg>
            </span>
          )}
        </span>
      </div>

      {/* aria-live so the outcome is announced without moving focus — the user
          has already tabbed on by the time the answer arrives. */}
      <p id={`${id}-status`} role="status" aria-live="polite" className="sr-only">
        {status === 'checking' ? 'Checking your NIN' : (message ?? (settled ? 'NIN verified' : ''))}
      </p>

      {failed ? (
        <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[15px] leading-5 text-distress-700">
          <span>{message}</span>
          <button
            type="button"
            onClick={onRetry}
            className="font-semibold underline underline-offset-2 hover:no-underline"
          >
            Try again
          </button>
        </p>
      ) : status === 'pending' ? (
        <p className="mt-3 text-[15px] leading-5 text-ink-500">{message}</p>
      ) : status === 'verified' ? (
        <p className="mt-3 text-[15px] leading-5 text-emerald-deep">NIN verified.</p>
      ) : (
        <SecureNote>Your data is encrypted and used only for verification</SecureNote>
      )}
    </div>
  );
}
