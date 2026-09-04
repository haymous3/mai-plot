import type { Metadata } from 'next';
import Link from 'next/link';

import { InspectionsTable } from './inspections-table';
import { ArrowLeftIcon } from '../_icons';
import type { RealtorInspectionsResponse } from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { countInspections } from '@/lib/realtor-inspection';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Assigned Inspections · Maihomme Realtor' };

/** Assigned Inspections (SCRUM-140, redesigned in SCRUM-204 from Figma
 * 280:5555). Summary tiles over the realtor's whole caseload, then a searchable
 * table. Per-assignment actions — accepting inside the 2-hour window, proposing
 * an alternate time, submitting the report — live on the detail page behind
 * "View Details"; the designed table carries no inline action. */
export default async function RealtorInspectionsPage() {
  const res = await sessionBackendGet<RealtorInspectionsResponse>(
    `${realtorServiceUrl()}/inspections/mine`,
  );
  const items = res.ok ? res.data.data : [];
  const counts = countInspections(items);

  return (
    <main className="mx-auto max-w-[1088px] px-8 py-8">
      <Link
        href="/realtor"
        className="inline-flex items-center gap-2 text-sm font-medium text-ink-600 transition hover:text-ink-900"
      >
        <ArrowLeftIcon className="h-4 w-4" />
        Back to Dashboard
      </Link>
      <h1 className="mt-3 font-display text-3xl font-bold text-ink-900">Assigned Inspections</h1>
      <p className="mt-2 text-base text-ink-600">
        Manage your property inspection schedule and assignments
      </p>

      {!res.ok ? (
        <div className="mt-8 rounded-card-sm border border-status-danger/30 bg-distress-100 px-6 py-10 text-center text-sm text-distress-700">
          Could not load your inspections. Please retry.
        </div>
      ) : items.length === 0 ? (
        <div className="mt-8 rounded-card-sm border border-dashed border-line-strong bg-surface-card px-6 py-16 text-center text-sm text-ink-500">
          You have no assigned inspections yet. New assignments will appear here.
        </div>
      ) : (
        <>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Tile value={counts.total} label="Total Assignments" />
            <Tile
              value={counts.awaiting}
              label="Pending"
              tint="border-pending-200 bg-pending-50 text-pending-700"
            />
            <Tile
              value={counts.scheduled}
              label="Scheduled"
              tint="border-scheduled-200 bg-scheduled-50 text-scheduled-700"
            />
            <Tile
              value={counts.completed}
              label="Completed"
              tint="border-done-200 bg-done-50 text-done-700"
            />
          </div>

          <InspectionsTable items={items} />
        </>
      )}
    </main>
  );
}

/** Summary tile (Figma 280:5575-5594): 86px tall, 10px radius, 17px inset.
 *
 * A state tile colours BOTH its value and its label the same -700 ink, so the
 * tint carries the text colour and the children inherit it. The neutral Total
 * tile is the only one that splits ink-900 value from ink-600 label. */
function Tile({ value, label, tint }: { value: number; label: string; tint?: string }) {
  return (
    <div className={`rounded-[10px] border p-[17px] ${tint ?? 'border-line bg-surface-card'}`}>
      <p className={`text-2xl font-bold leading-8 ${tint ? '' : 'text-ink-900'}`}>{value}</p>
      <p className={`text-sm leading-5 ${tint ? '' : 'text-ink-600'}`}>{label}</p>
    </div>
  );
}
