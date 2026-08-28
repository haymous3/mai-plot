'use client';

import { useRef, useState } from 'react';

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
import type { Account, NotificationPrefs } from '@/lib/settings';
import { NIGERIAN_BANKS } from '@/lib/nigerian-banks';
import { SESSION_LOGIN } from '@/lib/session';

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
const TrashIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden>
    <path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" />
  </svg>
);
const CameraIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden>
    <path d="M4 8h3l1.5-2h7L17 8h3v11H4z" />
    <circle cx="12" cy="13" r="3.2" />
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

/**
 * Profile photo — the avatar with a camera badge the design draws (SCRUM-188).
 *
 * `avatar_url` is a PRE-SIGNED URL with a 15-minute life, not a durable link,
 * so it is held in state only for this page view. After an upload the server's
 * fresh URL replaces it; nothing is cached anywhere it could outlive the
 * signature.
 *
 * Uploads go straight to the BFF rather than being previewed from a local
 * object URL first: the server is the only thing that decides whether the file
 * is acceptable (it sniffs magic bytes), so showing an optimistic preview would
 * mean rendering an image that may be rejected a moment later.
 */
function AvatarField({ initialUrl, name }: { initialUrl: string | null; name: string }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [url, setUrl] = useState(initialUrl);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const initials =
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() ?? '')
      .join('') || '?';

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const resp = await fetch('/api/auth/avatar', { method: 'POST', body: form });
      const body = (await resp.json().catch(() => ({}))) as {
        avatar_url?: string | null;
        error_code?: string;
      };
      if (!resp.ok) {
        setError(
          body.error_code === 'AVATAR_TOO_LARGE'
            ? 'That image is too large. Please choose one under 5MB.'
            : body.error_code === 'AVATAR_INVALID'
              ? 'Please choose a JPEG, PNG or WebP image.'
              : 'We could not upload that photo. Please retry.',
        );
        return;
      }
      setUrl(body.avatar_url ?? null);
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(false);
      // Clear the input so re-picking the SAME file fires change again.
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch('/api/auth/avatar', { method: 'DELETE' });
      if (!resp.ok) {
        setError('We could not remove that photo. Please retry.');
        return;
      }
      setUrl(null);
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-8 flex items-center gap-6">
      <div className="relative flex-none">
        <span className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-full bg-surface-warm text-xl font-bold text-ink-500">
          {url ? (
            /* A pre-signed S3 URL cannot go through next/image: the signature
               is per-request and the bucket host is not in the images
               allowlist, so the optimiser would fetch a URL that has already
               expired. Plain <img> is correct here. */
            // eslint-disable-next-line @next/next/no-img-element
            <img src={url} alt="" className="h-full w-full object-cover" />
          ) : (
            initials
          )}
        </span>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          aria-label={url ? 'Change profile photo' : 'Upload profile photo'}
          className="absolute -bottom-0.5 -right-0.5 flex h-8 w-8 items-center justify-center rounded-full border-2 border-white bg-emerald-deep text-white transition hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-deep focus-visible:ring-offset-2 disabled:opacity-60"
        >
          <CameraIcon />
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="sr-only"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void upload(file);
          }}
        />
      </div>

      <div className="min-w-0">
        <p className="text-sm font-bold leading-5 text-ink-buyer">Profile Photo</p>
        <p className="mt-1 text-sm leading-5 text-ink-500">
          {busy ? 'Working…' : 'Upload a photo to personalize your account'}
        </p>
        {url && !busy && (
          <button
            type="button"
            onClick={() => void remove()}
            className="mt-2 text-sm font-semibold text-status-danger underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-status-danger"
          >
            Remove photo
          </button>
        )}
        {error && <StatusNote tone="error">{error}</StatusNote>}
      </div>
    </div>
  );
}

/**
 * Where the Settings "Location" box reads and writes, which is NOT the same
 * column for every role (SCRUM-193).
 *
 *  - buyer  -> `buyer_profiles.preferred_location`, i.e. where they want to BUY
 *  - others -> `user_pii.location`, i.e. where the account holder IS
 *
 * Those are genuinely different questions — a seller can live in Abuja and be
 * selling in Lagos — so migration 0013 added a second column rather than
 * widening the first. The buyer path is left exactly as SCRUM-188 built it;
 * unifying the two behind one meaning would move existing buyers' data and
 * wants its own ticket.
 */
