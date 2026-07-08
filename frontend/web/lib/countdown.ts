/** Distress-listing expiry helpers (SCRUM-138). */

export interface Countdown {
  expired: boolean;
  days: number;
  hours: number;
  minutes: number;
  /** Short remaining-time label, e.g. "6d 4h left" or "Expired". */
  label: string;
}

/** Time remaining until an ISO timestamp, relative to `now` (ms since epoch). */
export function countdownTo(expiresAtIso: string, now: number = Date.now()): Countdown {
  const remaining = Date.parse(expiresAtIso) - now;
  if (!Number.isFinite(remaining) || remaining <= 0) {
    return { expired: true, days: 0, hours: 0, minutes: 0, label: 'Expired' };
  }
  const minutesTotal = Math.floor(remaining / 60000);
  const days = Math.floor(minutesTotal / (60 * 24));
  const hours = Math.floor((minutesTotal % (60 * 24)) / 60);
  const minutes = minutesTotal % 60;
  const label =
    days > 0 ? `${days}d ${hours}h left` : hours > 0 ? `${hours}h ${minutes}m left` : `${minutes}m left`;
  return { expired: false, days, hours, minutes, label };
}

const URGENCY_DAYS: Record<string, number> = { '7_days': 7, '14_days': 14, '30_days': 30 };

/** For the Create wizard: the projected expiry date + a friendly "in N days"
 * from an urgency tag, before the listing exists. */
export function projectedExpiry(
  urgencyTag: string,
  now: number = Date.now(),
): { date: Date; days: number } | null {
  const days = URGENCY_DAYS[urgencyTag];
  if (!days) return null;
  return { date: new Date(now + days * 24 * 60 * 60 * 1000), days };
}
