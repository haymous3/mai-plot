import { NextRequest, NextResponse } from 'next/server';

import { listingServiceUrl } from '@/lib/api';
import { buyerBackendSend } from '@/lib/buyer-server-api';

/**
 * Express-interest proxy (SCRUM-95). Forwards the optional message to
 * listing-service POST /listings/{id}/interest with the buyer token.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  let payload: { message?: unknown };
  try {
    payload = await request.json();
  } catch {
    payload = {};
  }
  const message = typeof payload.message === 'string' && payload.message ? payload.message : null;

  const { status, body } = await buyerBackendSend(
    'POST',
    `${listingServiceUrl()}/listings/${encodeURIComponent(params.id)}/interest`,
    { message },
  );
  return NextResponse.json(body, { status });
}
