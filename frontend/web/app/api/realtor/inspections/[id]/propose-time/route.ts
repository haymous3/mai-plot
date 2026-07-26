import { NextRequest, NextResponse } from 'next/server';

import { realtorServiceUrl } from '@/lib/api';
import { sessionBackendSend } from '@/lib/session-api';

/**
 * Realtor propose-alternate-time proxy (SCRUM-141). Forwards {proposed_date} to
 * realtor-service POST /inspections/{id}/propose-time with the realtor's session
 * token. The backend enforces ownership + the 2-hour window (403/409/422).
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  let payload: { proposed_date?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }
  const proposed_date = typeof payload.proposed_date === 'string' ? payload.proposed_date : '';
  if (!proposed_date) {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }

  const { status, body } = await sessionBackendSend(
    'POST',
    `${realtorServiceUrl()}/inspections/${encodeURIComponent(params.id)}/propose-time`,
    { proposed_date },
  );
  return NextResponse.json(body, { status });
}
