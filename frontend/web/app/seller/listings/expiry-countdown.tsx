'use client';

import { useEffect, useState } from 'react';

import { countdownTo } from '@/lib/countdown';

/** Live distress-expiry countdown badge (SCRUM-138). Re-computes each minute so
 * "6d 4h left" stays current without a page refresh. */
export function ExpiryCountdown({ expiresAt }: { expiresAt: string }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(t);
  }, []);

  const c = countdownTo(expiresAt, now);
  const date = new Date(expiresAt).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });

  return (
    <span
      title={`Auto-expires ${date}`}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
        c.expired
          ? 'bg-ink-300/20 text-ink-500'
          : c.days < 2
            ? 'bg-red-100 text-red-700'
            : 'bg-amber-100 text-amber-700'
      }`}
    >
      ⏳ {c.label}
    </span>
  );
}
