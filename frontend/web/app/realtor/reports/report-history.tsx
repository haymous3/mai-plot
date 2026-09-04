'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';

import {
  AlertCircleIcon,
  CalendarIcon,
  ClockIcon,
  EyeIcon,
  MapPinIcon,
  SearchIcon,
} from '../_icons';
import type { RealtorInspection } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { inspectionLocationLines, inspectionMatchesQuery } from '@/lib/realtor-inspection';

/** Report History (SCRUM-140 PR4, redesigned in SCRUM-204 from Figma 281:5895
 * and export 10.png).
 *
 * ⚠️ Every submitted report reads "Pending Review", because it genuinely is:
 * no service has a report-review workflow, so there is no approved/rejected
 * state, no admin feedback and no resubmit. Product owner's call is to ship the
 * designed layout now and leave those to the review ticket — so the Approved
 * and Rejected tiles are real counts that are currently zero, not placeholders,
 * and the design's Admin Feedback panel, Download PDF and Resubmit Report
 * buttons are omitted rather than faked.
 *
 * The designed review-status dropdown is omitted for the same reason: with one
 * reachable status a filter is worse than no filter. Search stays, because it
 * works. Both come back with the review workflow. */
export function ReportHistory({ reports }: { reports: RealtorInspection[] }) {
  const [query, setQuery] = useState('');

  const filtered = useMemo(
    () => reports.filter((r) => inspectionMatchesQuery(r, query)),
    [reports, query],
  );

  if (reports.length === 0) {
    return (
      <div className="mt-8 rounded-card-sm border border-dashed border-line-strong bg-surface-card px-6 py-16 text-center text-sm text-ink-500">
        You haven&apos;t submitted any reports yet. Submitted inspection reports will appear here.
      </div>
    );
  }

  return (
    <>
      <div className="mt-6 rounded-card-sm border border-line bg-surface-card p-6">
        <div className="flex flex-wrap items-center gap-4">
          <div className="relative min-w-[240px] flex-1">
            <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-500" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search reports"
              placeholder="Search by property, location, or report ID..."
              className="h-[50px] w-full rounded-[10px] border border-line-strong pl-10 pr-4 text-base text-ink-900 outline-none transition placeholder:text-ink-900/50 focus:border-emerald-deep"
            />
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile value={reports.length} label="Total Reports" />
        <Tile value={0} label="Approved" tint="border-done-200 bg-done-50 text-done-700" />
        <Tile
          value={reports.length}
          label="Pending Review"
          tint="border-pending-200 bg-pending-50 text-pending-700"
        />
        <Tile value={0} label="Rejected" tint="border-distress-200 bg-distress-50 text-distress-700" />
      </div>

      <p className="mt-4 flex items-start gap-2 rounded-[10px] border border-scheduled-200 bg-scheduled-50 px-4 py-3 text-sm text-scheduled-800">
        <AlertCircleIcon className="mt-0.5 h-4 w-4 flex-none" />
        Admin review is not live yet, so every submitted report sits at Pending Review. Approval
        decisions and feedback will appear on these cards once it is.
      </p>

      <div className="mt-6 space-y-4">
        {filtered.length === 0 ? (
          <p className="py-10 text-center text-sm text-ink-500">No reports match your search.</p>
        ) : (
          filtered.map((r) => <ReportCard key={r.inspection_id} report={r} />)
        )}
      </div>
    </>
  );
}

function ReportCard({ report }: { report: RealtorInspection }) {
  const { primary, secondary } = inspectionLocationLines(report);
  return (
    <article className="rounded-card-sm border border-line bg-surface-card p-6">
      <div className="flex flex-wrap items-start gap-4">
        {report.cover_photo_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={report.cover_photo_url}
            alt=""
            className="h-16 w-16 flex-none rounded-[10px] object-cover"
          />
        ) : (
          <div aria-hidden className="h-16 w-16 flex-none rounded-[10px] bg-surface-muted" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p className="text-base font-semibold text-ink-900">
              {report.property_title ?? 'Property inspection'}
            </p>
            <span className="inline-flex h-[26px] flex-none items-center gap-1.5 rounded-full border border-pending-200 bg-pending-100 px-3 text-xs font-medium text-pending-700">
              <ClockIcon className="h-3 w-3 flex-none" strokeWidth={2} />
              Pending Review
            </span>
          </div>
          <p className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-600">
            <span className="flex items-center gap-1.5">
              <MapPinIcon className="h-4 w-4 flex-none" />
              {[primary, secondary].filter(Boolean).join(', ')}
            </span>
            <span className="flex items-center gap-1.5">
              <CalendarIcon className="h-4 w-4 flex-none" />
              Submitted{' '}
              {report.report_submitted_at ? formatDate(report.report_submitted_at) : '—'}
            </span>
          </p>
          {/* The design shows a Report ID beside the Inspection ID. A report has
              no id of its own — it is stored on the inspection row — so a
              separate "RPT-…" would be the same value wearing a different
              prefix. One honest identifier instead of two that look distinct. */}
          <p className="mt-3 text-xs text-ink-600">
            Inspection ID:{' '}
            <span className="font-mono text-ink-900">{report.inspection_ref.toUpperCase()}</span>
          </p>
          <Link
            href={`/realtor/reports/${report.inspection_id}`}
            className="mt-4 inline-flex h-9 items-center gap-2 rounded-[10px] bg-emerald-deep px-4 text-sm font-medium text-white transition hover:bg-emerald-accent"
          >
            <EyeIcon className="h-4 w-4 flex-none" />
            View Report
          </Link>
        </div>
      </div>
    </article>
  );
}

function Tile({ value, label, tint }: { value: number; label: string; tint?: string }) {
  return (
    <div className={`rounded-[10px] border p-[17px] ${tint ?? 'border-line bg-surface-card'}`}>
      <p className={`text-2xl font-bold leading-8 ${tint ? '' : 'text-ink-900'}`}>{value}</p>
      <p className={`text-sm leading-5 ${tint ? '' : 'text-ink-600'}`}>{label}</p>
    </div>
  );
}
