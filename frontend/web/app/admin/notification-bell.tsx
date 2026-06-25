'use client';

import { useCallback, useEffect, useState } from 'react';

import type { NotificationItem, NotificationListResponse } from '@/lib/api';
import { relativeTime } from '@/lib/notifications';

/**
 * In-app notification centre (SCRUM-124). A bell in the admin nav with an
 * unread-count badge and a dropdown panel listing notifications newest-first.
 * Clicking an item marks it read (optimistic + persisted); "Mark all read"
 * clears the badge. Consumes the SCRUM-82 backend via same-origin proxies.
 */
export function NotificationBell() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch('/api/admin/notifications?limit=20', { cache: 'no-store' });
      if (!resp.ok) {
        setError('Could not load notifications.');
        return;
      }
      const data = (await resp.json()) as NotificationListResponse;
      setItems(data.items);
      setUnread(data.unread_count);
    } catch {
      setError('Could not reach the server.');
    } finally {
      setLoading(false);
    }
  }, []);

  // Populate the badge on mount.
  useEffect(() => {
    void load();
  }, [load]);

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next) void load(); // refresh on open
  }

  async function markRead(item: NotificationItem) {
    if (item.is_read) return;
    // Optimistic: flip the row + drop the badge, roll back on failure.
    setItems((prev) => prev.map((n) => (n.id === item.id ? { ...n, is_read: true } : n)));
    setUnread((u) => Math.max(0, u - 1));
    try {
      const resp = await fetch(`/api/admin/notifications/${item.id}/read`, { method: 'PATCH' });
      if (!resp.ok) void load();
    } catch {
      void load();
    }
  }

  async function markAll() {
    if (unread === 0) return;
    setItems((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnread(0);
    try {
      const resp = await fetch('/api/admin/notifications/read-all', { method: 'PATCH' });
      if (!resp.ok) void load();
    } catch {
      void load();
    }
  }

  const badge = unread > 9 ? '9+' : String(unread);

  return (
    <div className="relative">
      <button
        onClick={toggle}
        aria-label={`Notifications${unread > 0 ? ` (${unread} unread)` : ''}`}
        aria-expanded={open}
        className="relative flex h-9 w-9 items-center justify-center rounded-md text-ink-500 transition hover:bg-ink-900/5 hover:text-ink-900"
      >
        <BellIcon />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex min-w-[1.1rem] items-center justify-center rounded-full bg-red-600 px-1 text-[0.65rem] font-semibold leading-none text-white">
            {badge}
          </span>
        )}
      </button>

      {open && (
        <>
          {/* Click-away backdrop. */}
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} aria-hidden />
          <div className="absolute right-0 z-20 mt-2 w-80 overflow-hidden rounded-xl border border-ink-300/30 bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-ink-300/20 px-4 py-3">
              <h2 className="font-display text-sm text-ink-900">Notifications</h2>
              {unread > 0 && (
                <button
                  onClick={markAll}
                  className="text-xs font-medium text-emerald-deep transition hover:text-emerald-accent"
                >
                  Mark all read
                </button>
              )}
            </div>

            <div className="max-h-96 overflow-y-auto">
              {loading && items.length === 0 ? (
                <p className="px-4 py-8 text-center text-sm text-ink-300">Loading…</p>
              ) : error ? (
                <p className="px-4 py-8 text-center text-sm text-red-600">{error}</p>
              ) : items.length === 0 ? (
                <p className="px-4 py-10 text-center text-sm text-ink-300">You&apos;re all caught up.</p>
              ) : (
                <ul>
                  {items.map((item) => (
                    <li key={item.id}>
                      <button
                        onClick={() => markRead(item)}
                        className={`flex w-full gap-2.5 border-b border-ink-300/15 px-4 py-3 text-left transition last:border-0 hover:bg-bone ${
                          item.is_read ? '' : 'bg-emerald-deep/[0.03]'
                        }`}
                      >
                        <span
                          className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                            item.is_read ? 'bg-transparent' : 'bg-emerald-deep'
                          }`}
                          aria-hidden
                        />
                        <span className="min-w-0 flex-1">
                          {item.title && (
                            <span className="block truncate text-sm font-medium text-ink-900">
                              {item.title}
                            </span>
                          )}
                          <span className="block text-sm text-ink-500">{item.body}</span>
                          <span className="mt-0.5 block text-xs text-ink-300">
                            {relativeTime(item.created_at)}
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function BellIcon() {
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
      <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
      <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
    </svg>
  );
}
