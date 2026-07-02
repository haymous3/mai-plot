import Link from 'next/link';

import { BuyerSignOut } from './buyer-sign-out';
import { BUYER_HOME } from '@/lib/buyer-auth';

/** Shared buyer header: brand + a link home + sign out. Minimal by design —
 * the full buyer navigation lands with the buyer dashboard Figma. */
export function BuyerNav() {
  return (
    <header className="flex items-center justify-between border-b border-ink-300/30 bg-white px-6 py-3.5">
      <Link href={BUYER_HOME} className="flex items-center gap-2.5">
        <span className="flex h-7 w-7 items-center justify-center rounded-sm bg-emerald-deep font-display text-sm text-bone">
          M
        </span>
        <span className="font-display text-lg tracking-tight text-ink-900">Maiplot</span>
      </Link>
      <div className="flex items-center gap-4">
        <Link href={BUYER_HOME} className="text-sm text-ink-500 transition hover:text-ink-900">
          Dashboard
        </Link>
        <BuyerSignOut />
      </div>
    </header>
  );
}
