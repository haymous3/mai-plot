'use client';

import Link from 'next/link';
import { useState } from 'react';

// Onboarding (SCRUM-132 → reworked SCRUM-155 for email verification):
// intro carousel → role select → account details (name/email/phone/password)
// → [seller: selling authority] → register → "check your email".
//
// Verification is now an email magic link (SCRUM-152): registration no longer
// establishes a session, so the old post-OTP steps (set-password, personal
// details, KYC) are gone. KYC moves to point-of-need (buyer BVN at loan-apply,
// seller NIN/PoA at listing creation — both already gate there). The session is
// established when the user clicks the email link and lands on /verify-email.

const SLIDES = [
  {
    title: 'Access Distress & Premium Property Deals',
    body: 'From value deals to prime locations, buyers explore verified options, sellers connect with serious buyers.',
  },
  {
    title: 'Verified Documents & Listings',
    body: 'Every property is thoroughly vetted — transparency for buyers, credibility for sellers.',
  },
  {
    title: 'Get Financing in Days',
    body: 'Buyers access loans up to 50% of property value, sellers get paid faster with approved buyers.',
  },
];

const ROLES = [
  { value: 'buyer', label: 'Buyer / Investor', desc: 'Find verified properties and get financing to close deals fast' },
  { value: 'seller', label: 'Property Seller', desc: 'List your property and connect with serious, pre-qualified buyers' },
  { value: 'realtor', label: 'Realtor / Agent', desc: 'Grow your business with verified listings and commission tracking' },
];

const REGISTER_ERRORS: Record<string, string> = {
  EMAIL_ALREADY_REGISTERED: 'An account with this email already exists. Try signing in.',
  PHONE_ALREADY_REGISTERED: 'An account with this phone number already exists. Try signing in.',
  VERIFICATION_RATE_LIMITED: 'Too many attempts for this email. Please try again later.',
  VERIFICATION_EMAIL_FAILED: 'We could not send the verification email. Please retry.',
  VALIDATION_ERROR: 'Please check your details and try again.',
  INVALID_REQUEST: 'Please complete all required fields.',
  AUTH_SERVICE_UNAVAILABLE: 'Sign-up is temporarily unavailable. Please retry.',
};

type Step = 'intro' | 'role' | 'account' | 'seller-authority' | 'check-email';
type SellerAuthority = 'owner' | 'power_of_attorney';

export function RegisterFlow() {
  const [step, setStep] = useState<Step>('intro');
  const [role, setRole] = useState('');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
          ...(role === 'seller' && sellerAuthority
            ? { seller_authority_type: sellerAuthority }
            : {}),
        }),
      });
      if (resp.ok) {
        setStep('check-email');
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
    <main className="min-h-screen bg-white">
      <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-12">
        {step === 'intro' && <Intro onDone={() => setStep('role')} />}

        {step === 'role' && (
          <RoleSelect
            role={role}
            setRole={setRole}
            onContinue={() => {
              setError(null);
              setStep('account');
            }}
          />
        )}

        {step === 'account' && (
          <AccountStep
            fullName={fullName}
            setFullName={setFullName}
            email={email}
            setEmail={setEmail}
            phone={phone}
            setPhone={setPhone}
            password={password}
            setPassword={setPassword}
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
        )}

        {step === 'seller-authority' && (
          <SellerAuthorityStep
            busy={busy}
            error={error}
            onBack={() => {
              setError(null);
              setStep('account');
            }}
            onContinue={(authority) => void submitRegister(authority)}
          />
        )}

        {step === 'check-email' && <CheckEmailStep email={email.trim()} />}

        {step !== 'check-email' && (
          <p className="mt-8 text-center text-sm text-ink-500">
            Already have an account?{' '}
            <Link href="/login" className="font-medium text-emerald-deep hover:underline">
              Sign in
            </Link>
          </p>
        )}
      </div>
    </main>
  );
}

