import type { Metadata } from 'next';
import Link from 'next/link';

import { RealtorHeader } from '../realtor-header';
import type { RealtorProfile } from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Profile · Maihomme Realtor' };

/** Realtor Profile (SCRUM-144). A read view of the realtor's own credentials +
 * coverage from the existing GET /realtors/me — ESVARBON licence, coverage
 * area, experience, approval status, completed deals. Read-only; editing
 * coverage would need a backend PATCH (out of scope). */
export default async function RealtorProfilePage() {
  const res = await sessionBackendGet<RealtorProfile>(`${realtorServiceUrl()}/realtors/me`);

  // 404 = not onboarded yet (SCRUM-156): point them at onboarding rather than
  // showing an empty profile.
  if (!res.ok && res.status === 404) {
    return (
      <main className="mx-auto max-w-3xl px-8 py-8">
        <RealtorHeader title="Profile" subtitle="Your realtor credentials and coverage" />
        <div className="mt-8 rounded-2xl border border-amber-200 bg-amber-50 px-6 py-10 text-center text-sm text-amber-800">
          <p className="font-medium">You haven&rsquo;t submitted your credentials yet.</p>
          <Link
            href="/realtor/onboarding"
            className="mt-4 inline-flex rounded-md bg-emerald-deep px-4 py-2.5 text-sm font-medium text-bone transition hover:bg-emerald-accent"
          >
            Complete your profile
          </Link>
        </div>
      </main>
    );
  }

  if (!res.ok) {
    return (
      <main className="mx-auto max-w-3xl px-8 py-8">
        <RealtorHeader title="Profile" subtitle="Your realtor credentials and coverage" />
        <div className="mt-8 rounded-xl border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
          Could not load your profile. Please retry.
        </div>
      </main>
    );
  }

  const profile = res.data;
  const approval = APPROVAL_META[profile.approval_status] ?? {
    label: profile.approval_status,
    pill: 'bg-ink-300/20 text-ink-500',
  };

  return (
    <main className="mx-auto max-w-3xl px-8 py-8">
      <RealtorHeader title="Profile" subtitle="Your realtor credentials and coverage" />

      <div className="mt-6 space-y-6">
        <section className="rounded-card-sm border border-line bg-surface-card p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-wide text-ink-500">Account status</p>
              <span
                className={`mt-1 inline-flex rounded-full px-3 py-1 text-sm font-medium ${approval.pill}`}
              >
                {approval.label}
              </span>
            </div>
            {profile.approval_status !== 'approved' && (
              <p className="max-w-xs text-right text-xs text-ink-500">
                You&rsquo;ll start receiving inspection assignments once our team approves your
                credentials.
              </p>
            )}
          </div>

          <dl className="mt-6 grid gap-5 sm:grid-cols-2">
            <Field label="ESVARBON licence" value={profile.esvarbon_number ?? '—'} />
            <Field
              label="Years of experience"
              value={
                profile.years_of_experience === null
                  ? '—'
                  : `${profile.years_of_experience} year${profile.years_of_experience === 1 ? '' : 's'}`
              }
            />
            <Field label="Completed deals" value={String(profile.completed_deals)} />
          </dl>
        </section>

        <section className="rounded-card-sm border border-line bg-surface-card p-6">
          <h2 className="font-display text-lg text-ink-900">Coverage area</h2>
          <p className="mt-1 text-sm text-ink-500">Where you provide inspection services.</p>

          <Chips label="States" values={profile.coverage_states} />
          <Chips label="LGAs" values={profile.coverage_lgas} />
        </section>
      </div>
    </main>
  );
}

const APPROVAL_META: Record<string, { label: string; pill: string }> = {
  approved: { label: 'Approved', pill: 'bg-emerald-deep/10 text-emerald-deep' },
  pending: { label: 'Under review', pill: 'bg-amber-100 text-amber-700' },
  suspended: { label: 'Suspended', pill: 'bg-red-50 text-red-700' },
  rejected: { label: 'Not approved', pill: 'bg-red-50 text-red-700' },
};

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-ink-500">{label}</dt>
      <dd className="mt-1 text-sm font-medium text-ink-900">{value}</dd>
    </div>
  );
}

function Chips({ label, values }: { label: string; values: string[] }) {
  return (
    <div className="mt-4">
      <p className="text-xs uppercase tracking-wide text-ink-500">{label}</p>
      {values.length === 0 ? (
        <p className="mt-1.5 text-sm text-ink-300">None on file.</p>
      ) : (
        <div className="mt-2 flex flex-wrap gap-2">
          {values.map((v) => (
            <span
              key={v}
              className="rounded-full bg-bone px-3 py-1 text-xs font-medium text-ink-700"
            >
              {v}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
