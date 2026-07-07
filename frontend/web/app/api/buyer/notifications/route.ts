import { NextResponse } from 'next/server';

import { notificationServiceUrl } from '@/lib/api';
import { buyerBackendGet } from '@/lib/buyer-server-api';

/**
 * Buyer notifications proxy (SCRUM-95). Same-origin GET the header bell polls
 * for the in-app centre; forwards to notification-service GET /notifications
 * with the buyer token (kept server-side).
 */
export async function GET(): Promise<NextResponse> {
  const result = await buyerBackendGet<unknown>(`${notificationServiceUrl()}/notifications`);
  if (!result.ok) {
    return NextResponse.json({ error_code: result.code }, { status: result.status });
  }
  return NextResponse.json(result.data);
}
