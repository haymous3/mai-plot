'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { IntroCarousel } from '../_onboarding/intro-carousel';
import { RolePicker } from '../_onboarding/role-picker';
import { OnboardingShell } from '../_onboarding/ui';
import {
  OTP_TTL_SECONDS,
  VERIFY_EMAIL_KEY,
  VERIFY_EXPIRES_KEY,
  VERIFY_PHONE_KEY,
} from '@/lib/verify-handoff';

// Onboarding (SCRUM-132 → SCRUM-155 → re-pointed at phone OTP by SCRUM-175):
// intro carousel → role select → account details (name/email/phone/password)
// → [seller: selling authority] → register → /verify-otp.
//
// Verification is a 6-digit SMS code again (SCRUM-175 moved it back from the
// SCRUM-152 email magic link). Registration still does NOT establish a session,
// so the old post-OTP steps (set-password, personal details, KYC) stay gone —
// KYC remains at point-of-need (buyer BVN at loan-apply, seller NIN/PoA at
// listing creation, both already gating there). The session is established when
// the code is verified on /verify-otp.
//
// Email is still collected and still required: it is the login identifier
// (SCRUM-45), and it backs the "Email me a link instead" fallback on the verify
// screen — which matters because SMS to Nigerian numbers is not reliable from
// the current sender (see services/auth-service/app/adapters/twilio.py).

const REGISTER_ERRORS: Record<string, string> = {
  EMAIL_ALREADY_REGISTERED: 'An account with this email already exists. Try signing in.',
  PHONE_ALREADY_REGISTERED: 'An account with this phone number already exists. Try signing in.',
  VERIFICATION_RATE_LIMITED: 'Too many attempts for this email. Please try again later.',
  VERIFICATION_EMAIL_FAILED: 'We could not send the verification email. Please retry.',
  VALIDATION_ERROR: 'Please check your details and try again.',
  INVALID_REQUEST: 'Please complete all required fields.',
  AUTH_SERVICE_UNAVAILABLE: 'Sign-up is temporarily unavailable. Please retry.',
};

type Step = 'intro' | 'role' | 'account' | 'seller-authority';
type VerificationChannel = 'email' | 'phone';
type SellerAuthority = 'owner' | 'power_of_attorney';

