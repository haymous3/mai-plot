'use client';

import Link from 'next/link';
import { useState } from 'react';

import { FinancialTab, NotificationsTab, ProfileTab, SecurityTab } from './tabs';
import type { SettingsTab } from './settings-ui';
import type { Account, NotificationPrefs, PayoutAccount } from '@/lib/settings';

/**
 * Settings shell — SCRUM-188.
 *
 * Measured on `design/buyer-profile-page/` (1577 artboard, 1:1): a 1216px
 * container of a 278px sidebar card and a 904px content card at a 32px gutter,
 * on a #fbfbfb page. Nav items are 246×48 with the active one filled
 * `emerald-deep`.
 *
 * Lives OUTSIDE the (buyer) route group deliberately. The design replaces the
 * app header with its own back-arrow bar, and Settings is not buyer-specific —
 * the same page serves sellers and realtors, which the shared session cookie
 * already makes possible.
 */

const NAV: {
  id: SettingsTab;
  label: string;
  icon: () => React.ReactElement;
}[] = [
  {
    id: 'profile',
    label: 'Profile',
    icon: () => (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="h-[18px] w-[18px]"
      >
        <circle cx="12" cy="8" r="3.5" />
        <path d="M5 20a7 7 0 0 1 14 0" />
      </svg>
    ),
  },
  {
    id: 'financial',
    label: 'Financial',
    icon: () => (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="h-[18px] w-[18px]"
      >
        <rect x="3" y="6" width="18" height="13" rx="2" />
        <path d="M3 10h18M7 15h3" />
      </svg>
    ),
  },
  {
    id: 'notifications',
    label: 'Notifications',
    icon: () => (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="h-[18px] w-[18px]"
      >
        <path d="M18 9a6 6 0 1 0-12 0c0 5-2 6-2 6h16s-2-1-2-6" />
        <path d="M10.5 20a2 2 0 0 0 3 0" />
      </svg>
    ),
  },
  {
    id: 'security',
    label: 'Security',
    icon: () => (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="h-[18px] w-[18px]"
      >
        <rect x="4.5" y="10.5" width="15" height="10" rx="2" />
        <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
      </svg>
    ),
  },
];

export function SettingsClient({
  account,
  payout,
  prefs,
  home,
}: {
  account: Account;
  payout: PayoutAccount | null;
  prefs: NotificationPrefs;
  home: string;
}) {
  const [tab, setTab] = useState<SettingsTab>('profile');

  return (
    <main className="min-h-screen bg-[#fbfbfb]">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex h-[102px] w-full max-w-[1280px] items-center gap-5 px-8">
          <Link
            href={home}
            aria-label="Back"
            className="rounded-lg p-1 text-ink-buyer transition hover:bg-surface-page focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-deep"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-5 w-5"
              aria-hidden
            >
              <path d="M19 12H5" />
              <path d="m11 6-6 6 6 6" />
            </svg>
          </Link>
          {/*
            The design draws a bespoke leaf mark here. No such asset exists in
            the repo — there is no logo SVG or image anywhere, and SCRUM-169
            established that vector shapes must not be traced off a raster. The
            rest of the app (buyer/seller/realtor navs) uses this "M" tile, so
            Settings matches the shipped brand lockup rather than an invented
            one. Swap both together if the mark is ever exported.
          */}
          <span
            aria-hidden
            className="flex h-9 w-9 flex-none items-center justify-center rounded-lg bg-emerald-deep font-display text-base text-bone"
          >
            M
          </span>
          <div>
            <h1 className="text-2xl font-bold leading-8 text-ink-buyer">Settings</h1>
            <p className="text-sm leading-5 text-ink-500">Manage your account preferences</p>
          </div>
        </div>
      </header>

      <div className="mx-auto w-full max-w-[1280px] px-8 py-9">
        <div className="grid gap-8 lg:grid-cols-[278px_minmax(0,1fr)]">
          <nav
            aria-label="Settings sections"
            className="h-fit rounded-2xl border border-line bg-white p-4"
          >
            <ul className="flex flex-col gap-1.5">
              {NAV.map((item) => {
                const active = item.id === tab;
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => setTab(item.id)}
                      aria-current={active ? 'page' : undefined}
                      className={`flex h-12 w-full items-center gap-3 rounded-xl px-4 text-left text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-deep ${
                        active
                          ? 'bg-emerald-deep text-white'
                          : 'text-ink-500 hover:bg-surface-page hover:text-ink-buyer'
                      }`}
                    >
                      <item.icon />
                      {item.label}
                    </button>
                  </li>
                );
              })}
            </ul>
          </nav>

          <div>
            {tab === 'profile' && <ProfileTab account={account} />}
            {tab === 'financial' && <FinancialTab account={account} payout={payout} />}
            {tab === 'notifications' && <NotificationsTab initial={prefs} />}
            {tab === 'security' && <SecurityTab />}
          </div>
        </div>
      </div>
    </main>
  );
}
