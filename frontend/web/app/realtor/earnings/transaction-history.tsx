'use client';

import { useMemo, useRef, useState } from 'react';

import {
  CalendarIcon,
  ChevronDownIcon,
  FilterIcon,
  UploadIcon,
} from '../_icons';
import type { CommissionHistoryItem } from '@/lib/api';
import { formatDate, formatNaira } from '@/lib/format';
import {
  COMMISSION_FILTERS,
  commissionStatusMeta,
  commissionsToCsv,
  filterCommissions,
  type CommissionFilter,
} from '@/lib/realtor-earnings';

/** Transaction History (SCRUM-204, Figma 287:61 + 287:78). Filter + Export live
 * in the card header above the table, as drawn. */
export function TransactionHistory({ items }: { items: CommissionHistoryItem[] }) {
  const [status, setStatus] = useState<CommissionFilter>('all');
  const linkRef = useRef<HTMLAnchorElement>(null);

  const rows = useMemo(() => filterCommissions(items, status), [items, status]);

  /** Export what is on screen. Built client-side from rows already loaded —
   * there is no export endpoint, and the object URL is revoked once the click
   * has been dispatched so the blob is not retained. */
  function exportCsv() {
    const blob = new Blob([commissionsToCsv(rows)], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = linkRef.current;
    if (!a) return;
    a.href = url;
    a.download = `maihomme-earnings-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <div className="mt-6 rounded-card-sm border border-line bg-surface-card p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-xl font-bold text-ink-900">Transaction History</h2>
          <div className="flex items-center gap-4">
            <div className="relative w-[159px]">
              <FilterIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-500" />
              <ChevronDownIcon className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-500" />
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as CommissionFilter)}
                aria-label="Filter by payment status"
                className="h-[42px] w-full appearance-none rounded-[10px] border border-line-strong bg-surface-card pl-9 pr-9 text-sm text-ink-900 outline-none transition focus:border-emerald-deep"
              >
                {COMMISSION_FILTERS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="button"
              onClick={exportCsv}
              disabled={rows.length === 0}
              className="inline-flex h-10 items-center gap-2 rounded-[10px] border-2 border-line-strong px-4 text-sm font-medium text-ink-700 transition hover:border-ink-500 disabled:opacity-50 disabled:hover:border-line-strong"
            >
              <UploadIcon className="h-4 w-4 flex-none rotate-180" />
              Export
            </button>
            {/* Anchor the export click through a real link so the browser owns
                the download; kept out of the tab order since the button drives it. */}
            <a ref={linkRef} className="hidden" aria-hidden tabIndex={-1} />
          </div>
        </div>
      </div>

      <div className="mt-6 overflow-hidden rounded-card-sm border border-line bg-surface-card">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left">
            <thead>
              <tr className="border-b border-line bg-surface-page text-sm font-semibold text-ink-900">
                <th scope="col" className="px-6 py-4">
                  Transaction
                </th>
                <th scope="col" className="py-4 pr-6">
                  Property
                </th>
                <th scope="col" className="py-4 pr-6">
                  Date
                </th>
                <th scope="col" className="py-4 pr-6">
                  Amount
                </th>
                <th scope="col" className="py-4 pr-6">
                  Status
                </th>
                <th scope="col" className="py-4 pr-6">
                  Payment
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-16 text-center text-sm text-ink-500">
                    {items.length === 0
                      ? 'No commissions yet. You earn once a deal you inspected completes.'
                      : 'No payments match this filter.'}
                  </td>
                </tr>
              ) : (
                rows.map((c) => <Row key={c.commission_id} c={c} />)
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function Row({ c }: { c: CommissionHistoryItem }) {
  const meta = commissionStatusMeta(c.status);
  return (
    <tr className="border-b border-line last:border-b-0">
      <td className="px-6 py-4 align-middle">
        <p className="font-mono text-sm text-ink-900">TXN-{c.transaction_id.slice(0, 8).toUpperCase()}</p>
        <p className="mt-0.5 text-xs text-ink-600">
          Commission: <span className="font-mono">{c.commission_id.slice(0, 8).toUpperCase()}</span>
        </p>
      </td>
      <td className="py-4 pr-6 align-middle text-sm font-medium text-ink-900">
        {c.property_title ?? 'Property deal'}
      </td>
      <td className="py-4 pr-6 align-middle">
        <p className="flex items-center gap-2 text-sm text-ink-900">
          <CalendarIcon className="h-4 w-4 flex-none text-ink-500" />
          {formatDate(c.created_at)}
        </p>
      </td>
      <td className="py-4 pr-6 align-middle text-sm font-bold text-ink-900">
        {formatNaira(c.amount_kobo)}
      </td>
      <td className="py-4 pr-6 align-middle">
        <span
          className={`inline-flex h-[26px] items-center rounded-full border px-3 text-xs font-medium ${meta.pill}`}
        >
          {meta.label}
        </span>
      </td>
      <td className="py-4 pr-6 align-middle">
        {meta.paid && c.disbursed_at ? (
          <>
            <p className="text-sm text-ink-900">Bank Transfer</p>
            <p className="text-xs text-ink-600">{formatDate(c.disbursed_at)}</p>
          </>
        ) : c.status === 'available' ? (
          <p className="text-xs text-scheduled-700">Ready for payout</p>
        ) : (
          <p className="text-xs text-pending-700">
            Clears {formatDate(c.available_at)}
          </p>
        )}
      </td>
    </tr>
  );
}
