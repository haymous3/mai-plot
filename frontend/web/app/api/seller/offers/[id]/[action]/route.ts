import { NextRequest, NextResponse } from 'next/server';

import { transactionServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Seller offer-decision proxy (SCRUM-98). Forwards accept/counter/reject to
 * transaction-service POST /transactions/{offer_id}/{action} with the session
 * bearer. Counter carries a JSON body ({counter_amount_kobo}); accept/reject do
 * not. The action segment is whitelisted so nothing else is proxied through.
 */
const ACTIONS = new Set(['accept', 'counter', 'reject']);

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string; action: string } },
): Promise<NextResponse> {
  if (!ACTIONS.has(params.action)) {
    return NextResponse.json({ error_code: 'UNKNOWN_ACTION' }, { status: 404 });
  }
  const token = sessionAccessToken();
  if (!token) return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });

  // Only the counter action forwards a body.
  let body: string | undefined;
  if (params.action === 'counter') {
    try {
      body = JSON.stringify(await request.json());
    } catch {
      return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
    }
  }

  let resp: Response;
  try {
    resp = await fetch(
      `${transactionServiceUrl()}/transactions/${encodeURIComponent(params.id)}/${params.action}`,
      {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
        body,
        cache: 'no-store',
      },
    );
  } catch {
    return NextResponse.json({ error_code: 'TRANSACTION_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const respBody = await resp.json().catch(() => ({}));
  return NextResponse.json(respBody, { status: resp.status });
}
