import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import {
  ActivityRow,
  ImpactCard,
  StatCard,
  UpcomingRow,
  VerificationImpactCard,
  type ActivityItem,
} from './dashboard-parts';
import { BellIcon, CheckCircleIcon, ClipboardIcon, UploadIcon } from './_icons';
import type {
  CommissionHistoryItem,
  CommissionHistoryResponse,
  CommissionSummary,
  RealtorInspection,
  RealtorInspectionsResponse,
  RealtorProfile,
} from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { formatNaira } from '@/lib/format';
import { reportSubmittable } from '@/lib/inspection-report';
import {
  countInspections,
  isSameMonth,
  upcomingInspections,
  upcomingTodayCount,
} from '@/lib/realtor-inspection';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Dashboard · Maihomme Realtor' };

const HOW_REPORTS_HELP = [
  'Validates property for buyers',
  'Increases listing credibility',
  'Powers trust indicators',
  'Appears in deal tracker',
];

/** Realtor Dashboard Overview (SCRUM-140, redesigned in SCRUM-204 from Figma
 * 276:4). Every figure is derived from the realtor's own assignments and
 * commission summary — there is no dedicated dashboard stats endpoint. */
export default async function RealtorOverviewPage() {
  const [inspRes, commissionRes, historyRes, profileRes] = await Promise.all([
    sessionBackendGet<RealtorInspectionsResponse>(`${realtorServiceUrl()}/inspections/mine`),
    sessionBackendGet<CommissionSummary>(`${realtorServiceUrl()}/realtors/me/commission`),
    sessionBackendGet<CommissionHistoryResponse>(`${realtorServiceUrl()}/realtors/me/commissions`),
    sessionBackendGet<RealtorProfile>(`${realtorServiceUrl()}/realtors/me`),
  ]);

  // /realtors/me 404s until the realtor submits their credentials (SCRUM-156):
  // send them to onboarding. Only a definite 404 redirects — a transient 502
  // must not bounce an already-onboarded realtor into onboarding.
  if (!profileRes.ok && profileRes.status === 404) redirect('/realtor/onboarding');

  const inspections = inspRes.ok ? inspRes.data.data : [];
  const commission = commissionRes.ok ? commissionRes.data : null;
  const commissions = historyRes.ok ? historyRes.data.data : [];
  const profile = profileRes.ok ? profileRes.data : null;

  const counts = countInspections(inspections);
  const upcoming = upcomingInspections(inspections).slice(0, 3);
  const activity = buildActivity(inspections, commissions).slice(0, 5);
  const totalEarnings = commission
    ? commission.pending_kobo + commission.available_kobo + commission.withdrawn_kobo
    : 0;
  const verifiedThisMonth = inspections.filter((i) => isSameMonth(i.report_submitted_at)).length;

  // "Upload Report" goes to the assignment that is actually reportable right
  // now, rather than being a second link to the same list as View Inspections.
  const reportable = inspections.find((i) => reportSubmittable(i).ok);

  return (
    <div className="flex items-start">
      <main className="min-w-0 flex-1">
        <div className="mx-auto max-w-[896px] px-8 py-8">
          <h1 className="text-3xl font-bold leading-9 text-ink-900">Dashboard Overview</h1>
          <p className="mt-2 text-base leading-6 text-ink-600">
            Manage inspections, verify properties, and track your earnings
          </p>

          {profile && profile.approval_status !== 'approved' && (
            <div className="mt-6 rounded-card-sm border border-pending-200 bg-pending-50 px-5 py-4 text-sm text-pending-700">
              <p className="font-semibold">
                Your realtor account is {approvalLabel(profile.approval_status)}.
              </p>
              <p className="mt-1">
                You&apos;ll start receiving inspection assignments once our team approves your
                ESVARBON credentials.
              </p>
            </div>
          )}

          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard tone="pending" value={String(counts.awaiting)} label="Pending Inspections" />
            <StatCard tone="done" value={String(counts.completed)} label="Completed Inspections" />
            <StatCard
              tone="scheduled"
              value={String(upcomingTodayCount(inspections))}
              label="Upcoming Today"
            />
            <StatCard tone="neutral" value={formatNaira(totalEarnings)} label="Total Earnings" />
          </div>

          <section className="mt-6 rounded-card-sm border border-line bg-surface-card p-6">
            <div className="flex items-center justify-between gap-4">
              <h2 className="text-lg font-bold text-ink-900">Upcoming Inspections</h2>
              <Link
                href="/realtor/inspections"
                className="text-sm font-medium text-ink-600 transition hover:text-ink-900"
              >
                View All →
              </Link>
            </div>
            <div className="mt-4 space-y-3">
              {upcoming.length === 0 ? (
                <p className="py-10 text-center text-sm text-ink-500">
                  No inspections assigned to you yet.
                </p>
              ) : (
                upcoming.map((i) => <UpcomingRow key={i.inspection_id} insp={i} />)
              )}
            </div>
          </section>

          <section className="mt-6 rounded-card-sm border border-line bg-surface-card p-6">
            <h2 className="text-lg font-bold text-ink-900">Recent Activity</h2>
            <ul className="mt-2">
              {activity.length === 0 ? (
                <li className="py-10 text-center text-sm text-ink-500">No recent activity yet.</li>
              ) : (
                activity.map((a, i) => <ActivityRow key={`${a.kind}-${a.ts}-${i}`} item={a} />)
              )}
            </ul>
          </section>
        </div>
      </main>

      <aside className="hidden w-80 flex-none self-stretch space-y-6 border-l border-line bg-surface-card p-6 xl:block">
        <div className="space-y-4">
          <h2 className="text-lg font-bold text-ink-900">Your Impact</h2>
          <ImpactCard value={String(verifiedThisMonth)} label="Properties Verified" />
          <VerificationImpactCard body="Your inspection reports directly contribute to buyer trust and help validate property authenticity across the platform." />
        </div>

        <div className="space-y-4">
          <h2 className="text-lg font-bold text-ink-900">Quick Actions</h2>
          <div className="space-y-2">
            <Link
              href="/realtor/inspections"
              className="flex h-11 items-center gap-3 rounded-[10px] bg-emerald-deep px-4 text-sm font-medium text-white transition hover:bg-emerald-accent"
            >
              <ClipboardIcon className="h-5 w-5 flex-none" />
              View Inspections
            </Link>
            <Link
              href={
                reportable
                  ? `/realtor/inspections/${reportable.inspection_id}/report`
                  : '/realtor/inspections'
              }
              className="flex h-11 items-center gap-3 rounded-[10px] border border-line px-4 text-sm font-medium text-ink-700 transition hover:border-ink-500"
            >
              <UploadIcon className="h-5 w-5 flex-none" />
              Upload Report
            </Link>
            <a
              href="mailto:hello@maihomme.com"
              className="flex h-11 items-center gap-3 rounded-[10px] border border-line px-4 text-sm font-medium text-ink-700 transition hover:border-ink-500"
            >
              <BellIcon className="h-5 w-5 flex-none" />
              Contact Support
            </a>
          </div>
        </div>

        <div className="rounded-card-sm border border-pending-200 bg-pending-50 p-[17px]">
          <p className="text-sm font-semibold text-pending-900">How Reports Help</p>
          <ul className="mt-2 space-y-2">
            {HOW_REPORTS_HELP.map((item) => (
              <li key={item} className="flex items-center gap-2 text-xs text-pending-800">
                <CheckCircleIcon className="h-3 w-3 flex-none" strokeWidth={2.4} />
                {item}
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}

function approvalLabel(status: string): string {
  switch (status) {
    case 'pending':
      return 'under review';
    case 'suspended':
      return 'suspended';
    case 'rejected':
      return 'not approved';
    default:
      return status.replace('_', ' ');
  }
}

/** Recent activity derived from the realtor's inspections and commissions,
 * newest first. There is no activity feed endpoint.
 *
 * The design's "Inspection report approved" row is live as of SCRUM-205.
 * Rejections are surfaced too, carrying the admin's note, because a realtor
 * needs to know a report came back at least as much as that one passed. */
function buildActivity(
  inspections: RealtorInspection[],
  commissions: CommissionHistoryItem[],
): ActivityItem[] {
  const events: ActivityItem[] = [];

  for (const i of inspections) {
    const property = i.property_title ?? 'a property';
    events.push({
      kind: 'assigned',
      title: 'New inspection assigned',
      detail: property,
      ts: i.created_at,
    });
    if (i.report_submitted_at) {
      events.push({
        kind: 'submitted',
        title: 'Report submitted successfully',
        detail: property,
        ts: i.report_submitted_at,
      });
    }
    // The admin's decision (SCRUM-205). Timestamped by when it was reviewed, so
    // it sorts after the submission it decided rather than alongside it.
    if (i.report_reviewed_at && i.report_review_status === 'approved') {
      events.push({
        kind: 'approved',
        title: 'Inspection report approved',
        detail: property,
        ts: i.report_reviewed_at,
      });
    }
    if (i.report_reviewed_at && i.report_review_status === 'rejected') {
      events.push({
        kind: 'rejected',
        title: 'Report needs changes',
        detail: i.report_review_note ?? property,
        ts: i.report_reviewed_at,
      });
    }
  }

  for (const c of commissions) {
    if (c.disbursed_at) {
      events.push({
        kind: 'payment',
        title: `Payment received: ${formatNaira(c.amount_kobo)}`,
        detail: c.property_title ?? 'Commission payout',
        ts: c.disbursed_at,
      });
    }
  }

  return events.sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts));
}
