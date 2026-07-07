import { NextRequest, NextResponse } from 'next/server';

import { transactionServiceUrl } from '@/lib/api';
import { buyerBackendSend } from '@/lib/buyer-server-api';

/**
 * Buyer deposit proxy (SCRUM-95, §11 collection — wires the existing SCRUM-83
 * endpoint, no new disbursement logic). Forwards {idempotency_key, amount_kobo}
 * to transaction-service POST /transactions/{id}/deposit; the response's
 * authorization_url is the Paystack hosted-checkout URL.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  let payload: { idempotency_key?: unknown; amount_kobo?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }
  const idempotency_key = typeof payload.idempotency_key === 'string' ? payload.idempotency_key : '';
  const amount_kobo = typeof payload.amount_kobo === 'number' ? payload.amount_kobo : 0;

  const { status, body } = await buyerBackendSend(
    'POST',
    `${transactionServiceUrl()}/transactions/${encodeURIComponent(params.id)}/deposit`,
    { idempotency_key, amount_kobo },
  );
  return NextResponse.json(body, { status });
}
