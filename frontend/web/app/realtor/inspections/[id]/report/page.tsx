import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { ReportWizard } from './report-wizard';
import { ArrowLeftIcon } from '../../../_icons';
import type { RealtorInspectionsResponse } from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { reportSubmittable } from '@/lib/inspection-report';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Inspection Report · Maihomme Realtor' };

/** Inspection report submission (SCRUM-140, redesigned in SCRUM-204 from Figma
 * 278:3729). Resolves the inspection from the realtor's own assignments (there
 * is no single-inspection GET, which also means another realtor's inspection
 * 404s rather than leaking), then either renders the wizard or explains why the
 * report can't be submitted yet — mirroring the backend's accepted +
 * on/after-date guards so the realtor isn't surprised by a 422.
 *
 * The wizard owns the full-width two-column layout, so this page is only the
 * fetch, the gate, and the fallbacks. */
export default async function InspectionReportPage({ params }: { params: { id: string } }) {
  const res = await sessionBackendGet<RealtorInspectionsResponse>(
    `${realtorServiceUrl()}/inspections/mine`,
  );

  if (!res.ok) {
    return (
      <Shell>
        <div className="rounded-card-sm border border-status-danger/30 bg-distress-50 px-6 py-10 text-center text-sm text-distress-700">
          Could not load this inspection. Please retry.
        </div>
      </Shell>
    );
  }

  const insp = res.data.data.find((i) => i.inspection_id === params.id);
  if (!insp) notFound();

  const gate = reportSubmittable(insp);
  if (gate.ok) return <ReportWizard insp={insp} />;

  return (
    <Shell backTo={`/realtor/inspections/${insp.inspection_id}`}>
      <div className="rounded-card-sm border border-pending-200 bg-pending-50 px-6 py-10 text-center">
        {gate.reason === 'too_early' ? (
          <>
            <p className="text-sm font-semibold text-pending-700">
              Report submission isn&apos;t open yet.
            </p>
            <p className="mt-1 text-sm text-pending-700">
              You can submit your report on or after the confirmed inspection date
              {gate.opensAt ? ` (${formatDate(gate.opensAt)})` : ''}.
            </p>
          </>
        ) : (
          <>
            <p className="text-sm font-semibold text-pending-700">
              This inspection isn&apos;t ready for a report.
            </p>
            <p className="mt-1 text-sm text-pending-700">
              Accept the assignment first — a report can only be submitted once the inspection is
              scheduled, and only once.
            </p>
          </>
        )}
      </div>
    </Shell>
  );
}

function Shell({
  children,
  backTo = '/realtor/inspections',
}: {
  children: React.ReactNode;
  backTo?: string;
}) {
  return (
    <main className="mx-auto max-w-[896px] px-8 py-8">
      <Link
        href={backTo}
        className="inline-flex items-center gap-2 text-sm font-medium text-ink-600 transition hover:text-ink-900"
      >
        <ArrowLeftIcon className="h-4 w-4" />
        Back to Inspections
      </Link>
      <div className="mt-6">{children}</div>
    </main>
  );
}
