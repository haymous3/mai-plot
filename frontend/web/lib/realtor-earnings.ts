/**
 * Realtor earnings helpers (SCRUM-204) — pure + dependency-free.
 *
 * ⚠️ The design (Figma 287:2) is drawn against a DIFFERENT compensation model:
 * "Earnings Per Inspection — ₦50,000 — a fixed amount for each completed and
 * approved inspection report, paid within 24-48 hours of report approval."
 *
 * The shipped model is CLAUDE.md §8 rule 7: a commission of 2% of each
 * completed deal's value, held for 3 business days before it becomes available
 * for payout. Product owner's call is to keep the real model and take the
 * design's visual treatment, so the copy here describes what actually happens.
 * Switching to a fixed per-inspection fee would touch commission_service,
 * escrow and §8, and is a separate ticket.
 */

import type { CommissionHistoryItem, CommissionSummary } from '@/lib/api';

/** How the backend's three commission states map onto the two balance cards the
 * design draws. `available` money is neither paid out nor still on hold, so it
 * sits with pending under "not yet paid" and is called out in the sub-line. */
export interface EarningsBalances {
  totalKobo: number;
  paidKobo: number;
  paidCount: number;
  outstandingKobo: number;
  outstandingCount: number;
  availableKobo: number;
}

export function earningsBalances(
  summary: CommissionSummary | null,
  history: CommissionHistoryItem[],
): EarningsBalances {
  const pending = summary?.pending_kobo ?? 0;
  const available = summary?.available_kobo ?? 0;
  const withdrawn = summary?.withdrawn_kobo ?? 0;
  return {
    totalKobo: pending + available + withdrawn,
    paidKobo: withdrawn,
    paidCount: history.filter((c) => c.status === 'withdrawn').length,
    outstandingKobo: pending + available,
    outstandingCount: history.filter((c) => c.status !== 'withdrawn').length,
    availableKobo: available,
  };
}

export type CommissionFilter = 'all' | 'withdrawn' | 'available' | 'pending';

export const COMMISSION_FILTERS: { value: CommissionFilter; label: string }[] = [
  { value: 'all', label: 'All payments' },
  { value: 'withdrawn', label: 'Paid' },
  { value: 'available', label: 'Available' },
  { value: 'pending', label: 'Pending' },
];

export function filterCommissions(
  items: CommissionHistoryItem[],
  status: CommissionFilter,
): CommissionHistoryItem[] {
  return status === 'all' ? items : items.filter((c) => c.status === status);
}

interface CommissionStatusMeta {
  label: string;
  /** -100 fill inside a -200 border, matching the inspection pills. */
  pill: string;
  /** True once the money has actually left — drives the Payment column. */
  paid: boolean;
}

const COMMISSION_STATUS: Record<string, CommissionStatusMeta> = {
  withdrawn: {
    label: 'Paid',
    pill: 'border-done-200 bg-done-100 text-done-700',
    paid: true,
  },
  available: {
    label: 'Available',
    pill: 'border-scheduled-200 bg-scheduled-100 text-scheduled-700',
    paid: false,
  },
  pending: {
    label: 'Pending',
    pill: 'border-pending-200 bg-pending-100 text-pending-700',
    paid: false,
  },
};

export function commissionStatusMeta(status: string): CommissionStatusMeta {
  return (
    COMMISSION_STATUS[status] ?? {
      label: status,
      pill: 'border-line bg-surface-muted text-ink-500',
      paid: false,
    }
  );
}

/** Commission rate as a percentage string, from the stored basis points.
 * Read per-row rather than hard-coded so an admin-configured rate (§8 rule 7)
 * shows the truth. Falls back to the platform default when there is no history
 * to read it from. */
export const DEFAULT_RATE_BPS = 200;

export function commissionRateLabel(items: CommissionHistoryItem[]): string {
  const rates = new Set(items.map((c) => c.rate_bps));
  if (rates.size === 1) {
    const [bps] = [...rates];
    return `${(bps / 100).toFixed(bps % 100 === 0 ? 0 : 2)}%`;
  }
  if (rates.size > 1) return 'Varies';
  return `${DEFAULT_RATE_BPS / 100}%`;
}

/** CSV of the transaction history, for the designed Export button. Built in the
 * browser from the rows already on screen — there is no export endpoint, and
 * inventing one is out of scope for a presentation ticket. Money stays in kobo
 * alongside the naira column so the file reconciles exactly. */
export function commissionsToCsv(items: CommissionHistoryItem[]): string {
  const header = [
    'Transaction',
    'Commission',
    'Property',
    'Date',
    'Amount (NGN)',
    'Amount (kobo)',
    'Rate',
    'Status',
    'Paid on',
  ];
  const rows = items.map((c) => [
    c.transaction_id,
    c.commission_id,
    c.property_title ?? '',
    c.created_at,
    (c.amount_kobo / 100).toFixed(2),
    String(c.amount_kobo),
    `${c.rate_bps / 100}%`,
    commissionStatusMeta(c.status).label,
    c.disbursed_at ?? '',
  ]);
  return [header, ...rows].map((r) => r.map(csvCell).join(',')).join('\r\n');
}

/** RFC 4180 quoting. A property title containing a comma or quote must not
 * shift every later column. */
function csvCell(value: string): string {
  return /[",\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}
