'use client';

import { useEffect, useState } from 'react';

/** Graceful offline notice for buyer pages (SCRUM-136). Watches the browser's
 * online/offline events and shows a sticky banner while disconnected, so a
 * failed fetch reads as "you're offline" rather than a hard error. */
export function OfflineBanner() {
  // Assume online for the first paint (SSR has no navigator); reconcile on mount.
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    const sync = () => setOffline(!navigator.onLine);
    sync();
    window.addEventListener('online', sync);
    window.addEventListener('offline', sync);
    return () => {
      window.removeEventListener('online', sync);
      window.removeEventListener('offline', sync);
    };
  }, []);

  if (!offline) return null;

  return (
    <div
      role="status"
      className="sticky top-0 z-50 flex items-center justify-center gap-2 bg-amber-500 px-4 py-2 text-center text-sm font-medium text-white"
    >
      <span aria-hidden>⚠</span>
      You&rsquo;re offline — showing your recently viewed properties. Some data may be out of date.
    </div>
  );
}