export function RegisterFlow() {
  const router = useRouter();
  const [step, setStep] = useState<Step>('intro');
  const [role, setRole] = useState('');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  // Mirrors the backend default (SCRUM-180). Email is the only enabled option
  // until SMS can reach Nigerian networks.
  const [channel, setChannel] = useState<VerificationChannel>('email');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Set once the verification email is away — this is a terminal state for the
  // funnel, since the user continues by clicking the link, not by typing here.
  const [sentToEmail, setSentToEmail] = useState<string | null>(null);

  async function submitRegister(sellerAuthority?: SellerAuthority) {
    setError(null);
    setBusy(true);
    try {
      const local = phone.replace(/\D/g, '').replace(/^0/, '');
      const resp = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          phone: `+234${local}`,
          role,
          email: email.trim(),
          password,
          full_name: fullName.trim(),
          verification_channel: channel,
          ...(role === 'seller' && sellerAuthority
            ? { seller_authority_type: sellerAuthority }
            : {}),
        }),
      });
      if (resp.ok) {
        const b = (await resp.json().catch(() => ({}))) as {
          verification_expires_in_seconds?: number;
          verification_channel?: VerificationChannel;
        };
        // Trust the server's answer over our own request: it is authoritative
        // about which channel actually ran, so a future server-side fallback
        // would route correctly without a frontend change.
        const used = b.verification_channel ?? channel;

        if (used === 'phone') {
          // sessionStorage, not a query param: an MSISDN in the URL would sit
          // in browser history and server access logs.
          sessionStorage.setItem(VERIFY_PHONE_KEY, `+234${local}`);
          sessionStorage.setItem(VERIFY_EMAIL_KEY, email.trim());
          sessionStorage.setItem(
            VERIFY_EXPIRES_KEY,
            String(Date.now() + (b.verification_expires_in_seconds ?? OTP_TTL_SECONDS) * 1000),
          );
          router.push('/verify-otp');
          return;
        }

        // Email: the link is in their inbox, so there is nothing to type here.
        // Stay put and tell them to go and check it.
        setSentToEmail(email.trim());
        return;
      }
      const b = (await resp.json()) as { error_code?: string };
      setError(REGISTER_ERRORS[b.error_code ?? ''] ?? 'Could not create your account. Please retry.');
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    // 768px column, measured on every screen in design/onboarding/ and the
    // three post-verification flows. Was max-w-md (448px).
    <OnboardingShell>
      {sentToEmail !== null ? (
        <FormColumn>
          <CheckEmailStep email={sentToEmail} />
        </FormColumn>
      ) : (
          <>
        {step === 'intro' && <IntroCarousel onDone={() => setStep('role')} />}

        {step === 'role' && (
          <RolePicker
            role={role}
            setRole={setRole}
            onContinue={() => {
              setError(null);
              setStep('account');
            }}
          />
        )}

        {step === 'account' && (
          <FormColumn>
          <AccountStep
            fullName={fullName}
            setFullName={setFullName}
            email={email}
            setEmail={setEmail}
            phone={phone}
            setPhone={setPhone}
            password={password}
            setPassword={setPassword}
            channel={channel}
            setChannel={setChannel}
            busy={busy}
            error={error}
            onBack={() => {
              setError(null);
              setStep('role');
            }}
            onContinue={() => {
              setError(null);
              // Sellers pick a selling authority before we create the account;
              // everyone else registers straight away.
              if (role === 'seller') {
                setStep('seller-authority');
              } else {
                void submitRegister();
              }
            }}
          />
          </FormColumn>
        )}

        {step === 'seller-authority' && (
          <FormColumn>
          <SellerAuthorityStep
            busy={busy}
            error={error}
            onBack={() => {
              setError(null);
              setStep('account');
            }}
            onContinue={(authority) => void submitRegister(authority)}
          />
          </FormColumn>
        )}

        {/* The designed screens (carousel, role picker) show no sign-in
            footer, so it appears only on the undesigned account steps where
            it is genuinely useful. */}
        {(step === 'account' || step === 'seller-authority') && (
          <p className="mt-8 text-center text-sm text-ink-500">
            Already have an account?{' '}
            <Link href="/login" className="font-medium text-emerald-deep hover:underline">
              Sign in
            </Link>
          </p>
        )}
          </>
        )}
    </OnboardingShell>
  );
}

/**
 * 672px inner column for the form steps — the field width measured on the
 * designed form screens (buyers-flow-1 etc.), inset 48px each side of the
 * 768px shell. The account and check-email steps have no export of their own;
 * holding them to the same measured field width keeps the funnel coherent
 * rather than snapping between two widths mid-flow.
 */
