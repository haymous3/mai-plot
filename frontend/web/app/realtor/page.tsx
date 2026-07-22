import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import { RealtorHeader } from './realtor-header';
import type {
  CommissionSummary,
  RealtorInspection,
  RealtorInspectionsResponse,
  RealtorProfile,
} from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { formatDate, formatDateTime, formatNaira } from '@/lib/format';
import {
  countInspections,
  inspectionLocation,
  inspectionStatusMeta,
  isAwaitingAcceptance,
  upcomingInspections,
} from '@/lib/realtor-inspection';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Dashboard · Maiplot Realtor' };

/** Realtor Dashboard Overview (SCRUM-140). Stats + upcoming inspections + recent
 * activity are all derived from the realtor's assigned inspections + commission
 * summary — there is no dedicated dashboard stats source. */
export default async function RealtorOverviewPage() {
  const [inspRes, commissionRes, profileRes] = await Promise.all([
    sessionBackendGet<RealtorInspectionsResponse>(`${realtorServiceUrl()}/inspections/mine`),
    sessionBackendGet<CommissionSummary>(`${realtorServiceUrl()}/realtors/me/commission`),
    sessionBackendGet<RealtorProfile>(`${realtorServiceUrl()}/realtors/me`),
  ]);

  // /realtors/me 404s until the realtor submits their credentials (SCRUM-156):
  // send them to onboarding. Only a definite 404 redirects — a transient 502
  // must not bounce an already-onboarded realtor into onboarding.
  if (!profileRes.ok && profileRes.status === 404) redirect('/realtor/onboarding');

  const inspections = inspRes.ok ? inspRes.data.data : [];
  const commission = commissionRes.ok ? commissionRes.data : null;
  const profile = profileRes.ok ? profileRes.data : null;

  const counts = countInspections(inspections);
  const upcoming = upcomingInspections(inspections).slice(0, 5);
  const activity = buildActivity(inspections).slice(0, 6);
  const availableKobo = commission?.available_kobo ?? 0;
  const pendingKobo = commission?.pending_kobo ?? 0;
  const completedDeals = profile?.completed_deals ?? counts.completed;

  return (
    <main className="mx-auto max-w-6xl px-8 py-8">
      <RealtorHeader title="Dashboard Overview" subtitle="Welcome back" />

      {profile && profile.approval_status !== 'approved' && (
        <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800">
          <p className="font-medium">
            Your realtor account is {approvalLabel(profile.approval_status)}.
          </p>
          <p className="mt-1 text-amber-700">
            You&apos;ll start receiving inspection assignments once our team approves your ESVARBON
            credentials.
          </p>
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_300px]">
        <div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Stat
              icon="📥"
              value={String(counts.awaiting)}
              label="Awaiting Acceptance"
              hint={counts.awaiting > 0 ? 'Needs your response' : undefined}
            />
            <Stat icon="📅" value={String(counts.scheduled)} label="Scheduled" />
            <Stat icon="✓" value={String(counts.completed)} label="Reports Submitted" />
            <Stat
              icon="💰"
              value={formatNaira(availableKobo)}
              label="Available Earnings"
              hint={pendingKobo > 0 ? `${formatNaira(pendingKobo)} pending` : undefined}
            />
          </div>

          <section className="mt-6 rounded-2xl border border-ink-300/25 bg-white p-6">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-lg text-ink-900">Upcoming Inspections</h2>
              <Link
                href="/realtor/inspections"
                className="text-sm text-emerald-deep hover:underline"
              >
                View all →
              </Link>
            </div>
            <div className="mt-4 space-y-3">
              {upcoming.length === 0 ? (
                <p className="py-8 text-center text-sm text-ink-500">
                  No inspections assigned to you yet.
                </p>
              ) : (
                upcoming.map((insp) => <UpcomingRow key={insp.inspection_id} insp={insp} />)
              )}
            </div>
          </section>

          <section className="mt-6 rounded-2xl border border-ink-300/25 bg-white p-6">
            <h2 className="font-display text-lg text-ink-900">Recent Activity</h2>
            <ul className="mt-3 divide-y divide-ink-300/15">
              {activity.length === 0 ? (
                <li className="py-8 text-center text-sm text-ink-500">No recent activity yet.</li>
              ) : (
                activity.map((a, i) => (
                  <li key={i} className="flex items-start gap-3 py-3">
                    <span className="mt-0.5 flex h-8 w-8 flex-none items-center justify-center rounded-lg bg-bone text-sm">
                      {a.icon}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-ink-900">{a.title}</p>
                      <p className="truncate text-sm text-ink-500">{a.detail}</p>
                      <p className="text-xs text-ink-300">{formatDate(a.ts)}</p>
                    </div>
                  </li>
                ))
              )}
            </ul>
          </section>
        </div>

        <aside className="space-y-4">
          <div className="space-y-2">
            <Link
              href="/realtor/inspections"
              className="block rounded-xl bg-emerald-deep px-4 py-3 text-center text-sm font-semibold text-bone transition hover:bg-emerald-accent"
            >
              View Assigned Inspections ({counts.awaiting})
            </Link>
            <Link
              href="/realtor/earnings"
              className="block rounded-xl border border-emerald-deep/40 px-4 py-3 text-center text-sm font-semibold text-emerald-deep transition hover:bg-emerald-deep/5"
            >
              View Earnings
            </Link>
          </div>

          <div className="rounded-2xl bg-bone/70 p-5">
            <p className="text-sm font-medium text-ink-800">Your Impact</p>
            <Insight label="Completed Deals" value={String(completedDeals)} />
            <Insight label="Total Assigned" value={String(counts.total)} />
            <Insight label="Pending Payout" value={formatNaira(pendingKobo)} />
          </div>

          <div className="rounded-2xl border border-emerald-deep/15 bg-emerald-deep/5 p-5">
            <p className="text-sm font-medium text-emerald-deep">Tip</p>
            <p className="mt-1 text-xs text-ink-700">
              Accept assignments within the 2-hour window — a lapsed window is reassigned to another
              realtor in range.
            </p>
          </div>
        </aside>
      </div>
    </main>
  );
}

function UpcomingRow({ insp }: { insp: RealtorInspection }) {
  const meta = inspectionStatusMeta(insp.status);
  return (
    <Link
      href="/realtor/inspections"
      className="flex items-start justify-between gap-3 rounded-xl border border-ink-300/25 p-3 transition hover:border-ink-500/40"
    >
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-ink-900">
          {insp.property_title ?? 'Property inspection'}
        </p>
        <p className="truncate text-xs text-ink-500">📍 {inspectionLocation(insp)}</p>
        <p className="mt-1 text-xs text-ink-600">🗓 {formatDate(insp.proposed_date)}</p>
        {isAwaitingAcceptance(insp) && (
          <p className="mt-0.5 text-xs font-medium text-amber-700">
            Respond by {formatDateTime(insp.assignment_expires_at)}
          </p>
        )}
      </div>
      <span className={`flex-none rounded-full px-2.5 py-1 text-xs font-medium ${meta.pill}`}>
        {meta.label}
      </span>
    </Link>
  );
}

function Stat({
  icon,
  value,
  label,
  hint,
}: {
  icon: string;
  value: string;
  label: string;
  hint?: string;
}) {
  return (
    <div className="rounded-2xl border border-ink-300/25 bg-white p-5">
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-bone text-lg">
        {icon}
      </span>
      <p className="mt-3 font-display text-3xl text-ink-900">{value}</p>
      <p className="text-sm text-ink-600">{label}</p>
      {hint && <p className="mt-0.5 text-xs text-emerald-accent">↗ {hint}</p>}
    </div>
  );
}

function Insight({ label, value }: { label: string; value: string }) {
  return (
    <div className="mt-3 flex items-center justify-between border-t border-ink-300/15 pt-2 first:border-0 first:pt-0">
      <span className="text-xs text-ink-600">{label}</span>
      <span className="text-sm font-semibold text-ink-900">{value}</span>
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

interface Activity {
  icon: string;
  title: string;
  detail: string;
  ts: string;
}

/** Recent activity derived from the realtor's inspections — an "assigned" event
 * per inspection, plus a "report submitted" event where one exists — newest
 * first. There is no dedicated activity feed. */
function buildActivity(items: RealtorInspection[]): Activity[] {
  const events: Activity[] = [];
  for (const i of items) {
    const property = i.property_title ?? 'a property';
    events.push({ icon: '📋', title: 'Inspection assigned', detail: property, ts: i.created_at });
    if (i.report_submitted_at) {
      events.push({
        icon: '✓',
        title: 'Report submitted',
        detail: property,
        ts: i.report_submitted_at,
      });
    }
  }
  return events.sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts));
}
