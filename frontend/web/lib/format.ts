/**
 * Display formatters. Money is stored as BIGINT kobo (1 NGN = 100 kobo,
 * CLAUDE.md) — never floats — so naira formatting divides by 100 only at the
 * presentation edge. Pure + dependency-free for unit testing.
 */

/** Format kobo as Naira, e.g. 850_000_000 -> "₦8,500,000". Rounds to whole
 * naira (listings are whole-naira amounts; the fractional kobo is noise here). */
export function formatNaira(kobo: number): string {
  const naira = Math.round(kobo / 100);
  return `₦${naira.toLocaleString('en-NG')}`;
}

/** Format an ISO timestamp as a short, stable date, e.g. "15 Jun 2026". */
export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

/** Format an ISO timestamp as a precise UTC date+time, e.g.
 * "15 Jun 2026, 09:30" — used by the audit log where the exact moment matters.
 * Fixed to UTC so it's deterministic regardless of the runner's timezone. */
export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'UTC',
  });
}

/** Format an ISO timestamp as a 12-hour time of day, e.g. "10:00 AM" — the
 * inspection schedule column (SCRUM-204), where the realtor needs the arrival
 * time and not just the date. Fixed to UTC for the same determinism reason as
 * formatDateTime. */
export function formatTimeOfDay(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
    timeZone: 'UTC',
  });
}

/** Human label for a loans.status value (SCRUM-94). Unknown values are
 * title-cased as a fallback so a new backend status never renders as a raw slug. */
const LOAN_STATUS_LABELS: Record<string, string> = {
  submitted: 'Submitted',
  under_review: 'Under review',
  info_required: 'Info required',
  approved: 'Approved',
  rejected: 'Rejected',
  disbursed: 'Disbursed',
  repaying: 'Repaying',
  fully_repaid: 'Fully repaid',
  defaulted: 'Defaulted',
};

export function loanStatusLabel(status: string): string {
  return (
    LOAN_STATUS_LABELS[status] ??
    status.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
  );
}

/** True when the seller holds power-of-attorney authority (gets the PoA tag). */
export function isPowerOfAttorney(authorityType: string | null | undefined): boolean {
  return authorityType === 'power_of_attorney';
}