function FormColumn({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto w-full max-w-[672px]">{children}</div>;
}

function passwordChecks(pw: string) {
  return {
    length: pw.length >= 8,
    upper: /[A-Z]/.test(pw),
    digit: /\d/.test(pw),
  };
}

// A light client-side check only — normalise_email on the backend is the real
// gate. Just enough to catch obvious typos before we hit the API.
function looksLikeEmail(value: string): boolean {
  return /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(value.trim());
}

function AccountStep({
  fullName,
  setFullName,
  email,
  setEmail,
  phone,
  setPhone,
  password,
  setPassword,
  channel,
  setChannel,
  busy,
  error,
  onBack,
  onContinue,
}: {
  fullName: string;
  setFullName: (v: string) => void;
  email: string;
  setEmail: (v: string) => void;
  phone: string;
  setPhone: (v: string) => void;
  password: string;
  setPassword: (v: string) => void;
  channel: VerificationChannel;
  setChannel: (v: VerificationChannel) => void;
  busy: boolean;
  error: string | null;
  onBack: () => void;
  onContinue: () => void;
}) {
  const [confirm, setConfirm] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);

  const checks = passwordChecks(password);
  const passed = Object.values(checks).filter(Boolean).length;
  const strong = passed === 3;
  const strength = passed <= 1 ? 'Weak' : passed === 2 ? 'Medium' : 'Strong';
  const strengthColor = passed <= 1 ? 'bg-red-500' : passed === 2 ? 'bg-amber-500' : 'bg-emerald-deep';

  const local = phone.replace(/\D/g, '').replace(/^0/, '');
  const nameOk = fullName.trim().length > 0;
  const emailOk = looksLikeEmail(email);
  const phoneOk = local.length === 10;
  const passwordOk = strong && confirm === password;
  const canContinue = nameOk && emailOk && phoneOk && passwordOk;

  function submit() {
    if (!nameOk) return setLocalError('Please enter your full name.');
    if (!emailOk) return setLocalError('Please enter a valid email address.');
    if (!phoneOk) return setLocalError('Enter a valid 10-digit phone number.');
    if (!strong) return setLocalError('Choose a stronger password (see the requirements below).');
    if (confirm !== password) return setLocalError('Passwords do not match.');
    setLocalError(null);
    onContinue();
  }

  return (
    <div>
      <button onClick={onBack} className="mb-6 text-sm text-ink-500 hover:text-ink-900">
        ← Back
      </button>
      <h1 className="text-center font-display text-3xl text-ink-900">Create your account</h1>
      <p className="mt-2 text-center text-sm text-ink-500">
        We&rsquo;ll email you a link to verify your account.
      </p>

      <label className="mt-8 block text-sm font-medium text-ink-700">Full Name</label>
      <input
        value={fullName}
        onChange={(e) => setFullName(e.target.value)}
        placeholder="John Doe"
        autoComplete="name"
        className="mt-1.5 w-full rounded-md border border-ink-300/60 bg-white px-3.5 py-2.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
      />

      <label className="mt-5 block text-sm font-medium text-ink-700">Email Address</label>
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="john@example.com"
        autoComplete="email"
        className="mt-1.5 w-full rounded-md border border-ink-300/60 bg-white px-3.5 py-2.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
      />
      <p className="mt-1.5 text-xs text-ink-500">You&rsquo;ll use your email to sign in.</p>

      <label className="mt-5 block text-sm font-medium text-ink-700">Phone Number</label>
      <div className="mt-1.5 flex gap-2">
        <span className="flex items-center rounded-md border border-ink-300/60 px-3.5 text-sm text-ink-700">
          +234
        </span>
        <input
          inputMode="numeric"
          value={phone}
          onChange={(e) => setPhone(e.target.value.replace(/\D/g, ''))}
          placeholder="8012345678"
          autoComplete="tel-national"
          className="w-full rounded-md border border-ink-300/60 bg-white px-3.5 py-2.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
        />
      </div>

      <label className="mt-5 block text-sm font-medium text-ink-700">Password</label>
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Enter password"
        autoComplete="new-password"
        className="mt-1.5 w-full rounded-md border border-ink-300/60 bg-white px-3.5 py-2.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
      />
      {password && (
        <>
          <div className="mt-2 flex gap-1">
            {[0, 1, 2].map((n) => (
              <span
                key={n}
                className={`h-1 flex-1 rounded-full ${n < passed ? strengthColor : 'bg-ink-300/30'}`}
              />
            ))}
          </div>
          <p className="mt-1 text-xs text-ink-500">Password strength: {strength}</p>
        </>
      )}

      <label className="mt-5 block text-sm font-medium text-ink-700">Confirm Password</label>
      <input
        type="password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        placeholder="Re-enter password"
        autoComplete="new-password"
        className="mt-1.5 w-full rounded-md border border-ink-300/60 bg-white px-3.5 py-2.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
      />
      {confirm && confirm !== password && (
        <p className="mt-1 text-xs text-red-600">Passwords do not match</p>
      )}

      <VerificationChannelChoice value={channel} onChange={setChannel} />

      <div className="mt-5 space-y-1.5 rounded-lg bg-bone px-4 py-3 text-xs">
        <p className="font-medium text-ink-700">Password must contain:</p>
        <Requirement ok={checks.length}>At least 8 characters</Requirement>
        <Requirement ok={checks.upper}>One uppercase letter</Requirement>
        <Requirement ok={checks.digit}>One number</Requirement>
      </div>

      {(localError || error) && (
        <p role="alert" className="mt-4 rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
          {localError ?? error}
        </p>
      )}
      <button
        type="button"
        disabled={busy || !canContinue}
        onClick={submit}
        className="mt-6 w-full rounded-lg bg-emerald-deep px-4 py-3 text-sm font-semibold text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? 'Creating account…' : 'Continue'}
      </button>
    </div>
  );
}

