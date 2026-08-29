'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { SellerSignOut } from './seller-sign-out';

const NAV = [
  { href: '/seller', label: 'Dashboard Overview', icon: '🏠', exact: true },
  { href: '/seller/listings', label: 'My Listings', icon: '📦' },
  { href: '/seller/offers', label: 'Offers', icon: '🤝' },
  { href: '/seller/transactions', label: 'Transactions', icon: '📈' },
  { href: '/seller/documents', label: 'Documents', icon: '📄' },
  { href: '/seller/notifications', label: 'Notifications', icon: '🔔' },
  // `/settings`, not `/seller/profile` — that route never existed either, so
  // this was the SECOND dead link in this nav (SCRUM-193 fixed the Settings
  // one below). The seller's Profile IS the Settings Profile tab, which is
  // what /settings opens on.
  { href: '/settings', label: 'Profile', icon: '👤' },
];

/**
 * Seller dashboard sidebar (SCRUM-98), brought to spec in SCRUM-170.
 *
 * Values from Figma node 276:364. Unlike the buyer dashboard — whose 1562px
 * artboard is scaled 1.0597 — this artboard is 1:1, so the numbers below are
 * literal: 256px rail (255 + 1px rule), 101px brand block, 44px nav items at a
 * 48px pitch, 12px radius, 16px inset.
 *
 * Buyer has a 72px top bar; seller and realtor have this rail. There is no
 * shared shell, so the two are deliberately separate components.
 *
 * Typeface: the design specifies Inter throughout. Per product decision the app
 * keeps Archivo + Fraunces, so `font-display` is retained on the wordmark and
 * only sizes, weights and colours are matched.
 */
export function SellerNav() {
  const pathname = usePathname();

  const itemClass = (active: boolean) =>
    `flex h-11 items-center gap-3 rounded-xl px-4 text-sm font-semibold transition ${
      active ? 'bg-emerald-deep text-white' : 'text-ink-700 hover:bg-surface-muted'
    }`;

  return (
    <aside className="flex w-64 flex-none flex-col border-r border-line bg-surface-card">
      {/* 101px brand block with its own bottom rule — node 276:365. */}
      <div className="flex h-[101px] flex-none flex-col gap-1 border-b border-line px-6 pt-6">
        <div className="flex h-8 items-center gap-2">
          <span className="flex h-8 w-8 flex-none items-center justify-center rounded-xl bg-emerald-deep text-sm font-bold text-white">
            M
          </span>
          <span className="font-display text-lg font-bold leading-7 text-emerald-deep">Maihomme</span>
        </div>
        <span className="text-xs leading-4 text-ink-500">Seller Dashboard</span>
      </div>

      <nav className="flex flex-1 flex-col gap-1 px-4 pt-4">
        {NAV.map((item) => {
          const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
          return (
            <Link key={item.href} href={item.href} className={itemClass(active)}>
              <span aria-hidden className="flex h-5 w-5 flex-none items-center justify-center">
                {item.icon}
              </span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Settings + Logout pinned to the bottom behind a top rule — node 276:421. */}
      <div className="flex flex-none flex-col gap-2 border-t border-line px-4 py-4">
        {/*
          `/settings`, not `/seller/settings` — the latter never existed and
          this link 404'd from SCRUM-98 until SCRUM-193. Settings is one screen
          for every role: it replaces the app chrome with its own bar (which is
          what the seller export draws, sidebar absent) and its back arrow
          returns to roleHome(), so a seller lands back on /seller.
        */}
        <Link href="/settings" className={itemClass(false)}>
          <span aria-hidden className="flex h-5 w-5 flex-none items-center justify-center">
            ⚙
          </span>
          Settings
        </Link>
        <SellerSignOut />
      </div>
    </aside>
  );
}
