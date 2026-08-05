import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { RealtorHeader } from '../../realtor-header';
import type { InspectionReport, RealtorInspectionsResponse } from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { CONDITION_OPTIONS } from '@/lib/inspection-report';
import { inspectionLocation } from '@/lib/realtor-inspection';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Report · Maiplot Realtor' };

function conditionLabel(value: string | null): string {
  if (!value) return '—';
  return CONDITION_OPTIONS.find((o) => o.value === value)?.label ?? value;
}

/** Submitted-report detail (SCRUM-140, PR4). Reads the existing
 * GET /inspections/{id}/report (realtor is authorised for their own report);
 * property context comes from GET /inspections/mine. Photos are pre-signed S3
 * URLs served by the backend. */
export default async function ReportDetailPage({ params }: { params: { id: string } }) {
  const [reportRes, mineRes] = await Promise.all([
    sessionBackendGet<InspectionReport>(
      `${realtorServiceUrl()}/inspections/${params.id}/report`,
    ),
    sessionBackendGet<RealtorInspectionsResponse>(`${realtorServiceUrl()}/inspections/mine`),
  ]);

  if (!reportRes.ok) {
    if (reportRes.status === 404) notFound();
    return (
      <main className="mx-auto max-w-3xl px-8 py-8">
        <RealtorHeader title="Report" subtitle="" />
        <div className="mt-8 rounded-xl border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
          Could not load this report. Please retry.
        </div>
      </main>
    );
  }

  const report = reportRes.data;
  const insp = mineRes.ok
    ? mineRes.data.data.find((i) => i.inspection_id === params.id)
    : undefined;
  const title = insp?.property_title ?? 'Inspection report';

  return (
    <main className="mx-auto max-w-3xl px-8 py-8">
      <Link href="/realtor/reports" className="text-sm text-ink-500 transition hover:text-ink-900">
        ← Back to report history
      </Link>

      <div className="mt-4">
        <RealtorHeader title="Inspection Report" subtitle={title} />
      </div>

      <section className="mt-6 rounded-card-sm border border-line bg-surface-card p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            {insp && <p className="text-sm text-ink-500">📍 {inspectionLocation(insp)}</p>}
            {report.report_submitted_at && (
              <p className="mt-1 text-xs text-ink-500">
                Submitted {formatDateTime(report.report_submitted_at)}
              </p>
            )}
          </div>
          <span className="rounded-full bg-emerald-deep/10 px-2.5 py-1 text-xs font-medium text-emerald-deep">
            Submitted
          </span>
        </div>

        <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-line pt-4">
          <Detail label="Property condition" value={conditionLabel(report.property_condition)} />
          <Detail
            label="Amenities"
            value={report.amenities.length > 0 ? report.amenities.join(', ') : 'None recorded'}
          />
        </dl>

        {report.discrepancies && (
          <Block label="Discrepancies noted" body={report.discrepancies} tone="warn" />
        )}
        {report.remarks && <Block label="Remarks" body={report.remarks} />}

        {report.gps_lat !== null && report.gps_lng !== null && (
          <div className="mt-4">
            <p className="text-xs text-ink-500">Captured location</p>
            <a
              href={`https://www.google.com/maps/search/?api=1&query=${report.gps_lat},${report.gps_lng}`}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-0.5 inline-block text-sm text-emerald-deep hover:underline"
            >
              🗺 {report.gps_lat.toFixed(5)}, {report.gps_lng.toFixed(5)}
            </a>
          </div>
        )}
      </section>

      <section className="mt-6 rounded-card-sm border border-line bg-surface-card p-6">
        <h2 className="font-display text-lg text-ink-900">
          Photos ({report.photo_urls.length})
        </h2>
        {report.photo_urls.length === 0 ? (
          <p className="mt-3 text-sm text-ink-500">No photos on this report.</p>
        ) : (
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {report.photo_urls.map((url, i) => (
              <a
                key={i}
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="aspect-square overflow-hidden rounded-lg bg-bone"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={url} alt={`Report photo ${i + 1}`} className="h-full w-full object-cover" />
              </a>
            ))}
          </div>
        )}
      </section>

      {report.video_url && (
        <section className="mt-6 rounded-card-sm border border-line bg-surface-card p-6">
          <h2 className="font-display text-lg text-ink-900">Video walkthrough</h2>
          <video
            src={report.video_url}
            controls
            className="mt-4 w-full rounded-lg bg-ink-900"
          />
        </section>
      )}
    </main>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-500">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium capitalize text-ink-900">{value}</dd>
    </div>
  );
}

function Block({ label, body, tone }: { label: string; body: string; tone?: 'warn' }) {
  return (
    <div className="mt-4">
      <p className="text-xs text-ink-500">{label}</p>
      <p
        className={`mt-1 whitespace-pre-line rounded-lg px-3 py-2 text-sm ${
          tone === 'warn' ? 'bg-amber-50 text-amber-800' : 'bg-bone text-ink-700'
        }`}
      >
        {body}
      </p>
    </div>
  );
}
