import type { Metadata } from 'next';
import { Suspense } from 'react';

import { ResetPasswordClient } from './reset-password-client';

export const metadata: Metadata = {
  title: 'Set a new password · Maihomme',
};

/**
 * Landing page for the password-reset link (SCRUM-191). The email links here
 * with `?token=…`; the client component reads the token, collects a new
 * password, and POSTs both to /api/auth/password/reset. The token is spent via
 * a POST (not this GET) so it never lands in server access logs.
 *
 * Unlike /verify-email this page does NOT act on mount — the token is only
 * spent once the user has actually typed a password. See design/password-recovery.
 */
export default function ResetPasswordPage() {
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
          <p className="text-xs uppercase tracking-[0.2em] text-bone/50">Account recovery</p>
          <h1 className="mt-4 font-display text-4xl leading-tight text-bone">
            Choose a new password.
          </h1>
          <p className="mt-5 text-sm leading-relaxed text-bone/70">
            Setting a new password signs you out everywhere else, so anyone still using your account
            loses access.
          </p>
        </div>

        <p className="relative z-10 text-xs text-bone/40">Secure · encrypted · af-south-1</p>
      </section>

      <section className="flex items-center justify-center px-6 py-16 sm:px-12">
        <Suspense fallback={null}>
          <ResetPasswordClient />
        </Suspense>
      </section>
    </main>
  );
}
