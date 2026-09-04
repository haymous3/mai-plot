/**
 * Realtor-portal inspection helpers (SCRUM-140) — pure + dependency-free so the
 * status vocabulary stays consistent across the dashboard, assigned-inspections
 * list, and report history, and is unit-testable without React.
 */

import type { RealtorInspection } from '@/lib/api';

export type InspectionBucket = 'awaiting' | 'scheduled' | 'completed';

interface StatusMeta {
  label: string;
  bucket: InspectionBucket;
  /** Tailwind classes for the status pill — the -100 fill + -200 border pairing
   * measured on Figma 280:5555. Stock amber/blue/green would render Tailwind
   * v3.4's values, which are visibly off-design (see tailwind.config.ts). */
  pill: string;
}

const STATUS_META: Record<string, StatusMeta> = {
  pending: {
    label: 'Pending',
    bucket: 'awaiting',
    pill: 'border-pending-200 bg-pending-100 text-pending-700',
  },
  accepted: {
    label: 'Scheduled',
    bucket: 'scheduled',
    pill: 'border-scheduled-200 bg-scheduled-100 text-scheduled-700',
  },
  // The design draws only three states. "Rescheduled" is kept as its own label
  // — it is a real backend state and a realtor whose proposed time was taken
  // needs to see that — but it wears the Scheduled treatment and counts in the
  // Scheduled bucket, so the tiles still add up to the designed four.
  rescheduled: {
    label: 'Rescheduled',
    bucket: 'scheduled',
    pill: 'border-scheduled-200 bg-scheduled-100 text-scheduled-700',
  },
  completed: {
    label: 'Completed',
    bucket: 'completed',
    pill: 'border-done-200 bg-done-100 text-done-700',
  },
};

const FALLBACK: StatusMeta = {
  label: 'Unknown',
  bucket: 'scheduled',
  pill: 'border-line bg-surface-muted text-ink-500',
};

export function inspectionStatusMeta(status: string): StatusMeta {
  return STATUS_META[status] ?? FALLBACK;
}

/** True when the realtor still has to accept the assignment (drives the "needs
 * response" emphasis + the acceptance countdown). */
export function isAwaitingAcceptance(insp: RealtorInspection): boolean {
  return insp.status === 'pending';
}

/** Live (not yet reported) assignments the realtor still has to act on or attend,
 * soonest first — the dashboard's "Upcoming Inspections" + the assigned list. */
export function upcomingInspections(items: RealtorInspection[]): RealtorInspection[] {
  return items
    .filter((i) => inspectionStatusMeta(i.status).bucket !== 'completed')
    .sort((a, b) => Date.parse(a.proposed_date) - Date.parse(b.proposed_date));
}

export interface InspectionCounts {
  awaiting: number;
  scheduled: number;
  completed: number;
  total: number;
}

export function countInspections(items: RealtorInspection[]): InspectionCounts {
  const counts: InspectionCounts = { awaiting: 0, scheduled: 0, completed: 0, total: items.length };
  for (const i of items) counts[inspectionStatusMeta(i.status).bucket] += 1;
  return counts;
}

/** A one-line location for an inspection card, from the joined property fields. */
export function inspectionLocation(insp: RealtorInspection): string {
  const parts = [insp.address_text, insp.lga, insp.state].filter(Boolean);
  return parts.length > 0 ? parts.join(', ') : 'Location unavailable';
}

/** The two-line location the designed table row uses (Figma 280:5555): the
 * street address above, then "LGA, State" beneath it. Either line can be empty
 * when the listing is incomplete, so callers render only what comes back. */
export function inspectionLocationLines(insp: RealtorInspection): {
  primary: string;
  secondary: string;
} {
  const secondary = [insp.lga, insp.state].filter(Boolean).join(', ');
  const primary = insp.address_text ?? (secondary ? '' : 'Location unavailable');
  return { primary, secondary };
}

/** Listing `property_type` as the design writes it. The backend vocabulary is
 * only land | residential | commercial — the design's richer labels ("Villa",
 * "Office Space") have no backing field, so they are not invented. */
const PROPERTY_TYPE_LABELS: Record<string, string> = {
  land: 'Land',
  residential: 'House',
  commercial: 'Commercial',
};

export function propertyTypeLabel(type: string | null): string | null {
  if (!type) return null;
  return PROPERTY_TYPE_LABELS[type] ?? type;
}

/** Distress listings carry the red marker on their table row (§8 rule 2). */
export function isDistressSale(insp: RealtorInspection): boolean {
  return insp.sale_type === 'distress';
}

/** The Status filter behind the table's dropdown. `all` is the default and
 * matches everything; the rest select a single bucket. */
export type InspectionFilter = 'all' | InspectionBucket;

export const INSPECTION_FILTERS: { value: InspectionFilter; label: string }[] = [
  { value: 'all', label: 'All statuses' },
  { value: 'awaiting', label: 'Pending' },
  { value: 'scheduled', label: 'Scheduled' },
  { value: 'completed', label: 'Completed' },
];

/** Search + status filter applied together, preserving the caller's order. */
export function filterInspections(
  items: RealtorInspection[],
  { query, status }: { query: string; status: InspectionFilter },
): RealtorInspection[] {
  return items.filter(
    (i) =>
      inspectionMatchesQuery(i, query) &&
      (status === 'all' || inspectionStatusMeta(i.status).bucket === status),
  );
}

/** Case-insensitive match of a search query against an inspection's property
 * title, location and reference ids — the placeholder promises "property,
 * location, or ID", so the ids have to be searchable (SCRUM-204). An empty
 * query matches everything. */
export function inspectionMatchesQuery(insp: RealtorInspection, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const haystack = [
    insp.property_title ?? '',
    inspectionLocation(insp),
    insp.inspection_ref,
    insp.buyer_ref,
  ]
    .join(' ')
    .toLowerCase();
  return haystack.includes(q);
}

/** Whether an ISO timestamp falls in the same calendar month as `now` — the
 * "This Month" report tile. */
export function isSameMonth(iso: string | null, now: number = Date.now()): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return false;
  const ref = new Date(now);
  return d.getUTCFullYear() === ref.getUTCFullYear() && d.getUTCMonth() === ref.getUTCMonth();
}

export interface AcceptanceWindow {
  expired: boolean;
  /** Live remaining-time label, e.g. "1h 23m left" or "4m 07s left". */
  label: string;
  /** True in the final stretch (<15 min) — drives the red emphasis. */
  urgent: boolean;
}

/** Time left in a 2-hour acceptance window, relative to `now` (ms since epoch).
 * Shows h+m while there's an hour+, then m+s in the final stretch so the ticking
 * seconds are visible near expiry. */
export function acceptanceWindow(expiresAtIso: string, now: number = Date.now()): AcceptanceWindow {
  const ms = Date.parse(expiresAtIso) - now;
  if (!Number.isFinite(ms) || ms <= 0) {
    return { expired: true, label: 'Window elapsed', urgent: true };
  }
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  const label = h > 0 ? `${h}h ${m}m left` : `${m}m ${String(s).padStart(2, '0')}s left`;
  return { expired: false, label, urgent: totalSec < 900 };
}