/**
 * How the account proves ownership of an identifier (SCRUM-181; backend
 * SCRUM-180). Email is the default and the only enabled option.
 *
 * Phone is shown DISABLED rather than hidden: the backend path is complete and
 * tested (SCRUM-175/176), so this is a real product option that is temporarily
 * undeliverable — SMS from the current sender does not reach Nigerian networks
 * (see ng-sender-id-registration.md). Showing it sets the expectation that it
 * is coming; hiding it would make its later appearance look like a new feature.
 *
 * To enable it once a sender ID is registered: delete `disabled` here. The
 * backend, the /verify-otp screen and the routing below already work.
 */
/**
 * Terminal state of the funnel on the email channel: the user continues by
 * clicking the link, not by typing anything here.
 *
 * Restored from the version deleted in SCRUM-175 (when registration stopped
 * sending links), with a resend control the original lacked — /auth/verify/
 * email/resend has existed since SCRUM-154 and a dead end here was the most
 * common reason to abandon signup.
 */
function CheckEmailStep({ email }: { email: string }) {
  const [state, setState] = useState<'idle' | 'sending' | 'sent'>('idle');
  const [error, setError] = useState<string | null>(null);

  async function resend() {
    if (state === 'sending') return;
    setState('sending');
    setError(null);
    try {
      const resp = await fetch('/api/auth/verify-email/resend', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      if (resp.status === 202) {
        setState('sent');
        return;
      }
      const b = (await resp.json().catch(() => ({}))) as { error?: string };
      setState('idle');
      setError(
        b.error === 'VERIFICATION_RATE_LIMITED'
          ? 'Too many requests. Please wait a little and try again.'
          : 'Could not send another link just now. Please try again.',
      );
    } catch {
      setState('idle');
      setError('Could not reach the server. Please try again.');
    }
  }

  return (
    <div className="text-center">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-deep/12 text-emerald-deep">
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
          <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
          <path d="M3 7l9 6 9-6" />
        </svg>
      </div>

      <h1 className="mt-6 font-display text-2xl text-ink-900">Check your email</h1>
      <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-ink-500">
        We&rsquo;ve sent a verification link to{' '}
        <span className="font-medium text-ink-900">{email || 'your email address'}</span>. Open it
        to activate your account and sign in.
      </p>

      <div className="mx-auto mt-7 max-w-sm space-y-2 rounded-xl bg-surface-warm px-4 py-3.5 text-left text-sm text-ink-500">
        <p>The link expires in 30 minutes and can only be used once.</p>
        <p>Not there? Check your spam or promotions folder.</p>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
          {error}
        </p>
      )}

      {state === 'sent' ? (
        <p className="mt-6 rounded-md bg-emerald-deep/10 px-3.5 py-3 text-sm text-emerald-deep">
          If that email needs verification, we&rsquo;ve sent a new link.
        </p>
      ) : (
        <p className="mt-6 text-sm text-ink-500">
          Didn&rsquo;t get it?{' '}
          <button
            type="button"
            onClick={() => void resend()}
            disabled={state === 'sending'}
            className="font-medium text-emerald-deep hover:underline disabled:opacity-60"
          >
            {state === 'sending' ? 'Sending…' : 'Resend link'}
          </button>
        </p>
      )}

      <p className="mt-6 text-sm text-ink-500">
        Already verified?{' '}
        <Link href="/login" className="font-medium text-emerald-deep hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}


function VerificationChannelChoice({
  value,
  onChange,
}: {
  value: VerificationChannel;
  onChange: (v: VerificationChannel) => void;
}) {
  const options: {
    value: VerificationChannel;
    label: string;
    desc: string;
    disabled?: boolean;
  }[] = [
    {
      value: 'email',
      label: 'Email',
      desc: 'We send a secure link to your inbox',
    },
    {
      value: 'phone',
      label: 'Phone (SMS)',
      desc: 'A 6-digit code by text message',
      disabled: true,
    },
  ];

  return (
    <fieldset className="mt-5">
      <legend className="block text-sm font-medium text-ink-700">How should we verify you?</legend>
      <div className="mt-1.5 grid grid-cols-2 gap-2.5">
        {options.map((o) => {
          const active = o.value === value && !o.disabled;
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={active}
              aria-disabled={o.disabled || undefined}
              disabled={o.disabled}
              onClick={() => onChange(o.value)}
              className={`relative flex flex-col rounded-xl border px-4 py-3.5 text-left transition ${
                active
                  ? 'border-emerald-deep bg-emerald-deep/5'
                  : o.disabled
                    ? 'cursor-not-allowed border-ink-300/40 bg-surface-muted'
                    : 'border-ink-300/40 hover:border-ink-500'
              }`}
            >
              <span
                className={`text-sm font-medium ${o.disabled ? 'text-ink-400' : 'text-ink-900'}`}
              >
                {o.label}
              </span>
              <span className={`mt-0.5 text-xs ${o.disabled ? 'text-ink-400' : 'text-ink-500'}`}>
                {o.disabled ? 'Coming soon' : o.desc}
              </span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}


function Requirement({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <p className={`flex items-center gap-2 ${ok ? 'text-emerald-deep' : 'text-ink-500'}`}>
      <span aria-hidden>{ok ? '✓' : '○'}</span>
      {children}
    </p>
  );
}

function SellerAuthorityStep({
  busy,
  error,
  onBack,
  onContinue,
}: {
  busy: boolean;
  error: string | null;
  onBack: () => void;
  onContinue: (authority: SellerAuthority) => void;
}) {
  const [authority, setAuthority] = useState<SellerAuthority | ''>('');
  const options: { value: SellerAuthority; title: string; desc: string }[] = [
    { value: 'owner', title: 'Property Owner', desc: 'I own the property' },
    { value: 'power_of_attorney', title: 'Power of Attorney', desc: 'Authorized to sell on the owner’s behalf' },
  ];

  return (
    <div>
      <button onClick={onBack} className="mb-6 text-sm text-ink-500 hover:text-ink-900">
        ← Back
      </button>
      <h1 className="text-center font-display text-3xl text-ink-900">How do you sell?</h1>
      <p className="mt-2 text-center text-sm text-ink-500">
        This sets up your listing authority. You&rsquo;ll verify the details (NIN or Power of
        Attorney) when you create your first listing.
      </p>

      <div className="mt-8 grid grid-cols-2 gap-3">
        {options.map((o) => {
          const active = authority === o.value;
          return (
            <button
              key={o.value}
              type="button"
              onClick={() => setAuthority(o.value)}
              className={`rounded-xl border px-4 py-4 text-left transition ${
                active ? 'border-emerald-deep bg-emerald-deep/5' : 'border-ink-300/50 hover:border-ink-500'
              }`}
            >
              <span className="block text-sm font-medium text-ink-900">{o.title}</span>
              <span className="mt-0.5 block text-xs text-ink-500">{o.desc}</span>
            </button>
          );
        })}
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
          {error}
        </p>
      )}
      <button
        type="button"
        disabled={busy || authority === ''}
        onClick={() => authority && onContinue(authority)}
        className="mt-6 w-full rounded-lg bg-emerald-deep px-4 py-3 text-sm font-semibold text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? 'Creating account…' : 'Create account'}
      </button>
    </div>
  );
}
