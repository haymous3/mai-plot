'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import type { InspectionReport, ReportReviewFilter, ReportReviewItem } from '@/lib/api';
import { formatDate, formatDateTime } from '@/lib/format';

const REVIEW_ERRORS: Record<string, string> = {
  REPORT_NOT_FOUND: 'This report no longer exists.',
  REPORT_NOT_PENDING: 'This report has already been decided — refresh to see the decision.',
  REVIEW_NOTE_REQUIRED: 'A reason is required when rejecting.',
  REPORT_UNAVAILABLE: 'Could not open the report body.',
  NO_SESSION: 'Your session expired — please sign in again.',
  BACKEND_UNAVAILABLE: 'The realtor service is unreachable.',
};

const STATUS_PILL: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-800',
  approved: 'bg-emerald-100 text-emerald-800',
  rejected: 'bg-red-100 text-red-800',
};

/** Report review queue table (SCRUM-205). A reviewer opens the report body
 * inline before deciding — approving something you have not read is the failure
 * mode this whole feature exists to prevent. */
export function ReportsTable({
  items,
  status,
}: {
  items: ReportReviewItem[];
  status: ReportReviewFilter;
}) {
  const router = useRouter();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [report, setReport] = useState<InspectionReport | null>(null);
  const [rejecting, setRejecting] = useState<ReportReviewItem | null>(null);
  const [note, setNote] = useState('');

  async function open(item: ReportReviewItem) {
    if (openId === item.inspection_id) {
      setOpenId(null);
      setReport(null);
      return;
    }
    setOpenId(item.inspection_id);
    setReport(null);
    setError(null);
    try {
      const resp = await fetch(`/api/admin/inspections/${item.inspection_id}/report`);
      if (!resp.ok) {
        const body = (await resp.json().catch(() => ({}))) as { error?: string };
        setError(REVIEW_ERRORS[body.error ?? ''] ?? 'Could not open the report.');
        return;
      }
      setReport((await resp.json()) as InspectionReport);
    } catch {
      setError('Could not reach the server. Please try again.');
    }
  }

  async function review(item: ReportReviewItem, action: 'approve' | 'reject', reason?: string) {
    setBusyId(item.inspection_id);
    setError(null);
    try {
      const resp = await fetch(`/api/admin/inspections/${item.inspection_id}/report/review`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ action, note: reason }),
      });
      if (!resp.ok) {
        const body = (await resp.json().catch(() => ({}))) as { error?: string };
        setError(REVIEW_ERRORS[body.error ?? ''] ?? 'Could not complete the review.');
        return;
      }
      setRejecting(null);
      setNote('');
      setOpenId(null);
      setReport(null);
      router.refresh();
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusyId(null);
    }
  }

  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-ink-300/60 bg-white/60 px-6 py-16 text-center text-sm text-ink-500">
        {status === 'pending'
          ? 'No reports are waiting for review.'
          : 'No reports match this filter.'}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {items.map((item) => {
        const isOpen = openId === item.inspection_id;
        const busy = busyId === item.inspection_id;
        return (
          <article
            key={item.inspection_id}
            className="rounded-lg border border-ink-300/30 bg-white p-6"
          >
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-3">
                  <h2 className="font-medium text-ink-900">
                    {item.property_title ?? 'Property inspection'}
                  </h2>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      STATUS_PILL[item.report_review_status] ?? 'bg-ink-900/5 text-ink-500'
                    }`}
                  >
                    {item.report_review_status}
                  </span>
                  {item.report_revision > 1 && (
                    <span className="rounded-full bg-ink-900/5 px-2.5 py-0.5 text-xs text-ink-600">
                      Revision {item.report_revision}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-sm text-ink-500">
                  {[item.address_text, item.lga, item.state].filter(Boolean).join(', ') ||
                    'Location unavailable'}
                </p>
                <p className="mt-2 text-xs text-ink-500">
                  Filed by{' '}
                  <span className="text-ink-900">{item.realtor_name ?? 'Unknown realtor'}</span>
                  {item.esvarbon_number && ` · ESVARBON ${item.esvarbon_number}`}
                  {item.report_submitted_at &&
                    ` · submitted ${formatDateTime(item.report_submitted_at)}`}
                </p>
              </div>

              <button
                type="button"
                onClick={() => void open(item)}
                aria-expanded={isOpen}
                className="rounded-lg border border-ink-300/60 px-4 py-2 text-sm font-medium text-ink-700 transition hover:border-ink-500"
              >
                {isOpen ? 'Hide report' : 'Read report'}
              </button>
            </div>

            {item.report_review_status !== 'pending' && item.report_review_note && (
              <p className="mt-4 rounded-lg bg-ink-900/5 px-4 py-3 text-sm text-ink-700">
                <span className="font-medium">Reviewer note:</span> {item.report_review_note}
                {item.report_reviewed_at && (
                  <span className="text-ink-500"> · {formatDate(item.report_reviewed_at)}</span>
                )}
              </p>
            )}

            {isOpen && <ReportBody report={report} />}

            {item.report_review_status === 'pending' && (
              <div className="mt-5 border-t border-ink-300/25 pt-4">
                {rejecting?.inspection_id === item.inspection_id ? (
                  <div className="space-y-3">
                    <label
                      htmlFor={`note-${item.inspection_id}`}
                      className="block text-sm font-medium text-ink-900"
                    >
                      Why is this being rejected?
                    </label>
                    <textarea
                      id={`note-${item.inspection_id}`}
                      rows={3}
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="The realtor sees this — say what to fix."
                      className="w-full rounded-lg border border-ink-300/60 px-3 py-2 text-sm text-ink-900 outline-none focus:border-ink-500"
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setRejecting(null);
                          setNote('');
                        }}
                        disabled={busy}
                        className="rounded-lg border border-ink-300/60 px-4 py-2 text-sm text-ink-700 transition hover:border-ink-500 disabled:opacity-50"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={() => void review(item, 'reject', note)}
                        disabled={busy || note.trim() === ''}
                        className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-700 disabled:opacity-50"
                      >
                        {busy ? 'Rejecting…' : 'Confirm rejection'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void review(item, 'approve')}
                      disabled={busy}
                      className="rounded-lg bg-emerald-deep px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-accent disabled:opacity-50"
                    >
                      {busy ? 'Approving…' : 'Approve'}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setRejecting(item);
                        setNote('');
                        setError(null);
                      }}
                      disabled={busy}
                      className="rounded-lg border border-red-300 px-4 py-2 text-sm font-medium text-red-700 transition hover:border-red-500 disabled:opacity-50"
                    >
                      Reject
                    </button>
                  </div>
                )}
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}

/** The report body a reviewer reads before deciding. Photos arrive as
 * short-TTL pre-signed URLs. */
function ReportBody({ report }: { report: InspectionReport | null }) {
  if (report === null) {
    return <p className="mt-4 text-sm text-ink-500">Loading report…</p>;
  }
  return (
    <div className="mt-4 space-y-4 rounded-lg bg-bone/60 p-4">
      <dl className="grid gap-3 sm:grid-cols-3">
        <Detail label="Condition">{report.property_condition ?? '—'}</Detail>
        <Detail label="Amenities">
          {report.amenities.length > 0 ? report.amenities.join(', ') : 'None recorded'}
        </Detail>
        <Detail label="GPS">
          {report.gps_lat !== null && report.gps_lng !== null
            ? `${report.gps_lat.toFixed(5)}, ${report.gps_lng.toFixed(5)}`
            : '—'}
        </Detail>
      </dl>

      <Block label="Discrepancies" tone={report.discrepancies ? 'warn' : 'plain'}>
        {report.discrepancies ?? 'None reported.'}
      </Block>
      <Block label="Remarks">{report.remarks ?? 'None.'}</Block>

      <div>
        <p className="text-xs uppercase tracking-wider text-ink-300">
          Photos ({report.photo_urls.length})
        </p>
        {report.photo_urls.length === 0 ? (
          <p className="mt-1 text-sm text-ink-500">No photos.</p>
        ) : (
          <div className="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-5">
            {report.photo_urls.map((url, i) => (
              <a key={url} href={url} target="_blank" rel="noreferrer noopener">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={url}
                  alt={`Inspection photo ${i + 1}`}
                  className="aspect-square w-full rounded-lg object-cover"
                />
              </a>
            ))}
          </div>
        )}
        {report.video_url && (
          <a
            href={report.video_url}
            target="_blank"
            rel="noreferrer noopener"
            className="mt-2 inline-block text-sm font-medium text-emerald-deep hover:underline"
          >
            Open the walkthrough video
          </a>
        )}
      </div>
    </div>
  );
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-ink-300">{label}</dt>
      <dd className="mt-0.5 text-sm capitalize text-ink-900">{children}</dd>
    </div>
  );
}

function Block({
  label,
  tone = 'plain',
  children,
}: {
  label: string;
  tone?: 'plain' | 'warn';
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wider text-ink-300">{label}</p>
      <p
        className={`mt-1 whitespace-pre-line text-sm ${
          tone === 'warn' ? 'text-amber-800' : 'text-ink-700'
        }`}
      >
        {children}
      </p>
    </div>
  );
}