function storedLocation(account: Account): string {
  return (account.role === 'buyer' ? account.preferred_location : account.location) ?? '';
}

export function ProfileTab({ account }: { account: Account }) {
  const [fullName, setFullName] = useState(account.full_name ?? '');
  const [location, setLocation] = useState(storedLocation(account));
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{
    tone: 'ok' | 'error';
    text: string;
  } | null>(null);

  const dirty = fullName !== (account.full_name ?? '') || location !== storedLocation(account);

  async function save() {
    setBusy(true);
    setNote(null);
    try {
      const profile = await fetch('/api/auth/profile', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        // `location` is sent for every role, but only means anything for the
        // non-buyer ones — a buyer's box is saved to buyer_profiles below.
        // Sending null rather than omitting it lets a location be CLEARED;
        // the endpoint distinguishes "sent null" from "not sent".
        body: JSON.stringify({
          full_name: fullName.trim(),
          ...(account.role === 'buyer' ? {} : { location: location.trim() || null }),
        }),
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

      // A buyer's box means "where I want to buy" and lives on buyer_profile.
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

      <AvatarField initialUrl={account.avatar_url} name={account.full_name ?? ''} />

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

        <Field id="location" label="Location">
          <TextInput
            id="location"
            value={location}
            onChange={setLocation}
            placeholder="Lagos, Nigeria"
            icon={<PinIcon />}
          />
        </Field>
      </div>

      {note && <StatusNote tone={note.tone}>{note.text}</StatusNote>}

      <div className="mt-8 flex items-center justify-end gap-3 border-t border-line pt-6">
        <GhostButton
          onClick={() => {
            setFullName(account.full_name ?? '');
            setLocation(storedLocation(account));
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
  const [nin, setNin] = useState('');
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
      if (nin.trim() && !account.nin_verified) {
        const resp = await fetch('/api/buyer/nin-verify', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ nin: nin.trim() }),
        });
        if (!resp.ok) {
          const b = (await resp.json().catch(() => ({}))) as {
            error_code?: string;
          };
          setNote({
            tone: 'error',
            text:
              b.error_code === 'NIN_FORMAT_INVALID'
                ? 'NIN must be exactly 11 digits.'
                : 'We could not verify that NIN. Please retry.',
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
        id="nin"
        label="NIN"
        hint="(National Identification Number)"
        note={<SecureNote>Your data is encrypted and used only for verification</SecureNote>}
      >
        {/*
          Once verified the NIN cannot be re-submitted — /auth/verify/nin 409s
          with NIN_ALREADY_VERIFIED — and the value is never readable back (it
          is a bcrypt hash). So a verified account gets a status, not a field.
        */}
        {account.nin_verified ? (
          <TextInput id="nin" value="Verified" />
        ) : (
          <TextInput
            id="nin"
            value={nin}
            onChange={(v) => setNin(v.replace(/[^\d]/g, ''))}
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

// Alias, not a second declaration: this used to be a local copy of the shape,
// which silently went stale when marketing_enabled was added to the real type.
type Prefs = NotificationPrefs;

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
        {/*
          Marketing sits apart from the three above and is opt-IN: it defaults
          false server-side because NDPR (§9) requires explicit consent for
          promotional messaging, while the transactional channels follow the
          table's opt-out model. See notification-service migration 0005.
        */}
        <ToggleRow
          id="marketing-emails"
          label="Marketing Emails"
          description="Receive promotional content and offers"
          checked={prefs.marketing_enabled}
          onChange={(v) => void toggle('marketing_enabled', v)}
        />
      </div>

      {note && <StatusNote tone={note.tone}>{note.text}</StatusNote>}
    </Card>
  );
}

// ── Security ───────────────────────────────────────────────────────────────

export function SecurityTab() {
  return (
    <>
      <ChangePasswordCard />
      <DangerZone />
    </>
  );
}

function ChangePasswordCard() {
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
          // SCRUM-191: this used to point at a "Forgot password" control that
          // had never been built. It exists now, so name where it actually is.
          NO_PASSWORD_SET:
            'This account has no password yet. Set one from the Forgot password page.',
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

      {/*
        SCRUM-191. This form needs the CURRENT password, so a signed-in user who
        cannot recall it — or who has no password at all (NO_PASSWORD_SET, which
        registration leaves possible) — was stuck here with nowhere to go. The
        reset flow is that way out, and it is the destination the error copy
        above now names.
      */}
      <p className="mt-2 text-xs leading-4 text-ink-500">
        Don&rsquo;t know your current password?{' '}
        <a href="/forgot-password" className="font-medium text-emerald-deep hover:underline">
          Reset it by email
        </a>
        .
      </p>
    </Card>
  );
}

/**
 * Danger Zone — irreversible account actions (SCRUM-188).
 *
 * ⚠️ The design's copy says "All your data will be permanently removed." That
 * is NOT what happens and the copy is deliberately changed. The deletion is
 * SOFT: transactions, escrow movements, commissions and audit rows survive,
 * because CBN and AMLON require the financial trail to outlive the account
 * (CLAUDE.md §9). Telling a user their financial records are gone when the
 * ledger deliberately keeps them would be a false promise, and an NDPR
 * subject-access request would immediately contradict it.
 *
 * What IS removed: the account stops authenticating, every session is revoked,
 * the profile photo is deleted from S3, and the phone and email are released
 * for re-registration (migrations 0009/0010).
 *
 * Two-step confirm rather than a window.confirm(): the destructive button is
 * inert until the user types DELETE, which is hard to do by accident and does
 * not depend on a dialog the browser may suppress.
 */
const _CONFIRM_WORD = 'DELETE';

function DangerZone() {
  const [arming, setArming] = useState(false);
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch('/api/account/delete', { method: 'POST' });
      if (!resp.ok) {
        const b = (await resp.json().catch(() => ({}))) as { error_code?: string };
        setError(
          b.error_code === 'ACCOUNT_HAS_ACTIVE_DEALS'
            ? 'You still have a deal in progress. Complete or cancel it before deleting your account.'
            : b.error_code === 'DELETE_UNAVAILABLE'
              ? 'We could not confirm your account has no deals in progress. Please try again shortly.'
              : 'We could not delete your account. Please retry.',
        );
        return;
      }
      // The BFF cleared the session cookies, so a full navigation (not a
      // client-side push) is what makes the app re-read them as signed out.
      window.location.href = SESSION_LOGIN;
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-8 rounded-2xl border border-status-danger/30 bg-white p-8">
      <h2 className="text-xl font-bold leading-7 text-status-danger">Danger Zone</h2>
      <p className="mt-1.5 text-sm leading-5 text-ink-500">Irreversible actions for your account</p>

      <div className="mt-7 rounded-xl border border-status-danger/20 bg-status-danger/5 p-6">
        <h3 className="text-base font-bold leading-6 text-ink-buyer">Delete Account</h3>
        <p className="mt-1.5 text-sm leading-5 text-ink-500">
          Your profile and photo are removed and you are signed out everywhere. Records we are
          legally required to keep — completed transactions and their financial history — are
          retained.
        </p>

        {!arming ? (
          <div className="mt-5">
            <PrimaryButton tone="danger" onClick={() => setArming(true)}>
              <TrashIcon />
              Delete My Account
            </PrimaryButton>
          </div>
        ) : (
          <div className="mt-5">
            <label
              htmlFor="confirm-delete"
              className="block text-sm font-bold leading-5 text-ink-buyer"
            >
              Type {_CONFIRM_WORD} to confirm
            </label>
            <div className="max-w-[320px]">
              <TextInput
                id="confirm-delete"
                value={typed}
                onChange={setTyped}
                placeholder={_CONFIRM_WORD}
              />
            </div>
            {error && <StatusNote tone="error">{error}</StatusNote>}
            <div className="mt-5 flex items-center gap-4">
              <PrimaryButton
                tone="danger"
                disabled={typed !== _CONFIRM_WORD || busy}
                onClick={() => void remove()}
              >
                {busy ? 'Deleting…' : 'Permanently delete'}
              </PrimaryButton>
              <GhostButton
                onClick={() => {
                  setArming(false);
                  setTyped('');
                  setError(null);
                }}
              >
                Cancel
              </GhostButton>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
