import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import { RequestsTable } from './requests-table';
import { AdminNav } from '../../admin-nav';
import type { AssignableRealtorsResponse, UnassignedInspectionsResponse } from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { ADMIN_LOGIN } from '@/lib/auth';
import { backendGet } from '@/lib/server-api';

export const metadata: Metadata = {
  title: 'Inspection requests · Maihomme',
  robots: { index: false, follow: false },
};

/**
 * Inspection requests waiting for a realtor (SCRUM-208).
 *
 * Before this, a request that found nobody within 50km answered 503 and was
 * gone — the only trace was a log line, and the 503's "an admin has been
 * alerted" was not true of anything. The request is now kept as an unassigned
 * inspection, and this is where an admin places it.
 *
 * The queue and the picker are read together on the server: an admin who opens
 * this page is here to assign something, so making them wait for a second
 * client fetch before the dropdown works would be a worse first render.
 */
export default async function InspectionRequestsPage() {
  const [queue, realtors] = await Promise.all([
    backendGet<UnassignedInspectionsResponse>(`${realtorServiceUrl()}/admin/inspections/unassigned`),
    backendGet<AssignableRealtorsResponse>(
      `${realtorServiceUrl()}/admin/inspections/assignable-realtors`,
    ),
  ]);

  if (!queue.ok && queue.status === 401) redirect(ADMIN_LOGIN);
  const forbidden = !queue.ok && queue.status === 403;

  const items = queue.ok ? queue.data.items : [];
  // A failed picker read is NOT fatal: the queue is still worth showing, and the
  // table degrades to "cannot load realtors" on the row the admin tries to act
  // on rather than replacing the whole page with an error.
  const assignable = realtors.ok ? realtors.data.items : [];
  const noneLocated = assignable.length > 0 && assignable.every((r) => !r.has_base_location);

  return (
    <div className="min-h-screen bg-bone">
      <AdminNav active="requests" count={queue.ok ? items.length : null} />

      <main className="mx-auto max-w-6xl px-6 py-12">
        <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Admin</p>
        <h1 className="mt-2 font-display text-3xl text-ink-900">Inspection requests</h1>
        <p className="mt-3 max-w-prose text-sm text-ink-500">
          Buyers and sellers whose inspection request found no realtor nearby. Assigning one opens
          the usual 2-hour acceptance window and notifies the realtor, exactly as an automatic
          assignment would.
        </p>

        {noneLocated && (
          <div className="mt-6 max-w-prose rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <span className="font-medium">Every approved realtor needs assigning by hand.</span>{' '}
            None of them has a base location on file, and automatic assignment can only find
            realtors who do — onboarding does not ask for one yet. These requests will not resolve
            themselves.
          </div>
        )}

        <div className="mt-8">
          {forbidden ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-6 py-10 text-center text-sm text-amber-800">
              This queue is restricted to admin reviewers.
            </div>
          ) : !queue.ok ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
              Could not load the queue ({queue.code}). Please retry.
            </div>
          ) : items.length === 0 ? (
            <div className="rounded-lg border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center text-sm text-ink-300">
              No inspection requests are waiting for a realtor.
              <p className="mt-2 text-xs">
                Assignments made automatically appear under{' '}
                <Link href="/admin/inspections/reports" className="underline">
                  inspection reports
                </Link>{' '}
                once the realtor files one.
              </p>
            </div>
          ) : (
            <RequestsTable items={items} realtors={assignable} realtorsLoaded={realtors.ok} />
          )}
        </div>
      </main>
    </div>
  );
}
