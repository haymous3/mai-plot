import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { NotificationInbox } from '@/app/_components/notification-inbox';
import { SESSION_LOGIN } from '@/lib/session';
import { sessionAccessToken } from '@/lib/session-server';

export const metadata: Metadata = { title: 'Notifications · Maihomme' };

/**
 * Buyer notification inbox (SCRUM-196).
 *
 * Buyers have had a header bell since SCRUM-95 with no full view behind it —
 * the dropdown shows a short unread list and nothing else. This is that view,
 * and it is the SAME component the seller route renders: the categories are
 * role-agnostic on the server, so a buyer's Documents tab is the same query as
 * a seller's. Only the subtitle and the route it links back to differ.
 *
 * Inside the (buyer) group, so it keeps the buyer header and its bell — unlike
 * /settings, which deliberately replaces the app chrome with its own bar.
 */
export default function BuyerNotificationsPage({
  searchParams,
}: {
  searchParams: { category?: string; q?: string };
}) {
  const token = sessionAccessToken();
  if (!token) redirect(SESSION_LOGIN);

  return (
    <NotificationInbox
      token={token}
      basePath="/notifications"
      subtitle="Deposits, offers and document updates on your purchases"
      category={searchParams.category}
      q={searchParams.q}
    />
  );
}
