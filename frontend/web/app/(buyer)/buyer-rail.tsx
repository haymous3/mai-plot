'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { BuyerSignOut } from './buyer-sign-out';
import { AccountSwitch } from '@/app/_components/account-switch';
import { BrandLogo } from '@/app/_components/brand-logo';
import { RailShell } from '@/app/_components/rail-shell';

const NAV = [
  // SCRUM-238 sends the logo to the landing page, so the rail is the way home.
  { href: '/dashboard', label: 'Dashboard', icon: '🏠' },
  { href: '/offers', label: 'My Offers', icon: '🤝' },
  { href: '/wallet', label: 'My Wallet', icon: '👛' },
  // SCRUM-232 hid "My Documents" for every role; /documents still exists, so
  // restoring it is adding `{ href: '/documents', label: 'My Documents', icon: '📄' }`.
];

/**
 * Buyer sidebar (SCRUM-248) — the links that lived in the header's Account
 * dropdown, moved into a rail on every buyer page.
 *
 * The seller rail's measured vocabulary (256px, 44px items at a 48px pitch,
 * 12px radius, emerald-deep active), so buyer and seller read as one product.
 * Unlike seller, the buyer keeps its green 72px top bar (greeting, bell,
 * account photo): the rail sits UNDER it on desktop, and below `lg` it is the
 * shared RailShell drawer opened from the ☰ in that bar (RailDrawerProvider in
 * the layout), so there is no second top bar.
 *
 * The brand block only appears in the drawer — on desktop the logo is already
 * in the green bar directly above.
 */
export function BuyerRail() {
  const pathname = usePathname();

  const itemClass = (active: boolean) =>
    `flex h-11 items-center gap-3 rounded-xl px-4 text-sm font-semibold transition ${
      active ? 'bg-emerald-deep text-white' : 'text-ink-700 hover:bg-surface-muted'
    }`;

  return (
    <RailShell subtitle="Buyer">
      <div className="flex h-[101px] flex-none flex-col gap-1 border-b border-line px-6 pt-6 lg:hidden">
        <div className="flex h-8 items-center gap-2">
          <BrandLogo height={28} />
        </div>
        <span className="text-xs leading-4 text-ink-500">Buyer Account</span>
      </div>

      <nav className="flex flex-1 flex-col gap-1 px-4 pt-4">
        {/* Reserved row: the switch renders nothing until /auth/me answers,
            and without it every item would jump 44px after load (SCRUM-242). */}
        <div className="mb-3 min-h-11">
          <AccountSwitch current="buyer" variant="rail" />
        </div>
        {NAV.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link key={item.href} href={item.href} className={itemClass(active)} aria-current={active ? 'page' : undefined}>
              <span aria-hidden className="flex h-5 w-5 flex-none items-center justify-center">
                {item.icon}
              </span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="flex flex-none flex-col gap-2 border-t border-line px-4 py-4">
        {/* `/settings` is one page for every role and draws its own bar, so it
            renders without this rail; its back arrow returns to /dashboard. */}
        <Link href="/settings" className={itemClass(false)}>
          <span aria-hidden className="flex h-5 w-5 flex-none items-center justify-center">
            ⚙
          </span>
          Settings
        </Link>
        <BuyerSignOut />
      </div>
    </RailShell>
  );
}
