import type { Metadata } from 'next';
import { Suspense } from 'react';

import { ForgotPasswordForm } from './forgot-password-form';
import { isNonAdminRole } from '@/lib/session';

export const metadata: Metadata = {
  title: 'Forgot password · Maihomme',
};

/**
 * Request a password-reset link (SCRUM-191).
 *
 * Deliberately NO session redirect, unlike /login. A signed-in user is a
 * legitimate visitor here: Settings → Security links to this page for someone
 * who cannot recall their current password (the change-password form needs it)
 * or who has none at all. Bouncing a session holder to the dashboard would make
 * that link a no-op.
 *
 * Shares the split-panel shell with /login and /verify-email; the role comes
 * through from the "Forgot password?" link so the left panel keeps saying the
 * same thing it said on the sign-in screen the user just left.
 */
const ROLE_PANEL: Record<string, string> = {
  buyer: 'Browse verified listings and apply for a soft loan of up to 50% of the price.',
  seller: 'List your property, respond to verified buyers, and track every deal to close.',
  realtor: 'Manage client listings, coordinate inspections, and grow your commission income.',
};

export default function ForgotPasswordPage({
  searchParams,
}: {
  searchParams: { role?: string | string[] };
}) {
  const roleParam = Array.isArray(searchParams.role) ? searchParams.role[0] : searchParams.role;
  const role = isNonAdminRole(roleParam) ? roleParam : 'buyer';

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
            Locked out? Let&rsquo;s get you back in.
          </h1>
          <p className="mt-5 text-sm leading-relaxed text-bone/70">
            {ROLE_PANEL[role] ?? ROLE_PANEL.buyer}
          </p>
        </div>

        <p className="relative z-10 text-xs text-bone/40">Secure · encrypted · af-south-1</p>
      </section>

      <section className="flex items-center justify-center px-6 py-16 sm:px-12">
        <div className="w-full max-w-sm animate-rise">
          <div className="mb-9 lg:hidden">
            <span className="font-display text-2xl tracking-tight text-emerald-deep">Maihomme</span>
          </div>

          <Suspense fallback={null}>
            <ForgotPasswordForm role={role} />
          </Suspense>
        </div>
      </section>
    </main>
  );
}
