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

  const itemClass = (active: boolean) =>
    `flex h-11 items-center gap-3 rounded-xl px-4 text-sm font-semibold transition ${
      active ? 'bg-emerald-deep text-white' : 'text-ink-700 hover:bg-surface-muted'
    }`;

  return (
    // Same rail as the seller sidebar (SCRUM-170, Figma 276:364): 256px,
    // 101px brand block, 44px items at a 48px pitch, 12px radius, 16px inset.
    <aside className="flex w-64 flex-none flex-col border-r border-line bg-surface-card">
      <div className="flex h-[101px] flex-none flex-col gap-1 border-b border-line px-6 pt-6">
        <div className="flex h-8 items-center gap-2">
          <span className="flex h-8 w-8 flex-none items-center justify-center rounded-xl bg-emerald-deep text-sm font-bold text-white">
            M
          </span>
          <span className="font-display text-lg font-bold leading-7 text-emerald-deep">Maiplot</span>
        </div>
        <span className="text-xs leading-4 text-ink-500">Realtor Portal</span>
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

      <div className="flex flex-none flex-col gap-2 border-t border-line px-4 py-4">
        <RealtorSignOut />
      </div>
    </aside>
  );
}
