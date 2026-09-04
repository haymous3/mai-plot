import type { Metadata } from 'next';
import Link from 'next/link';

import { ReportHistory } from './report-history';
import { ArrowLeftIcon } from '../_icons';
import type { RealtorInspectionsResponse } from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Report History · Maihomme Realtor' };

/** Report History (SCRUM-140 PR4, redesigned in SCRUM-204 from Figma 281:5895).
 * Derived from the realtor's completed inspections — reports are stored on the
 * inspection row, so there is no separate reports collection to read. */
export default async function RealtorReportsPage() {
  const res = await sessionBackendGet<RealtorInspectionsResponse>(
    `${realtorServiceUrl()}/inspections/mine`,
  );

  const reports = res.ok
    ? res.data.data
        .filter((i) => i.report_submitted_at !== null)
        .sort(
          (a, b) =>
            Date.parse(b.report_submitted_at ?? '') - Date.parse(a.report_submitted_at ?? ''),
        )
    : [];

  return (
    <main className="mx-auto max-w-[1088px] px-8 py-8">
      <Link
        href="/realtor"
        className="inline-flex items-center gap-2 text-sm font-medium text-ink-600 transition hover:text-ink-900"
      >
        <ArrowLeftIcon className="h-4 w-4" />
        Back to Dashboard
      </Link>
      <h1 className="mt-3 text-3xl font-bold leading-9 text-ink-900">Report History</h1>
      <p className="mt-2 text-base leading-6 text-ink-600">
        View and manage all submitted inspection reports
      </p>

      {!res.ok ? (
        <div className="mt-8 rounded-card-sm border border-status-danger/30 bg-distress-50 px-6 py-10 text-center text-sm text-distress-700">
          Could not load your reports. Please retry.
        </div>
      ) : (
        <ReportHistory reports={reports} />
      )}
    </main>
  );
}
