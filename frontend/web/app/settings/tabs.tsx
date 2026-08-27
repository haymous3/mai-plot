'use client';

import { useState } from 'react';

import {
  Card,
  CardHeading,
  Field,
  GhostButton,
  PrimaryButton,
  SecureNote,
  SelectInput,
  StatusNote,
  TextInput,
  ToggleRow,
} from './settings-ui';
import { PasswordField } from '../_components/password-field';
import type { Account } from '@/lib/settings';
import { NIGERIAN_BANKS } from '@/lib/nigerian-banks';

/**
 * The four Settings panels — SCRUM-188.
 *
 * ⚠️ THREE ELEMENTS OF THE DESIGN ARE NOT BUILT HERE, each because nothing
 * backs them yet. They land with their migrations/endpoints in the next PR
 * rather than as controls that silently forget what the user did:
 *   - the Profile photo upload (no photo column, endpoint or S3 path)
 *   - the "Marketing Emails" toggle (preferences store push/sms/email only)
 *   - "Delete My Account" (no endpoint; soft-delete columns exist, no route)
 */

const EMPLOYMENT = [
  { value: 'employed', label: 'Employed' },
  { value: 'self_employed', label: 'Self-employed' },
  { value: 'business_owner', label: 'Business owner' },
  { value: 'retired', label: 'Retired' },
  { value: 'student', label: 'Student' },
  { value: 'other', label: 'Other' },
] as const;

const UserIcon = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="h-4 w-4"
  >
    <circle cx="12" cy="8" r="3.5" />
    <path d="M5 20a7 7 0 0 1 14 0" />
  </svg>
);
const MailIcon = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="h-4 w-4"
  >
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <path d="m3.5 6.5 8.5 6 8.5-6" />
  </svg>
);
const PhoneIcon = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="h-4 w-4"
  >
    <path d="M6.5 3.5h-2a2 2 0 0 0-2 2C2.5 13.5 10.5 21.5 18.5 21.5a2 2 0 0 0 2-2v-2l-4.5-2-2.5 2.5a14 14 0 0 1-5-5L11 10.5z" />
  </svg>
);
/** The save glyph the design puts inside both submit buttons. */
const SaveIcon = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="h-4 w-4"
    aria-hidden
  >
    <path d="M5 3h11l3 3v15H5z" />
    <path d="M8 3v6h7V3M8 21v-6h8v6" />
  </svg>
);
const PinIcon = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="h-4 w-4"
  >
    <path d="M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11Z" />
    <circle cx="12" cy="10" r="2.5" />
  </svg>
);

// ── Profile ────────────────────────────────────────────────────────────────

