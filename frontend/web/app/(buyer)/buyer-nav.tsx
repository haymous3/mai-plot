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

/** Shared buyer header (SCRUM-95): brand · greeting · notification bell ·
 * account menu. Rendered on every buyer page via the (buyer) layout. */
export function BuyerNav() {
  return (
    <header className="flex items-center justify-between bg-emerald-deep px-6 py-3">
      <Link href={BUYER_HOME} className="flex items-center gap-2.5">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-white/10 font-display text-sm text-bone">
          M
        </span>
        <span className="font-display text-lg tracking-tight text-bone">Maiplot</span>
      </Link>
      <p className="hidden text-sm text-bone/80 sm:block">{greeting()}</p>
      <div className="flex items-center gap-1.5">
        <NotificationBell />
        <AvatarMenu />
      </div>
    </header>
  );
}
