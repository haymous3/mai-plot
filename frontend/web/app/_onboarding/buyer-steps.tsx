'use client';

import { useState } from 'react';

import { CONTROL, FieldError, FieldLabel, SecureNote, SelectField, TextField } from './fields';
import { OnboardingHeading, PrimaryButton } from './ui';
import { MoneyInput } from '@/app/_components/money-input';
import { nairaToKobo } from '@/lib/money-input';

/**
 * The buyer profile step — `buyers-flow-after-email-verification-2.png`.
 * (Screen 1, Personal details, was removed in SCRUM-197; see below.)
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
 * Step 2 collects a NIN, as the design draws it. SCRUM-185 had to substitute
 * a BVN here because /auth/verify/nin was hard-gated to sellers with owner
 * authority (403 NIN_NOT_ELIGIBLE) and would have rejected every buyer.
 * SCRUM-189 removed that gate — NIN is now the platform-wide identity check
 * for every role — so the field matches the design again.
 *
 * It posts to `/api/buyer/nin-verify`. SCRUM-185 briefly added a second route
 * for this on the belief that `/api/buyer/*` and the onboarding session read
 * DIFFERENT cookies — they do not. `lib/buyer-auth.ts` re-exports
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

// PersonalDetailsStep lived here until SCRUM-197. Registration collects the
// full name again — for every role, not just buyers — so a second ask would
// have shown an empty field for something already typed.

export function BuyerProfileStep({
  onDone,
  fullName,
}: {
  onDone: () => void | Promise<void>;
  /**
   * The name registration collected (SCRUM-197), passed down from the page's
   * GET /auth/me. POST /auth/profile requires full_name, so saving an address
   * means re-sending the name the account already has — sending nothing would
   * be a 422 FULL_NAME_REQUIRED.
   */
  fullName?: string | null;
}) {
  const [nin, setNin] = useState('');
  const [employment, setEmployment] = useState('');
  const [location, setLocation] = useState('');
  const [address, setAddress] = useState('');
  const [budget, setBudget] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ninLooksValid = /^\d{11}$/.test(nin.trim());
  const canSubmit = ninLooksValid && address.trim().length > 0;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      // NIN is REQUIRED for every role from SCRUM-201; it used to be optional
      // here, with a "Skip for now" beside it. Both are gone.
      {
        if (!ninLooksValid) {
          setError('NIN must be exactly 11 digits.');
          return;
        }
        const resp = await fetch('/api/buyer/nin-verify', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ nin: nin.trim() }),
        });
        if (!resp.ok) {
          const b = (await resp.json().catch(() => ({}))) as { error_code?: string };
          setError(
            b.error_code === 'NIN_FORMAT_INVALID'
              ? 'NIN must be exactly 11 digits.'
              : b.error_code === 'NIN_ALREADY_VERIFIED'
                ? 'This NIN has already been verified.'
                : 'We could not verify that NIN. Please check it and retry.',
          );
          return;
        }
      }

      // Money as kobo, never a float (CLAUDE.md §4). Strip separators first so
      // "40,000,000" and "40000000" both work.
      const budgetKobo = nairaToKobo(budget);
      // Address lives on user_pii (migration 0014) and so goes to the shared
      // profile endpoint, not buyer_profiles below — every role has one.
      const addr = await fetch('/api/auth/profile', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ full_name: fullName ?? '', address: address.trim() }),
      });
      if (!addr.ok) {
        setError('We could not save your address. Please retry.');
        return;
      }

      const resp = await fetch('/api/auth/buyer/profile', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          employment_status: employment || null,
          preferred_location: location.trim() || null,
          budget_kobo: budgetKobo || null,
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
        <FieldLabel htmlFor="nin" hint="(National Identification Number)">
          NIN
        </FieldLabel>
        <TextField
          id="nin"
          value={nin}
          onChange={(v) => setNin(v.replace(/[^\d]/g, ''))}
          placeholder="NIN should not be more than 11 digits"
          inputMode="numeric"
          maxLength={11}
          disabled={busy}
        />
        <SecureNote>Your data is encrypted and used only for verification</SecureNote>

        <div className="mt-9">
          <FieldLabel htmlFor="address" required>
            Address
          </FieldLabel>
          <TextField
            id="address"
            value={address}
            onChange={setAddress}
            placeholder="e.g., 12 Admiralty Way, Lekki Phase 1, Lagos"
            disabled={busy}
          />
        </div>

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
          <MoneyInput
            id="budget"
            value={budget}
            onChange={setBudget}
            placeholder="e.g., 40,000,000"
            disabled={busy}
            className={CONTROL}
          />
        </div>

        {error && <FieldError>{error}</FieldError>}

        {/*
          "Skip for now" is gone (SCRUM-201): NIN and address are now required
          for every role, and a skip button beside required fields would be
          offering something the submit path no longer honours.
        */}
        <div className="mt-12 flex items-center justify-end gap-6">
          <div className="w-[320px]">
            <PrimaryButton disabled={busy || !canSubmit} onClick={() => void submit()}>
              {busy ? 'Saving…' : 'Complete Profile'}
            </PrimaryButton>
          </div>
        </div>
      </div>
    </div>
  );
}
