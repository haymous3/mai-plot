import Link from 'next/link';

import { onboardingExit, welcomeGreeting } from '@/lib/onboarding-steps';

/**
 * Closing screen, shared by all three roles — the `*-flow-after-email-
 * verification-{3,4,2}.png` exports. They are the same screen: only the name,
 * the subcopy and the profile label differ, so this is one component rather
 * than three near-copies.
 *
 * Measured (1562 artboard, 1:1 — column 768):
 *   badge        160px `emerald-deep/10` circle (that alpha composites to
 *                exactly the measured #e7eceb) with a 100px emerald check
 *   title        ~58px band; 56px here, which keeps a long Nigerian given name
 *                on one line where 60 would wrap
 *   profile card 768×268, no border, diagonal gradient — measured darkest at
 *                the top-left (#0f3d2e) and lightest at the bottom-right
 *                (#1a5540)
 *   stat tiles   240×112 at a 24px gutter (3×240 + 2×24 = 768), `surface-warm`,
 *                20px bold `emerald-deep` value over a 14px `ink-500` label
 *
 * The CTA is the shared 68px button, not the 76px this one export draws — one
 * button component across the flow is worth more than 8px on the last screen.
 *
 * ⚠️ THE STAT TILES ARE MARKETING FIGURES, hardcoded. They are identical on all
 * three exports (including "Fast / Loans" for a realtor), and there is no
 * metrics endpoint to source them from — analytics-service exposes only the
 * admin audit log. Same standing gap as the landing page's stats.
 */

const COPY: Record<string, { profile: string; subtitle: string }> = {
  buyer: {
    profile: 'Buyer',
    subtitle: 'Start exploring verified properties and get instant loan pre-approval',
  },
  seller: {
    profile: 'Seller',
    subtitle: 'List your properties and connect with verified buyers instantly',
  },
  realtor: {
    profile: 'Realtor',
    subtitle: 'Access your professional dashboard and manage listings',
  },
};

const STATS = [
  { value: '2.5K+', label: 'Properties' },
  { value: '98%', label: 'Verified' },
  { value: 'Fast', label: 'Loans' },
];

export function Welcome({ role, fullName }: { role: string; fullName?: string | null }) {
  const copy = COPY[role] ?? COPY.buyer;
  // Derived in lib/ so it is testable — vitest collects lib/** only, and the
  // empty-string case (accounts predating SCRUM-197) is easy to get wrong.
  const greeting = welcomeGreeting(fullName);

  return (
    <div className="w-full text-center">
      <span className="mx-auto flex h-40 w-40 items-center justify-center rounded-full bg-emerald-deep/10 text-emerald-deep">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-[100px] w-[100px]" aria-hidden>
          <circle cx="12" cy="12" r="9" />
          <path d="m8.5 12.2 2.4 2.4 4.6-5" />
        </svg>
      </span>

      <h1 className="mt-10 text-[36px] font-bold leading-[1.1] text-ink-buyer sm:text-[56px]">
        {greeting}
      </h1>
      <p className="mx-auto mt-4 max-w-[640px] text-lg leading-7 text-ink-500 sm:text-xl">
        {copy.subtitle}
      </p>

      <div className="mt-12 rounded-2xl bg-gradient-to-br from-emerald-deep to-[#1a5540] p-9 text-left text-white">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-base leading-6 text-white/70">Your Profile</p>
            <p className="mt-1 text-[28px] font-semibold leading-9">{copy.profile}</p>
          </div>
          <span className="flex h-14 w-14 flex-none items-center justify-center rounded-full bg-white/10 text-white">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6" aria-hidden>
              <circle cx="12" cy="12" r="9" />
              <path d="m8.5 12.2 2.4 2.4 4.6-5" />
            </svg>
          </span>
        </div>

        <hr className="my-9 border-white/15" />

        <p className="text-base leading-6 text-white/70">Account Status</p>
        {/*
          "Verification in progress" is accurate rather than decorative: BVN and
          NIN checks are 202-accepted and resolved asynchronously, and a PoA
          seller waits on manual legal review (CLAUDE.md §8.1). Nobody reaches
          this screen already verified.
        */}
        <p className="mt-2 flex items-center gap-2.5 text-base leading-6">
          <span aria-hidden className="h-2.5 w-2.5 flex-none rounded-full bg-status-gold" />
          Verification in progress
        </p>
      </div>

      <Link
        href={onboardingExit(role)}
        className="mt-6 flex h-[68px] w-full items-center justify-center gap-2.5 rounded-2xl bg-emerald-deep text-base font-semibold text-white transition hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-deep focus-visible:ring-offset-2"
      >
        Go to Dashboard
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5" aria-hidden>
          <path d="M4 12h15" />
          <path d="m13 6 6 6-6 6" />
        </svg>
      </Link>

      <dl className="mt-6 grid grid-cols-3 gap-6">
        {STATS.map((s) => (
          <div key={s.label} className="flex h-28 flex-col items-center justify-center rounded-2xl bg-surface-warm">
            <dd className="text-xl font-bold leading-7 text-emerald-deep">{s.value}</dd>
            <dt className="mt-1 text-sm leading-5 text-ink-500">{s.label}</dt>
          </div>
        ))}
      </dl>

      <p className="mt-10 text-base leading-6 text-ink-500">Secure • Transparent • Trusted</p>
    </div>
  );
}
