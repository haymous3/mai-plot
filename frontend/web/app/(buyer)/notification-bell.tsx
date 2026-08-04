'use client';

import { useEffect, useRef, useState } from 'react';

interface NotificationItem {
  id: string;
  title: string | null;
  body: string;
  is_read: boolean;
  created_at: string;
}

interface NotificationList {
  items: NotificationItem[];
  unread_count: number;
}

function timeAgo(iso: string): string {
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return 'just now';
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

/** Header notification bell (SCRUM-95). Polls the in-app centre on open, shows
 * an unread badge, and marks all read. Read-only otherwise. */
export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<NotificationList | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  async function load() {
    try {
      const resp = await fetch('/api/buyer/notifications', { cache: 'no-store' });
      if (resp.ok) setData((await resp.json()) as NotificationList);
    } catch {
      /* header bell is best-effort; ignore transient errors */
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  async function markAllRead() {
    setData((d) => (d ? { ...d, unread_count: 0, items: d.items.map((i) => ({ ...i, is_read: true })) } : d));
    try {
      await fetch('/api/buyer/notifications/read-all', { method: 'PATCH' });
    } catch {
      /* optimistic; a reload will reconcile */
    }
  }

  const unread = data?.unread_count ?? 0;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`}
        className="relative flex h-9 w-9 items-center justify-center rounded-full text-bone/90 transition hover:bg-white/10"
      >
        <span aria-hidden className="text-lg">
          🔔
        </span>
        {unread > 0 && (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-status-urgent px-1 text-[10px] font-semibold text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-20 mt-2 w-80 overflow-hidden rounded-xl border border-ink-300/30 bg-white shadow-lg">
          <div className="flex items-center justify-between border-b border-ink-300/20 px-4 py-3">
            <span className="text-sm font-semibold text-ink-900">Notifications</span>
            {unread > 0 && (
              <button
                type="button"
                onClick={markAllRead}
                className="text-xs font-medium text-emerald-deep hover:underline"
              >
                Mark all read
              </button>
            )}
          </div>
          <ul className="max-h-80 divide-y divide-ink-300/15 overflow-y-auto">
            {!data || data.items.length === 0 ? (
              <li className="px-4 py-8 text-center text-sm text-ink-400">You&rsquo;re all caught up.</li>
            ) : (
              data.items.slice(0, 8).map((n) => (
                <li key={n.id} className={`px-4 py-3 ${n.is_read ? '' : 'bg-emerald-deep/5'}`}>
                  <p className="text-sm font-medium text-ink-900">{n.title ?? 'Notification'}</p>
                  <p className="mt-0.5 line-clamp-2 text-xs text-ink-500">{n.body}</p>
                  <p className="mt-1 text-[11px] text-ink-400">{timeAgo(n.created_at)}</p>
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