function Intro({ onDone }: { onDone: () => void }) {
  const [i, setI] = useState(0);
  const last = i === SLIDES.length - 1;
  return (
    <div className="text-center">
      <div className="mb-8 flex items-center justify-between">
        <span className="font-display text-lg tracking-tight text-emerald-deep">Maiplot</span>
        <button onClick={onDone} className="text-sm text-ink-500 hover:text-ink-900">
          Skip
        </button>
      </div>
      <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-2xl bg-bone text-emerald-deep">
        <span className="font-display text-2xl">{i + 1}</span>
      </div>
      <h1 className="font-display text-2xl text-ink-900">{SLIDES[i].title}</h1>
      <p className="mx-auto mt-3 max-w-sm text-sm text-ink-500">{SLIDES[i].body}</p>
      <div className="mt-8 flex items-center justify-center gap-2">
        {SLIDES.map((_, n) => (
          <span
            key={n}
            className={`h-1.5 rounded-full transition-all ${n === i ? 'w-6 bg-emerald-deep' : 'w-1.5 bg-ink-300/50'}`}
          />
        ))}
      </div>
      <button
        onClick={() => (last ? onDone() : setI(i + 1))}
        className="mt-8 w-full rounded-lg bg-emerald-deep px-4 py-3 text-sm font-semibold text-bone transition hover:bg-emerald-accent"
      >
        {last ? 'Get Started' : 'Next'}
      </button>
    </div>
  );
}

function RoleSelect({
  role,
  setRole,
  onContinue,
}: {
  role: string;
  setRole: (r: string) => void;
  onContinue: () => void;
}) {
  return (
    <div>
      <h1 className="text-center font-display text-3xl text-ink-900">Welcome to Maiplot</h1>
      <p className="mt-2 text-center text-sm text-ink-500">Tell us what brings you here today</p>
      <ul className="mt-8 space-y-3">
        {ROLES.map((r) => {
          const active = r.value === role;
          return (
            <li key={r.value}>
              <button
                type="button"
                onClick={() => setRole(r.value)}
                className={`flex w-full items-center justify-between rounded-xl border px-5 py-4 text-left transition ${
                  active ? 'border-emerald-deep bg-emerald-deep/5' : 'border-ink-300/40 hover:border-ink-500'
                }`}
              >
                <span>
                  <span className="block font-medium text-ink-900">{r.label}</span>
                  <span className="mt-1 block text-xs text-ink-500">{r.desc}</span>
                </span>
                {active && (
                  <span className="ml-3 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-emerald-deep text-xs text-white">
                    ✓
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
      <button
        type="button"
        disabled={!role}
        onClick={onContinue}
        className="mt-8 w-full rounded-lg bg-emerald-deep px-4 py-3 text-sm font-semibold text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:opacity-50"
      >
        Continue
      </button>
    </div>
  );
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

function CheckEmailStep({ email }: { email: string }) {
  return (
    <div className="text-center">
      <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-bone">
        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-emerald-deep/10 text-3xl text-emerald-deep">
          ✉
        </span>
      </div>
      <h1 className="mt-6 font-display text-3xl text-ink-900">Check your email</h1>
      <p className="mx-auto mt-3 max-w-sm text-sm text-ink-500">
        We&rsquo;ve sent a verification link to{' '}
        <span className="font-medium text-ink-900">{email || 'your email address'}</span>. Open it to
        activate your account and sign in.
      </p>

      <div className="mx-auto mt-8 max-w-sm rounded-2xl bg-bone px-5 py-4 text-left text-sm text-ink-500">
        <p className="flex items-start gap-2">
          <span aria-hidden>⏱</span> The link expires in 30 minutes and can only be used once.
        </p>
        <p className="mt-2 flex items-start gap-2">
          <span aria-hidden>📁</span> Not there? Check your spam or promotions folder.
        </p>
      </div>

      <p className="mt-8 text-sm text-ink-500">
        Already verified?{' '}
        <Link href="/login" className="font-medium text-emerald-deep hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
