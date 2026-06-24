import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { AdminNav } from '../../admin-nav';
import { RealtorTable } from './realtor-table';
import type { RealtorQueueResponse } from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { ADMIN_LOGIN } from '@/lib/auth';
import { backendGet } from '@/lib/server-api';

export const metadata: Metadata = {
  title: 'Realtor onboarding queue · Maiplot',
  robots: { index: false, follow: false },
};

export default async function RealtorQueuePage() {
  const result = await backendGet<RealtorQueueResponse>(
    `${realtorServiceUrl()}/admin/realtors/queue`,
  );
  if (!result.ok && result.status === 401) {
    redirect(ADMIN_LOGIN);
  }
  const forbidden = !result.ok && result.status === 403;

  return (
    <div className="min-h-screen bg-bone">
      <AdminNav active="realtors" count={result.ok ? result.data.items.length : null} />

      <main className="mx-auto max-w-6xl px-6 py-12">
        <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Onboarding</p>
        <h1 className="mt-2 font-display text-3xl text-ink-900">Realtor credential review</h1>
        <p className="mt-3 max-w-prose text-sm text-ink-500">
          Review each applicant&apos;s ESVARBON licence and uploaded ID before approving them to take
          inspections. A rejected applicant is told why and can re-apply.
        </p>

        <div className="mt-8">
          {forbidden ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-6 py-10 text-center text-sm text-amber-800">
              This queue is restricted to admin reviewers.
            </div>
          ) : !result.ok ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
              Could not load the queue ({result.code}). Please retry.
            </div>
          ) : (
            <RealtorTable items={result.data.items} />
          )}
        </div>
      </main>
    </div>
  );
}
