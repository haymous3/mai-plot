'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';

import {
  AlertCircleIcon,
  CalendarIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ClockIcon,
  EyeIcon,
  FilterIcon,
  MapPinIcon,
  SearchIcon,
  UploadIcon,
} from '../_icons';
import type { RealtorInspection } from '@/lib/api';
import { formatDate } from '@/lib/format';
import {
  countReports,
  filterReports,
  inspectionLocationLines,
  REPORT_FILTERS,
  reportReviewMeta,
  type ReportFilter,
} from '@/lib/realtor-inspection';

/** Report History (SCRUM-140 PR4, redesigned in SCRUM-204 from Figma 281:5895,
 * completed in SCRUM-205 once report review existed).
 *
 * SCRUM-204 shipped this with every report reading "Pending Review", real-but-
 * always-zero Approved/Rejected tiles, and no feedback, resubmit or filter —
 * because no service reviewed a report. All four are now live. */
export function ReportHistory({ reports }: { reports: RealtorInspection[] }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<ReportFilter>('all');

  const counts = useMemo(() => countReports(reports), [reports]);
  const filtered = useMemo(
    () => filterReports(reports, { query, status }),
    [reports, query, status],
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
          <div className="relative w-[183px]">
            <FilterIcon className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-500" />
            <ChevronDownIcon className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-500" />
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as ReportFilter)}
              aria-label="Filter by review status"
              className="h-[50px] w-full appearance-none rounded-[10px] border border-line-strong bg-surface-card pl-10 pr-9 text-sm text-ink-900 outline-none transition focus:border-emerald-deep"
            >
              {REPORT_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile value={counts.total} label="Total Reports" />
        <Tile
          value={counts.approved}
          label="Approved"
          tint="border-done-200 bg-done-50 text-done-700"
        />
        <Tile
          value={counts.pending}
          label="Pending Review"
          tint="border-pending-200 bg-pending-50 text-pending-700"
        />
        <Tile
          value={counts.rejected}
          label="Rejected"
          tint="border-distress-200 bg-distress-50 text-distress-700"
        />
      </div>

      <div className="mt-6 space-y-4">
        {filtered.length === 0 ? (
          <p className="py-10 text-center text-sm text-ink-500">
            No reports match your search.
          </p>
        ) : (
          filtered.map((r) => <ReportCard key={r.inspection_id} report={r} />)
        )}
      </div>
    </>
  );
}

function ReportCard({ report }: { report: RealtorInspection }) {
  const { primary, secondary } = inspectionLocationLines(report);
  const meta = reportReviewMeta(report.report_review_status);
  const StatusIcon =
    report.report_review_status === 'approved'
      ? CheckCircleIcon
      : report.report_review_status === 'rejected'
        ? AlertCircleIcon
        : ClockIcon;

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
            <span
              className={`inline-flex h-[26px] flex-none items-center gap-1.5 rounded-full border px-3 text-xs font-medium ${meta.pill}`}
            >
              <StatusIcon className="h-3 w-3 flex-none" strokeWidth={2} />
              {meta.label}
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
              prefix. The revision is the part that genuinely varies. */}
          <p className="mt-3 text-xs text-ink-600">
            Inspection ID:{' '}
            <span className="font-mono text-ink-900">{report.inspection_ref.toUpperCase()}</span>
            {report.report_revision > 1 && (
              <span className="ml-3">Revision {report.report_revision}</span>
            )}
          </p>

          {report.report_review_note && <AdminFeedback report={report} />}

          <div className="mt-4 flex flex-wrap gap-2">
            <Link
              href={`/realtor/reports/${report.inspection_id}`}
              className="inline-flex h-9 items-center gap-2 rounded-[10px] bg-emerald-deep px-4 text-sm font-medium text-white transition hover:bg-emerald-accent"
            >
              <EyeIcon className="h-4 w-4 flex-none" />
              View Report
            </Link>
            {meta.resubmittable && (
              <Link
                href={`/realtor/inspections/${report.inspection_id}/report`}
                className="inline-flex h-9 items-center gap-2 rounded-[10px] border-2 border-emerald-deep px-4 text-sm font-medium text-emerald-deep transition hover:bg-emerald-deep/5"
              >
                <UploadIcon className="h-4 w-4 flex-none" />
                Resubmit Report
              </Link>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

/** The admin's note (Figma 281:5895 "Admin Feedback"). Present on a rejection —
 * where it says what to fix — and optionally on an approval. */
function AdminFeedback({ report }: { report: RealtorInspection }) {
  const rejected = report.report_review_status === 'rejected';
  return (
    <div
      className={`mt-3 rounded-[10px] border px-4 py-3 ${
        rejected
          ? 'border-distress-200 bg-distress-50'
          : 'border-done-200 bg-done-50'
      }`}
    >
      <p
        className={`text-xs font-semibold ${rejected ? 'text-distress-700' : 'text-done-700'}`}
      >
        Admin Feedback
      </p>
      <p className="mt-1 text-sm text-ink-700">{report.report_review_note}</p>
      {report.report_reviewed_at && (
        <p className="mt-1 text-xs text-ink-500">
          Reviewed {formatDate(report.report_reviewed_at)}
        </p>
      )}
    </div>
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
