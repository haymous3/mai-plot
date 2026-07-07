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
  { href: '/seller/profile', label: 'Profile', icon: '👤' },
];

/** Seller dashboard sidebar (SCRUM-98). Fixed left rail with the section nav +
 * settings/logout, highlighting the active route. */
export function SellerNav() {
  const pathname = usePathname();

  return (
    <aside className="flex w-60 flex-none flex-col border-r border-ink-300/25 bg-white">
      <div className="flex items-center gap-2.5 px-5 py-4">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-deep font-display text-lg text-bone">
          M
        </span>
        <span>
          <span className="block font-display text-lg leading-tight text-ink-900">Maiplot</span>
          <span className="block text-xs text-ink-400">Seller Dashboard</span>
        </span>
      </div>

      <nav className="mt-2 flex-1 space-y-1 px-3">
        {NAV.map((item) => {
          const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition ${
                active
                  ? 'bg-emerald-deep font-medium text-bone'
                  : 'text-ink-600 hover:bg-bone'
              }`}
            >
              <span aria-hidden>{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="space-y-1 border-t border-ink-300/20 px-3 py-3">
        <Link
          href="/seller/settings"
          className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-ink-600 transition hover:bg-bone"
        >
          <span aria-hidden>⚙</span> Settings
        </Link>
        <SellerSignOut />
      </div>
    </aside>
  );
}
