import Link from 'next/link';

import { NotificationBell } from './notification-bell';
import { PushToggle } from './push-toggle';
import { SignOutButton } from './sign-out-button';

const TABS = [
  { key: 'listings', label: 'Listings', href: '/admin/listings/queue' },
  { key: 'poa', label: 'Power of Attorney', href: '/admin/poa/queue' },
  { key: 'realtors', label: 'Realtors', href: '/admin/realtors/queue' },
  { key: 'loans', label: 'Loans', href: '/admin/loans' },
  { key: 'audit', label: 'Audit log', href: '/admin/audit' },
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
  active: 'listings' | 'poa' | 'realtors' | 'loans' | 'audit' | 'settings';
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
        <Link
          href="/admin/settings/notifications"
          aria-label="Notification settings"
          aria-current={active === 'settings' ? 'page' : undefined}
          className={`flex h-9 w-9 items-center justify-center rounded-md transition hover:bg-ink-900/5 ${
            active === 'settings' ? 'bg-ink-900/5 text-ink-900' : 'text-ink-500 hover:text-ink-900'
          }`}
        >
          <SettingsIcon />
        </Link>
        <SignOutButton />
      </div>
    </header>
  );
}

function SettingsIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}
