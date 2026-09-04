import { redirect } from 'next/navigation';

import { RealtorNav } from './realtor-nav';
import type { RealtorInspectionsResponse } from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { countInspections } from '@/lib/realtor-inspection';
import { SESSION_LOGIN } from '@/lib/session';
import { sessionBackendGet } from '@/lib/session-api';
import { sessionAccessToken, sessionRole } from '@/lib/session-server';

/** Realtor portal shell (SCRUM-140). Gates every /realtor page on a realtor
 * session; a signed-out visitor goes to the login, a non-realtor to their own
 * role home. Mirrors the seller shell.
 *
 * The sidebar's pending-response badge (SCRUM-204, Figma 276:4) is read here so
 * it shows on every page, not just the dashboard. On the dashboard this is the
 * same request the page itself makes, which React memoises within the render
 * pass; elsewhere it is one extra read. A failed read simply hides the badge —
 * the nav must never depend on it. */
export default async function RealtorLayout({ children }: { children: React.ReactNode }) {
  if (!sessionAccessToken()) redirect(`${SESSION_LOGIN}?role=realtor`);
  const role = sessionRole();
  if (role !== 'realtor') {
    redirect(role === 'seller' ? '/seller' : role === 'buyer' ? '/dashboard' : SESSION_LOGIN);
  }

  const res = await sessionBackendGet<RealtorInspectionsResponse>(
    `${realtorServiceUrl()}/inspections/mine`,
  );
  const pendingCount = res.ok ? countInspections(res.data.data).awaiting : 0;

  return (
    <div className="flex min-h-screen bg-surface-page">
      <RealtorNav pendingCount={pendingCount} />
      <div className="flex-1 overflow-x-hidden">{children}</div>
    </div>
  );
}
