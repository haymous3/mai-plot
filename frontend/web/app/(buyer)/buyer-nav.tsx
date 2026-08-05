import Link from 'next/link';

import { AvatarMenu } from './avatar-menu';
import { NotificationBell } from './notification-bell';
import { BUYER_HOME } from '@/lib/buyer-auth';

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

/**
 * Shared buyer header (SCRUM-95): brand · greeting · notification bell ·
 * account menu. Rendered on every buyer page via the (buyer) layout.
 *
 * Measured against the design (SCRUM-166): 72px tall, 44px inline padding,
 * `#144735` fill and a 1px `#e5e7eb` bottom rule. The fill is `brand-header`,
 * not `emerald-deep` — the buyer top bar is the one place the design uses a
 * lighter green than the `#0f3d2e` primary. Seller and realtor have a sidebar
 * instead, so this token is used nowhere else.
 *
 * The greeting is centred absolutely rather than by `justify-between`, which
 * only centres it when both flanking groups happen to be the same width.
 */
export function BuyerNav() {
  return (
    <header className="relative flex h-18 items-center justify-between border-b border-line bg-brand-header px-11">
      <Link href={BUYER_HOME} className="flex items-center gap-2.5">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-white/10 font-display text-sm text-bone">
          M
        </span>
        {/* The design was inconsistent here — "MaiHome" in 5 buyer export
            frames, "Maiplot" in 2. Product owner chose "Maihomme" (SCRUM-173),
            confirmed verbatim.

            BUYER ONLY. Seller, realtor and admin sidebars and every page title
            still read "Maiplot", as do CLAUDE.md, the repo and the maiplot.ng
            domain. That inconsistency is deliberate and accepted; a full
            rebrand would be its own ticket outside this epic. */}
        <span className="font-display text-lg tracking-tight text-bone">Maihomme</span>
      </Link>
      <p className="pointer-events-none absolute left-1/2 hidden -translate-x-1/2 text-sm text-bone/80 sm:block">
        {greeting()}
      </p>
      <div className="flex items-center gap-1.5">
        <NotificationBell />
        <AvatarMenu />
      </div>
    </header>
  );
}
