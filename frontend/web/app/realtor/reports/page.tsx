import type { Metadata } from 'next';

import { ReportHistory } from './report-history';
import { RealtorHeader } from '../realtor-header';
import type { RealtorInspectionsResponse } from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Reports Submitted · Maiplot Realtor' };

/** Report History (SCRUM-140, PR4). Lists the realtor's submitted reports —
 * derived from their completed inspections (GET /inspections/mine) — with client
 * search + summary tiles. Per-report detail is a separate page reading the
 * existing GET /inspections/{id}/report. Admin review/feedback/resubmit is
 * deferred (no backend report-review workflow yet). */
export default async function RealtorReportsPage() {
  const res = await sessionBackendGet<RealtorInspectionsResponse>(
    `${realtorServiceUrl()}/inspections/mine`,
  );

  const reports = res.ok
    ? res.data.data
        .filter((i) => i.report_submitted_at !== null)
        .sort(
          (a, b) => Date.parse(b.report_submitted_at ?? '') - Date.parse(a.report_submitted_at ?? ''),
        )
    : [];

  return (
    <main className="mx-auto max-w-4xl px-8 py-8">
      <RealtorHeader title="Reports Submitted" subtitle="Your inspection report history" />

      {!res.ok ? (
        <div className="mt-8 rounded-xl border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
          Could not load your reports. Please retry.
        </div>
      ) : (
        <ReportHistory reports={reports} />
      )}
    </main>
  );
}
