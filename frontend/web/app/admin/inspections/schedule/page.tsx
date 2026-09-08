import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import { ScheduleTable } from './schedule-table';
import { AdminNav } from '../../admin-nav';
import type { AdminDealsResponse, AssignableRealtorsResponse } from '@/lib/api';
import { realtorServiceUrl, transactionServiceUrl } from '@/lib/api';
import { ADMIN_LOGIN } from '@/lib/auth';
import { backendGet } from '@/lib/server-api';

export const metadata: Metadata = {
  title: 'Schedule an inspection · Maihomme',
  robots: { index: false, follow: false },
};

/**
 * Schedule an inspection on any live deal (SCRUM-213).
 *
 * The sibling "Inspection requests" queue only shows deals where a buyer or
 * seller ALREADY asked for an inspection and proximity found nobody. An admin
 * who wants to send a realtor to a deal nobody has asked about had no route at
 * all — `POST /inspections` answers 403 to an admin, who is not a party to the
 * transaction. This page is that route.
 *
 * Deals and the realtor picker are read together on the server: an admin here
 * is going to assign something, and making them wait for a second client fetch
 * before the dropdown works would be a worse first render.
 */
export default async function ScheduleInspectionPage({
  searchParams,
}: {
  searchParams: { q?: string };
}) {
  const query = searchParams.q?.trim() ?? '';
  const dealsUrl = new URL(`${transactionServiceUrl()}/admin/transactions`);
  // The backend requires at least 2 characters, so a one-letter box is simply
  // an unfiltered list rather than a 422 the admin has to decode.
  if (query.length >= 2) dealsUrl.searchParams.set('search', query);

  const [deals, realtors] = await Promise.all([
    backendGet<AdminDealsResponse>(dealsUrl.toString()),
    backendGet<AssignableRealtorsResponse>(
      `${realtorServiceUrl()}/admin/inspections/assignable-realtors`,
    ),
  ]);

  if (!deals.ok && deals.status === 401) redirect(ADMIN_LOGIN);
  const forbidden = !deals.ok && deals.status === 403;

  const items = deals.ok ? deals.data.items : [];
  // A failed picker read is NOT fatal: the deal list is still worth showing, and
  // the table says so on the row the admin tries to act on rather than
  // replacing the whole page with an error.
  const assignable = realtors.ok ? realtors.data.items : [];

  return (
    <div className="min-h-screen bg-bone">
      <AdminNav active="schedule" count={null} />

      <main className="mx-auto max-w-6xl px-6 py-12">
        <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Admin</p>
        <h1 className="mt-2 font-display text-3xl text-ink-900">Schedule an inspection</h1>
        <p className="mt-3 max-w-prose text-sm text-ink-500">
          Send a realtor to any live deal, whether or not the buyer or seller asked. The realtor
          gets the usual 2-hour acceptance window and is notified in the app and by email. Deals
          that have already closed or been cancelled are not listed.
        </p>
        <p className="mt-2 max-w-prose text-sm text-ink-500">
          Requests the buyer or seller raised that found nobody nearby are handled under{' '}
          <Link href="/admin/inspections/requests" className="underline">
            inspection requests
          </Link>
          .
        </p>

        <form method="get" className="mt-8 flex max-w-md gap-2">
          <label className="sr-only" htmlFor="q">
            Search deals by property or transaction id
          </label>
          <input
            id="q"
            name="q"
            defaultValue={query}
            placeholder="Property title, or a full transaction id"
            className="flex-1 rounded-md border border-ink-300/60 bg-white px-3 py-2 text-sm text-ink-900 outline-none focus:border-emerald-accent"
          />
          <button
            type="submit"
            className="rounded-md border border-ink-300/60 px-4 py-2 text-sm font-medium text-ink-900 transition hover:bg-white"
          >
            Search
          </button>
        </form>

        <div className="mt-8">
          {forbidden ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-6 py-10 text-center text-sm text-amber-800">
              This list is restricted to admin reviewers.
            </div>
          ) : !deals.ok ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
              Could not load deals ({deals.code}). Please retry.
            </div>
          ) : items.length === 0 ? (
            <div className="rounded-lg border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center text-sm text-ink-300">
              {query ? `No live deals match “${query}”.` : 'There are no live deals right now.'}
            </div>
          ) : (
            <ScheduleTable items={items} realtors={assignable} realtorsLoaded={realtors.ok} />
          )}
        </div>
      </main>
    </div>
  );
}
