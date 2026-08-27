'use client';

import { useState } from 'react';

import { FieldError, FieldLabel, SecureNote, SelectField, TextField } from './fields';
import { GhostButton, OnboardingHeading, PrimaryButton } from './ui';

/**
 * The two buyer steps — `buyers-flow-after-email-verification-{1,2}.png`.
 *
 * ⚠️ TWO ELEMENTS OF THE EXPORT ARE NOT BUILT, because nothing backs them:
 *
 *  - The avatar with its camera badge. There is no photo field anywhere in
 *    auth-service — no column, no endpoint, no S3 path. A control that cannot
 *    save is worse than no control.
 *  - "Email Address (Optional)". Email is now the verification channel
 *    (SCRUM-180/181), so by this screen it is already known AND verified.
 *    Re-asking would invite a user to change the address they just proved they
 *    control. (SCRUM-188 added GET /auth/me, so it COULD now be pre-filled —
 *    but the reason for omitting it was never the missing read: re-asking for
 *    an address the user just proved they control is the problem.)
 *
 * The NIN field on step 2 is a BVN here. /auth/verify/nin is hard-gated to
 * sellers with owner authority (403 NIN_NOT_ELIGIBLE); BVN is the buyer
 * identity check and has no role gate. Product owner confirmed the swap.
 *
 * It posts to the existing `/api/buyer/bvn-verify`. SCRUM-185 briefly added a
 * second route for this on the belief that `/api/buyer/*` and the onboarding
 * session read DIFFERENT cookies — they do not. `lib/buyer-auth.ts` re-exports
 * `SESSION_ACCESS_COOKIE as BUYER_ACCESS_COOKIE`: one cookie, two names. The
 * duplicate was removed in SCRUM-188.
 */

const EMPLOYMENT = [
  { value: 'employed', label: 'Employed' },
  { value: 'self_employed', label: 'Self-employed' },
  { value: 'business_owner', label: 'Business owner' },
  { value: 'retired', label: 'Retired' },
  { value: 'student', label: 'Student' },
  { value: 'other', label: 'Other' },
] as const;

/** Step 1 — the full name registration no longer collects (SCRUM-185). */
export function PersonalDetailsStep({
  onDone,
}: {
  onDone: (fullName: string) => void | Promise<void>;
}) {
  const [fullName, setFullName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch('/api/auth/profile', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ full_name: fullName.trim() }),
      });
      if (!resp.ok) {
        const b = (await resp.json().catch(() => ({}))) as { error_code?: string };
        setError(
          b.error_code === 'FULL_NAME_REQUIRED'
            ? 'Please enter your full name.'
            : 'We could not save your details. Please retry.',
        );
        return;
      }
      await onDone(fullName.trim());
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-full">
      <OnboardingHeading title="Personal details" subtitle="Tell us a bit about yourself" />

      <div className="mx-auto mt-14 max-w-[672px]">
        <FieldLabel htmlFor="full-name" required>
          Full Name
        </FieldLabel>
        <TextField
          id="full-name"
          value={fullName}
          onChange={setFullName}
          placeholder="John Doe"
          autoComplete="name"
          disabled={busy}
        />
        {error && <FieldError>{error}</FieldError>}

        <div className="mt-12">
          <PrimaryButton disabled={!fullName.trim() || busy} onClick={() => void submit()}>
            {busy ? 'Saving…' : 'Continue'}
          </PrimaryButton>
        </div>
      </div>
    </div>
  );
}

/**
 * Step 2 — identity and buying capacity. Every field is optional server-side,
 * which is why this is the one step the design gives a "Skip for now".
 *
 * BVN and the capacity fields go to different endpoints, so they are sent
 * independently: a BVN that fails verification must not silently discard the
 * budget the user just typed.
 */
export function BuyerProfileStep({ onDone }: { onDone: () => void | Promise<void> }) {
  const [bvn, setBvn] = useState('');
  const [employment, setEmployment] = useState('');
  const [location, setLocation] = useState('');
  const [budget, setBudget] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bvnLooksValid = /^\d{11}$/.test(bvn.trim());

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (bvn.trim()) {
        if (!bvnLooksValid) {
          setError('BVN must be exactly 11 digits.');
          return;
        }
        const resp = await fetch('/api/buyer/bvn-verify', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ bvn: bvn.trim() }),
        });
        if (!resp.ok) {
          const b = (await resp.json().catch(() => ({}))) as { error_code?: string };
          setError(
            b.error_code === 'BVN_FORMAT_INVALID'
              ? 'BVN must be exactly 11 digits.'
              : b.error_code === 'BVN_ALREADY_VERIFIED'
                ? 'This BVN has already been verified.'
                : 'We could not verify that BVN. You can skip and add it later.',
          );
          return;
        }
      }

      // Money as kobo, never a float (CLAUDE.md §4). Strip separators first so
      // "40,000,000" and "40000000" both work.
      const naira = budget.replace(/[^\d]/g, '');
      const resp = await fetch('/api/auth/buyer/profile', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          employment_status: employment || null,
          preferred_location: location.trim() || null,
          budget_kobo: naira ? Number(naira) * 100 : null,
        }),
      });
      if (!resp.ok) {
        setError('We could not save your details. Please retry.');
        return;
      }
      await onDone();
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-full">
      <OnboardingHeading
        title="Personal Information"
        subtitle="Help us understand your buying capacity"
      />

      <div className="mx-auto mt-14 max-w-[672px]">
        <FieldLabel htmlFor="bvn" hint="(Bank Verification Number)">
          BVN
        </FieldLabel>
        <TextField
          id="bvn"
          value={bvn}
          onChange={(v) => setBvn(v.replace(/[^\d]/g, ''))}
          placeholder="12345678901"
          inputMode="numeric"
          maxLength={11}
          disabled={busy}
        />
        <SecureNote>Your data is encrypted and used only for verification</SecureNote>

        <div className="mt-9">
          <FieldLabel htmlFor="employment">Employment Status</FieldLabel>
          <SelectField
            id="employment"
            value={employment}
            onChange={setEmployment}
            options={EMPLOYMENT}
            placeholder="Select your employment status"
          />
        </div>

        <div className="mt-9">
          <FieldLabel htmlFor="location">Preferred Location</FieldLabel>
          <TextField
            id="location"
            value={location}
            onChange={setLocation}
            placeholder="e.g., Lagos, Abuja"
            disabled={busy}
          />
        </div>

        <div className="mt-9">
          <FieldLabel htmlFor="budget">Budget</FieldLabel>
          <TextField
            id="budget"
            value={budget}
            onChange={setBudget}
            placeholder="e.g., 40,000,000"
            inputMode="numeric"
            disabled={busy}
          />
        </div>

        {error && <FieldError>{error}</FieldError>}

        <div className="mt-12 flex items-center justify-end gap-6">
          <GhostButton onClick={() => void onDone()} disabled={busy}>
            Skip for now
          </GhostButton>
          <div className="w-[320px]">
            <PrimaryButton disabled={busy} onClick={() => void submit()}>
              {busy ? 'Saving…' : 'Complete Profile'}
            </PrimaryButton>
          </div>
        </div>
      </div>
    </div>
  );
}
