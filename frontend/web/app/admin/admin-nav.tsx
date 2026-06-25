import Link from 'next/link';

import { NotificationBell } from './notification-bell';
import { PushToggle } from './push-toggle';
import { SignOutButton } from './sign-out-button';

const TABS = [
  { key: 'listings', label: 'Listings', href: '/admin/listings/queue' },
  { key: 'poa', label: 'Power of Attorney', href: '/admin/poa/queue' },
  { key: 'realtors', label: 'Realtors', href: '/admin/realtors/queue' },
] as const;

/**
 * Shared admin header: brand, queue navigation, and the count of the active
 * queue (SCRUM-60/61/62). The count sits next to the active tab so it's always
 * visible in the navigation.
 */
export function AdminNav({
  active,
  count,
}: {
  active: 'listings' | 'poa' | 'realtors';
  count: number | null;
}) {
  return (
    <header className="flex items-center justify-between border-b border-ink-300/30 bg-white px-6 py-3.5">
      <div className="flex items-center gap-7">
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-sm bg-emerald-deep font-display text-sm text-bone">
            M
          </span>
          <span className="font-display text-lg tracking-tight text-ink-900">Maiplot</span>
        </div>
        <nav className="flex items-center gap-1" aria-label="Admin queues">
          {TABS.map((t) => {
            const isActive = t.key === active;
            return (
              <Link
                key={t.key}
                href={t.href}
                aria-current={isActive ? 'page' : undefined}
                className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition ${
                  isActive ? 'bg-ink-900/5 font-medium text-ink-900' : 'text-ink-500 hover:text-ink-900'
                }`}
              >
                {t.label}
                {isActive && count !== null && (
                  <span className="rounded-full bg-emerald-deep/10 px-2 py-0.5 text-xs font-semibold text-emerald-deep">
                    {count}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
      </div>
      <div className="flex items-center gap-3">
        <PushToggle />
        <NotificationBell />
        <SignOutButton />
      </div>
    </header>
  );
}
