'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { RealtorSignOut } from './realtor-sign-out';

const NAV = [
  { href: '/realtor', label: 'Dashboard Overview', icon: '🏠', exact: true },
  { href: '/realtor/inspections', label: 'Assigned Inspections', icon: '📋' },
  { href: '/realtor/reports', label: 'Reports Submitted', icon: '📝' },
  { href: '/realtor/earnings', label: 'Earnings', icon: '💰' },
  { href: '/realtor/profile', label: 'Profile', icon: '👤' },
];

/** Realtor portal sidebar (SCRUM-140). Fixed left rail with the section nav +
 * logout, highlighting the active route. Mirrors the seller nav. */
export function RealtorNav() {
  const pathname = usePathname();

  return (
    <aside className="flex w-60 flex-none flex-col border-r border-ink-300/25 bg-white">
      <div className="flex items-center gap-2.5 px-5 py-4">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-deep font-display text-lg text-bone">
          M
        </span>
        <span>
          <span className="block font-display text-lg leading-tight text-ink-900">Maiplot</span>
          <span className="block text-xs text-ink-500">Realtor Portal</span>
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
                active ? 'bg-emerald-deep font-medium text-bone' : 'text-ink-600 hover:bg-bone'
              }`}
            >
              <span aria-hidden>{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="space-y-1 border-t border-ink-300/20 px-3 py-3">
        <RealtorSignOut />
      </div>
    </aside>
  );
}
