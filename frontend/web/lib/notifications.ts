/**
 * Notification-centre helpers (SCRUM-124).
 *
 * Pure formatting used by the bell/panel UI; unit-tested in node.
 */

import { formatDate } from './format';

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * A compact relative timestamp for a notification ("just now", "5m ago",
 * "3h ago", "2d ago"), falling back to an absolute date past a week. `now` is
 * injectable so the result is deterministic in tests. Future timestamps (clock
 * skew) read as "just now".
 */
export function relativeTime(iso: string, now: Date = new Date()): string {
  const then = new Date(iso).getTime();
  const diff = now.getTime() - then;

  if (diff < MINUTE) return 'just now';
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m ago`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h ago`;
  if (diff < 7 * DAY) return `${Math.floor(diff / DAY)}d ago`;
  return formatDate(iso);
}
