import Link from 'next/link';
import { BrandLogo } from '@/app/_components/brand-logo';

import {
  BanknoteIcon,
  CalendarIcon,
  ClipboardCheckIcon,
  ClipboardIcon,
  FileCheckIcon,
  FileSignatureIcon,
  FileTextIcon,
  HistoryIcon,
  HouseIcon,
  SettingsIcon,
  UserCheckIcon,
  UsersIcon,
} from './_icons';
import { NotificationBell } from './notification-bell';
import { PushToggle } from './push-toggle';
import { SignOutButton } from './sign-out-button';

/** Every destination the admin rail can mark active. */
export type AdminNavKey =
  | 'users'
  | 'listings'
  | 'listing-review'
  | 'poa'
  | 'documents'
  | 'realtors'
  | 'requests'
  | 'schedule'
  | 'reports'
  | 'loans'
  | 'audit'
  | 'settings';

type NavItem = {
  key: AdminNavKey;
  label: string;
  href: string;
  Icon: (props: { className?: string }) => React.JSX.Element;
};

/**
 * The rail is grouped rather than flat: eleven destinations in one undivided
 * column is a wall of equal-weight links. The groups are the admin's own mental
 * model — who is on the platform, what is waiting on a decision, what is
 * happening on the ground, and the money and paper trail.
 *
 * Ordering within a group is unchanged from the horizontal bar it replaces.
 */
const SECTIONS: { label: string | null; items: NavItem[] }[] = [
  {
    // Users first: it is the only destination that is a lookup rather than a
    // queue, and it is where an admin starts when somebody contacts support
    // (SCRUM-209). Browse-listings sits beside it for the same reason — "find
    // me this property" is a question the review queue could never answer
    // (SCRUM-215).
    label: null,
    items: [
      { key: 'users', label: 'Users', href: '/admin/users', Icon: UsersIcon },
      { key: 'listings', label: 'Listings', href: '/admin/listings', Icon: HouseIcon },
    ],
  },
  {
    label: 'Review queues',
    items: [
      {
        key: 'listing-review',
        label: 'Listing review',
        href: '/admin/listings/queue',
        Icon: ClipboardCheckIcon,
      },
      {
        key: 'poa',
        label: 'Power of Attorney',
        href: '/admin/poa/queue',
        Icon: FileSignatureIcon,
      },
      {
        key: 'documents',
        label: 'Documents',
        href: '/admin/documents/queue',
        Icon: FileTextIcon,
      },
      { key: 'realtors', label: 'Realtors', href: '/admin/realtors/queue', Icon: UserCheckIcon },
    ],
  },
  {
    label: 'Inspections',
    items: [
      // Requests sits BEFORE reports: a request waiting for a realtor is work
      // the platform owes someone, where a report is work already done
      // (SCRUM-208). Scheduling is an admin-initiated action rather than a
      // queue, so it follows the queue it complements (SCRUM-213).
      {
        key: 'requests',
        label: 'Requests',
        href: '/admin/inspections/requests',
        Icon: ClipboardIcon,
      },
      {
        key: 'schedule',
        label: 'Schedule',
        href: '/admin/inspections/schedule',
        Icon: CalendarIcon,
      },
      {
        key: 'reports',
        label: 'Reports',
        href: '/admin/inspections/reports',
        Icon: FileCheckIcon,
      },
    ],
  },
  {
    label: 'Finance & records',
    items: [
      { key: 'loans', label: 'Loans', href: '/admin/loans', Icon: BanknoteIcon },
      { key: 'audit', label: 'Audit log', href: '/admin/audit', Icon: HistoryIcon },
    ],
  },
];

/**
 * Shared row treatment for nav links — same 44px pitch and 12px radius as the
 * seller (SCRUM-170) and realtor (SCRUM-204) rails.
 */
function rowClass(active: boolean): string {
  return `flex min-h-11 items-center gap-3 rounded-xl px-4 py-2 text-sm font-semibold transition ${
    active ? 'bg-emerald-deep text-white' : 'text-ink-700 hover:bg-surface-muted'
  }`;
}

/**
 * Admin console sidebar: brand, grouped navigation, and the count of the active
 * queue (SCRUM-60/61/62).
 *
 * This was a horizontal header until SCRUM-217. Eleven tabs on one row read as
 * a crowded strip of small text and left no room to group or label them; the
 * 256px rail is the same one the seller and realtor portals use, so the admin
 * console now matches the rest of the app.
 *
 * `active` is still passed by each page rather than derived from `usePathname`,
 * which keeps this a server component — the pages already know which queue they
 * are, and they are the only place the `count` can come from.
 */
export function AdminNav({ active, count }: { active: AdminNavKey; count: number | null }) {
  return (
    // `sticky` + `self-start` + `h-screen`, unlike the seller and realtor rails:
    // the admin pages are long paginated tables, and a rail that stretched to the
    // content height would scroll off the top after the first screenful.
    <aside className="sticky top-0 flex h-screen w-64 flex-none flex-col self-start border-r border-line bg-surface-card">
      {/* 101px brand block with its own bottom rule, matching the seller and
          realtor rails. The bell lives here because the rail replaced the top
          bar it used to sit in. */}
      <div className="flex h-[101px] flex-none items-start justify-between gap-2 border-b border-line px-6 pt-6">
        <div className="flex flex-col gap-1">
          <div className="flex h-8 items-center gap-2">
            <BrandLogo height={28} priority />
          </div>
          <span className="text-xs leading-4 text-ink-500">Admin Console</span>
        </div>
        <div className="-mr-2 flex-none">
          <NotificationBell />
        </div>
      </div>

      {/* Scrolls independently: eleven rows plus the group labels overflow a
          short viewport, and the sign-out block below must stay reachable. */}
      <nav className="flex-1 overflow-y-auto px-4 py-4" aria-label="Admin sections">
        {SECTIONS.map((section, index) => (
          <div key={section.label ?? 'primary'} className={index === 0 ? '' : 'mt-5'}>
            {section.label && (
              <p className="px-4 pb-2 text-[0.6875rem] font-semibold uppercase tracking-[0.12em] text-ink-300">
                {section.label}
              </p>
            )}
            <div className="flex flex-col gap-1">
              {section.items.map(({ key, label, href, Icon }) => {
                const isActive = key === active;
                return (
                  <Link
                    key={key}
                    href={href}
                    aria-current={isActive ? 'page' : undefined}
                    className={rowClass(isActive)}
                  >
                    <Icon className="h-5 w-5 flex-none" />
                    <span className="flex-1">{label}</span>
                    {isActive && count !== null && (
                      <span className="flex h-5 min-w-5 flex-none items-center justify-center rounded-full bg-white/20 px-1.5 text-xs font-semibold text-white">
                        {count}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Settings, push opt-in and sign-out pinned to the bottom behind a top
          rule — same placement as the seller rail. */}
      <div className="flex flex-none flex-col gap-2 border-t border-line px-4 py-4">
        <Link
          href="/admin/settings/notifications"
          aria-current={active === 'settings' ? 'page' : undefined}
          className={rowClass(active === 'settings')}
        >
          <SettingsIcon className="h-5 w-5 flex-none" />
          <span className="flex-1">Settings</span>
        </Link>
        <PushToggle />
        <SignOutButton />
      </div>
    </aside>
  );
}
