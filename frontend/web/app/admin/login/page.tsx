import type { Metadata } from 'next';

import { LoginForm } from './login-form';

export const metadata: Metadata = {
  title: 'Admin sign in · Maihomme',
  robots: { index: false, follow: false },
};

export default function AdminLoginPage() {
  return (
    <main className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      {/* Brand panel — institutional, deep, deliberately quiet. */}
      <section className="grain relative hidden overflow-hidden bg-emerald-deep px-12 py-14 text-bone lg:flex lg:flex-col lg:justify-between">
        <div className="relative z-10 flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-sm bg-bone/10 font-display text-lg text-bone ring-1 ring-bone/20">
            M
          </span>
          <span className="font-display text-xl tracking-tight">Maihomme</span>
        </div>

        <div className="relative z-10 max-w-md">
          <p className="text-xs uppercase tracking-[0.2em] text-bone/50">Operations console</p>
          <h1 className="mt-4 font-display text-4xl leading-tight text-bone">
            Curating Nigeria&rsquo;s distressed property, one verified deal at a time.
          </h1>
          <p className="mt-5 text-sm leading-relaxed text-bone/70">
            Review listings, verify Power-of-Attorney documents, and move deals from months to
            days. Access is restricted to authorised staff.
          </p>
        </div>

        <p className="relative z-10 text-xs text-bone/40">
          Restricted system · activity is logged · af-south-1
        </p>
      </section>

      {/* Form panel. */}
      <section className="flex items-center justify-center px-6 py-16 sm:px-12">
        <div className="w-full max-w-sm animate-rise">
          <div className="mb-9 lg:hidden">
            <span className="font-display text-2xl tracking-tight text-emerald-deep">Maihomme</span>
          </div>

          <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Admin &amp; legal team</p>
          <h2 className="mt-2 font-display text-3xl text-ink-900">Sign in</h2>
          <p className="mt-2 text-sm text-ink-500">
            Use your staff credentials to continue to the review queue.
          </p>

          <div className="mt-8">
            <LoginForm />
          </div>

          <p className="mt-8 text-xs leading-relaxed text-ink-300">
            This is a restricted, IP-allowlisted surface. Unauthorised access attempts are recorded.
          </p>
        </div>
      </section>
    </main>
  );
}
