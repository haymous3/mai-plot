import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { SESSION_LOGIN } from '@/lib/session';
import { sessionAccessToken } from '@/lib/session-server';

export const metadata: Metadata = {
  title: 'Realtor · Maiplot',
};

/** Placeholder landing for a signed-in realtor. The full realtor onboarding +
 * dashboard land with their Figma (deferred — SCRUM-132 remaining screens). */
export default function RealtorHomePage() {
  if (!sessionAccessToken()) redirect(SESSION_LOGIN);
  return (
    <main className="mx-auto max-w-md px-6 py-24 text-center">
      <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Realtor</p>
      <h1 className="mt-2 font-display text-3xl text-ink-900">You&rsquo;re signed in</h1>
      <p className="mt-3 text-sm text-ink-500">
        Your realtor workspace — assignments, inspections, and commissions — is coming next.
      </p>
    </main>
  );
}
