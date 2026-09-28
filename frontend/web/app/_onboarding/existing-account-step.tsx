'use client';

import { useState } from 'react';

import { CONTROL, FieldLabel } from './fields';
import { EnvelopeIcon, PlusIcon, UserCircleIcon } from './icons';
import { OnboardingHeading, PrimaryButton, SelectCard } from './ui';

/**
 * "Do you already have a Maihomme account?" — the step between the role picker
 * and the account form (SCRUM-226, backend SCRUM-225; reworked in SCRUM-236).
 *
 * Two ways to say yes, depending on what the existing account is:
 *
 * 1. SIGN IN (buyer ↔ seller, SCRUM-236 — the default for those two roles).
 *    A buyer and a seller account now share ONE sign-in. The person signs in
 *    with the account they have and the new one is added to it: no name, no
 *    email, no password to type again, straight to onboarding. Signing in IS
 *    the proof of ownership, so nothing has to be mailed anywhere first.
 *
 * 2. NIN LOOKUP (anything involving a realtor — SCRUM-225, unchanged).
 *    Realtors keep separate sign-ins (they use a registration number), so a
 *    realtor ↔ seller pair is still linked by NIN, with the confirmation sent to
 *    the EXISTING account's inbox.
 *
 *    ⚠️ THE COPY ABOUT WHERE THE EMAIL GOES IS LOAD-BEARING, NOT DECORATION.
 *    On a match the link goes to the address on the EXISTING account, never
 *    the one typed on the next screen — that is what stops someone who merely
 *    knows a name and a NIN from claiming a verified identity. A user who is
 *    not told this waits at an inbox that will never receive anything.
 *
 * Measured vocabulary, same as the role picker: 768×144 select cards at a 24px
 * gap, 16px radius, 1px SOLID #e5e7eb, 80×80 chip inverting to `emerald-deep`.
 * Fields are the 68px onboarding CONTROL, matching the CTA below them.
 */

export type ExistingAccountAnswer = 'yes' | 'no';
export type LinkBy = 'signin' | 'nin';

const NIN_DIGITS = 11;

/** Whether this signup can be added to an existing sign-in (SCRUM-236). */
export function canLinkBySignIn(role: string): boolean {
  return role === 'buyer' || role === 'seller';
}

