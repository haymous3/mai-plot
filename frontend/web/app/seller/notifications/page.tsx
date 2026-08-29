import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { NotificationInbox } from '@/app/_components/notification-inbox';
import { SESSION_LOGIN } from '@/lib/session';
import { sessionAccessToken } from '@/lib/session-server';

export const metadata: Metadata = { title: 'Notifications · Maihomme' };

/** Seller notification inbox (SCRUM-194). The screen itself is shared with the
 * buyer route — see app/_components/notification-inbox. */
export default function SellerNotificationsPage({
  searchParams,
}: {
  searchParams: { category?: string; q?: string };
}) {
  const token = sessionAccessToken();
  if (!token) redirect(`${SESSION_LOGIN}?role=seller`);

  return (
    <NotificationInbox
      token={token}
      basePath="/seller/notifications"
      subtitle="Stay updated with your listing activities"
      category={searchParams.category}
      q={searchParams.q}
    />
  );
}
