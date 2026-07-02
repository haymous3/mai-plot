import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { Suspense } from 'react';

import { LoginForm } from './login-form';
import { BUYER_HOME } from '@/lib/buyer-auth';
import { buyerAccessToken } from '@/lib/buyer-server-api';

export const metadata: Metadata = {
  title: 'Sign in · Maiplot',
};

export default function BuyerLoginPage() {
  // Already signed in — skip the form.
  if (buyerAccessToken()) redirect(BUYER_HOME);

  return (
    <main className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <section className="grain relative hidden overflow-hidden bg-emerald-deep px-12 py-14 text-bone lg:flex lg:flex-col lg:justify-between">
        <div className="relative z-10 flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-sm bg-bone/10 font-display text-lg text-bone ring-1 ring-bone/20">
            M
          </span>
          <span className="font-display text-xl tracking-tight">Maiplot</span>
        </div>

        <div className="relative z-10 max-w-md">
          <p className="text-xs uppercase tracking-[0.2em] text-bone/50">Buyers &amp; investors</p>
          <h1 className="mt-4 font-display text-4xl leading-tight text-bone">
            Finance your property purchase in days, not months.
          </h1>
          <p className="mt-5 text-sm leading-relaxed text-bone/70">
            Browse verified listings and apply for a soft loan of up to 50% of the price, funded
            through our bank partners and protected via escrow.
          </p>
        </div>

        <p className="relative z-10 text-xs text-bone/40">Secure · encrypted · af-south-1</p>
      </section>

      <section className="flex items-center justify-center px-6 py-16 sm:px-12">
        <div className="w-full max-w-sm animate-rise">
          <div className="mb-9 lg:hidden">
            <span className="font-display text-2xl tracking-tight text-emerald-deep">Maiplot</span>
          </div>

          <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Buyer account</p>
          <h2 className="mt-2 font-display text-3xl text-ink-900">Sign in</h2>
          <p className="mt-2 text-sm text-ink-500">
            Sign in to browse financing and track your loan applications.
          </p>

          <div className="mt-8">
            <Suspense fallback={null}>
              <LoginForm />
            </Suspense>
          </div>

          <p className="mt-8 text-sm text-ink-500">
            New to Maiplot?{' '}
            <a href="/register" className="font-medium text-emerald-deep hover:underline">
              Create an account
            </a>
          </p>
        </div>
      </section>
    </main>
  );
}