export function ProfileTab({ account }: { account: Account }) {
  const [fullName, setFullName] = useState(account.full_name ?? '');
  const [location, setLocation] = useState(account.preferred_location ?? '');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{
    tone: 'ok' | 'error';
    text: string;
  } | null>(null);

  const dirty =
    fullName !== (account.full_name ?? '') || location !== (account.preferred_location ?? '');

  async function save() {
    setBusy(true);
    setNote(null);
    try {
      const profile = await fetch('/api/auth/profile', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ full_name: fullName.trim() }),
      });
      if (!profile.ok) {
        const b = (await profile.json().catch(() => ({}))) as {
          error_code?: string;
        };
        setNote({
          tone: 'error',
          text:
            b.error_code === 'FULL_NAME_REQUIRED'
              ? 'Please enter your full name.'
              : 'We could not save your details. Please retry.',
        });
        return;
      }

      // Location lives on buyer_profile, so only buyers have somewhere to put it.
      if (account.role === 'buyer') {
        const buyer = await fetch('/api/auth/buyer/profile', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ preferred_location: location.trim() || null }),
        });
        if (!buyer.ok) {
          setNote({
            tone: 'error',
            text: 'Saved your name, but not your location. Please retry.',
          });
          return;
        }
      }
      setNote({ tone: 'ok', text: 'Changes saved.' });
    } catch {
      setNote({
        tone: 'error',
        text: 'Could not reach the server. Please try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeading title="Personal Information" />

      <div className="grid gap-6 sm:grid-cols-2">
        <Field id="full-name" label="Full Name" required>
          <TextInput
            id="full-name"
            value={fullName}
            onChange={setFullName}
            placeholder="Ada Obi"
            icon={<UserIcon />}
            autoComplete="name"
          />
        </Field>

        {/*
          Email and phone are READ-ONLY. Both are verified identifiers, not
          preferences: email is the login identifier and phone carries a partial
          unique index scoped to the phone verification channel (SCRUM-183).
          Changing either has to re-run verification, which is a flow that does
          not exist yet — so they are shown, not edited.
        */}
        <Field
          id="email"
          label="Email Address"
          note={<SecureNote>Verified — contact support to change</SecureNote>}
        >
          <TextInput id="email" value={account.email ?? ''} icon={<MailIcon />} />
        </Field>

        <Field
          id="phone"
          label="Phone Number"
          note={<SecureNote>Verified — contact support to change</SecureNote>}
        >
          <TextInput id="phone" value={account.phone} icon={<PhoneIcon />} />
        </Field>

        {account.role === 'buyer' && (
          <Field id="location" label="Location">
            <TextInput
              id="location"
              value={location}
              onChange={setLocation}
              placeholder="Lagos, Nigeria"
              icon={<PinIcon />}
            />
          </Field>
        )}
      </div>

      {note && <StatusNote tone={note.tone}>{note.text}</StatusNote>}

      <div className="mt-8 flex items-center justify-end gap-3 border-t border-line pt-6">
        <GhostButton
          onClick={() => {
            setFullName(account.full_name ?? '');
            setLocation(account.preferred_location ?? '');
            setNote(null);
          }}
        >
          Cancel
        </GhostButton>
        <PrimaryButton disabled={!dirty || !fullName.trim() || busy} onClick={() => void save()}>
          <SaveIcon />
          {busy ? 'Saving…' : 'Save Changes'}
        </PrimaryButton>
      </div>
    </Card>
  );
}

// ── Financial ──────────────────────────────────────────────────────────────

export function FinancialTab({
  account,
  payout,
}: {
  account: Account;
  payout: {
    account_number_masked: string;
    bank_code: string;
    account_name: string;
  } | null;
}) {
  const [bvn, setBvn] = useState('');
  const [bankCode, setBankCode] = useState(payout?.bank_code ?? '');
  const [accountNumber, setAccountNumber] = useState('');
  const [accountName, setAccountName] = useState(payout?.account_name ?? '');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{
    tone: 'ok' | 'error';
    text: string;
  } | null>(null);

  const canSave = /^\d{10}$/.test(accountNumber) && bankCode !== '' && accountName.trim() !== '';

  async function save() {
    setBusy(true);
    setNote(null);
    try {
      if (bvn.trim() && !account.bvn_verified) {
        const resp = await fetch('/api/buyer/bvn-verify', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ bvn: bvn.trim() }),
        });
        if (!resp.ok) {
          const b = (await resp.json().catch(() => ({}))) as {
            error_code?: string;
          };
          setNote({
            tone: 'error',
            text:
              b.error_code === 'BVN_FORMAT_INVALID'
                ? 'BVN must be exactly 11 digits.'
                : 'We could not verify that BVN. Please retry.',
          });
          return;
        }
      }

      const resp = await fetch('/api/settings/payout-account', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          account_number: accountNumber,
          bank_code: bankCode,
          account_name: accountName.trim(),
        }),
      });
      if (!resp.ok) {
        const b = (await resp.json().catch(() => ({}))) as {
          error_code?: string;
        };
        setNote({
          tone: 'error',
          text:
            b.error_code === 'RECIPIENT_UNAVAILABLE'
              ? 'We could not verify that bank account right now. Please retry.'
              : 'We could not save your bank account. Please check the details.',
        });
        return;
      }
      setNote({ tone: 'ok', text: 'Financial details saved.' });
    } catch {
      setNote({
        tone: 'error',
        text: 'Could not reach the server. Please try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeading
        title="Financial Information"
        subtitle="Manage your financial details for loan applications and transactions"
      />

      <Field
        id="bvn"
        label="BVN"
        hint="(Bank Verification Number)"
        note={<SecureNote>Your data is encrypted and used only for verification</SecureNote>}
      >
        {/*
          Once verified the BVN cannot be re-submitted — /auth/verify/bvn 409s
          with BVN_ALREADY_VERIFIED — and the value is never readable back (it
          is a bcrypt hash). So a verified account gets a status, not a field.
        */}
        {account.bvn_verified ? (
          <TextInput id="bvn" value="Verified" />
        ) : (
          <TextInput
            id="bvn"
            value={bvn}
            onChange={(v) => setBvn(v.replace(/[^\d]/g, ''))}
            placeholder="12345678901"
            inputMode="numeric"
            maxLength={11}
          />
        )}
      </Field>

      <h3 className="mt-8 border-t border-line pt-8 text-lg font-bold leading-6 text-ink-buyer">
        Bank Account
      </h3>

      <div className="mt-5">
        <Field id="bank" label="Bank Name">
          <SelectInput
            id="bank"
            value={bankCode}
            onChange={setBankCode}
            options={NIGERIAN_BANKS.map((b) => ({
              value: b.code,
              label: b.name,
            }))}
            placeholder="Select your bank"
          />
        </Field>
      </div>

      <div className="mt-6 grid gap-6 sm:grid-cols-2">
        <Field
          id="account-number"
          label="Account Number"
          note={
            payout ? (
              <SecureNote>
                Currently {payout.account_number_masked} — enter a number to replace it
              </SecureNote>
            ) : undefined
          }
        >
          <TextInput
            id="account-number"
            value={accountNumber}
            onChange={(v) => setAccountNumber(v.replace(/[^\d]/g, ''))}
            placeholder={payout ? payout.account_number_masked : '0123456789'}
            inputMode="numeric"
            maxLength={10}
          />
        </Field>

        <Field id="account-name" label="Account Name">
          <TextInput
            id="account-name"
            value={accountName}
            onChange={setAccountName}
            placeholder="Ada Obi"
          />
        </Field>
      </div>

      {note && <StatusNote tone={note.tone}>{note.text}</StatusNote>}

      <div className="mt-8 flex justify-end border-t border-line pt-6">
        <PrimaryButton disabled={!canSave || busy} onClick={() => void save()}>
          <SaveIcon />
          {busy ? 'Saving…' : 'Save Financial Info'}
        </PrimaryButton>
      </div>
    </Card>
  );
}

// ── Notifications ──────────────────────────────────────────────────────────

type Prefs = {
  push_enabled: boolean;
  sms_enabled: boolean;
  email_enabled: boolean;
};

export function NotificationsTab({ initial }: { initial: Prefs }) {
  const [prefs, setPrefs] = useState<Prefs>(initial);
  const [note, setNote] = useState<{
    tone: 'ok' | 'error';
    text: string;
  } | null>(null);

  async function toggle(key: keyof Prefs, value: boolean) {
    const previous = prefs;
    setPrefs({ ...prefs, [key]: value }); // optimistic — a switch that lags feels broken
    setNote(null);
    try {
      const resp = await fetch('/api/settings/notifications', {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ [key]: value }),
      });
      if (!resp.ok) {
        setPrefs(previous);
        setNote({
          tone: 'error',
          text: 'Could not save that preference. Please retry.',
        });
      }
    } catch {
      setPrefs(previous);
      setNote({
        tone: 'error',
        text: 'Could not reach the server. Please try again.',
      });
    }
  }

  return (
    <Card>
      <CardHeading
        title="Notification Preferences"
        subtitle="Choose how you want to receive updates"
      />

      <div className="flex flex-col gap-4">
        <ToggleRow
          id="email-notifications"
          label="Email Notifications"
          description="Receive updates via email"
          checked={prefs.email_enabled}
          onChange={(v) => void toggle('email_enabled', v)}
        />
        <ToggleRow
          id="sms-notifications"
          label="SMS Notifications"
          description="Receive updates via SMS"
          checked={prefs.sms_enabled}
          onChange={(v) => void toggle('sms_enabled', v)}
        />
        <ToggleRow
          id="push-notifications"
          label="Push Notifications"
          description="Receive browser notifications"
          checked={prefs.push_enabled}
          onChange={(v) => void toggle('push_enabled', v)}
        />
      </div>

      {note && <StatusNote tone={note.tone}>{note.text}</StatusNote>}
    </Card>
  );
}

