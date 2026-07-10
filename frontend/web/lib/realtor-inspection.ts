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
  /** Tailwind classes for the status pill (tokens only — no gold/ink-400). */
  pill: string;
}

const STATUS_META: Record<string, StatusMeta> = {
  pending: {
    label: 'Awaiting acceptance',
    bucket: 'awaiting',
    pill: 'bg-amber-100 text-amber-700',
  },
  accepted: {
    label: 'Scheduled',
    bucket: 'scheduled',
    pill: 'bg-blue-100 text-blue-700',
  },
  rescheduled: {
    label: 'Rescheduled',
    bucket: 'scheduled',
    pill: 'bg-blue-100 text-blue-700',
  },
  completed: {
    label: 'Report submitted',
    bucket: 'completed',
    pill: 'bg-emerald-deep/10 text-emerald-deep',
  },
};

const FALLBACK: StatusMeta = {
  label: 'Unknown',
  bucket: 'scheduled',
  pill: 'bg-ink-300/20 text-ink-500',
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
