'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { CheckIcon, EnvelopeIcon } from '../_onboarding/icons';
import {
  NinAlreadyVerified,
  NinVerifyField,
  ninIsSettled,
  useNinVerification,
} from '../_onboarding/nin-verify-field';
import { OnboardingHeading, OnboardingShell, PrimaryButton } from '../_onboarding/ui';
import type { SwitchableRole } from '@/lib/api';
import { roleHome } from '@/lib/session';

/**
 * The confirm-and-create body of /add-account — SCRUM-236.
 *
 * Built from the onboarding vocabulary (768px column, 68px CTA, 16px radii,
 * `surface-warm` rail) because it leads straight into onboarding; a person
 * should not feel they have left one flow for a different product.
 *
 * Three things, in order: what carries over, the NIN (only when it is not yet
 * verified), and one button. The email rail is the receipt this action sends —
 * saying so here means the email is expected rather than alarming.
 */

const ERRORS: Record<string, string> = {
  NIN_VERIFICATION_REQUIRED: 'Verify your NIN above before adding another account.',
  ROLE_ALREADY_HELD: 'You already have this account — switch to it from the account menu.',
  ROLE_NOT_SWITCHABLE: 'This kind of account can’t be added here.',
  NO_SESSION: 'Your session has ended. Sign in again to continue.',
  AUTH_SERVICE_UNAVAILABLE: 'We couldn’t reach the server. Please try again.',
};

const WHAT: Record<SwitchableRole, { noun: string; does: string }> = {
  seller: { noun: 'seller', does: 'list property and manage offers on it' },
  buyer: { noun: 'buyer', does: 'browse listings, make offers and apply for financing' },
};

const CARRIED = ['Your name', 'Email and password', 'Phone number and address'];

function CarriedItem({ label, done }: { label: string; done: boolean }) {
  return (
    <li className={`flex items-center gap-3 text-[15px] font-semibold ${done ? 'text-ink-700' : 'text-ink-400'}`}>
      <span
        className={`flex h-6 w-6 flex-none items-center justify-center rounded-full ${
          done ? 'bg-emerald-deep/10 text-emerald-deep' : 'border border-dashed border-line-strong'
        }`}
      >
        {done && <CheckIcon className="h-3.5 w-3.5" />}
      </span>
      {label}
    </li>
  );
}

export function AddAccountFlow({
  current,
  target,
  firstName,
  email,
  ninVerified,
}: {
  current: SwitchableRole;
  target: SwitchableRole;
  firstName: string | null;
  email: string | null;
  ninVerified: boolean;
}) {
  const router = useRouter();
  const [nin, setNin] = useState('');
  const ninCheck = useNinVerification('/api/auth/nin');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const identityReady = ninVerified || ninIsSettled(ninCheck.status);
  const { noun, does } = WHAT[target];

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch('/api/auth/add-role', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ role: target }),
      });
      const body = (await resp.json().catch(() => ({}))) as { redirect?: string; error?: string };
      if (resp.ok && body.redirect) {
        router.replace(body.redirect);
        router.refresh();
        return;
      }
      setError(ERRORS[body.error ?? ''] ?? 'We couldn’t create the account. Please try again.');
    } catch {
      setError(ERRORS.AUTH_SERVICE_UNAVAILABLE);
    } finally {
      setBusy(false);
    }
  }

  return (
    <OnboardingShell>
      <OnboardingHeading
        title={`Create your ${noun} account`}
        subtitle={`${firstName ? `${firstName}, you` : 'You'}’ll use the same email and password, and switch between buying and selling from your account menu.`}
      />

      <section className="mt-14 rounded-2xl border border-line px-6 py-6 sm:px-8">
        <h2 className="text-base font-bold leading-6 text-ink-buyer">
          Carried over from this account
        </h2>
        <p className="mt-1 text-[15px] leading-[22px] text-ink-500">
          Nothing to fill in again. You can change any of it later in Settings.
        </p>
        <ul className="mt-5 grid gap-3 sm:grid-cols-2">
          {CARRIED.map((item) => (
            <CarriedItem key={item} label={item} done />
          ))}
          {/* Only claimed once it is true: before the NIN is verified, the
              identity is exactly what does NOT carry over yet. */}
          <CarriedItem
            label={identityReady ? 'Verified identity (NIN)' : 'Verified identity — after you verify below'}
            done={identityReady}
          />
        </ul>
        <p className="mt-5 text-[15px] leading-[22px] text-ink-500">
          Your {noun} account is where you {does}.
          {target === 'seller' &&
            ' Next you’ll tell us whether you own the property or sell under a power of attorney.'}
        </p>
      </section>

      <div className="mt-8">
        {ninVerified ? (
          <NinAlreadyVerified />
        ) : (
          <>
            <p className="mb-4 rounded-2xl bg-distress-50 px-6 py-4 text-[15px] font-semibold leading-[23px] text-distress-700">
              Your new account inherits your verified identity, so we need your NIN on this account
              first.
            </p>
            <NinVerifyField
              value={nin}
              onChange={(v) => {
                setNin(v);
                if (ninCheck.status !== 'idle') ninCheck.reset();
              }}
              status={ninCheck.status}
              message={ninCheck.message}
              onBlurVerify={() => void ninCheck.verify(nin)}
              onRetry={() => void ninCheck.verify(nin)}
              disabled={busy}
            />
          </>
        )}
      </div>

      <div className="mt-8 flex items-start gap-3.5 rounded-2xl bg-surface-warm px-6 py-5">
        <EnvelopeIcon className="mt-px h-[22px] w-[22px] flex-none text-emerald-deep" />
        <p className="text-[15px] font-semibold leading-[23px] text-ink-700">
          We&rsquo;ll email {email ? <strong className="font-bold text-ink-buyer">{email}</strong> : 'you'}{' '}
          to confirm a {noun} account was added to your sign-in.
        </p>
      </div>

      {error && (
        <p
          role="alert"
          className="mt-8 rounded-2xl bg-distress-50 px-6 py-4 text-[15px] font-semibold leading-[23px] text-distress-700"
        >
          {error}
        </p>
      )}

      <div className="mt-12">
        <PrimaryButton disabled={!identityReady || busy} onClick={() => void create()}>
          {busy ? 'Creating…' : `Create ${noun} account`}
        </PrimaryButton>
      </div>

      <div className="mt-6 flex justify-center">
        <Link
          href={roleHome(current)}
          className="rounded-lg px-4 py-3 text-base font-semibold text-ink-500 transition hover:text-ink-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-deep"
        >
          Not now
        </Link>
      </div>
    </OnboardingShell>
  );
}
