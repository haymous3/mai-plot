import type { Metadata } from 'next';

import { InspectionCard } from './inspection-card';
import { RealtorHeader } from '../realtor-header';
import type { RealtorInspection, RealtorInspectionsResponse } from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { inspectionStatusMeta } from '@/lib/realtor-inspection';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Assigned Inspections · Maiplot Realtor' };

/** Assigned Inspections list (SCRUM-140, PR2). Groups the realtor's assignments
 * into Needs Response / Scheduled / Completed. Pending cards carry a live 2-hour
 * acceptance countdown + Accept; the backend enforces the window + ownership. */
export default async function RealtorInspectionsPage() {
  const res = await sessionBackendGet<RealtorInspectionsResponse>(
    `${realtorServiceUrl()}/inspections/mine`,
  );
  const items = res.ok ? res.data.data : [];

  const pending = items
    .filter((i) => i.status === 'pending')
    .sort((a, b) => Date.parse(a.assignment_expires_at) - Date.parse(b.assignment_expires_at));
  const scheduled = items
    .filter((i) => inspectionStatusMeta(i.status).bucket === 'scheduled')
    .sort((a, b) => Date.parse(a.proposed_date) - Date.parse(b.proposed_date));
  const completed = items
    .filter((i) => inspectionStatusMeta(i.status).bucket === 'completed')
    .sort((a, b) => Date.parse(b.report_submitted_at ?? '') - Date.parse(a.report_submitted_at ?? ''));

  return (
    <main className="mx-auto max-w-4xl px-8 py-8">
      <RealtorHeader
        title="Assigned Inspections"
        subtitle="Accept assignments within the 2-hour window, then submit your report"
      />

      {!res.ok ? (
        <div className="mt-8 rounded-xl border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
          Could not load your inspections. Please retry.
        </div>
      ) : items.length === 0 ? (
        <div className="mt-8 rounded-2xl border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center text-sm text-ink-500">
          You have no assigned inspections yet. New assignments will appear here.
        </div>
      ) : (
        <div className="mt-6 space-y-8">
          <Section title="Needs Your Response" count={pending.length} items={pending} accent />
          <Section title="Scheduled" count={scheduled.length} items={scheduled} />
          <Section title="Completed" count={completed.length} items={completed} />
        </div>
      )}
    </main>
  );
}

function Section({
  title,
  count,
  items,
  accent = false,
}: {
  title: string;
  count: number;
  items: RealtorInspection[];
  accent?: boolean;
}) {
  if (items.length === 0) return null;
  return (
    <section>
      <h2 className="flex items-center gap-2 font-display text-lg text-ink-900">
        {title}
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            accent ? 'bg-amber-100 text-amber-700' : 'bg-ink-300/20 text-ink-500'
          }`}
        >
          {count}
        </span>
      </h2>
      <div className="mt-3 space-y-3">
        {items.map((insp) => (
          <InspectionCard key={insp.inspection_id} insp={insp} />
        ))}
      </div>
    </section>
  );
}
