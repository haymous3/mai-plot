'use client';

import { useState } from 'react';

import { EnvelopeIcon, PlusIcon, UserCircleIcon } from './icons';
import { OnboardingHeading, PrimaryButton, SelectCard } from './ui';

/**
 * "Do you already have a Maihomme account?" — the step between the role picker
 * and the account form (SCRUM-226, backend SCRUM-225).
 *
 * One person may legitimately hold more than one account: a seller who is also
 * a realtor. Answering yes and giving the NIN links the new account to the one
 * that already holds it, so identity is verified once rather than per account.
 *
 * ⚠️ THE COPY ABOUT WHERE THE EMAIL GOES IS LOAD-BEARING, NOT DECORATION.
 * On a match the confirmation link is sent to the address on the EXISTING
 * account, never the one typed on the next screen — that is what stops someone
 * who merely knows a name and a NIN from claiming a verified identity (a NIN is
 * handed to banks, agents and landlords; the name is on every listing). A user
 * who is not told this waits at an inbox that will never receive anything, so
 * removing the rail below breaks the flow as surely as it hides the reason.
 *
 * Measured vocabulary, same as the role picker: 768×144 select cards at a 24px
 * gap, 16px radius, 1px SOLID #e5e7eb, 80×80 chip inverting to `emerald-deep`.
 * The NIN field matches the 68px CTA height rather than the smaller undesigned
 * `AccountStep` inputs — it sits among designed cards, not among those.
 */

export type ExistingAccountAnswer = 'yes' | 'no';

const NIN_DIGITS = 11;

export function ExistingAccountStep({
  answer,
  setAnswer,
  nin,
  setNin,
  error,
  onBack,
  onContinue,
}: {
  answer: ExistingAccountAnswer | null;
  setAnswer: (a: ExistingAccountAnswer) => void;
  nin: string;
  setNin: (v: string) => void;
  /** Surfaced here because the backend rejects a role conflict at register. */
  error: string | null;
  onBack: () => void;
  onContinue: () => void;
}) {
  const [touched, setTouched] = useState(false);

  const ninDigits = nin.trim();
  const ninLooksValid = new RegExp(`^\\d{${NIN_DIGITS}}$`).test(ninDigits);
  const canContinue = answer === 'no' || (answer === 'yes' && ninLooksValid);
  const showNinError = touched && answer === 'yes' && ninDigits !== '' && !ninLooksValid;

  return (
    <div className="w-full">
      <OnboardingHeading
        title="Do you already have a Maihomme account?"
        subtitle="You can hold more than one — a seller account and a realtor account, for example."
      />

      <div className="mt-14 flex flex-col gap-6">
        <SelectCard
          Icon={UserCircleIcon}
          label="Yes, I already have one"
          description="We'll link this new account to it, so you only verify your identity once"
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

      {answer === 'yes' && (
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
          Continue
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
