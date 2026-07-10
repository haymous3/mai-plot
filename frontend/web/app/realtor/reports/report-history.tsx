'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';

import type { RealtorInspection } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { inspectionLocation, inspectionMatchesQuery, isSameMonth } from '@/lib/realtor-inspection';

/** Report History list (SCRUM-140, PR4). Client-side search + summary tiles over
 * the realtor's submitted reports; each links to its detail view. */
export function ReportHistory({ reports }: { reports: RealtorInspection[] }) {
  const [query, setQuery] = useState('');

  const thisMonth = useMemo(
    () => reports.filter((r) => isSameMonth(r.report_submitted_at)).length,
    [reports],
  );
  const filtered = useMemo(
    () => reports.filter((r) => inspectionMatchesQuery(r, query)),
    [reports, query],
  );

  if (reports.length === 0) {
    return (
      <div className="mt-8 rounded-2xl border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center text-sm text-ink-500">
        You haven&apos;t submitted any reports yet. Submitted inspection reports will appear here.
      </div>
    );
  }

  return (
    <div className="mt-6 space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <Tile icon="📝" value={String(reports.length)} label="Total Reports" />
        <Tile icon="📆" value={String(thisMonth)} label="Submitted This Month" />
      </div>

      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search by property or location…"
        className="w-full rounded-lg border border-ink-300/50 px-4 py-2.5 text-sm text-ink-900 outline-none focus:border-emerald-deep"
      />

      <div className="rounded-xl border border-emerald-deep/15 bg-emerald-deep/5 px-4 py-3 text-xs text-ink-700">
        Admin review feedback will appear on each report once report review is available.
      </div>

      {filtered.length === 0 ? (
        <p className="py-10 text-center text-sm text-ink-500">No reports match your search.</p>
      ) : (
        <div className="space-y-3">
          {filtered.map((r) => (
            <Link
              key={r.inspection_id}
              href={`/realtor/reports/${r.inspection_id}`}
              className="flex items-center justify-between gap-3 rounded-2xl border border-ink-300/25 bg-white p-5 transition hover:border-ink-500/40"
            >
              <div className="min-w-0">
                <p className="truncate font-medium text-ink-900">
                  {r.property_title ?? 'Property inspection'}
                </p>
                <p className="mt-0.5 truncate text-sm text-ink-500">📍 {inspectionLocation(r)}</p>
                <p className="mt-1 text-xs text-ink-600">
                  📝 Submitted {r.report_submitted_at ? formatDate(r.report_submitted_at) : '—'}
                </p>
              </div>
              <div className="flex flex-none items-center gap-3">
                <span className="rounded-full bg-emerald-deep/10 px-2.5 py-1 text-xs font-medium text-emerald-deep">
                  Submitted
                </span>
                <span aria-hidden className="text-ink-300">
                  →
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function Tile({ icon, value, label }: { icon: string; value: string; label: string }) {
  return (
    <div className="rounded-2xl border border-ink-300/25 bg-white p-5">
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-bone text-lg">
        {icon}
      </span>
      <p className="mt-3 font-display text-3xl text-ink-900">{value}</p>
      <p className="text-sm text-ink-600">{label}</p>
    </div>
  );
}
