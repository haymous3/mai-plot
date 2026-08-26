import type { Metadata } from 'next';
import { Suspense } from 'react';

import { VerifyEmailClient } from './verify-email-client';

export const metadata: Metadata = {
  title: 'Verify your email · Maihomme',
};

/**
 * Landing page for the account-verification magic link (SCRUM-153; backend
 * SCRUM-152). The email links here with `?token=…`; the client component reads
 * the token, POSTs it to /api/auth/verify-email, and shows the outcome. The
 * token is confirmed via a POST (not this GET) so it never lands in server
 * access logs.
 */
export default function VerifyEmailPage() {
  return (
    <main className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <section className="grain relative hidden overflow-hidden bg-emerald-deep px-12 py-14 text-bone lg:flex lg:flex-col lg:justify-between">
        <div className="relative z-10 flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-sm bg-bone/10 font-display text-lg text-bone ring-1 ring-bone/20">
            M
          </span>
          <span className="font-display text-xl tracking-tight">Maihomme</span>
        </div>

        <div className="relative z-10 max-w-md">
          <p className="text-xs uppercase tracking-[0.2em] text-bone/50">Almost there</p>
          <h1 className="mt-4 font-display text-4xl leading-tight text-bone">
            One click to confirm it&rsquo;s really you.
          </h1>
          <p className="mt-5 text-sm leading-relaxed text-bone/70">
            Verifying your email keeps your account secure and unlocks listings, offers, and
            financing.
          </p>
        </div>

        <p className="relative z-10 text-xs text-bone/40">Secure · encrypted · af-south-1</p>
      </section>

      <section className="flex items-center justify-center px-6 py-16 sm:px-12">
        <Suspense fallback={null}>
          <VerifyEmailClient />
        </Suspense>
      </section>
    </main>
  );
}
