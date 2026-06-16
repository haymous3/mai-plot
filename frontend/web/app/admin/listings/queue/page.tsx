import type { Metadata } from 'next';

import { SignOutButton } from '../../sign-out-button';

export const metadata: Metadata = {
  title: 'Listing review queue · Maiplot',
  robots: { index: false, follow: false },
};

// Redirect target after admin sign-in (SCRUM-59). The queue itself is built in
// SCRUM-60 — this is the authenticated landing shell it will fill in.
export default function ListingQueuePage() {
  return (
    <div className="min-h-screen bg-bone">
      <header className="flex items-center justify-between border-b border-ink-300/30 bg-white px-6 py-4">
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-sm bg-emerald-deep font-display text-sm text-bone">
            M
          </span>
          <span className="font-display text-lg tracking-tight text-ink-900">Maiplot</span>
          <span className="ml-2 text-xs uppercase tracking-[0.18em] text-ink-300">Admin</span>
        </div>
        <SignOutButton />
      </header>

      <main className="mx-auto max-w-5xl px-6 py-16">
        <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Review</p>
        <h1 className="mt-2 font-display text-3xl text-ink-900">Listing review queue</h1>
        <p className="mt-3 max-w-prose text-sm text-ink-500">
          You&rsquo;re signed in. The review queue UI lands in the next slice — listings pending
          approval, Power-of-Attorney sellers surfaced first, with approve / reject actions.
        </p>
        <div className="mt-10 rounded-lg border border-dashed border-ink-300/50 bg-white/60 px-6 py-12 text-center text-sm text-ink-300">
          Queue coming in SCRUM-60
        </div>
      </main>
    </div>
  );
}
