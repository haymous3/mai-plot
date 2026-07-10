import { NextRequest, NextResponse } from 'next/server';

import { realtorServiceUrl } from '@/lib/api';
import { sessionBackendSend } from '@/lib/session-api';

/**
 * Realtor accept-assignment proxy (SCRUM-140). Forwards to realtor-service
 * POST /inspections/{id}/accept with the realtor's session token. No body — the
 * assigned realtor accepts within the 2-hour window; the backend enforces the
 * window + ownership (422 if elapsed, 403 if not theirs, 409 if not pending).
 */
export async function POST(
  _request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const { status, body } = await sessionBackendSend(
    'POST',
    `${realtorServiceUrl()}/inspections/${encodeURIComponent(params.id)}/accept`,
  );
  return NextResponse.json(body, { status });
}
