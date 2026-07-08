import { NextRequest, NextResponse } from 'next/server';

import { transactionServiceUrl } from '@/lib/api';
import { buyerBackendSend } from '@/lib/buyer-server-api';

/**
 * Buyer respond-to-counter proxy (SCRUM-134). Forwards {action: accept|reject}
 * to transaction-service POST /transactions/{offer_id}/respond with the buyer
 * token. Accepting a counter creates a transaction (returned in the body).
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  let payload: { action?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }
  const action = payload.action === 'accept' || payload.action === 'reject' ? payload.action : null;
  if (!action) return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });

  const { status, body } = await buyerBackendSend(
    'POST',
    `${transactionServiceUrl()}/transactions/${encodeURIComponent(params.id)}/respond`,
    { action },
  );
  return NextResponse.json(body, { status });
}