export function ExistingAccountStep({
  role,
  answer,
  setAnswer,
  linkBy,
  setLinkBy,
  identifier,
  setIdentifier,
  password,
  setPassword,
  nin,
  setNin,
  busy,
  error,
  onBack,
  onContinue,
}: {
  /** The role being signed up for. */
  role: string;
  answer: ExistingAccountAnswer | null;
  setAnswer: (a: ExistingAccountAnswer) => void;
  linkBy: LinkBy;
  setLinkBy: (l: LinkBy) => void;
  identifier: string;
  setIdentifier: (v: string) => void;
  password: string;
  setPassword: (v: string) => void;
  nin: string;
  setNin: (v: string) => void;
  busy: boolean;
  /** Sign-in failures, and the backend's role conflict at register. */
  error: string | null;
  onBack: () => void;
  onContinue: () => void;
}) {
  const [touched, setTouched] = useState(false);

  const signInAvailable = canLinkBySignIn(role);
  const mode: LinkBy = signInAvailable ? linkBy : 'nin';
  const roleNoun = role === 'seller' ? 'seller' : role === 'buyer' ? 'buyer' : 'new';

  const ninDigits = nin.trim();
  const ninLooksValid = new RegExp(`^\\d{${NIN_DIGITS}}$`).test(ninDigits);
  const signInReady = identifier.trim() !== '' && password !== '';
  const canContinue =
    !busy &&
    (answer === 'no' ||
      (answer === 'yes' && (mode === 'signin' ? signInReady : ninLooksValid)));
  const showNinError = touched && answer === 'yes' && ninDigits !== '' && !ninLooksValid;

  return (
    <div className="w-full">
      <OnboardingHeading
        title="Do you already have a Maihomme account?"
        subtitle={
          signInAvailable
            ? 'Buying and selling share one sign-in — add this to the account you already have.'
            : 'You can hold more than one — a seller account and a realtor account, for example.'
        }
      />

      <div className="mt-14 flex flex-col gap-6">
        <SelectCard
          Icon={UserCircleIcon}
          label="Yes, I already have one"
          description={
            mode === 'signin'
              ? 'Sign in and we’ll add it — no form to fill in again'
              : 'We’ll link this new account to it, so you only verify your identity once'
          }
          selected={answer === 'yes'}
          onSelect={() => setAnswer('yes')}
        />
        <SelectCard
          Icon={PlusIcon}
          label="No, this is my first"
          description="We'll set you up from scratch"
          selected={answer === 'no'}
          onSelect={() => setAnswer('no')}
        />
      </div>

      {answer === 'yes' && mode === 'signin' && (
        <div className="mt-8 flex flex-col gap-6">
          <div>
            <FieldLabel htmlFor="existing-identifier">Email address</FieldLabel>
            <input
              id="existing-identifier"
              type="text"
              inputMode="email"
              autoComplete="username"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              placeholder="you@example.com"
              disabled={busy}
              className={CONTROL}
            />
          </div>
          <div>
            <FieldLabel htmlFor="existing-password">Password</FieldLabel>
            <input
              id="existing-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && canContinue) onContinue();
              }}
              disabled={busy}
              className={CONTROL}
            />
          </div>
          <div className="flex items-start gap-3.5 rounded-2xl bg-surface-warm px-6 py-5">
            <EnvelopeIcon className="mt-px h-[22px] w-[22px] flex-none text-emerald-deep" />
            <p className="text-[15px] font-semibold leading-[23px] text-ink-700">
              Your {roleNoun} account will use this same email and password. Your name and verified
              identity carry over, and we&rsquo;ll email you to confirm it was added.
            </p>
          </div>

          <button
            type="button"
            onClick={() => setLinkBy('nin')}
            className="self-start text-[15px] font-semibold text-emerald-deep underline-offset-4 hover:underline"
          >
            My existing account is a realtor account
          </button>
        </div>
      )}

      {answer === 'yes' && mode === 'nin' && (
        <div className="mt-8">
          <label htmlFor="existing-nin" className="block text-base font-semibold leading-6 text-ink-buyer">
            National Identification Number
          </label>
          <p className="mt-1 text-[15px] leading-[22px] text-ink-500">
            The 11-digit NIN on your existing account. We use it to find the account, not to verify
            you again.
          </p>
          <input
            id="existing-nin"
            type="text"
            inputMode="numeric"
            autoComplete="off"
            value={nin}
            // Digits only: a NIN is 11 digits and nothing else, so stripping as
            // they type beats rejecting them afterwards.
            onChange={(e) => setNin(e.target.value.replace(/\D/g, '').slice(0, NIN_DIGITS))}
            onBlur={() => setTouched(true)}
            placeholder="12345678901"
            aria-invalid={showNinError}
            aria-describedby={showNinError ? 'existing-nin-error' : undefined}
            className={`mt-3 h-[68px] w-full rounded-2xl border bg-white px-6 text-lg font-semibold tracking-[0.04em] text-ink-buyer outline-none transition placeholder:font-normal placeholder:tracking-normal placeholder:text-ink-300 focus:ring-2 focus:ring-emerald-deep/20 ${
              showNinError ? 'border-distress-700' : 'border-line-strong focus:border-emerald-deep'
            }`}
          />
          {showNinError && (
            <p id="existing-nin-error" className="mt-3 text-[15px] font-semibold leading-[23px] text-distress-700">
              A NIN is exactly 11 digits.
            </p>
          )}

          <div className="mt-5 flex items-start gap-3.5 rounded-2xl bg-surface-warm px-6 py-5">
            <EnvelopeIcon className="mt-px h-[22px] w-[22px] flex-none text-emerald-deep" />
            <p className="text-[15px] font-semibold leading-[23px] text-ink-700">
              We&rsquo;ll send the confirmation link to the email address on your{' '}
              <strong className="font-bold text-ink-buyer">existing account</strong> — not to the one
              you enter next. Open it there to finish setting up.
            </p>
          </div>

          {signInAvailable && (
            <button
              type="button"
              onClick={() => setLinkBy('signin')}
              className="mt-5 text-[15px] font-semibold text-emerald-deep underline-offset-4 hover:underline"
            >
              Sign in with my email and password instead
            </button>
          )}
        </div>
      )}

      {error && (
        <p
          role="alert"
          className="mt-8 rounded-2xl bg-distress-50 px-6 py-4 text-[15px] font-semibold leading-[23px] text-distress-700"
        >
          {error}
        </p>
      )}

      <div className="mt-12">
        <PrimaryButton disabled={!canContinue} onClick={onContinue}>
          {busy ? 'Signing in…' : answer === 'yes' && mode === 'signin' ? 'Sign in and continue' : 'Continue'}
        </PrimaryButton>
      </div>

      <div className="mt-6 flex justify-center">
        <button
          type="button"
          onClick={onBack}
          className="rounded-lg px-4 py-3 text-base font-semibold text-ink-500 transition hover:text-ink-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-deep"
        >
          Back
        </button>
      </div>
    </div>
  );
}