// ── Security ───────────────────────────────────────────────────────────────

export function SecurityTab() {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{
    tone: 'ok' | 'error';
    text: string;
  } | null>(null);

  const mismatch = confirm !== '' && confirm !== next;
  const canSubmit = current !== '' && next.length >= 8 && confirm === next && !busy;

  async function submit() {
    setBusy(true);
    setNote(null);
    try {
      const resp = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      if (!resp.ok) {
        const b = (await resp.json().catch(() => ({}))) as {
          error_code?: string;
        };
        const messages: Record<string, string> = {
          CURRENT_PASSWORD_INCORRECT: 'Your current password is incorrect.',
          PASSWORD_UNCHANGED: 'Your new password must be different from your current one.',
          PASSWORD_TOO_WEAK:
            'Use at least 8 characters, including an uppercase letter and a number.',
          NO_PASSWORD_SET: 'This account has no password yet. Use "Forgot password" to set one.',
        };
        setNote({
          tone: 'error',
          text: messages[b.error_code ?? ''] ?? 'Could not change your password. Please retry.',
        });
        return;
      }
      // The backend revoked every session and the BFF cleared our cookies, so
      // there is nothing to go back to — send them to sign in with the new one.
      setNote({ tone: 'ok', text: 'Password changed. Signing you out…' });
      window.setTimeout(() => {
        window.location.href = '/login';
      }, 1200);
    } catch {
      setNote({
        tone: 'error',
        text: 'Could not reach the server. Please try again.',
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeading
        title="Change Password"
        subtitle="Keep your account secure with a strong password"
      />

      <div className="flex max-w-[520px] flex-col gap-5">
        <Field id="current-password" label="Current Password">
          <div className="mt-2">
            <PasswordField
              id="current-password"
              value={current}
              onChange={setCurrent}
              autoComplete="current-password"
              placeholder="Enter current password"
            />
          </div>
        </Field>

        <Field id="new-password" label="New Password">
          <div className="mt-2">
            <PasswordField
              id="new-password"
              value={next}
              onChange={setNext}
              autoComplete="new-password"
              placeholder="Enter new password"
            />
          </div>
        </Field>

        <Field
          id="confirm-password"
          label="Confirm New Password"
          note={
            mismatch ? (
              <p className="mt-2 text-xs leading-4 text-status-danger">Passwords do not match</p>
            ) : undefined
          }
        >
          <div className="mt-2">
            <PasswordField
              id="confirm-password"
              value={confirm}
              onChange={setConfirm}
              autoComplete="new-password"
              placeholder="Confirm new password"
            />
          </div>
        </Field>
      </div>

      {note && <StatusNote tone={note.tone}>{note.text}</StatusNote>}

      <div className="mt-7">
        <PrimaryButton disabled={!canSubmit} onClick={() => void submit()}>
          {busy ? 'Updating…' : 'Update Password'}
        </PrimaryButton>
      </div>

      <p className="mt-4 text-xs leading-4 text-ink-500">
        Changing your password signs you out on every device.
      </p>
    </Card>
  );
}
