import { NextResponse } from 'next/server';

import { notificationServiceUrl } from '@/lib/api';
import { buyerBackendSend } from '@/lib/buyer-server-api';

/**
 * Buyer "mark all read" proxy (SCRUM-95). Forwards to notification-service
 * PATCH /notifications/read-all with the buyer token.
 */
export async function PATCH(): Promise<NextResponse> {
  const { status, body } = await buyerBackendSend(
    'PATCH',
    `${notificationServiceUrl()}/notifications/read-all`,
    {},
  );
  return NextResponse.json(body, { status });
}
