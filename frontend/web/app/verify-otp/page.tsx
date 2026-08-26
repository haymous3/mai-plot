import type { Metadata } from 'next';
import { Suspense } from 'react';

import { VerifyOtpClient } from './verify-otp-client';

export const metadata: Metadata = {
  title: 'Enter your code · Maihomme',
};

/**
 * Registration OTP entry (SCRUM-175 PR3; backend SCRUM-175 + SCRUM-176).
 *
 * The register funnel lands here after POST /auth/register, which now sends a
 * 6-digit code by SMS rather than an email link. The client component reads the
 * phone from sessionStorage — deliberately NOT a query parameter, since an
 * MSISDN is PII and would otherwise sit in browser history and server access
 * logs (the same reasoning that made /verify-email POST its token instead of
 * taking it from a GET).
 *
 * The shell mirrors /verify-email so the two verification routes feel like one
 * product; only the right-hand panel differs.
 */
export default function VerifyOtpPage() {
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
            Six digits, and your account is live.
          </h1>
          <p className="mt-5 text-sm leading-relaxed text-bone/70">
            We text a short code instead of a password so nobody can sign up with a number they
            don&rsquo;t control.
          </p>
        </div>

        <p className="relative z-10 text-xs text-bone/40">Secure &middot; encrypted &middot; af-south-1</p>
      </section>

      <section className="flex items-center justify-center px-6 py-16 sm:px-12">
        <Suspense fallback={null}>
          <VerifyOtpClient />
        </Suspense>
      </section>
    </main>
  );
}
