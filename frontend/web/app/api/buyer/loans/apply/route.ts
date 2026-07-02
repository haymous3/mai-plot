import { NextRequest, NextResponse } from 'next/server';

import { loanServiceUrl } from '@/lib/api';
import { buyerBackendSend } from '@/lib/buyer-server-api';

/** Same-origin proxy for the buyer's loan application (SCRUM-94). Forwards the
 * body to loan-service POST /loans/apply with the server-side buyer token and
 * mirrors the backend status/body (including the idempotency_key the client
 * generated). */
export async function POST(request: NextRequest): Promise<NextResponse> {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }

  const { status, body } = await buyerBackendSend(
    'POST',
    `${loanServiceUrl()}/loans/apply`,
    payload,
  );
  return NextResponse.json(body, { status });
}
