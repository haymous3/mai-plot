import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import type { NotificationListResponse } from '@/lib/api';
import { notificationServiceUrl } from '@/lib/api';
import {
  ACCENT_TILE,
  INBOX_TABS,
  TAB_LABELS,
  accentFor,
  headingFor,
  parseTab,
} from '@/lib/notification-inbox';
import { relativeTime } from '@/lib/notifications';
import { SESSION_LOGIN } from '@/lib/session';
import { sessionAccessToken } from '@/lib/session-server';

export const metadata: Metadata = { title: 'Notifications · Maihomme' };

const PAGE_SIZE = 30;

export default async function SellerNotificationsPage({
  searchParams,
}: {
  searchParams: { category?: string; q?: string };
}) {
  const token = sessionAccessToken();
  if (!token) redirect(`${SESSION_LOGIN}?role=seller`);

  const tab = parseTab(searchParams.category);
  const q = searchParams.q?.trim() ?? '';

  const url = new URL(`${notificationServiceUrl()}/notifications`);
  url.searchParams.set('limit', String(PAGE_SIZE));
  // "All" is the absence of a category; sending it would 422 against the
  // backend Literal.
  if (tab !== 'all') url.searchParams.set('category', tab);
  if (q) url.searchParams.set('q', q);

  let page: NotificationListResponse | null = null;
  try {
    const resp = await fetch(url.toString(), {
      headers: { authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
    if (resp.ok) page = (await resp.json()) as NotificationListResponse;
  } catch {
    page = null;
  }

  const href = (nextTab: string, nextQ: string = q) => {
    const params = new URLSearchParams();
    if (nextTab !== 'all') params.set('category', nextTab);
    if (nextQ) params.set('q', nextQ);
    const qs = params.toString();
    return `/seller/notifications${qs ? `?${qs}` : ''}`;
  };

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <BellIcon />
          <div>
            <h1 className="font-display text-3xl text-emerald-deep">Notifications</h1>
            <p className="mt-1 text-sm text-ink-500">
              Stay updated with your listing activities
            </p>
          </div>
        </div>

        {/*
          Search is a plain GET form, not client state: the feed is a Server
          Component read, so searching is a navigation. That also makes a
          search result a shareable, reloadable URL.

          The design also draws a "Filter" button beside this. It is omitted —
          nothing in the export says what it filters beyond these tabs, and a
          control that does nothing is worse than one that is absent.
        */}
        <form method="GET" action="/seller/notifications" className="flex items-center gap-2">
          {tab !== 'all' && <input type="hidden" name="category" value={tab} />}
          <input
            type="search"
            name="q"
            defaultValue={q}
            placeholder="Search notifications"
            aria-label="Search notifications"
            className="h-10 w-56 rounded-lg border border-ink-300/60 bg-white px-3.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-deep focus:ring-2 focus:ring-emerald-deep/20"
          />
          <button
            type="submit"
            className="h-10 rounded-lg border border-ink-300/60 bg-white px-4 text-sm font-medium text-ink-700 transition hover:border-ink-500"
          >
            Search
          </button>
        </form>
      </header>

      <nav
        aria-label="Notification categories"
        className="mt-8 flex flex-wrap gap-1 rounded-xl border border-ink-300/30 bg-white p-1.5"
      >
        {INBOX_TABS.map((t) => (
          <Link
            key={t}
            href={href(t)}
            aria-current={t === tab ? 'page' : undefined}
            className={`rounded-lg px-4 py-2 text-sm transition ${
              t === tab
                ? 'bg-emerald-deep font-semibold text-bone'
                : 'text-ink-700 hover:bg-ink-900/5'
            }`}
          >
            {TAB_LABELS[t]}
          </Link>
        ))}
      </nav>

      <div className="mt-6 space-y-3">
        {page === null ? (
          <Panel tone="error">Could not load your notifications. Please retry.</Panel>
        ) : page.items.length === 0 ? (
          <Panel tone="empty">
            {q
              ? `No notifications match “${q}”.`
              : tab === 'deposits'
                ? // Truthful about the state of the world: the deposit flow
                  // exists but raises no notification yet, so this tab cannot
                  // fill until a producer is added. See the SCRUM-194 notes.
                  'No deposit updates yet.'
                : 'Nothing here yet.'}
          </Panel>
        ) : (
          page.items.map((item) => {
            const accent = accentFor(item.type);
            return (
              <article
                key={item.id}
                className={`flex gap-4 rounded-xl border bg-white px-5 py-4 ${
                  item.is_read
                    ? 'border-ink-300/30'
                    : 'border-ink-300/30 border-l-4 border-l-emerald-deep'
                }`}
              >
                <span
                  aria-hidden
                  className={`flex h-10 w-10 flex-none items-center justify-center rounded-lg ${ACCENT_TILE[accent]}`}
                >
                  <DotIcon />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                    <h2 className="font-semibold text-emerald-deep">{headingFor(item)}</h2>
                    <time
                      dateTime={item.created_at}
                      className="flex-none text-xs text-ink-300"
                    >
                      {relativeTime(item.created_at)}
                    </time>
                  </div>
                  <p className="mt-1 text-sm leading-6 text-ink-500">{item.body}</p>
                </div>
              </article>
            );
          })
        )}
      </div>

      {page?.next_cursor && (
        <p className="mt-6 text-center text-sm text-ink-300">
          Showing your {PAGE_SIZE} most recent notifications.
        </p>
      )}
    </main>
  );
}

function Panel({ tone, children }: { tone: 'error' | 'empty'; children: React.ReactNode }) {
  const cls =
    tone === 'error'
      ? 'border-red-200 bg-red-50 text-red-700'
      : 'border-dashed border-ink-300/50 bg-white/60 text-ink-300';
  return (
    <div className={`rounded-xl border px-6 py-16 text-center text-sm ${cls}`}>{children}</div>
  );
}

function BellIcon() {
  return (
    <svg
      width="26"
      height="26"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="mt-1 flex-none text-emerald-deep"
      aria-hidden
    >
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

function DotIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <circle cx="12" cy="12" r="5" />
    </svg>
  );
}
