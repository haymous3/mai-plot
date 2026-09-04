'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { RealtorSignOut } from './realtor-sign-out';
import { ClipboardIcon, FileTextIcon, HouseIcon, UserIcon, WalletIcon } from './_icons';

const NAV = [
  { href: '/realtor', label: 'Dashboard Overview', Icon: HouseIcon, exact: true },
  { href: '/realtor/inspections', label: 'Assigned Inspections', Icon: ClipboardIcon },
  { href: '/realtor/reports', label: 'Reports Submitted', Icon: FileTextIcon },
  { href: '/realtor/earnings', label: 'Earnings', Icon: WalletIcon },
  { href: '/realtor/profile', label: 'Profile', Icon: UserIcon },
];

/** Realtor portal sidebar (SCRUM-140, brought to the designed treatment in
 * SCRUM-204 from Figma 276:4). Same 256px rail as the seller sidebar
 * (SCRUM-170); the emoji glyphs are replaced by the drawn line icons, and
 * Assigned Inspections carries the pending-response count. */
export function RealtorNav({ pendingCount = 0 }: { pendingCount?: number }) {
  const pathname = usePathname();

  return (
    <aside className="flex w-64 flex-none flex-col border-r border-line bg-surface-card">
      <div className="flex h-[101px] flex-none flex-col gap-1 border-b border-line px-6 pt-6">
        <div className="flex h-8 items-center gap-2">
          <span className="flex h-8 w-8 flex-none items-center justify-center rounded-xl bg-emerald-deep text-sm font-bold text-white">
            M
          </span>
          <span className="font-display text-lg font-bold leading-7 text-emerald-deep">
            Maihomme
          </span>
        </div>
        <span className="text-xs leading-4 text-ink-500">Realtor Portal</span>
      </div>

      <nav className="flex flex-1 flex-col gap-1 px-4 pt-4">
        {NAV.map(({ href, label, Icon, exact }) => {
          const active = exact ? pathname === href : pathname.startsWith(href);
          const badge = href === '/realtor/inspections' ? pendingCount : 0;
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? 'page' : undefined}
              className={`flex min-h-11 items-center gap-3 rounded-xl px-4 py-2 text-sm font-semibold transition ${
                active ? 'bg-emerald-deep text-white' : 'text-ink-700 hover:bg-surface-muted'
              }`}
            >
              <Icon className="h-5 w-5 flex-none" />
              <span className="flex-1">{label}</span>
              {badge > 0 && (
                <span
                  className={`flex h-5 min-w-5 flex-none items-center justify-center rounded-full px-1.5 text-xs font-semibold ${
                    active ? 'bg-white/20 text-white' : 'bg-emerald-deep text-white'
                  }`}
                >
                  {badge}
                </span>
              )}
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
