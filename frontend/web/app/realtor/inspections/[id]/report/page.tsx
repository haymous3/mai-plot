import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { ReportWizard } from './report-wizard';
import { RealtorHeader } from '../../../realtor-header';
import type { RealtorInspectionsResponse } from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { reportSubmittable } from '@/lib/inspection-report';
import { inspectionLocation } from '@/lib/realtor-inspection';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Inspection Report · Maiplot Realtor' };

/** Inspection report submission (SCRUM-140, PR3). Resolves the inspection from
 * the realtor's own assignments (there is no single-inspection GET), then either
 * renders the 5-step wizard or explains why the report can't be submitted yet
 * (mirrors the backend's accepted + on/after-date guards). */
export default async function InspectionReportPage({ params }: { params: { id: string } }) {
  const res = await sessionBackendGet<RealtorInspectionsResponse>(
    `${realtorServiceUrl()}/inspections/mine`,
  );

  if (!res.ok) {
    return (
      <main className="mx-auto max-w-3xl px-8 py-8">
        <RealtorHeader title="Inspection Report" subtitle="" />
        <div className="mt-8 rounded-xl border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
          Could not load this inspection. Please retry.
        </div>
      </main>
    );
  }

  const insp = res.data.data.find((i) => i.inspection_id === params.id);
  if (!insp) notFound();

  const gate = reportSubmittable(insp);

  return (
    <main className="mx-auto max-w-3xl px-8 py-8">
      <Link
        href="/realtor/inspections"
        className="text-sm text-ink-500 transition hover:text-ink-900"
      >
        ← Back to assigned inspections
      </Link>

      <div className="mt-4">
        <RealtorHeader title="Inspection Report" subtitle={insp.property_title ?? 'Property inspection'} />
      </div>

      <section className="mt-6 rounded-2xl border border-ink-300/25 bg-white p-5">
        <p className="text-xs text-ink-500">Property under inspection</p>
        <p className="mt-1 font-medium text-ink-900">{insp.property_title ?? 'Property inspection'}</p>
        <p className="mt-0.5 text-sm text-ink-500">📍 {inspectionLocation(insp)}</p>
        {insp.confirmed_date && (
          <p className="mt-2 text-xs text-ink-600">
            Confirmed inspection date: {formatDate(insp.confirmed_date)}
          </p>
        )}
      </section>

      {gate.ok ? (
        <ReportWizard inspectionId={insp.inspection_id} />
      ) : (
        <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 px-6 py-10 text-center">
          {gate.reason === 'too_early' ? (
            <>
              <p className="text-sm font-medium text-amber-800">Report submission isn&apos;t open yet.</p>
              <p className="mt-1 text-sm text-amber-700">
                You can submit your report on or after the confirmed inspection date
                {gate.opensAt ? ` (${formatDate(gate.opensAt)})` : ''}.
              </p>
            </>
          ) : (
            <>
              <p className="text-sm font-medium text-amber-800">
                This inspection isn&apos;t ready for a report.
              </p>
              <p className="mt-1 text-sm text-amber-700">
                Accept the assignment first — a report can only be submitted once the inspection is
                scheduled, and only once.
              </p>
            </>
          )}
        </div>
      )}
    </main>
  );
}
