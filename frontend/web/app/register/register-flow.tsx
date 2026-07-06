'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useRef, useState } from 'react';

// Onboarding: intro carousel → role select → phone → OTP → password → personal
// details (SCRUM-132). Mobile-styled Figma built as a responsive web funnel.

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
  PHONE_ALREADY_REGISTERED: 'An account with this phone number already exists. Try signing in.',
  OTP_RATE_LIMITED: 'Too many requests for this number. Please try again later.',
  OTP_DISPATCH_FAILED: 'We could not send the code. Please retry.',
  INVALID_REQUEST: 'Please enter a valid phone number.',
  AUTH_SERVICE_UNAVAILABLE: 'Sign-up is temporarily unavailable. Please retry.',
};

type Step = 'intro' | 'role' | 'phone' | 'otp' | 'password' | 'personal';

export function RegisterFlow() {
  const router = useRouter();
  const [step, setStep] = useState<Step>('intro');
  const [role, setRole] = useState('');
  const [phone, setPhone] = useState('');
  const [redirect, setRedirect] = useState('/dashboard');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
              setStep('phone');
            }}
          />
        )}
        {step === 'phone' && (
          <PhoneStep
            phone={phone}
            setPhone={setPhone}
            busy={busy}
            error={error}
            onBack={() => setStep('role')}
            onSubmit={async () => {
              setError(null);
              const local = phone.replace(/\D/g, '').replace(/^0/, '');
              if (local.length !== 10) {
                setError('Enter a valid 10-digit phone number.');
                return;
              }
              setBusy(true);
              try {
                const resp = await fetch('/api/auth/register', {
                  method: 'POST',
                  headers: { 'content-type': 'application/json' },
                  body: JSON.stringify({ phone: `+234${local}`, role }),
                });
                if (resp.ok) {
                  setStep('otp');
                  return;
                }
                const b = (await resp.json()) as { error_code?: string };
                setError(REGISTER_ERRORS[b.error_code ?? ''] ?? 'Could not start sign-up.');
              } catch {
                setError('Could not reach the server. Please try again.');
              } finally {
                setBusy(false);
              }
            }}
          />
        )}
        {step === 'otp' && (
          <OtpStep
            phone={`+234${phone.replace(/\D/g, '').replace(/^0/, '')}`}
            busy={busy}
            error={error}
            onVerify={async (code) => {
              setError(null);
              setBusy(true);
              try {
                const resp = await fetch('/api/auth/verify-otp', {
                  method: 'POST',
                  headers: { 'content-type': 'application/json' },
                  body: JSON.stringify({
                    phone: `+234${phone.replace(/\D/g, '').replace(/^0/, '')}`,
                    otp: code,
                  }),
                });
                const b = (await resp.json()) as {
                  ok?: boolean;
                  redirect?: string;
                  error_code?: string;
                };
                if (resp.ok && b.ok) {
                  setRedirect(b.redirect ?? '/dashboard');
                  setStep('password');
                  return;
                }
                setError(
                  b.error_code === 'OTP_EXPIRED'
                    ? 'That code has expired. Request a new one.'
                    : 'That code is invalid. Please check and retry.',
                );
              } catch {
                setError('Could not reach the server. Please try again.');
              } finally {
                setBusy(false);
              }
            }}
          />
        )}
        {step === 'password' && (
          <PasswordStep
            busy={busy}
            error={error}
            onSubmit={async (password) => {
              setError(null);
              setBusy(true);
              try {
                const resp = await fetch('/api/auth/set-password', {
                  method: 'POST',
                  headers: { 'content-type': 'application/json' },
                  body: JSON.stringify({ password }),
                });
                if (resp.ok) {
                  setStep('personal');
                  return;
                }
                const b = (await resp.json()) as { error_code?: string };
                setError(
                  b.error_code === 'PASSWORD_TOO_WEAK'
                    ? 'Password must be at least 8 characters with an uppercase letter and a number.'
                    : 'Could not set your password. Please retry.',
                );
              } catch {
                setError('Could not reach the server. Please try again.');
              } finally {
                setBusy(false);
              }
            }}
          />
        )}
        {step === 'personal' && (
          <PersonalDetailsStep
            busy={busy}
            error={error}
            onSubmit={async (fullName, email) => {
              setError(null);
              setBusy(true);
              try {
                const resp = await fetch('/api/auth/profile', {
                  method: 'POST',
                  headers: { 'content-type': 'application/json' },
                  body: JSON.stringify({ full_name: fullName, email: email || null }),
                });
                if (resp.ok) {
                  router.replace(redirect);
                  router.refresh();
                  return;
                }
                const b = (await resp.json()) as { error_code?: string };
                setError(
                  b.error_code === 'EMAIL_ALREADY_IN_USE'
                    ? 'That email is already linked to another account.'
                    : b.error_code === 'FULL_NAME_REQUIRED'
                      ? 'Please enter your full name.'
                      : 'Could not save your details. Please retry.',
                );
              } catch {
                setError('Could not reach the server. Please try again.');
              } finally {
                setBusy(false);
              }
            }}
          />
        )}

        {step !== 'personal' && (
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
                  <span className="ml-3 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-emerald-accent text-xs text-white">
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

function PhoneStep({
  phone,
  setPhone,
  busy,
  error,
  onBack,
  onSubmit,
}: {
  phone: string;
  setPhone: (p: string) => void;
  busy: boolean;
  error: string | null;
  onBack: () => void;
  onSubmit: () => void;
}) {
  return (
    <div>
      <button onClick={onBack} className="mb-6 text-sm text-ink-500 hover:text-ink-900">
        ← Back
      </button>
      <h1 className="text-center font-display text-3xl text-ink-900">Enter your phone number</h1>
      <p className="mt-2 text-center text-sm text-ink-500">We&rsquo;ll send you a verification code</p>
      <label className="mt-8 block text-sm font-medium text-ink-700">Phone Number</label>
      <div className="mt-1.5 flex gap-2">
        <span className="flex items-center rounded-md border border-ink-300/60 px-3.5 text-sm text-ink-700">
          +234
        </span>
        <input
          inputMode="numeric"
          value={phone}
          onChange={(e) => setPhone(e.target.value.replace(/\D/g, ''))}
          placeholder="8012345678"
          className="w-full rounded-md border border-ink-300/60 bg-white px-3.5 py-2.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
        />
      </div>
      <div className="mt-4 flex gap-2 rounded-lg bg-bone px-4 py-3 text-xs text-ink-500">
        <span aria-hidden>🛡</span> Your number is safe with us. We use encryption to protect your data.
      </div>
      {error && (
        <p role="alert" className="mt-4 rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
          {error}
        </p>
      )}
      <button
        type="button"
        disabled={busy}
        onClick={onSubmit}
        className="mt-6 w-full rounded-lg bg-emerald-deep px-4 py-3 text-sm font-semibold text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:opacity-60"
      >
        {busy ? 'Sending…' : 'Send OTP'}
      </button>
    </div>
  );
}

function OtpStep({
  phone,
  busy,
  error,
  onVerify,
}: {
  phone: string;
  busy: boolean;
  error: string | null;
  onVerify: (code: string) => void;
}) {
  const [digits, setDigits] = useState<string[]>(['', '', '', '', '', '']);
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const code = digits.join('');

  function setDigit(i: number, v: string) {
    const d = v.replace(/\D/g, '').slice(-1);
    setDigits((prev) => {
      const next = [...prev];
      next[i] = d;
      return next;
    });
    if (d && i < 5) refs.current[i + 1]?.focus();
  }

  return (
    <div>
      <h1 className="text-center font-display text-3xl text-ink-900">Verify your number</h1>
      <p className="mt-2 text-center text-sm text-ink-500">
        Enter the 6-digit code sent to <span className="font-medium text-ink-900">{phone}</span>
      </p>
      <div className="mt-8 flex justify-center gap-2">
        {digits.map((d, i) => (
          <input
            key={i}
            ref={(el) => {
              refs.current[i] = el;
            }}
            inputMode="numeric"
            maxLength={1}
            value={d}
            onChange={(e) => setDigit(i, e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Backspace' && !digits[i] && i > 0) refs.current[i - 1]?.focus();
            }}
            className="h-12 w-12 rounded-lg border border-ink-300/60 text-center text-lg text-ink-900 outline-none transition focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
          />
        ))}
      </div>
      {error && (
        <p role="alert" className="mt-4 rounded-md bg-red-50 px-3.5 py-2.5 text-center text-sm text-red-700">
          {error}
        </p>
      )}
      <button
        type="button"
        disabled={busy || code.length !== 6}
        onClick={() => onVerify(code)}
        className="mt-6 w-full rounded-lg bg-emerald-deep px-4 py-3 text-sm font-semibold text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? 'Verifying…' : 'Verify'}
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

function PasswordStep({
  busy,
  error,
  onSubmit,
}: {
  busy: boolean;
  error: string | null;
  onSubmit: (password: string) => void;
}) {
  const [pw, setPw] = useState('');
  const [confirm, setConfirm] = useState('');
  const checks = passwordChecks(pw);
  const passed = Object.values(checks).filter(Boolean).length;
  const strong = passed === 3;
  const meets = strong && confirm === pw;
  const strength = passed <= 1 ? 'Weak' : passed === 2 ? 'Medium' : 'Strong';
  const strengthColor = passed <= 1 ? 'bg-red-500' : passed === 2 ? 'bg-amber-500' : 'bg-emerald-accent';

  return (
    <div>
      <h1 className="text-center font-display text-3xl text-ink-900">Create a password</h1>
      <p className="mt-2 text-center text-sm text-ink-500">Secure your account with a strong password</p>

      <label className="mt-8 block text-sm font-medium text-ink-700">Password</label>
      <input
        type="password"
        value={pw}
        onChange={(e) => setPw(e.target.value)}
        placeholder="Enter password"
        className="mt-1.5 w-full rounded-md border border-ink-300/60 bg-white px-3.5 py-2.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
      />
      {pw && (
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
        className="mt-1.5 w-full rounded-md border border-ink-300/60 bg-white px-3.5 py-2.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
      />
      {confirm && confirm !== pw && (
        <p className="mt-1 text-xs text-red-600">Passwords do not match</p>
      )}

      <div className="mt-5 space-y-1.5 rounded-lg bg-bone px-4 py-3 text-xs">
        <p className="font-medium text-ink-700">Password must contain:</p>
        <Requirement ok={checks.length}>At least 8 characters</Requirement>
        <Requirement ok={checks.upper}>One uppercase letter</Requirement>
        <Requirement ok={checks.digit}>One number</Requirement>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
          {error}
        </p>
      )}
      <button
        type="button"
        disabled={busy || !meets}
        onClick={() => onSubmit(pw)}
        className="mt-6 w-full rounded-lg bg-emerald-deep px-4 py-3 text-sm font-semibold text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? 'Finishing…' : 'Continue'}
      </button>
    </div>
  );
}

function Requirement({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <p className={`flex items-center gap-2 ${ok ? 'text-emerald-accent' : 'text-ink-500'}`}>
      <span aria-hidden>{ok ? '✓' : '○'}</span>
      {children}
    </p>
  );
}

function PersonalDetailsStep({
  busy,
  error,
  onSubmit,
}: {
  busy: boolean;
  error: string | null;
  onSubmit: (fullName: string, email: string) => void;
}) {
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const canSubmit = fullName.trim().length > 0;

  return (
    <div>
      <h1 className="text-center font-display text-3xl text-ink-900">Personal details</h1>
      <p className="mt-2 text-center text-sm text-ink-500">Tell us a bit about yourself</p>

      <div className="mx-auto mt-8 flex h-20 w-20 items-center justify-center rounded-full bg-bone text-emerald-deep">
        <span aria-hidden className="text-2xl">
          {fullName.trim() ? fullName.trim()[0].toUpperCase() : '👤'}
        </span>
      </div>

      <label className="mt-8 block text-sm font-medium text-ink-700">
        Full Name <span className="text-red-500">*</span>
      </label>
      <input
        value={fullName}
        onChange={(e) => setFullName(e.target.value)}
        placeholder="John Doe"
        autoComplete="name"
        className="mt-1.5 w-full rounded-md border border-ink-300/60 bg-white px-3.5 py-2.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
      />

      <label className="mt-5 block text-sm font-medium text-ink-700">
        Email Address <span className="text-ink-500">(Optional)</span>
      </label>
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="john@example.com"
        autoComplete="email"
        className="mt-1.5 w-full rounded-md border border-ink-300/60 bg-white px-3.5 py-2.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
      />
      <p className="mt-1.5 text-xs text-ink-500">You&rsquo;ll use your email to sign in.</p>

      {error && (
        <p role="alert" className="mt-4 rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
          {error}
        </p>
      )}
      <button
        type="button"
        disabled={busy || !canSubmit}
        onClick={() => onSubmit(fullName.trim(), email.trim())}
        className="mt-6 w-full rounded-lg bg-emerald-deep px-4 py-3 text-sm font-semibold text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? 'Saving…' : 'Continue'}
      </button>
    </div>
  );
}
